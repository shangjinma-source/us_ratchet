"""Independent raw/Decimal historical-input readback. No producer or price kernel."""
import argparse,bisect,csv,gzip,hashlib,io,json,math,sys
from datetime import datetime,timezone,date
from decimal import Decimal,localcontext
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
BASE=ROOT/'data/cache/research'
ARTIFACT=BASE/'latest_twenty_historical_inputs_20260919_v1/inputs.json'
ARTIFACT_SHA='49551a1f9cc0069935646d696b27621b748681b5769bfecbe1c8e8fa87d80939'
PRODUCER=ROOT/'scripts/ndx_latest_twenty_historical_inputs_20260919.py'
PRODUCER_SHA='e61d5ab39b881068daf19d14cbc4b209805be8fd401a64663648654ab61c5aa9'
FALSE=('fit_performed','execution_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','latest_weights_backfilled','historical_liquidity_admission_verified','historical_risk_labels_verified','nav_publication_time_verified','currency_and_fx_alignment_verified','complete_corporate_actions_verified')
PRICE_FALSE=('source_bytes_authenticated','security_identity_verified','historical_identity_interval_verified','complete_corporate_actions_verified','exchange_calendar_completeness_verified','cash_dividends_included','point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed','oos_evaluation_performed','promotion_allowed')
TOP_KEYS=set(FALSE)|{'schema','input_references','prices','channel_evidence','candidate_coordinate_and_risk_rows','candidate_full_original_provenance','candidate_supplemental_dated_provenance','coordinate_interval_role','latest_liquidity_role','risk_label_role','incumbent_original_securities','incumbent_weights_reoptimized','target_012922','target_nav_observed_fetch_time','nominal_open_and_close_retained','formal_next_open_execution_performed','old_close_only_whole_lot_model_called','historical_expected_source_hashes','archive_resolution'}
PRICE_KEYS=set(PRICE_FALSE)|{'schema','nominal_open','nominal_close','returns','effective_day_share_ratios','submitted_full_split_events','applied_fit_split_events','roles','price_basis','return_basis','calendar','exclude_on_or_after','fit_return_dates','evaluation_return_dates','price_row_count','return_row_count','fit_days','evaluation_days','rolling_step_days','available_original_rolling_windows','known_evaluation_split_events','submitted_event_denominator_preserved','historical_risk_labels_are_separate_research_assumptions'}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(exclusive_publish.__code__.co_filename).resolve())}


def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b):return digest(a)==digest(b)
def number(value):
    if type(value) not in (str,int,float):raise ValueError('Nonboolean original numeric value required')
    v=Decimal(str(value))
    if not v.is_finite():raise ValueError('Finite value required')
    return v
def session(timestamp):
    if type(timestamp) is not int:raise ValueError('Integer timestamp required')
    return datetime.fromtimestamp(timestamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
def read_bytes(ref,sources):
    p=Path(ref['path']).resolve();raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Bound bytes differ')
    archive.merge(sources,{str(p):ref['sha256']});return raw
def read(ref,sources):return json.loads(read_bytes(ref,sources))


def evidence_metadata(evidence,session_count):
    keys={'quote_reference','raw_reference','received_at_utc','receipt_day_excluded','sealed_specific_event_witnesses','decoded_sha256','all_original_returned_events','raw_provider_session_count','fixed_selected_price_count','decimal_open_close_cells','maximum_absolute_decimal_error','provider_identity_authenticated','quote_basis_independently_authenticated','complete_actions_verified'}
    if set(evidence)!=keys or any(evidence[k] is not False for k in ('provider_identity_authenticated','quote_basis_independently_authenticated','complete_actions_verified')):raise ValueError('Exact conditional channel evidence required')
    for key,count in (('raw_provider_session_count',session_count),('fixed_selected_price_count',253),('decimal_open_close_cells',506)):
        if type(evidence[key]) is not int or evidence[key]!=count:raise ValueError('Independent channel evidence denominator differs')
    if type(evidence['maximum_absolute_decimal_error']) is not str or number(evidence['maximum_absolute_decimal_error'])<0:raise ValueError('Exact nonnegative decimal error required')


def matrix(frame,calendar,tickers):
    if set(frame)!={'type','index_kind','index','columns','dtypes','data'} or frame['type']!='dataframe' or frame['index_kind']!='DatetimeIndex' or frame['columns']!=tickers or frame['dtypes']!=['float64']*len(tickers) or frame['index']!=[d+'T00:00:00' for d in calendar] or len(frame['data'])!=len(calendar) or any(len(r)!=len(tickers) for r in frame['data']):raise ValueError('Complete float64 dated matrix required')
    if any(type(v) is not float or not math.isfinite(v) for row in frame['data'] for v in row):raise ValueError('Finite float64 matrix values required')
    return frame['data']


def audit_channel(ticker,prices,raw,nominal_rows,evidence):
    calendar=prices['calendar'];tickers=prices['returns']['columns'];column=tickers.index(ticker)
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    if hashlib.sha256(decoded).hexdigest()!=evidence['decoded_sha256']:raise ValueError('Decoded raw SHA differs')
    result,=json.loads(decoded)['chart']['result']
    if result['meta']['symbol']!=ticker or result['meta']['currency']!='USD':raise ValueError('Observed channel differs')
    dates=[session(v) for v in result['timestamp']];quote,=result['indicators']['quote']
    evidence_metadata(evidence,len(dates))
    if dates!=sorted(set(dates)) or [d for d in dates if calendar[0]<=d<=calendar[-1]]!=calendar:raise ValueError('Uncompressed full raw calendar required')
    events=result.get('events',{})
    if set(events)-{'splits','dividends'} or not exact(events,evidence['all_original_returned_events']):raise ValueError('Full original event denominator differs')
    submitted=[];ratios={}
    with localcontext() as ctx:
        ctx.prec=50
        for key,event in events.get('splits',{}).items():
            d=session(event['date']);n=number(event['numerator']);o=number(event['denominator'])
            parts=event['splitRatio'].split(':')
            if key!=str(event['date']) or n<=0 or o<=0 or len(parts)!=2 or number(parts[0])<=0 or number(parts[1])<=0 or number(parts[0])/number(parts[1])!=n/o or d in ratios:raise ValueError('Original positive split ratio/date differs')
            ratios[d]=n/o
            submitted.append(dict(session=d,new_shares=str(n),old_shares=str(o),event_kind='IDENTITY_TRANSITION_SHARE_SPLIT' if ticker=='LRCX' else 'ORDINARY_SHARE_SPLIT',provider_event_key=key,original_provider_fields=event))
        submitted.sort(key=lambda e:e['session'])
        if not exact(submitted,prices['submitted_full_split_events'][ticker]) or any(d in ratios for d in calendar[127:]):raise ValueError('Full split/evaluation-action boundary differs')
        if ticker=='LRCX' and (calendar[0]<'2024-10-03' or len(submitted)!=1 or submitted[0]['session']!='2024-10-03' or ratios['2024-10-03']!=10):raise ValueError('LRCX post-transition-only coordinate required')
        by_date={r['session']:r for r in nominal_rows}
        if len(by_date)!=len(nominal_rows):raise ValueError('Duplicate nominal session')
        pos={d:i for i,d in enumerate(dates)};nominal=[];raw_closes=[];max_price=Decimal(0);max_return=Decimal(0);applied=[];daily_ratio=[]
        for i,d in enumerate(calendar):
            row=by_date[d];j=pos[d];factor=Decimal(1)
            for event_day,ratio in ratios.items():
                if event_day>d:factor*=ratio
            for field,frame in (('open','nominal_open'),('close','nominal_close')):
                original=number(quote[field][j]);saved=number(row['nominal_'+field]);observed=number(prices[frame]['data'][i][column]);expected=original*factor
                error=abs(saved-expected);max_price=max(max_price,error)
                if original<=0 or saved<=0 or observed!=saved or error>max(Decimal('1e-10'),abs(expected)*Decimal('1e-12')):raise ValueError('Independent raw/nominal matrix differs')
            nominal.append(number(row['nominal_close']));raw_closes.append(number(quote['close'][j]))
        for i,d in enumerate(calendar[1:],1):
            ratio=ratios.get(d,Decimal(1));expected=nominal[i]*ratio/nominal[i-1]-1;raw_return=raw_closes[i]/raw_closes[i-1]-1
            observed=number(prices['returns']['data'][i-1][column]);error=max(abs(observed-expected),abs(observed-raw_return));max_return=max(max_return,error)
            if error>Decimal('1e-11'):raise ValueError('Split-neutral nominal/raw return mismatch')
            daily_ratio.append(str(ratio))
            if d in ratios:applied.append(dict(previous_session=calendar[i-1],session=d,share_ratio=str(ratio),split_neutral_price_return=str(expected)))
        if not exact(daily_ratio,prices['effective_day_share_ratios'][ticker]) or not exact(applied,prices['applied_fit_split_events'][ticker]):raise ValueError('Applied ratio/previous-session accounting differs')
        if number(evidence['maximum_absolute_decimal_error'])!=max_price:raise ValueError('Reported raw nominal audit error differs')
    return dict(ticker=ticker,price_rows=253,return_rows=252,open_close_cells=506,returned_split_count=len(submitted),maximum_nominal_decimal_error=str(max_price),maximum_return_decimal_error=str(max_return))


def audit_nav(value,raw,calendar):
    source=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))));dates=[r['Date'] for r in source]
    if dates!=sorted(set(dates)) or any(date.fromisoformat(d).isoformat()!=d for d in dates):raise ValueError('Canonical unique NAV dates required')
    mapped=[]
    for d in calendar:
        i=bisect.bisect_right(dates,d)-1
        if i<0 or number(source[i]['Close'])<=0:raise ValueError('Positive prior NAV observation required')
        mapped.append(dict(session=d,nav_source_date=dates[i],nav=str(number(source[i]['Close'])),same_date=dates[i]==d,known_published_by_us_session_cutoff=False))
    with localcontext() as ctx:
        ctx.prec=50
        returns=[dict(session=b['session'],previous_session=a['session'],conditional_original_currency_return=str(number(b['nav'])/number(a['nav'])-1)) for a,b in zip(mapped,mapped[1:])]
    expected=dict(rows=mapped,returns=returns,same_date_missing_count=sum(not r['same_date'] for r in mapped),alignment='BACKWARD_OBSERVATION_DATE_ONLY_NOT_PUBLICATION_TIME',future_nav_observation_used=False,original_currency_only=True,fx_applied=False,publication_time_verified=False,legal_comparison_ready=False)
    if not exact(value,expected):raise ValueError('Independent backward-only NAV mapping differs')
    return dict(mapped_rows=253,returns=252,missing_same_date=expected['same_date_missing_count'],publication_time_verified=False,fx_alignment_verified=False)


def build(path,sha256):
    if ARTIFACT_SHA is None or PRODUCER_SHA is None or Path(path).resolve()!=ARTIFACT or sha256!=ARTIFACT_SHA:raise ValueError('Externally sealed historical artifact and producer required')
    sources=dict(LOADED);archive.merge(sources,{str(PRODUCER):PRODUCER_SHA})
    reference=dict(path=str(ARTIFACT),sha256=ARTIFACT_SHA);value=read(reference,sources)
    if set(value)!=TOP_KEYS or value['schema']!='SOURCE_BOUND_TWENTY_CONDITIONAL_HISTORICAL_INPUTS_V1' or any(value[k] is not False for k in FALSE):raise ValueError('Historical source scope upgraded')
    archive.merge(sources,value['historical_expected_source_hashes'])
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Artifact archive partition differs')
    docs={k:read(ref,sources) for k,ref in value['input_references'].items()}
    panel=docs['panel']['panel'];universe=panel['universe'];candidate=[dict(zip(universe['columns'],row)) for row in universe['data']]
    for field,expected in (('candidate_coordinate_and_risk_rows',candidate),('candidate_full_original_provenance',panel['observed_provenance_and_missing']),('candidate_supplemental_dated_provenance',docs['panel']['supplemental_dated_and_risk_provenance']),('incumbent_original_securities',docs['control']['definition']['securities'])):
        if not exact(value[field],expected):raise ValueError('Original identity/risk/control provenance changed')
    for field,expected in (('coordinate_interval_role','EXPLICIT_RETROSPECTIVE_ASSUMPTION_NOT_HISTORICAL_IDENTITY_CERTIFICATION'),('latest_liquidity_role','STATIC_LATEST_63_REFERENCE_NOT_KNOWN_AT_2026_03_18'),('risk_label_role','STATIC_CONDITIONAL_LABEL_NOT_HISTORICAL_QUALIFICATION')):
        if value[field]!=expected:raise ValueError('Historical role upgraded')
    if any(value[k] is not False for k in ('incumbent_weights_reoptimized','formal_next_open_execution_performed','old_close_only_whole_lot_model_called')) or value['nominal_open_and_close_retained'] is not True:raise ValueError('Execution/nominal scope differs')
    prices=value['prices'];calendar=docs['readiness']['observed_reference_calendar'][-253:]
    if set(prices)!=PRICE_KEYS or prices['schema']!='CONDITIONAL_HISTORICAL_253_PRICE_252_RETURN_PANEL_V1':raise ValueError('Exact original historical price schema required')
    if calendar[0]!='2025-09-16' or calendar[-1]!='2026-09-17' or not exact(prices['calendar'],calendar) or len(set(calendar))!=253:raise ValueError('Explicit hard 253 reference dates required')
    candidates={r['ticker'] for r in candidate};control={r['ticker'] for r in value['incumbent_original_securities']};tickers=sorted(candidates|control)
    if len(candidates)!=14 or len(control)!=8 or len(tickers)!=20 or set(value['channel_evidence'])!=set(tickers):raise ValueError('14/8/20 channel roles differ')
    if any(prices[k] is not False for k in PRICE_FALSE) or prices['return_basis']!='SPLIT_ONLY_PRICE_RETURN_EXCLUDES_CASH_DIVIDENDS' or prices['price_basis']!='CONDITIONAL_NOMINAL_OPEN_CLOSE':raise ValueError('Price/return disclosure differs')
    for key,count in (('price_row_count',253),('return_row_count',252),('fit_days',126),('evaluation_days',126),('rolling_step_days',21),('available_original_rolling_windows',1)):
        if type(prices[key]) is not int or prices[key]!=count:raise ValueError('Exact original window denominator required')
    if prices['fit_return_dates']!=calendar[1:127] or prices['evaluation_return_dates']!=calendar[127:] or prices['known_evaluation_split_events']!=[] or prices['exclude_on_or_after']!='2026-09-18':raise ValueError('Fit/evaluation/exclusion boundary differs')
    expected_roles=[dict(ticker=t,candidate=t in candidates,original_incumbent=t in control,minimum_identity_date='2024-10-03' if t=='LRCX' else None,role_is_not_security_identity_authentication=True,security_id=None) for t in tickers]
    if not exact(prices['roles'],expected_roles) or prices['submitted_event_denominator_preserved'] is not True or prices['historical_risk_labels_are_separate_research_assumptions'] is not True:raise ValueError('Conditional coordinate/role declarations differ')
    for name,days in (('nominal_open',calendar),('nominal_close',calendar),('returns',calendar[1:])):matrix(prices[name],days,tickers)
    details=[]
    for ticker in tickers:
        evidence=value['channel_evidence'][ticker];quote=read(evidence['quote_reference'],sources);raw=read_bytes(evidence['raw_reference'],sources)
        if ticker=='TSM':
            rows=quote['reconstruction']['rows'];received=quote['received_at_utc'];record=read(quote['raw_readback'],sources);witness=[]
            rawref=dict(path=record['raw_path'],sha256=record['raw_sha256'])
        elif 'reconstruction' in quote.get('result',{}):
            rows=quote['result']['reconstruction']['rows'];received=quote['received_at_utc'];rawref=dict(path=quote['raw_path'],sha256=quote['raw_sha256']);witness=quote['result']['matched_specific_events']
        else:
            rows=quote['result']['rows'];received=quote['result']['received_at_utc'];record=quote['raw_decoding_evidence'];rawref=dict(path=record['raw_path'],sha256=record['raw_sha256']);witness=[]
        if not exact(rawref,evidence['raw_reference']) or not exact(witness,evidence['sealed_specific_event_witnesses']):raise ValueError('Original quote/raw/event-witness lineage differs')
        receipt=datetime.fromisoformat(received.replace('Z','+00:00'))
        if receipt.tzinfo is None or receipt.utcoffset().total_seconds()!=0:raise ValueError('Explicit UTC receipt required')
        receipt_day=receipt.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if evidence['received_at_utc']!=received or evidence['receipt_day_excluded']!=receipt_day or calendar[-1]>=receipt_day:raise ValueError('Receipt-day exclusion not proven from original metadata')
        details.append(audit_channel(ticker,prices,raw,rows,evidence))
    nav_entry=docs['snapshot']['files']['nav'];nav_raw=read_bytes(dict(path=nav_entry['snapshot_path'],sha256=nav_entry['sha256']),sources)
    meta_entry=docs['snapshot']['files']['nav_manifest'];meta=read(dict(path=meta_entry['snapshot_path'],sha256=meta_entry['sha256']),sources)
    if meta['content_sha256']!=nav_entry['sha256'] or meta['dataset_key']!='012922' or meta['dataset_type']!='fund_nav' or not exact(value['target_nav_observed_fetch_time'],meta.get('fetched_at')):raise ValueError('Original NAV bytes/type/fetch-time metadata differs')
    nav=audit_nav(value['target_012922'],nav_raw,calendar)
    return dict(schema='TWENTY_HISTORICAL_INPUTS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1',artifact_reference=reference,details=details,nav=nav,
        securities=20,price_rows_per_security=253,return_rows_per_security=252,open_close_cells=10120,return_cells=5040,
        source_roles_and_identity_assumptions_exact=True,producer_build_called=False,pure_assemble_called=False,fit_performed=False,point_in_time_verified=False,promotion_allowed=False,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()))


def verify(value):
    if value.get('schema')!='TWENTY_HISTORICAL_INPUTS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1':raise ValueError('Exact independent audit schema required')
    if not exact(value,build(str(ARTIFACT),ARTIFACT_SHA)):raise ValueError('Entire independent audit does not reproduce')


def publish_verified(path,value):
    verify(value);saved=exclusive_publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Post-publication source drift')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--artifact',required=True);parser.add_argument('--artifact-sha',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build(args.artifact,args.artifact_sha))))
