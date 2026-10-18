"""Read all 107 channels / 121 raw candidates; never reconstruct prices or fit."""
from collections import Counter
from datetime import datetime
import gzip,hashlib,json,math
from pathlib import Path
import re,sys
from urllib.parse import parse_qs,urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_simple_split_quote_guard_v2_research as guard
from backtest import ndx_specific_split_registry_v2_research as registry
nominal=guard.nominal
INDEX=ROOT/'data/cache/research/provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json'
INDEX_SHA='5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117'
COVERAGE=INDEX.parent/'coverage_addendum.json'
COVERAGE_SHA='6fc0d5ee29cecb12ae70433fece84cd43e64ae90030aa92fe00f95880a3b1b22'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(guard.__file__).resolve(),Path(registry.__file__).resolve())}

def valid(value):return type(value) in (int,float) and math.isfinite(value) and value>0

def request_status(request,received,ticker):
    errors=[]
    if received is None:return ['EXACT_RECEIPT_MISSING'],None
    instant=datetime.fromisoformat(received)
    if instant.tzinfo is None or instant.utcoffset().total_seconds()!=0:return ['EXACT_UTC_RECEIPT_MISSING'],None
    received_date=instant.astimezone(nominal.NEW_YORK).date().isoformat()
    if not isinstance(request,dict) or not request.get('url'):return ['EXACT_REQUEST_MISSING'],received_date
    url=urlparse(request['url']);query=parse_qs(url.query,keep_blank_values=True)
    if (request.get('method')!='GET' or request.get('credentials_sent') is not False or url.scheme!='https' or url.netloc!='query1.finance.yahoo.com'
      or url.path!='/v8/finance/chart/'+ticker or url.fragment or set(query)!={'period1','period2','interval','events'}
      or query.get('interval')!=['1d'] or query.get('events')!=['div,splits'] or any(len(query.get(k,[]))!=1 or re.fullmatch('[0-9]+',query[k][0]) is None for k in ('period1','period2'))):
        return ['EXACT_DAILY_EVENT_REQUEST_REQUIRED'],received_date
    start,end=[nominal._timestamp(int(query[k][0])) for k in ('period1','period2')]
    if start>=end or end>instant or end.astimezone(nominal.NEW_YORK).date().isoformat()!=received_date:errors.append('EVENT_HORIZON_NOT_RECEIPT_MARKET_DATE')
    return errors,received_date

def analyze_raw(*,raw,ticker,variant,original_capture,requirements,events):
    """Pure analysis; original_capture provenance must be bound by build before calling."""
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    if 'decoded_sha256' in original_capture and hashlib.sha256(decoded).hexdigest()!=original_capture['decoded_sha256']:raise ValueError('Decoded capture SHA differs')
    document=json.loads(decoded,object_pairs_hook=nominal._unique_pairs);chart=document['chart']
    if chart.get('error') is not None or len(chart['result'])!=1:raise ValueError('Successful unique raw channel required')
    data=chart['result'][0]
    if data['meta']!=variant['provider_meta'] or data['meta']['symbol']!=ticker:raise ValueError('Raw metadata differs from hard index')
    times=data['timestamp'];quotes=data['indicators']['quote']
    if len(quotes)!=1 or any(len(quotes[0][k])!=len(times) for k in ('open','close')):raise ValueError('Quote denominator differs')
    dates=[nominal._timestamp(t).astimezone(nominal.NEW_YORK).date().isoformat() for t in times]
    if dates!=sorted(set(dates)):raise ValueError('Unique ordered raw sessions required')
    received=original_capture.get('received_at_utc');request=original_capture.get('request')
    if request is None:request=dict(method=original_capture.get('request_method'),url=original_capture.get('request_url'),credentials_sent=original_capture.get('credentials_sent'))
    blockers,received_date=request_status(request,received,ticker)
    if any(data['meta'].get(key)!=value for key,value in {'currency':'USD','exchangeTimezoneName':'America/New_York','instrumentType':'EQUITY','dataGranularity':'1d'}.items()):blockers.append('UNSUPPORTED_PROVIDER_PRICE_COORDINATES')
    if any(not valid(value) for key in ('open','close') for value in quotes[0][key]):blockers.append('NONFINITE_OR_NONPOSITIVE_RAW_QUOTE_CELLS')
    query=parse_qs(urlparse(request.get('url') or '').query,keep_blank_values=True)
    if all(len(query.get(k,[]))==1 and query[k][0].isdigit() for k in ('period1','period2')):
        start,end=[int(query[k][0]) for k in ('period1','period2')]
        if times!=sorted(set(times)) or any(not start<=t<end for t in times):blockers.append('QUOTE_TIMESTAMPS_OUTSIDE_ORIGINAL_REQUEST')
        if any(not start<=e['date']<end for e in data.get('events',{}).get('splits',{}).values()):blockers.append('SPLIT_TIMESTAMPS_OUTSIDE_ORIGINAL_REQUEST')
    completed={k:{day for i,day in enumerate(dates) if valid(quotes[0][k][i]) and (received_date is None or day<received_date)} for k in ('open','close')}
    # Missing receipt still permits describing finite raw coverage, never completed-bar certification.
    period_checks=[]
    for selection,required in requirements.items():
        period_checks.append(dict(selection_date=selection,required_count=len(required),missing_open_dates=sorted(required-completed['open']),missing_close_dates=sorted(required-completed['close'])))
    missing=sum(len(x['missing_open_dates'])+len(x['missing_close_dates']) for x in period_checks)
    if missing:blockers.append('APPLICABLE_TRAINING_AND_PREVIOUS_CLOSE_GAPS')
    observed={}
    for kind in ('splits','dividends'):
        observed[kind]=[dict(provider_event_key=str(key),provider_fields=value,session=nominal._timestamp(value['date']).astimezone(nominal.NEW_YORK).date().isoformat()) for key,value in data.get('events',{}).get(kind,{}).items()]
        observed[kind].sort(key=lambda x:x['session'])
    if observed!=variant['returned_events']:raise ValueError('Raw event facts differ from hard index')
    event_errors=[];matches=[]
    if ticker in registry.BLOCKED:event_errors.append('COMPLEX_ACTION_OUTSIDE_SIMPLE_SPLIT')
    elif ticker in registry.TRANSITIONS:event_errors.append('CUSIP_IDENTITY_TRANSITION_REQUIRED')
    else:
        try:
            matches=guard.first_guard.match_returned_events(decoded=decoded,ticker=ticker,specific_events=events,blocked_tickers=registry.BLOCKED|registry.TRANSITIONS)
            if not blockers or not any(x in blockers for x in ('EXACT_RECEIPT_MISSING','EXACT_REQUEST_MISSING','EXACT_DAILY_EVENT_REQUEST_REQUIRED')):
                guard.validate_known_event_denominator(ticker=ticker,matches=matches,events=events,request=request)
        except (ValueError,KeyError,TypeError) as error:event_errors.append('KNOWN_EVENT_DENOMINATOR_OR_FACT_MISMATCH: '+str(error))
    blockers.extend(event_errors)
    interface_named=type(original_capture.get('name')) is str
    return dict(ticker=ticker,raw_path=variant['path'],raw_sha256=variant['sha256'],decoded_sha256=hashlib.sha256(decoded).hexdigest(),
      observed_slot_count=len(dates),valid_raw_open_count=sum(valid(x) for x in quotes[0]['open']),valid_raw_close_count=sum(valid(x) for x in quotes[0]['close']),
      observed_first=dates[0],observed_last=dates[-1],same_receipt_date_sessions=[x for x in dates if x==received_date],
      exact_receipt_present=received_date is not None,received_at_utc=received,completed_date_filter_applied=received_date is not None,
      request=request,period_checks=period_checks,missing_open_close_occurrences=missing,full_applicable_history_present=not missing,
      returned_split_count=len(observed['splits']),returned_dividend_count=len(observed['dividends']),matched_specific_events=matches,
      technical_blockers=blockers,technical_simple_split_preflight_passed=not blockers,
      guard_v2_capture_name_addressable=interface_named,guard_v2_capture_name=original_capture.get('name'),
      guard_interface_gap=None if interface_named else 'ORIGINAL_ROW_HAS_TICKER_BUT_NO_NAME_REQUIRES_RAW_PATH_SHA_ADDRESSING_ADAPTER',
      quote_field_basis_required=nominal.BASIS,explicit_basis_independently_authenticated=False,
      provider_historical_security_identity_verified=False,price_reconstruction_admitted=False,
      completed_dates_note='RECEIPT_MISSING_FINITE_RAW_COVERAGE_ONLY' if received_date is None else 'STRICTLY_BEFORE_RECEIPT_NEW_YORK_DATE')

def choose_candidate(rows):
    eligible=[x for x in rows if x['exact_receipt_present']]
    if not eligible:return None
    return min(eligible,key=lambda x:(not x['technical_simple_split_preflight_passed'],x['missing_open_close_occurrences'],x['observed_first'],x['raw_path']))['raw_path']

def build():
    evidence=registry.load_registry();sources=dict(evidence['source_hashes'])
    for p,h in LOADED.items():registry.merge_source(sources,p,h)
    def load(path,digest):
        registry.merge_source(sources,path,digest);nominal.verify({str(Path(path).resolve()):digest})
        data=json.loads(Path(path).read_bytes(),object_pairs_hook=nominal._unique_pairs)
        for p,h in data.get('source_hashes',{}).items():registry.merge_source(sources,p,h)
        return data
    index=load(INDEX,INDEX_SHA);coverage=load(COVERAGE,COVERAGE_SHA);nominal.verify(sources)
    channels=index['provider_channels']
    if len(channels)!=107 or sum(map(len,channels.values()))!=121 or coverage['union_security_count']!=112:raise ValueError('Hard original denominators differ')
    by_ticker={x['ticker']:x for x in coverage['candidate_rows']}
    manifests={};results=[];summaries=[]
    eligible_events=[x for x in evidence['events'] if x['simple_split_guard_eligible']]
    for ticker,variants in sorted(channels.items()):
        requirements={}
        for p in by_ticker[ticker]['periods']:
            date=p['selection_date'];c=coverage['calendar_requirements'][date]
            requirements[date]=set(c['return_dates'])|set(c['previous_close_by_return_date'].values())
        rows=[]
        for variant in variants:
            path=Path(variant['path']);digest=variant['sha256'];registry.merge_source(sources,path,digest)
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Raw index source drift')
            refs=[]
            for ref in variant['references']:
                manifest_path=ref['manifest_path'];expected=sources.get(manifest_path)
                if expected is None or ('manifest_sha256' in ref and ref['manifest_sha256']!=expected):raise ValueError('Manifest absent from original closure')
                if manifest_path not in manifests:manifests[manifest_path]=load(manifest_path,expected)
                m=manifests[manifest_path];candidates=m.get('captures',m.get('probes',[]))
                found=[c for c in candidates if c.get('raw_path',c.get('response_path'))==str(path) and c.get('raw_sha256',c.get('response_sha256'))==digest]
                if len(found)!=1:raise ValueError('Unique same-file original capture required')
                c=found[0]
                if c.get('http_status')!=200 or c.get('raw_bytes',c.get('response_bytes'))!=len(raw):raise ValueError('Original capture response differs')
                if c.get('received_at_utc')!=ref.get('received_at_utc'):raise ValueError('Indexed receipt differs')
                refs.append((ref,c))
            refs.sort(key=lambda pair:(pair[1].get('received_at_utc') is None,pair[0]['manifest_path']))
            ref,capture=refs[0]
            row=analyze_raw(raw=raw,ticker=ticker,variant=variant,original_capture=capture,requirements=requirements,events=eligible_events)
            row['capture_references']=[dict(manifest_path=x['manifest_path'],manifest_sha256=sources[x['manifest_path']],capture_name=c.get('name'),received_at_utc=c.get('received_at_utc')) for x,c in refs]
            rows.append(row);results.append(row)
        choice=choose_candidate(rows)
        full=any(x['full_applicable_history_present'] for x in rows)
        if full!=by_ticker[ticker]['updated_all_applicable_training_complete']:raise ValueError('Independent history coverage disagrees with sealed matrix')
        summaries.append(dict(ticker=ticker,capture_candidate_count=len(rows),preferred_research_capture_path=choice,
          any_technical_preflight_pass=any(x['technical_simple_split_preflight_passed'] for x in rows),any_complete_training_history=full,
          no_exact_receipt_candidate=choice is None,identity_note=index['identity_risks'].get(ticker.lower(),'PROVIDER_CHANNEL_NOT_HISTORICAL_SECURITY_IDENTITY'),
          price_reconstruction_admitted=False))
    nominal.verify(sources)
    return dict(schema='107_CHANNEL_121_RAW_STANDARD_SPLIT_PRECHECK_NOT_PRICE_RECONSTRUCTION',source_hashes=sources,
      proxy_security_denominator=112,channel_count=107,raw_candidate_count=121,registry_event_count=25,registry_guard_eligible_events=23,
      capture_candidates=results,by_ticker=summaries,technical_blocker_capture_counts=dict(Counter(reason for x in results for reason in x['technical_blockers'])),
      technical_pass_capture_count=sum(x['technical_simple_split_preflight_passed'] for x in results),
      technical_pass_channel_count=sum(x['any_technical_preflight_pass'] for x in summaries),
      full_history_channel_count=sum(x['any_complete_training_history'] for x in summaries),
      capture_addressing_interface_gap_count=sum(not x['guard_v2_capture_name_addressable'] for x in results),
      failed_channels_preserved=index['identity_risks']['failed_requests'],original_identity_risks=index['identity_risks'],
      selection_rule='EXACT_RECEIPT_THEN_TECHNICAL_PASS_THEN_FEWEST_MISSING_REQUIRED_CELLS_THEN_EARLIEST_START_THEN_PATH_NO_RETURN_RANKING',
      explicit_quote_basis_still_requires_separate_adjudication=True,provider_historical_identity_verified=False,
      full_historical_ndx_baseline_verified=False,price_reconstruction_performed=False,training_or_fit_performed=False,new_requests=False,
      point_in_time_verified=False,promotion_allowed=False)

if __name__=='__main__':
    # Preview only. Parent must review before a separate create-only artifact command.
    r=build();print(json.dumps({k:r[k] for k in ('channel_count','raw_candidate_count','technical_pass_capture_count','technical_pass_channel_count','full_history_channel_count','capture_addressing_interface_gap_count','technical_blocker_capture_counts')},sort_keys=True))
