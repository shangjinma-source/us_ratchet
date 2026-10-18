"""Independent raw arithmetic inspection of six505 scoring windows; no producer import."""
from copy import deepcopy
from datetime import datetime,date
from decimal import Decimal,Context,localcontext
from fractions import Fraction
from io import BytesIO
from zoneinfo import ZoneInfo
import gzip,hashlib,json,math

CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
CONTRACT=dict(decision_cutoffs=CUTOFFS,price_count_per_decision=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,windows_per_decision=13,receipt_exclusion_date='2026-09-23')
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
FALSE=('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','exchange_calendar_verified','complete_corporate_actions_verified','dividend_cash_flows_included','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','benchmark_qualified','promotion_allowed','execution_authorized','fit_performed','old_outputs_spliced','missing_values_filled','historical_timely_availability_verified','original_control_completeness_authenticated','ndx_candidate_admitted','control_weights_normalized','holdings_or_ads_converted','decision_time_action_knowledge_verified','missing_or_blocked_slots_dropped','score_computed','unequal_window_pooling_allowed')
MAX_BYTES=32*1024*1024

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return sha(encoded(v))
def exact(a,b,msg):require(encoded(a)==encoded(b),msg)
def safe(v):
    if type(v) is Decimal:return str(v)
    if type(v) is dict:return {k:safe(x) for k,x in v.items()}
    if type(v) is list:return [safe(x) for x in v]
    return v
def pairs(items):
    result={}
    for k,v in items:require(k not in result,'Duplicate JSON key');result[k]=v
    return result
def ref(r):require(type(r) is dict and type(r.get('path')) is str and r['path'] and type(r.get('sha256')) is str and len(r['sha256'])==64 and all(x in '0123456789abcdef' for x in r['sha256']),'Reference')
def number(v,positive=True):
    require(type(v) in (int,Decimal),'Raw numeric type');f=Fraction(v);require(f>0 if positive else f>=0,'Raw numeric sign');return f
def text(f):
    with localcontext(Context(prec=80)):return str(Decimal(f.numerator)/Decimal(f.denominator))
def day(s):require(type(s) is str and date.fromisoformat(s).isoformat()==s and date.fromisoformat(s).weekday()<5,'Session date')
def numeric_equal(a,b):
    if type(a) is dict:require(type(b) is dict and set(a)==set(b),'Split keys');return all(numeric_equal(v,b[k]) for k,v in a.items())
    if type(a) in (int,Decimal):return type(b) in (int,float) and math.isfinite(b) and Fraction(a)==Fraction(str(b))
    return type(a) is type(b) and a==b

REGISTRY_REFERENCE={'path':r'E:\Git\us_ratchet\data\cache\research\standard_split_exact_gap_20260919_v1\registry_readback.json','sha256':'61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'}

ADDITIONS_REFERENCE={'path':r'E:\Git\us_ratchet\data\cache\research\current_mstr_pdf_split_20260919_v1\three_split_facts.json','sha256':'e02e164554cb56f2aaed60b89e8adc3f059144bb350e88d7206e2fe74dbd401c'}

def event_reference(value):
    """Two explicit saved reference variants; no event authenticity upgrade."""
    require(type(value) is dict,'Specific event reference object')
    def direct(r):
        require(type(r) is dict and set(r)=={'path','sha256'},'Exact direct event byte reference')
        ref(r)
    if set(value)=={'path','sha256'}:
        direct(value);return
    require(set(value)=={'additional_execution_raw_reference','event_index','original_raw_reference','parent'},'Registered composite event reference keys')
    require(type(value['event_index']) is int and value['event_index']>=0,'Nonboolean registry event index')
    direct(value['parent']);require(encoded(value['parent']) in (encoded(REGISTRY_REFERENCE),encoded(ADDITIONS_REFERENCE)),'Registered split registry identity')
    direct(value['original_raw_reference'])
    if value['additional_execution_raw_reference'] is not None:direct(value['additional_execution_raw_reference'])


def inspect_tsm_control_history(*,saved_channel,raw_bytes,raw_reference,receipt,receipt_reference,bridge_row,reference_calendar,tzif_bytes,window_contract,original_control_contract):
    d=saved_channel;exact(window_contract,CONTRACT,'Fixed six505 contract')
    require(type(d) is dict and d['schema']=='ORIGINAL_EIGHT_TSM_SCORING_HISTORY_CHANNEL_V1','Saved channel schema')
    require(type(raw_bytes) is bytes and 0<len(raw_bytes)<=MAX_BYTES and type(tzif_bytes) is bytes and 0<len(tzif_bytes)<=1048576,'Input bounds')
    for r in (raw_reference,receipt_reference):ref(r)
    require(sha(raw_bytes)==raw_reference['sha256'],'Raw bytes binding')
    zone=ZoneInfo.from_file(BytesIO(tzif_bytes),key='America/New_York')
    ticker=bridge_row['ticker'];require(type(ticker) is str and ticker and ticker.strip()==ticker,'Ticker')
    exact(bridge_row['new_raw_reference'],raw_reference,'Bridge raw');exact(bridge_row['new_receipt_reference'],receipt_reference,'Bridge receipt')
    require(receipt['ticker']==ticker and receipt['raw_path']==raw_reference['path'] and receipt['raw_sha256']==raw_reference['sha256'] and type(receipt['raw_bytes']) is int and receipt['raw_bytes']==len(raw_bytes) and type(receipt['http_status']) is int and receipt['http_status']==200,'Receipt binds bytes')
    require(receipt['promotion_allowed'] is False and receipt['point_in_time_verified'] is False,'Receipt scope')
    received=datetime.fromisoformat(receipt['received_at_utc']);require(received.tzinfo is not None and received.utcoffset().total_seconds()==0 and received.astimezone(zone).date().isoformat()=='2026-09-23','Receipt clock')
    decoded=raw_bytes
    if raw_bytes.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=BytesIO(raw_bytes)) as f:decoded=f.read(MAX_BYTES+1)
    require(len(decoded)<=MAX_BYTES and sha(decoded)==bridge_row['new_decoded_sha256'],'Decoded bytes')
    def reject(v):raise ValueError('Nonfinite JSON')
    chart=json.loads(decoded,parse_float=Decimal,object_pairs_hook=pairs,parse_constant=reject)['chart'];require(chart.get('error') is None and type(chart['result']) is list and len(chart['result'])==1,'Successful chart')
    raw=chart['result'][0]
    for k,v in dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d').items():require(raw['meta'].get(k)==v,'Provider metadata')
    times=raw['timestamp'];require(type(times) is list and 0<len(times)<=10000 and all(type(t) is int and t>0 for t in times) and times==sorted(set(times)),'Unique timestamps')
    days=[datetime.fromtimestamp(t,zone).date().isoformat() for t in times];require(days==sorted(set(days)),'Unique sessions');locations={s:i for i,s in enumerate(days)}
    quotes=raw['indicators']['quote'];require(type(quotes) is list and len(quotes)==1,'One quote');q=quotes[0]
    require(all(type(q[k]) is list and len(q[k])==len(days) for k in ('open','close','high','low','volume')),'Quote shape')
    events=raw.get('events',{});require(type(events) is dict and set(events)<={'splits','dividends'} and type(events.get('dividends',{})) is dict,'Action families')
    splits=events.get('splits',{});require(type(splits) is dict and numeric_equal(splits,bridge_row['new_returned_splits']),'Full split evidence')
    mapping=bridge_row['event_policy_bridge'];floor=mapping['regular_floor'];mapped=mapping['events']
    if floor is not None:require(type(floor) is str and date.fromisoformat(floor).isoformat()==floor,'Floor date')
    require(type(mapped) is list and len(mapped)==len(splits) and {x['provider_event_key'] for x in mapped}==set(splits),'Split bijection')
    policies=[]
    for e in mapped:
        event=splits[e['provider_event_key']];stamp=event['date'];require(type(stamp) is int and str(stamp)==e['provider_event_key'],'Split timestamp')
        session=datetime.fromtimestamp(stamp,zone).date().isoformat();ratio=number(event['numerator'])/number(event['denominator']);parts=event['splitRatio'].split(':');require(len(parts)==2 and Fraction(parts[0])>0 and Fraction(parts[1])>0 and Fraction(parts[0])/Fraction(parts[1])==ratio,'Split ratio')
        p=e['policy'];require(e['status']=='SPECIFIC_POLICY_MATCH' and e['session']==p['session']==session and type(p['numerator']) is int and type(p['denominator']) is int and p['numerator']>0 and p['denominator']>0 and Fraction(p['numerator'],p['denominator'])==ratio,'Policy ratio/source')
        require(p['kind'] in ('ORDINARY_SPLIT','BEFORE_PARTITION_UNMODELLED'),'Policy kind')
        if p['kind']=='ORDINARY_SPLIT':event_reference(e['specific_event_reference'])
        else:require(floor is not None and session<=floor,'Partition boundary')
        policies.append(dict(session=session,kind=p['kind'],numerator=ratio.numerator,denominator=ratio.denominator))
    policies.sort(key=lambda x:x['session']);require(len({p['session'] for p in policies})==len(policies),'Unique action day')
    cal=reference_calendar;require(type(cal) is list and 505<=len(cal)<=10000 and cal==sorted(set(cal)) and cal[-1]<'2026-09-23','Full reference calendar')
    for x in cal:day(x)
    spans=[]
    for cutoff in CUTOFFS:
        require(cutoff in cal and cal.index(cutoff)>=504,'505 predecessors');end=cal.index(cutoff);spans.append(cal[end-504:end+1])
    union=cal[cal.index(spans[0][0]):cal.index(CUTOFFS[-1])+1]
    require(all(x in union for x in days if union[0]<=x<=union[-1]),'No extra provider day')
    require(all(p['session'] in union for p in policies if union[0]<p['session']<=union[-1]),'Action calendar')
    outer=original_control_contract
    require(type(outer) is dict and set(outer)=={'role','control_reference','securities','selected_security_id','identity_evidence','risk_evidence'},'Control contract')
    require(outer['role']=='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE' and ticker=='TSM','TSM control only')
    ref(outer['control_reference']);ss=outer['securities']
    require(type(ss) is list and len(ss)==8 and [x['ticker'] for x in ss]==['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG'],'Original8 order')
    require(len({x['security_id'] for x in ss})==8,'Eight distinct SID')
    for x in ss:
        require(type(x['issuer_id']) is str and x['issuer_id'].startswith('issuer:') and type(x['risk_chain']) is str and x['risk_chain'],'Issuer and chain')
        require(type(x['target_weight']) in (str,int,float) and Fraction(str(x['target_weight']))>=0,'Unmodified nonnegative target')
    require(outer['selected_security_id']==ss[4]['security_id']=='security:incumbent_overlay:TSM' and ss[4]['issuer_id']=='issuer:0001046179','TSM overlay')
    for k in ('identity_evidence','risk_evidence'):
        require(type(outer[k]) is list,'Evidence list')
        for r in outer[k]:ref(r)
    reconstructed=[];rawclose={}
    for session in union:
        i=locations.get(session);missing=[] if i is None else [k for k in ('open','high','low','close') if q[k][i] is None];reasons=[]
        if i is None:reasons.append('MISSING_REQUIRED_PRICE_DATE')
        if missing:reasons.append('MISSING_REQUIRED_OHLC_FIELD')
        if floor is not None and session<floor:reasons.append('BEFORE_REGULAR_FLOOR')
        x=dict(session=session,raw_row_index=i,provider_timestamp=None if i is None else times[i],status='BLOCKED_PRICE_SLOT' if reasons else 'CONDITIONAL_NUMERIC_SLOT',reasons=reasons,missing_fields=missing,nominal_open_exact=None,nominal_close_exact=None,nominal_open=None,nominal_close=None,split_factor_exact=None)
        if not reasons:
            values={k:number(q[k][i]) for k in ('open','close','high','low')};require(values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high'],'OHLC bounds')
            factor=math.prod((Fraction(p['numerator'],p['denominator']) for p in policies if p['kind']=='ORDINARY_SPLIT' and p['session']>session),start=Fraction(1));x.update(split_factor_exact=str(factor),raw_volume=safe(q['volume'][i]))
            if q['volume'][i] is not None:number(q['volume'][i],False)
            for k in ('open','close'):x.update({f'raw_{k}':safe(q[k][i]),f'nominal_{k}_exact':str(values[k]*factor),f'nominal_{k}':text(values[k]*factor)})
            rawclose[session]=values['close']
        reconstructed.append(x)
    exact(d['quote_rows'],reconstructed,'Independent complete nominal slots')
    rets=[]
    for a,b in zip(union,union[1:]):
        r=None if a not in rawclose or b not in rawclose else rawclose[b]/rawclose[a]-1;f=None if r is None else float(r)
        if f is not None:require(math.isfinite(f) and f>-1,'Float return boundary')
        rets.append(dict(previous_session=a,session=b,status='BLOCKED_RETURN_SLOT' if r is None else 'CONDITIONAL_NUMERIC_SLOT',split_only_return_exact=None if r is None else str(r),split_only_return_float=f,dividends_included=False))
    exact(d['return_rows'],rets,'Independent split neutral adjacent returns')
    decisions=[]
    for cutoff,span in zip(CUTOFFS,spans):
        start=union.index(span[0]);windows=[]
        for w in range(13):
            a=start+21*w;b=a+253;subset=reconstructed[a:b];blocked=[{k:deepcopy(x[k]) for k in ('session','reasons','missing_fields')} for x in subset if x['reasons']]
            windows.append(dict(window_index=w,relative_price_start=21*w,price_index_start=a,price_index_stop=b,training_return_index_start=a,training_return_index_stop=a+126,evaluation_return_index_start=a+126,evaluation_return_index_stop=a+252,training_price_predecessor=union[a],training_freeze_close=union[a+126],evaluation_first_return_end=union[a+127],evaluation_last_return_end=union[a+252],status='BLOCKED_WINDOW' if blocked else 'CONDITIONAL_NUMERIC_WINDOW',blocked_price_slots=blocked))
        complete=all(not x['blocked_price_slots'] for x in windows)
        decisions.append(dict(cutoff=cutoff,required_price_dates=span,required_price_count=505,required_return_count=504,price_index_start=start,price_index_stop=start+505,window_count=13,windows=windows,complete_thirteen_window_numeric_supply=complete,scoring_allowed=False,status='CONDITIONAL_ALL13_NUMERIC_SUPPLY' if complete else 'BLOCKED_FULL13_SCORING_SUPPLY',pooling_only_unblocked_windows_allowed=False))
    exact(d['decisions'],decisions,'Full6x13 causality and blocked denominator')
    metadata=dict(role='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE',arithmetic_reference={'path':'backtest/ndx_multidecision_scoring_history_research.py','sha256':'91dc5944120fcf0aeadc3c6ec8af428aa5ee37b4170824b4d215e2b58d93c313'},ticker=ticker,calendar=union,reference_calendar_preserved=cal,reference_calendar_sha256=digest(cal),window_contract=window_contract,original_control_contract=outer,raw_decode_count=1,raw_reference=raw_reference,receipt_reference=receipt_reference,receipt_preserved=receipt,decoded_sha256=sha(decoded),tzif_sha256=sha(tzif_bytes),regular_floor=floor,provider_metadata=safe(raw['meta']),returned_events=safe(events),bridge_row_preserved=bridge_row,event_policies=policies,quote_rows_sha256=digest(reconstructed),return_rows_sha256=digest(rets),returned_event_encoding='ALL_KEYS_PRESERVED_NONINTEGER_JSON_NUMBERS_AS_DECIMAL_STRINGS',provider_price_unit_assumption='SAVED_CHANNEL_SPLIT_ADJUSTED_PRICES_CONDITIONALLY_REVERSED_BY_ALL_LATER_ORDINARY_EVENTS_NOT_CERTIFIED',later_returned_actions_used_only_for_retrospective_unit_assumption=True,arithmetic='EXACT_FRACTION_FROM_RAW_DECIMAL;DISPLAY_DECIMAL_CONTEXT80;FLOAT_RETURNS_EXPLICIT_FITTER_BOUNDARY',historical_retrospective_only=True,status='CONDITIONAL_ALL_DECISIONS_NUMERIC_SUPPLY' if all(x['complete_thirteen_window_numeric_supply'] for x in decisions) else 'PARTIAL_NUMERIC_SUPPLY_FULL_SCORING_BLOCKED')
    for k,v in metadata.items():exact(d[k],v,'Exact source/scope: '+k)
    for k in FALSE:require(d[k] is False,'Authority false: '+k)
    require(set(d)==set(metadata)|set(FALSE)|{'schema','quote_rows','return_rows','decisions','content_sha256'},'Complete output schema')
    require(d['content_sha256']==digest({k:v for k,v in d.items() if k!='content_sha256'}),'Channel checksum')
    return dict(schema='TSM_CONTROL_SCORING_HISTORY_ARITHMETIC_INSPECTION_V1',status='PASS',ticker=ticker,price_slots=len(union),return_slots=len(rets),decision_count=6,window_count=78,blocked_price_slots=sum(bool(x['reasons']) for x in reconstructed),source_bytes_authenticated=False,original_control_completeness_authenticated=False,score_computed=False,fit_performed=False,point_in_time_verified=False)
