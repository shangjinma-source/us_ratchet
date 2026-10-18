"""Independent saved-price/raw Decimal audit; never imports a reconstruction guard."""
import argparse,gzip,hashlib,json,math,re,sys
from collections import Counter
from datetime import datetime,timezone,timedelta
from decimal import Decimal,localcontext
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_exact_price_cache_drift_research as drift
FOLDER=ROOT/'data/cache/research/current101_conditional_prices_20260919_v1'
PLAN=FOLDER/'plan.json';PLAN_SHA='5e3fc9d87dd180d458265bf256e55c04b51da3b9c74be2a58a187beb6e99daf0'
INDEX=FOLDER/'index_101.json';INDEX_SHA='0e48880f524f61c069efa9027f9dff64af7f39625b928bc07695402e7966d3ff'
SOURCE=Path(__file__).resolve();LOADED={str(p):drift.file_sha(p) for p in (SOURCE,drift.SOURCE)}
NY=ZoneInfo('America/New_York');BASIS='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS'
BLOCKED={'CMCSA','LRCX','HON','EXC','TRI','WDC'}
FLOORS={'HONA':'2026-06-29','SNDK':'2025-02-24','FER':'2024-05-09'}
MODES={'NEW_CONDITIONAL_RECONSTRUCTION':92,'REFERENCE_EXISTING_REGULAR':3,'BLOCKED_COMPLEX_OR_IDENTITY':6}
FALSE_FIELDS=('price_identity_verified','provider_dates_are_exchange_calendar','historical_alias_join_performed','point_in_time_verified','promotion_allowed','returns_generated','training_performed')
def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result
def loads(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def number(v):
    if type(v) not in (int,float) or not math.isfinite(v) or v<=0:raise ValueError('Finite positive nonboolean number required')
    return Decimal(str(v))
def day(t):
    if type(t) is not int or t<=0:raise ValueError('Integer timestamp required')
    return datetime.fromtimestamp(t,timezone.utc).astimezone(NY).date().isoformat()
def inspect_raw(raw,ticker):
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;body=loads(decoded)
    if body['chart'].get('error') is not None or len(body['chart']['result'])!=1:raise ValueError('One successful chart required')
    data=body['chart']['result'][0];meta=data['meta']
    for k,v in dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d').items():
        if meta.get(k)!=v:raise ValueError('Provider coordinates differ')
    times=data['timestamp'];quotes=data['indicators']['quote']
    if type(times) is not list or not times or len(quotes)!=1:raise ValueError('Nonempty unique quote channel required')
    days=[day(t) for t in times];q=quotes[0]
    if days!=sorted(set(days)) or any(len(q[k])!=len(days) for k in ('open','close')):raise ValueError('Full raw date/value dimensions differ')
    events=[];seen=set()
    for key,e in data.get('events',{}).get('splits',{}).items():
        d=day(e['date']);number(e['numerator']);number(e['denominator']);ratio=Fraction(str(e['numerator']))/Fraction(str(e['denominator']))
        if str(e['date'])!=key or d in seen or Fraction(e['splitRatio'].replace(':','/'))!=ratio:raise ValueError('Duplicate/inconsistent split event')
        seen.add(d);events.append(dict(session=d,timestamp=e['date'],numerator=ratio.numerator,denominator=ratio.denominator))
    return dict(data=data,days=days,quotes=q,times=times,events=sorted(events,key=lambda e:e['session']),decoded_sha256=digest(decoded))
def verify_request(task,receipt,started,rawinfo):
    if any(receipt.get(k)!=v for k,v in started.items()):raise ValueError('Request start/receipt differs')
    url=urlparse(started['request_url']);query=parse_qs(url.query,keep_blank_values=True)
    if (started['request_method']!='GET' or started['ticker']!=task['ticker'] or started['credentials_sent'] is not False
        or type(started['attempt_count']) is not int or started['attempt_count']!=1 or receipt['http_status']!=200
        or url.scheme!='https' or url.netloc!='query1.finance.yahoo.com' or url.path!='/v8/finance/chart/'+task['ticker']
        or set(query)!={'period1','period2','interval','events'} or query['interval']!=['1d'] or query['events']!=['div,splits']
        or any(len(query[k])!=1 or not query[k][0].isdigit() for k in ('period1','period2'))):raise ValueError('Original explicit daily quote request differs')
    start=datetime.fromisoformat(started['started_at_utc']);received=datetime.fromisoformat(receipt['received_at_utc']);end=int(query['period2'][0]);begin=int(query['period1'][0])
    if (any(t.tzinfo is None or t.utcoffset()!=timedelta(0) for t in (start,received)) or received<start or end!=int(start.timestamp()) or begin!=1640995200
        or end>received.timestamp() or day(end)!=received.astimezone(NY).date().isoformat()
        or task['received_at_utc']!=receipt['received_at_utc'] or task['exclude_on_or_after']!=day(end)
        or receipt['completed_training_excludes_dates_on_or_after']!=day(end)
        or any(t<begin or t>end for t in rawinfo['times']) or any(e['timestamp']<begin or e['timestamp']>end for e in rawinfo['events'])):raise ValueError('Request/receipt/event horizon differs')
def audit_rows(*,rawinfo,task,rows):
    floor=FLOORS.get(task['ticker']) if task['mode']=='REFERENCE_EXISTING_REGULAR' else None
    expected=[d for d in rawinfo['days'] if d<task['exclude_on_or_after'] and (floor is None or d>=floor)]
    if not expected or [r['session'] for r in rows]!=expected:raise ValueError('Entire completed provider/regular calendar required')
    positions={d:i for i,d in enumerate(rawinfo['days'])};maximum=Decimal(0)
    with localcontext() as context:
        context.prec=50
        for row in rows:
            i=positions[row['session']]
            if row['ticker']!=task['ticker'] or row['currency']!='USD' or row['provider_timestamp']!=rawinfo['times'][i]:raise ValueError('Output daily coordinate differs')
            factor=Fraction(1)
            for event in rawinfo['events']:
                if event['session']>row['session']:factor*=Fraction(event['numerator'],event['denominator'])
            for field in ('open','close'):
                quote=number(rawinfo['quotes'][field][i]);actual=number(row['nominal_'+field])
                expected_price=quote*Decimal(factor.numerator)/Decimal(factor.denominator)
                if number(row['quote_'+field])!=quote:raise ValueError('Stored source quote differs')
                error=abs(actual-expected_price);maximum=max(maximum,error)
                if error>max(Decimal('1e-10'),abs(expected_price)*Decimal('1e-12')):raise ValueError('Independent Decimal Open/Close disagreement')
            if (row['split_factor_numerator']!=str(factor.numerator) or row['split_factor_denominator']!=str(factor.denominator)
                or type(row['split_factor']) not in (int,float) or not math.isfinite(row['split_factor']) or row['split_factor']!=float(factor)):raise ValueError('Declared factor disagrees with raw event ratio')
    return dict(first_session=expected[0],last_session=expected[-1],row_count=len(expected),maximum_absolute_decimal_error=str(maximum),calendar=expected,regular_floor=floor,raw_event_factor_independently_recomputed=True)
def validate_index(index,plan):
    if (index.get('schema')!='CURRENT101_CONDITIONAL_PRICE_INDEX_V1' or index.get('plan_sha256')!=PLAN_SHA or type(index.get('completed')) is not int
        or index['completed']!=101 or type(index.get('planned')) is not int or index['planned']!=101 or index.get('status')!='COMPLETE'
        or index.get('point_in_time_verified') is not False or index.get('promotion_allowed') is not False):raise ValueError('External complete final 101 index required')
    tasks=plan['tasks'];entries=index['entries']
    if len(tasks)!=101 or len(entries)!=101 or len({t['ticker'] for t in tasks})!=101 or Counter(t['mode'] for t in tasks)!=MODES:raise ValueError('Exact 101/92/3/6 denominator required')
    if {t['ticker'] for t in tasks if t['mode']=='BLOCKED_COMPLEX_OR_IDENTITY'}!=BLOCKED or {t['ticker'] for t in tasks if t['mode']=='REFERENCE_EXISTING_REGULAR'}!=set(FLOORS):raise ValueError('Exact block/regular partition required')
    for entry,task in zip(entries,tasks):
        if entry['ticker']!=task['ticker'] or entry['mode']!=task['mode'] or Path(entry['path'])!=FOLDER/(task['ticker']+'.json'):raise ValueError('Unique original task mode/address order required')
def build(*,index_path,index_sha256):
    if Path(index_path).resolve()!=INDEX or index_sha256!=INDEX_SHA:raise ValueError('Hard final execution index required')
    sources=dict(LOADED)
    def include(mapping):
        for p,h in mapping.items():
            if p in sources and sources[p]!=h:raise ValueError('Source collision')
            sources[p]=h
    def read(path,h):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        if digest(raw)!=h:raise ValueError('External bound bytes differ')
        include({path:h});return loads(raw)
    plan=read(PLAN,PLAN_SHA);index=read(index_path,index_sha256);validate_index(index,plan)
    include(plan['historical_expected_source_hashes']);contract=drift.load_contract();partition=drift.verify_expected_sources(sources,contract)
    if partition['historical_gap_observations']!=plan['historical_price_cache_gap_observations']:raise ValueError('Plan exact historical gap partition differs')
    reports=[];common=None;all_raw_common=None;maximum=Decimal(0)
    for task,entry in zip(plan['tasks'],index['entries']):
        doc=read(entry['path'],entry['sha256'])
        if any(canonical(doc.get(k))!=canonical(v) for k,v in task.items()) or doc['plan_sha256']!=PLAN_SHA or any(doc.get(k) is not False for k in FALSE_FIELDS):raise ValueError('Task identity/disclosure differs')
        path=Path(task['raw_path']);raw=path.read_bytes()
        if digest(raw)!=task['raw_sha256'] or sources.get(str(path))!=task['raw_sha256']:raise ValueError('Hard planned raw differs')
        receipt_path=path.parent/(task['ticker']+'.receipt.json');receipt=read(receipt_path,sources[str(receipt_path)])
        started_path=path.parent/(task['ticker']+'.started.json');started=read(started_path,receipt['started_sha256'])
        info=inspect_raw(raw,task['ticker']);verify_request(task,receipt,started,info)
        parsed_path=path.parent/(task['ticker']+'.decoded.json');parsed=read(parsed_path,sources[str(parsed_path)])
        if (receipt['raw_sha256']!=task['raw_sha256'] or receipt['raw_bytes']!=len(raw) or parsed['decoded_sha256']!=info['decoded_sha256']
            or parsed['ticker']!=task['ticker'] or parsed['receipt_sha256']!=sources[str(receipt_path)]):raise ValueError('Original body/decode receipt differs')
        completed=[d for i,d in enumerate(info['days']) if d<task['exclude_on_or_after'] and all(type(info['quotes'][k][i]) in (int,float) and math.isfinite(info['quotes'][k][i]) and info['quotes'][k][i]>0 for k in ('open','close'))]
        all_raw_common=set(completed) if all_raw_common is None else all_raw_common&set(completed)
        item=dict(ticker=task['ticker'],mode=task['mode'],raw_slot_count=len(info['days']),valid_completed_raw_count=len(completed),valid_completed_raw_first=completed[0] if completed else None,valid_completed_raw_last=completed[-1] if completed else None,
            receipt_day_excluded=task['exclude_on_or_after'],unfinalized_raw_dates=[d for d in info['days'] if d>=task['exclude_on_or_after']],returned_split_events=info['events'],returned_dividend_count=len(info['data'].get('events',{}).get('dividends',{})),provider_history_starts_after_20220103=info['days'][0]>'2022-01-03')
        if task['mode']=='BLOCKED_COMPLEX_OR_IDENTITY':
            if doc['status']!='BLOCKED' or doc.get('reconstruction','MISSING') is not None or 'result' in doc:raise ValueError('Blocked must have no price output')
            item.update(status='EXPLICITLY_BLOCKED_NOT_MISSING_PRICE',output_row_count=0)
        else:
            if doc['status']!='CONDITIONAL_PRICE_NOT_IDENTITY':raise ValueError('Conditional output status required')
            result=doc['result'];reconstruction=result['reconstruction']
            if any(result.get(k) is not False for k in ('price_identity_verified','point_in_time_verified','promotion_allowed','returns_generated','training_performed','historical_full_source_closure_verified')):raise ValueError('Nested false scope upgraded')
            if task['mode']=='REFERENCE_EXISTING_REGULAR':
                reference=read(task['reference']['path'],task['reference']['sha256'])
                if canonical(reference)!=canonical(result) or result['regular_way_floor']!=FLOORS[task['ticker']]:raise ValueError('Existing regular reference differs')
            elif result['schema']!='CURRENT_RECEIPT_28_SPECIFIC_EVENT_QUOTE_GUARD_V1':raise ValueError('Exact conditional guard scope required')
            if reconstruction['ticker']!=task['ticker'] or reconstruction['row_count']!=len(reconstruction['rows']) or reconstruction['quote_field_basis']!=BASIS or reconstruction['adjclose_used'] is not False or reconstruction['dividends_applied_to_quote'] is not False:raise ValueError('Nominal quote basis/denominator differs')
            audited=audit_rows(rawinfo=info,task=task,rows=reconstruction['rows']);maximum=max(maximum,Decimal(audited['maximum_absolute_decimal_error']))
            common=set(audited['calendar']) if common is None else common&set(audited['calendar'])
            item.update(status='CONDITIONAL_PRICE_ARITHMETIC_VERIFIED_NOT_IDENTITY',**audited)
        reports.append(item)
    checked=drift.verify_expected_sources(sources,contract)
    result=dict(schema='CURRENT101_FINAL_PRICE_INDEPENDENT_DECIMAL_COVERAGE_AUDIT_V1',index=dict(path=str(Path(index_path).resolve()),sha256=index_sha256),plan=dict(path=str(PLAN),sha256=PLAN_SHA),rows=reports,
        completed_task_count=101,conditional_price_channel_count=95,blocked_channel_count=6,mode_counts=MODES,maximum_absolute_decimal_error=str(maximum),
        common_95_conditional_provider_calendar=sorted(common),common_101_valid_raw_provider_calendar=sorted(all_raw_common),
        short_provider_history_tickers=[r['ticker'] for r in reports if r['provider_history_starts_after_20220103']],regular_partition_tickers=sorted(FLOORS),
        historical_expected_source_hashes=sources,verified_source_hashes=checked['verified_source_hashes'],historical_price_cache_gap_observations=checked['historical_gap_observations'],
        reconstruction_guard_called=False,reported_factor_used_for_decimal_recalculation=False,provider_calendar_is_exchange_calendar=False,provider_start_date_is_verified_ipo_date=False,
        complete_corporate_action_history_verified=False,price_identity_verified=False,historical_full_source_closure_verified=False,returns_generated=False,training_performed=False,point_in_time_verified=False,promotion_allowed=False)
    verify(result);return result
def verify(report):
    if any(report['historical_expected_source_hashes'].get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded auditor source omitted')
    checked=drift.verify_expected_sources(report['historical_expected_source_hashes'],drift.load_contract())
    if checked['verified_source_hashes']!=report['verified_source_hashes'] or checked['historical_gap_observations']!=report['historical_price_cache_gap_observations']:raise ValueError('Independent source partition differs')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('index-path','index-sha256','output'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();report=build(index_path=args.index_path,index_sha256=args.index_sha256)
    with Path(args.output).open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    verify(report);print(json.dumps(dict(path=str(Path(args.output).resolve()),sha256=drift.file_sha(args.output))))
