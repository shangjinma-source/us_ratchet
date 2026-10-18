"""One decode per provider, explicit 505-price scoring windows; no scoring or fit."""
from copy import deepcopy
from datetime import date,datetime
from decimal import Decimal,Context,localcontext
from fractions import Fraction
from io import BytesIO
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
import math

SCHEMA='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1'
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
CONTRACT=dict(decision_cutoffs=CUTOFFS,price_count_per_decision=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,windows_per_decision=13,receipt_exclusion_date='2026-09-23')
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
MAX_BYTES=32*1024*1024
FLAGS=dict.fromkeys(('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','exchange_calendar_verified','complete_corporate_actions_verified','dividend_cash_flows_included','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','benchmark_qualified','promotion_allowed','execution_authorized','fit_performed','old_outputs_spliced','missing_values_filled','historical_timely_availability_verified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def safe(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,dict):return {k:safe(v) for k,v in value.items()}
    if isinstance(value,list):return [safe(v) for v in value]
    return deepcopy(value)


def digest(value):return sha(json.dumps(safe(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,'Duplicate JSON key');out[k]=v
    return out


def reject(value):raise ValueError('Nonfinite JSON literal')


def number(value,positive=True):
    require(type(value) in (int,Decimal),'Raw nonboolean JSON number required')
    result=Fraction(value)
    require(result>0 if positive else result>=0,'Invalid numeric sign')
    return result


def ref(value):
    require(type(value) is dict and {'path','sha256'}<=set(value),'Explicit reference required')
    require(type(value['path']) is str and value['path'],'Reference path required')
    s=value['sha256'];require(type(s) is str and len(s)==64 and all(c in '0123456789abcdef' for c in s),'Reference SHA required')


def decimal_text(value):
    with localcontext(Context(prec=80)):
        return str(Decimal(value.numerator)/Decimal(value.denominator))


def materialize_scoring_history_channel(*,raw_bytes,raw_reference,receipt,receipt_reference,
        bridge_row,reference_calendar,tzif_bytes,window_contract,outer_inventory_contract):
    """Return full calendar slots and 6x13 window coverage; never pool unequal windows.

    Source wrapper must invoke once for every original inventory ticker and retain
    all101 provenance rows/seven evidence layers. This single-channel result does
    not authenticate those outer declarations or certify a complete eligible pool.
    """
    require(digest(window_contract)==digest(CONTRACT),'Explicit six-cutoff505/13 contract required')
    outer=outer_inventory_contract
    require(type(outer) is dict and set(outer)=={'inventory_reference','security_count','issuer_count','observed_provenance_count','preserved_sidecar_references'},'Complete outer inventory contract')
    ref(outer['inventory_reference'])
    for k,v in dict(security_count=77,issuer_count=76,observed_provenance_count=101).items():require(type(outer[k]) is int and outer[k]==v,'Original outer denominator')
    require(set(outer['preserved_sidecar_references'])==set(SIDECARS),'All seven outer evidence references')
    for r in outer['preserved_sidecar_references'].values():ref(r)
    require(type(reference_calendar) is list and 505<=len(reference_calendar)<=10000,'Complete supplied reference calendar')
    require(all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in reference_calendar),'Canonical weekday reference dates')
    require(reference_calendar==sorted(set(reference_calendar)),'No calendar compression/sort')
    require(reference_calendar[-1]<CONTRACT['receipt_exclusion_date'],'Receipt day excluded')
    required=[]
    for cutoff in CONTRACT['decision_cutoffs']:
        require(cutoff in reference_calendar,'Missing historical cutoff')
        end=reference_calendar.index(cutoff);require(end>=504,'Missing full505 predecessors')
        required.append(reference_calendar[end-504:end+1])
    first,last=required[0][0],required[-1][-1]
    calendar253=[d for d in reference_calendar if first<=d<=last]
    require(type(raw_bytes) is bytes and 0<len(raw_bytes)<=MAX_BYTES,'Bounded raw bytes')
    require(type(tzif_bytes) is bytes and 0<len(tzif_bytes)<=1024*1024,'Bounded TZif bytes')
    zone=ZoneInfo.from_file(BytesIO(tzif_bytes),key='America/New_York')
    for r in (raw_reference,receipt_reference):ref(r)
    require(sha(raw_bytes)==raw_reference['sha256'],'Raw bytes differ')
    ticker=bridge_row['ticker'];require(type(ticker) is str and ticker and ticker==ticker.strip(),'Ticker required')
    require(digest(bridge_row['new_raw_reference'])==digest(raw_reference) and digest(bridge_row['new_receipt_reference'])==digest(receipt_reference),'Bridge references differ')
    require(receipt['ticker']==ticker and receipt['raw_path']==raw_reference['path'] and receipt['raw_sha256']==raw_reference['sha256'],'Receipt binding differs')
    require(type(receipt['raw_bytes']) is int and receipt['raw_bytes']==len(raw_bytes) and type(receipt['http_status']) is int and receipt['http_status']==200,'Receipt size/status differs')
    require(receipt['promotion_allowed'] is False and receipt['point_in_time_verified'] is False,'Receipt authority differs')
    observed=datetime.fromisoformat(receipt['received_at_utc']);require(observed.tzinfo is not None and observed.utcoffset().total_seconds()==0,'UTC receipt required')
    require(observed.astimezone(zone).date().isoformat()==CONTRACT['receipt_exclusion_date'],'Receipt exclusion day differs')
    if raw_bytes[:2]==b'\x1f\x8b':
        with gzip.GzipFile(fileobj=BytesIO(raw_bytes)) as stream:decoded=stream.read(MAX_BYTES+1)
    else:decoded=raw_bytes
    require(len(decoded)<=MAX_BYTES,'Decoded byte limit exceeded')
    require(sha(decoded)==bridge_row['new_decoded_sha256'],'Decoded hash differs')
    body=json.loads(decoded,parse_float=Decimal,object_pairs_hook=unique,parse_constant=reject)
    chart=body['chart'];require(chart.get('error') is None and type(chart['result']) is list and len(chart['result'])==1,'One successful chart required')
    channel=chart['result'][0]
    for k,v in dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d').items():require(channel['meta'].get(k)==v,'Raw metadata differs: '+k)
    timestamps=channel['timestamp'];require(type(timestamps) is list and 0<len(timestamps)<=10000 and all(type(t) is int and t>0 for t in timestamps),'Bounded integer timestamps')
    days=[datetime.fromtimestamp(t,zone).date().isoformat() for t in timestamps]
    require(timestamps==sorted(set(timestamps)) and days==sorted(set(days)),'Unique ordered raw dates required')
    quotes=channel['indicators']['quote'];require(type(quotes) is list and len(quotes)==1,'One quote array')
    quotes=quotes[0]
    require(all(type(quotes[k]) is list and len(quotes[k])==len(days) for k in ('open','high','low','close','volume')),'Raw dimensions differ')
    events=channel.get('events',{});require(type(events) is dict and set(events)<={'splits','dividends'},'Unknown action family requires separate review')
    splits=events.get('splits',{});dividends=events.get('dividends',{})
    require(type(splits) is dict and type(dividends) is dict,'Event objects required')
    # Decimal-vs-original-float equivalent numeric comparisons use rational values,
    # but every field/key is still required. No extra returned split is discarded.
    def numeric_tree(v):
        if type(v) in (int,float,Decimal):return str(Fraction(str(v)))
        if type(v) is dict:return {k:numeric_tree(x) for k,x in v.items()}
        if type(v) is list:return [numeric_tree(x) for x in v]
        return v
    require(digest(numeric_tree(splits))==digest(numeric_tree(bridge_row['new_returned_splits'])),'Bridge returned splits differ')
    mapping=bridge_row['event_policy_bridge'];mapped=mapping['events'];floor=mapping['regular_floor']
    if floor is not None:require(type(floor) is str and date.fromisoformat(floor).isoformat()==floor,'Canonical floor')
    require(type(mapped) is list and len(mapped)==len(splits) and {m['provider_event_key'] for m in mapped}==set(splits),'Full event policy denominator')
    policies=[];eventdays=set()
    for m in mapped:
        event=splits[m['provider_event_key']];stamp=event['date']
        require(type(stamp) is int and str(stamp)==m['provider_event_key'],'Split timestamp/key differs')
        d=datetime.fromtimestamp(stamp,zone).date().isoformat();require(d==m['session'] and d not in eventdays,'Split date differs/duplicate');eventdays.add(d)
        ratio=number(event['numerator'])/number(event['denominator']);parts=event['splitRatio'].split(':')
        require(len(parts)==2 and Fraction(parts[0])>0 and Fraction(parts[1])>0 and Fraction(parts[0])/Fraction(parts[1])==ratio,'Split ratio differs')
        require(m['status']=='SPECIFIC_POLICY_MATCH','Unresolved or complex event cannot enter numeric reconstruction')
        p=m['policy'];require(p['session']==d and type(p['numerator']) is int and type(p['denominator']) is int and Fraction(p['numerator'],p['denominator'])==ratio,'Policy ratio differs')
        require(p['kind'] in ('ORDINARY_SPLIT','BEFORE_PARTITION_UNMODELLED'),'Unknown policy')
        if p['kind']=='ORDINARY_SPLIT':require(m.get('specific_event_reference') is not None,'Specific ordinary event evidence required')
        else:require(floor is not None and d<=floor,'Unmodelled action after floor')
        require(not(calendar253[0]<d<=calendar253[-1]) or d in calendar253,'In-window event absent from calendar')
        policies.append(dict(session=d,kind=p['kind'],numerator=ratio.numerator,denominator=ratio.denominator))
    policies.sort(key=lambda x:x['session'])
    positions={d:i for i,d in enumerate(days)}
    # Retain every union calendar slot, including missing and pre-floor slots.
    actual=[d for d in days if calendar253[0]<=d<=calendar253[-1]]
    require(all(d in calendar253 for d in actual),'Extra provider day cannot disappear')
    rows=[];raw_closes={};factors={}
    for d in calendar253:
        reasons=[];i=positions.get(d)
        if i is None:reasons.append('MISSING_REQUIRED_PRICE_DATE')
        fields=[] if i is None else [k for k in ('open','high','low','close') if quotes[k][i] is None]
        if fields:reasons.append('MISSING_REQUIRED_OHLC_FIELD')
        if floor is not None and d<floor:reasons.append('BEFORE_REGULAR_FLOOR')
        row=dict(session=d,raw_row_index=i,provider_timestamp=None if i is None else timestamps[i],
            status='BLOCKED_PRICE_SLOT' if reasons else 'CONDITIONAL_NUMERIC_SLOT',reasons=reasons,
            missing_fields=fields,nominal_open_exact=None,nominal_close_exact=None,
            nominal_open=None,nominal_close=None,split_factor_exact=None)
        if not reasons:
            values={k:number(quotes[k][i]) for k in ('open','high','low','close')}
            require(values['low']<=min(values['open'],values['close']) and values['high']>=max(values['open'],values['close']) and values['low']<=values['high'],'OHLC bounds invalid')
            factor=Fraction(1)
            for policy in policies:
                if policy['kind']=='ORDINARY_SPLIT' and policy['session']>d:factor*=Fraction(policy['numerator'],policy['denominator'])
            row.update(split_factor_exact=str(factor),raw_volume=safe(quotes['volume'][i]))
            if quotes['volume'][i] is not None:number(quotes['volume'][i],False)
            for k in ('open','close'):
                nominal=values[k]*factor;row['raw_'+k]=safe(quotes[k][i]);row['nominal_'+k+'_exact']=str(nominal);row['nominal_'+k]=decimal_text(nominal)
            raw_closes[d]=values['close'];factors[d]=factor
        rows.append(row)
    returns=[]
    for previous,d in zip(calendar253,calendar253[1:]):
        value=None;f=None
        if previous in raw_closes and d in raw_closes:
            gross=raw_closes[d]/raw_closes[previous]
            equivalent=(raw_closes[d]*factors[d])/(raw_closes[previous]*factors[previous])*(factors[previous]/factors[d])
            require(gross==equivalent,'Split factor equivalence')
            value=str(gross-1);f=float(gross-1);require(math.isfinite(f) and f>-1,'Finite fitter boundary')
        returns.append(dict(previous_session=previous,session=d,status='BLOCKED_RETURN_SLOT' if value is None else 'CONDITIONAL_NUMERIC_SLOT',split_only_return_exact=value,split_only_return_float=f,dividends_included=False))
    row_index={r['session']:i for i,r in enumerate(rows)};decisions=[]
    for cutoff,dates in zip(CONTRACT['decision_cutoffs'],required):
        start=row_index[dates[0]];windows=[]
        for w,offset in enumerate(range(0,253,21)):
            price_start=start+offset;subset=rows[price_start:price_start+253]
            require(len(subset)==253 and subset[-1]['session']<=cutoff,'Causal complete inner window')
            blocked=[dict(session=r['session'],reasons=deepcopy(r['reasons']),missing_fields=deepcopy(r['missing_fields'])) for r in subset if r['reasons']]
            windows.append(dict(window_index=w,relative_price_start=offset,
                price_index_start=price_start,price_index_stop=price_start+253,
                training_return_index_start=price_start,training_return_index_stop=price_start+126,
                evaluation_return_index_start=price_start+126,evaluation_return_index_stop=price_start+252,
                training_price_predecessor=subset[0]['session'],training_freeze_close=subset[126]['session'],
                evaluation_first_return_end=subset[127]['session'],evaluation_last_return_end=subset[-1]['session'],
                status='BLOCKED_WINDOW' if blocked else 'CONDITIONAL_NUMERIC_WINDOW',blocked_price_slots=blocked))
        complete=all(w['status']=='CONDITIONAL_NUMERIC_WINDOW' for w in windows)
        decisions.append(dict(cutoff=cutoff,required_price_dates=deepcopy(dates),required_price_count=505,required_return_count=504,
            price_index_start=start,price_index_stop=start+505,window_count=13,windows=windows,
            complete_thirteen_window_numeric_supply=complete,scoring_allowed=False,
            status='CONDITIONAL_ALL13_NUMERIC_SUPPLY' if complete else 'BLOCKED_FULL13_SCORING_SUPPLY',
            pooling_only_unblocked_windows_allowed=False))
    out=dict(schema=SCHEMA,ticker=ticker,status='CONDITIONAL_ALL_DECISIONS_NUMERIC_SUPPLY' if all(d['complete_thirteen_window_numeric_supply'] for d in decisions) else 'PARTIAL_NUMERIC_SUPPLY_FULL_SCORING_BLOCKED',
        calendar=calendar253,reference_calendar_preserved=deepcopy(reference_calendar),reference_calendar_sha256=digest(reference_calendar),
        window_contract=deepcopy(window_contract),outer_inventory_contract=deepcopy(outer),outer_inventory_completeness_verified=False,
        raw_decode_count=1,raw_reference=deepcopy(raw_reference),receipt_reference=deepcopy(receipt_reference),receipt_preserved=deepcopy(receipt),decoded_sha256=sha(decoded),tzif_sha256=sha(tzif_bytes),
        regular_floor=floor,provider_metadata=safe(channel['meta']),returned_events=safe(events),bridge_row_preserved=deepcopy(bridge_row),event_policies=policies,
        returned_event_encoding='ALL_KEYS_PRESERVED_NONINTEGER_JSON_NUMBERS_AS_DECIMAL_STRINGS',
        provider_price_unit_assumption='SAVED_CHANNEL_SPLIT_ADJUSTED_PRICES_CONDITIONALLY_REVERSED_BY_ALL_LATER_ORDINARY_EVENTS_NOT_CERTIFIED',
        later_returned_actions_used_only_for_retrospective_unit_assumption=True,decision_time_action_knowledge_verified=False,
        arithmetic='EXACT_FRACTION_FROM_RAW_DECIMAL;DISPLAY_DECIMAL_CONTEXT80;FLOAT_RETURNS_EXPLICIT_FITTER_BOUNDARY',
        quote_rows=rows,return_rows=returns,quote_rows_sha256=digest(rows),return_rows_sha256=digest(returns),decisions=decisions,
        missing_or_blocked_slots_dropped=False,score_computed=False,unequal_window_pooling_allowed=False,historical_retrospective_only=True,**FLAGS)
    out['content_sha256']=digest(out)
    return out
