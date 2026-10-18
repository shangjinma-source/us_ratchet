"""Independent raw arithmetic oracle; never imports a producer, kernel, or old auditor."""
from datetime import datetime
from decimal import Decimal, Context, localcontext
from fractions import Fraction
import gzip
import hashlib
from importlib.resources import files
from io import BytesIO
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
SOURCE=Path(__file__).resolve()
NY_SOURCE=Path(str(files('tzdata.zoneinfo.America').joinpath('New_York'))).resolve()
NY_BYTES=NY_SOURCE.read_bytes();NY=ZoneInfo.from_file(BytesIO(NY_BYTES),key='America/New_York')
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),str(NY_SOURCE):hashlib.sha256(NY_BYTES).hexdigest()}
OUTPUT=BASE/'new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json'
BOUND={
 'bridge':('new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd'),
 'completeness':('new_cutoff_completeness_20260923_v1/manifest.json','d4b16c34ea81e6925dc8cb1d0f56cfdb80731aa7078c64bfd734b4fb375cfbd1'),
 'candidate':('new_cutoff_conditional_channels_20260923_v1/channels.json','3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
}
PRODUCER=ROOT/'scripts/ndx_new_cutoff_conditional_channels_20260923.py'
PRODUCER_SHA='3733003516f798129bb65f4c05e8383bf8e09de008c6fc191da85904b05b3265'
FALSE=('producer_called','old_raw_audit_called','fit_performed','http_performed','complete_actions_verified',
 'legal_training_input_admitted','security_identity_verified','volume_unit_verified','point_in_time_verified',
 'promotion_allowed','dividend_cash_flows_included')

def require(ok,message):
    if not ok:raise ValueError(message)

def unique(pairs):
    out={}
    for key,value in pairs:
        require(key not in out,'Duplicate JSON key');out[key]=value
    return out

def loads(raw,decimal=False):
    def invalid(value):raise ValueError('Nonfinite JSON token')
    return json.loads(raw,parse_float=Decimal if decimal else float,object_pairs_hook=unique,parse_constant=invalid)

def encoded(value):return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))

def positive(value):
    require(type(value) in (int,Decimal),'Raw numeric type differs')
    result=Decimal(value);require(result.is_finite() and result>0,'Positive finite numeric required');return result

def day(stamp):
    require(type(stamp) is int and stamp>0,'Positive integer timestamp required')
    return datetime.fromtimestamp(stamp,NY).date().isoformat()

def decimal_fraction(value,precision=80):
    with localcontext(Context(prec=precision)):
        return Decimal(value.numerator)/Decimal(value.denominator)

def derive(raw,ticker,calendar,policies,floor=None):
    require(len(calendar)==127 and calendar==sorted(set(calendar)),'Exactly 127 distinct ordered observed dates required')
    if floor is not None:require(floor<=calendar[0],'Partition insufficient for full window')
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    chart=loads(decoded,True)['chart'];require(chart['error'] is None and len(chart['result'])==1,'One successful raw result required')
    result=chart['result'][0]
    for key,value in dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d').items():
        require(result['meta'].get(key)==value,'Raw metadata differs')
    stamps=result['timestamp'];dates=[day(t) for t in stamps]
    require(dates==sorted(set(dates)),'Duplicate or unordered raw day')
    require([d for d in dates if d<=calendar[-1]][-127:]==calendar,'Raw calendar compressed or mismatched')
    quote=result['indicators']['quote'];require(len(quote)==1,'One quote channel required');quote=quote[0]
    require(all(len(quote[f])==len(dates) for f in ('open','high','low','close','volume')),'Raw quote dimensions differ')
    event_container=result.get('events',{});require(type(event_container) is dict and set(event_container)<={'splits','dividends'},'Unknown event family')
    split=event_container.get('splits',{});require(type(split) is dict and type(event_container.get('dividends',{})) is dict,'Event object required')
    parsed={}
    for key,event in split.items():
        d=day(event['date']);require(key==str(event['date']) and d not in parsed,'Split key/date duplicate')
        ratio=Fraction(positive(event['numerator']))/Fraction(positive(event['denominator']))
        text=event['splitRatio'];require(type(text) is str and len(text.split(':'))==2,'Ratio text required')
        left,right=text.split(':');require(Fraction(positive(Decimal(left)))/Fraction(positive(Decimal(right)))==ratio,'Ratio text mismatch')
        parsed[d]=ratio
    require(len(policies)==len(parsed) and [p['session'] for p in policies]==sorted(parsed),'Complete ordered policy denominator differs')
    ordinary={}
    for p in policies:
        require(set(p)=={'session','numerator','denominator','kind'} and type(p['numerator']) is int and type(p['denominator']) is int and
            p['numerator']>0 and p['denominator']>0,'Policy ratio shape differs')
        require(Fraction(p['numerator'],p['denominator'])==parsed[p['session']],'Policy ratio differs')
        if p['kind']=='ORDINARY_SPLIT':ordinary[p['session']]=parsed[p['session']]
        else:require(p['kind']=='BEFORE_PARTITION_UNMODELLED' and floor is not None and p['session']<=floor,'Unmodelled in-window event')
        if calendar[0]<p['session']<=calendar[-1]:require(p['session'] in calendar,'Missing event day')
    positions={d:i for i,d in enumerate(dates)};prices=[];nominal={};maximum_error=Decimal(0)
    for d in calendar:
        i=positions[d];factor=Fraction(1);later=[]
        positive(quote['high'][i]);positive(quote['low'][i])
        for e in sorted(ordinary):
            if e>d:factor*=ordinary[e];later.append(e)
        row=dict(session=d,ticker=ticker,currency='USD',provider_timestamp=stamps[i],split_factor_numerator=str(factor.numerator),
            split_factor_denominator=str(factor.denominator),split_factor=float(factor),later_split_effective_sessions=later)
        for field in ('open','close'):
            value=positive(quote[field][i])
            # Independently model the declared Decimal80 multiply then divide
            # boundaries, including nonterminating factors and long coefficients.
            product=decimal_fraction(Fraction(value)*factor.numerator)
            expected=decimal_fraction(Fraction(product)/factor.denominator)
            kernel_product=decimal_fraction(Fraction(value)*factor.numerator,50)
            kernel_expected=decimal_fraction(Fraction(kernel_product)/factor.denominator,50)
            error=decimal_fraction(abs(Fraction(expected)-Fraction(kernel_expected)),50)
            maximum_error=max(maximum_error,error)
            row['quote_'+field]=str(value);row['nominal_'+field]=str(expected)
            if field=='close':nominal[d]=Fraction(expected)
        prices.append(row)
    returns=[dict(previous_session=a,session=b,declared_share_ratio=str(ordinary.get(b,Fraction(1))),
        price_return=float(nominal[b]*ordinary.get(b,Fraction(1))/nominal[a]-1)) for a,b in zip(calendar,calendar[1:])]
    affected=[dict(session=d,numerator=parsed[d].numerator,denominator=parsed[d].denominator) for d in sorted(parsed) if d>=calendar[-63]]
    liquidity=dict(status='BLOCKED_VOLUME_UNIT_UNKNOWN',rows=None,median_dollar_volume_usd=None,numerical_threshold_passed=None,affecting_returned_events=affected)
    if not affected:
        liquid=[]
        for d in calendar[-63:]:
            volume=quote['volume'][positions[d]];require(type(volume) is int and volume>0,'Positive integer original raw volume required')
            liquid.append(dict(session=d,raw_volume=volume,dollar_volume=str(decimal_fraction(nominal[d]*volume,50))))
        median=sorted(Decimal(r['dollar_volume']) for r in liquid)[31]
        liquidity.update(status='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE',rows=liquid,median_dollar_volume_usd=str(median),numerical_threshold_passed=median>=Decimal(50000000))
    retained=loads(decoded)['chart']['result'][0].get('events',{})
    return dict(quote_rows=prices,price_rows=[dict(session=d,nominal_close=float(nominal[d])) for d in calendar],price_returns=returns,
        liquidity=liquidity,maximum_nominal_reconstruction_error=str(maximum_error),returned_events=retained,decoded_sha256=hashlib.sha256(decoded).hexdigest())

def same_decimal_text(actual,expected):
    require(type(actual) is str,'Exact Decimal string required')
    parsed=Decimal(actual);require(parsed.is_finite() and parsed==Decimal(expected),'Saved Decimal amount differs')

def inspect_numeric(raw,ticker,calendar,policies,floor,quote_rows,channel):
    expected=derive(raw,ticker,calendar,policies,floor)
    require(len(quote_rows)==127,'127 saved quote rows required')
    for actual,want in zip(quote_rows,expected['quote_rows']):
        require(set(actual)==set(want),'Saved nominal row fields differ')
        for key,value in want.items():
            if key in ('quote_open','quote_close','nominal_open','nominal_close'):same_decimal_text(actual[key],value)
            else:require(type(actual[key]) is type(value) and actual[key]==value,'Saved nominal factor/calendar differs')
    for key in ('price_rows','price_returns','returned_events'):
        require(encoded(channel[key])==encoded(expected[key]),'Saved '+key+' differs from independent raw arithmetic')
    actual=channel['liquidity'];want=expected['liquidity']
    require(set(actual)==set(want),'Liquidity shape differs')
    for key in ('status','numerical_threshold_passed','affecting_returned_events'):
        require(actual[key]==want[key] and type(actual[key]) is type(want[key]),'Liquidity disposition differs')
    if want['rows'] is None:require(actual['rows'] is None and actual['median_dollar_volume_usd'] is None,'Blocked volume must remain null')
    else:
        require(len(actual['rows'])==63,'63 volume observations required')
        for row,desired in zip(actual['rows'],want['rows']):
            require(set(row)==set(desired) and row['session']==desired['session'] and type(row['raw_volume']) is int and row['raw_volume']==desired['raw_volume'],'Raw volume changed')
            same_decimal_text(row['dollar_volume'],desired['dollar_volume'])
        same_decimal_text(actual['median_dollar_volume_usd'],want['median_dollar_volume_usd'])
    for flag in ('source_assertions_authenticated','security_identity_verified','volume_units_independently_certified','complete_actions_verified',
        'exchange_calendar_verified','dividend_cash_flows_included','legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed'):
        require(channel[flag] is False,'Channel authority upgraded')
    require(channel['calendar']==calendar and channel['cutoff']==calendar[-1] and channel['ticker']==ticker and
        channel['schema']=='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1' and
        channel['regular_floor']==floor and channel['event_policy']==policies and channel['minimum_median_dollar_volume_usd']==50000000 and
        channel['coordinate_kind']=='PROVIDER_TICKER_CHANNEL_NOT_SECURITY_ID','Channel contract differs')
    require(channel['event_policy_is_external_unverified_assertion'] is True and channel['zero_unreported_events_is_explicit_research_condition'] is True,'Conditional assertions missing')
    same_decimal_text(channel['maximum_nominal_reconstruction_error'],expected['maximum_nominal_reconstruction_error'])
    return dict(ticker=ticker,price_count=127,return_count=126,liquidity_status=want['status'],
        liquidity_count=0 if want['rows'] is None else 63,decoded_sha256=expected['decoded_sha256'],**dict.fromkeys(FALSE,False))


PRODUCER_FALSE=('http_performed','fit_performed','identity_interval_verified','point_in_time_verified',
 'complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed',
 'volume_units_independently_certified','exchange_calendar_verified','dividend_cash_flows_included',
 'old_outputs_spliced','missing_values_filled','full_transitive_source_closure_reverified')
PRICE_REASONS={'NEW_127_OBSERVED_OHLC_COVERAGE_SHORT','NEW_POST_ACTION_PARTITION_SHORT_OF_127',
 'COMPLEX_RETURNED_EVENT_NOT_ORDINARY_CERTIFICATE','NEW_OLD_SPLIT_PAYLOAD_DIFF_REQUIRES_REVIEW','UNRESOLVED_RETURNED_EVENTS'}
KERNEL=ROOT/'backtest/ndx_conditional_channel_input_research.py'
KERNEL_SHA='68595f10bde6d917682d8543ebd081462f0df90b0e330f606ca1ac9a2c596804'


def ref(role):
    path,digest=BOUND[role]
    require(len(digest)==64 and set(digest)<=set('0123456789abcdef'),'Final reviewed artifact SHA required')
    return dict(path=str(BASE/path),sha256=digest)


def guard(sources):
    require(len(PRODUCER_SHA)==64,'Final producer SHA required')
    for path,digest in {**sources,**LOADED,str(PRODUCER):PRODUCER_SHA}.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source drift: '+path)


def read(reference,sources):
    path=str(Path(reference['path']).resolve());digest=reference['sha256']
    require(path not in sources or sources[path]==digest,'Conflicting reference')
    raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'Reference bytes differ')
    sources[path]=digest;return raw


def policies_and_reasons(bridge,coverage,calendar):
    mapping=bridge['event_policy_bridge'];policies=[]
    for event in sorted(mapping['events'],key=lambda r:r['session']):
        if event['status']=='SPECIFIC_POLICY_MATCH':
            p=event['policy'];ratio=Fraction(p['numerator'],p['denominator'])
            policies.append(dict(session=p['session'],kind=p['kind'],numerator=ratio.numerator,denominator=ratio.denominator))
    reasons=[];floor=bridge['new_window_derivation']['policy_floor']
    if not coverage['ohlc_127']['numerical_coverage_complete']:reasons.append('NEW_127_OBSERVED_OHLC_COVERAGE_SHORT')
    if not coverage['volume_63']['numerical_coverage_complete']:reasons.append('NEW_63_RAW_VOLUME_COVERAGE_SHORT')
    if floor and sum(d>=floor for d in calendar)<127:reasons.append('NEW_POST_ACTION_PARTITION_SHORT_OF_127')
    if bridge['ticker'] in ('CMCSA','TRI'):reasons.append('COMPLEX_RETURNED_EVENT_NOT_ORDINARY_CERTIFICATE')
    if bridge['ticker'] in ('MNST','CRWD'):reasons.append('SAVED_VOLUME_UNIT_RESTRICTION_RETAINED')
    if not mapping['exact_payload_equal']:reasons.append('NEW_OLD_SPLIT_PAYLOAD_DIFF_REQUIRES_REVIEW')
    if any(e['status']=='UNRESOLVED_RETURNED_EVENT' for e in mapping['events']):reasons.append('UNRESOLVED_RETURNED_EVENTS')
    require(reasons==bridge['new_window_derivation']['reasons'],'Independent disposition differs from saved bridge')
    return policies,reasons,floor


def inspect_receipt(receipt,started,ticker,raw,rawref):
    require(receipt['ticker']==started['ticker']==ticker and all(key in receipt and encoded(receipt[key])==encoded(value) for key,value in started.items()),'Started/receipt mismatch')
    require(type(receipt['attempt_count']) is int and receipt['attempt_count']==1 and receipt['http_status']==200 and
        receipt['point_in_time_verified'] is False and receipt['promotion_allowed'] is False and receipt['credentials_sent'] is False,'Receipt authority differs')
    require(receipt['raw_path']==rawref['path'] and receipt['raw_sha256']==rawref['sha256'] and receipt['raw_bytes']==len(raw),'Raw receipt link differs')
    require(receipt['plan_sha256']=='96696abaaa7a8d9dc2765ce436ec2b312af74f4490243a963732bcf26bfedf71' and
        receipt['runner_sha256']=='f26d8c29533d21c1ae35779f7eb8b3ff5ba9143632f9fe0091b3955bee4713bd','Capture authority differs')
    start=datetime.fromisoformat(receipt['started_at_utc']);end=datetime.fromisoformat(receipt['received_at_utc'])
    require(start.tzinfo is not None and end.tzinfo is not None and start.utcoffset().total_seconds()==0 and end.utcoffset().total_seconds()==0 and end>=start,'Receipt UTC clock invalid')
    require(day(int(start.timestamp()))==day(int(end.timestamp()))==receipt['completed_training_excludes_dates_on_or_after']=='2026-09-23','Receipt exclusion day differs')
    expected='https://query1.finance.yahoo.com/v8/finance/chart/'+ticker+'?period1=1640995200&period2='+str(int(start.timestamp()))+'&interval=1d&events=div,splits'
    require(receipt['request_method']=='GET' and receipt['request_url']==receipt['final_url']==expected,'Exact request differs')


def build():
    sources=dict(LOADED);guard(sources)
    docs={role:loads(read(ref(role),sources)) for role in BOUND};candidate=docs['candidate'];bridge=docs['bridge'];complete=docs['completeness']
    require(candidate['schema']=='NEW_CUTOFF_CONDITIONAL_CHANNELS_V1' and candidate['candidate_cutoff']==complete['candidate_cutoff']=='2026-09-21','Candidate schema/cutoff differs')
    require(candidate['input_references']=={role:ref(role) for role in ('bridge','completeness')} and
        candidate['kernel_reference']==dict(path=str(KERNEL),sha256=KERNEL_SHA),'Candidate parent/kernel reference differs')
    require(candidate['member_queue_count']==101 and candidate['full_capture_queue_count']==104 and
        candidate['additional_roles']==bridge['additional_roles'] and candidate['conditional_reconstruction_performed'] is True and
        candidate['bridge_price_generation_allowed'] is False,'Candidate denominator/scope differs')
    require(candidate['scope']=='CONDITIONAL_RESEARCH_CALCULATION' and all(candidate[k] is False for k in PRODUCER_FALSE),'Candidate authority upgraded')
    require(candidate['raw_volume_scope']=='SEALED_COMPLETE_63_DAY_NUMERICAL_OBSERVATIONS_ONLY_UNIT_UNCERTAINTY_REMAINS_SEPARATE','Raw numerical volume scope differs')
    calendar=complete['observed_reference_calendar_127'];require(candidate['calendar']==bridge['observed_reference_calendar_127']==calendar,'Candidate calendar differs')
    coverage={r['ticker']:r for r in complete['rows']};members=[r['ticker'] for r in complete['rows'] if r['role']=='OBSERVED_MEMBER_PROVIDER_CHANNEL']
    require(len(members)==len(set(members))==101 and [r['ticker'] for r in candidate['rows']]==[r['ticker'] for r in bridge['rows']]==members,'Exact 101 ordered denominator required')
    producer_sources={str(PRODUCER):PRODUCER_SHA,str(KERNEL):KERNEL_SHA,str(NY_SOURCE):LOADED[str(NY_SOURCE)],
        **{ref(role)['path']:ref(role)['sha256'] for role in ('bridge','completeness')}}
    for path,digest in producer_sources.items():read(dict(path=path,sha256=digest),sources)
    details=[]
    for row,parent in zip(candidate['rows'],bridge['rows']):
        ticker=row['ticker'];require(encoded(row['bridge_row'])==encoded(parent),'Candidate bridge row changed')
        require(row['raw_reference']==parent['new_raw_reference'] and row['receipt_reference']==parent['new_receipt_reference'],'Candidate raw/receipt source changed')
        raw=read(row['raw_reference'],sources);receipt=loads(read(row['receipt_reference'],sources))
        startedref=dict(path=str(Path(row['receipt_reference']['path']).with_name(ticker+'.started.json')),sha256=receipt['started_sha256'])
        require(row['started_reference']==startedref,'Started ref changed');started=loads(read(startedref,sources))
        inspect_receipt(receipt,started,ticker,raw,row['raw_reference'])
        for reference in (row['raw_reference'],row['receipt_reference'],startedref):producer_sources[reference['path']]=reference['sha256']
        policies,reasons,floor=policies_and_reasons(parent,coverage[ticker],calendar)
        require(coverage[ticker]['volume_63']['numerical_coverage_complete'] is True and 'NEW_63_RAW_VOLUME_COVERAGE_SHORT' not in reasons,'This candidate requires complete numerical 63 volume observations')
        require(row['reasons']==reasons and row['event_policy']==policies and row['regular_floor']==floor and all(row[k] is False for k in PRODUCER_FALSE),'Candidate disposition/authority changed')
        decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        require(hashlib.sha256(decoded).hexdigest()==row['raw_decoded_sha256']==parent['new_decoded_sha256'],'Decoded raw digest differs')
        raw_body=loads(decoded)['chart']['result'][0]
        require(raw_body['meta']['symbol']==ticker and encoded(row['returned_events'])==encoded(raw_body.get('events',{})),'Raw returned events not fully retained')
        blocked=bool(set(reasons)&PRICE_REASONS)
        if blocked:
            raw_dates=[day(t) for t in raw_body['timestamp']];quote=raw_body['indicators']['quote'][0]
            require(raw_dates==sorted(set(raw_dates)) and all(len(quote[f])==len(raw_dates) for f in ('open','high','low','close','volume')),'Blocked raw dimensions differ')
            positions={d:i for i,d in enumerate(raw_dates)}
            def valid(value):return type(value) in (int,float) and math.isfinite(value) and value>0
            complete_count=sum(d in positions and all(valid(quote[f][positions[d]]) for f in ('open','high','low','close')) for d in calendar)
            require(complete_count==coverage[ticker]['ohlc_127']['complete_day_count'],'Blocked original OHLC coverage differs')
            require(all(d in positions and type(quote['volume'][positions[d]]) is int and quote['volume'][positions[d]]>0 for d in calendar[-63:]),'Blocked channel volume coverage differs')
            require(row['status']=='BLOCKED_PRICE_INPUT' and row['quote_rows'] is None and row['channel_input'] is None and row['conditional_reconstruction_performed'] is False,'Blocked channel was promoted')
            details.append(dict(ticker=ticker,status='BLOCKED_PRICE_INPUT',reasons=reasons,**dict.fromkeys(FALSE,False)))
        else:
            require(row['status']=='CONDITIONAL_NUMERIC_RESULT' and row['conditional_reconstruction_performed'] is True,'Numeric channel disposition differs')
            audited=inspect_numeric(raw,ticker,calendar,policies,floor,row['quote_rows'],row['channel_input'])
            details.append(dict(status='CONDITIONAL_NUMERIC_RESULT',reasons=reasons,**audited))
    require(candidate['source_hashes']==producer_sources,'Exact producer source closure differs')
    blocked=[r['ticker'] for r in details if r['status']=='BLOCKED_PRICE_INPUT']
    unit=[r['ticker'] for r in details if r.get('liquidity_status')=='BLOCKED_VOLUME_UNIT_UNKNOWN']
    require(set(blocked)=={'CMCSA','TRI','HON','SPCX','HONA'} and set(unit)=={'MNST','CRWD'},'Frozen gap denominator differs')
    require(candidate['summary']==dict(conditional_price_channels=96,blocked_price_channels=5),'Candidate counts differ')
    guard(sources)
    return dict(schema='NEW_CUTOFF_CHANNELS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1',status='PASSED',completed=101,
        candidate_reference=ref('candidate'),candidate_producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),
        input_references={role:ref(role) for role in BOUND},source_hashes=sources,details=details,
        independently_recomputed_price_channels=96,blocked_price_channels=blocked,volume_unit_blocked_channels=unit,
        candidate_cutoff='2026-09-21',raw_decimal_fraction_oracle_used=True,**dict.fromkeys(FALSE,False))


def publish():
    import os
    require(not OUTPUT.exists(),'Independent audit is create-only')
    value=build();guard(value['source_hashes']);raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with OUTPUT.open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Audit publication bytes differ')
    return dict(path=str(OUTPUT),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
