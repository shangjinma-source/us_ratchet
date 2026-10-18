"""Raw-provider 253-session conditional arithmetic; never identity or admission."""
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

SCHEMA='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1'
CONTRACT=dict(cutoff='2026-09-21',fit_return_count=126,evaluation_return_count=126,receipt_exclusion_date='2026-09-23')
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


def reconstruct_long_channel(*,raw_bytes,raw_reference,receipt,receipt_reference,bridge_row,calendar253,tzif_bytes,window_contract):
    """One decode, exact Fraction arithmetic; gaps/floors return a blocked row.

    Decimal strings are display encodings; numerator/denominator strings remain
    authoritative if a rational has no finite decimal expansion. Saved events
    preserve every key, with original noninteger JSON numbers encoded as strings.
    """
    require(digest(window_contract)==digest(CONTRACT),'Fixed retrospective window contract required')
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
    require(type(calendar253) is list and len(calendar253)==253,'Exactly253 prices required')
    require(all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in calendar253),'Canonical observed weekdays')
    require(calendar253==sorted(set(calendar253)) and calendar253[-1]==CONTRACT['cutoff'],'Ordered complete calendar required')
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
    missing=[d for d in calendar253 if d not in positions]
    missing_fields=[]
    for d in calendar253:
        if d in positions:
            fields=[k for k in ('open','high','low','close') if quotes[k][positions[d]] is None]
            if fields:missing_fields.append(dict(session=d,fields=fields))
    blocked=[]
    if missing:blocked.append('MISSING_REQUIRED_PRICE_DATE')
    if missing_fields:blocked.append('MISSING_REQUIRED_OHLC_FIELD')
    if floor is not None and floor>calendar253[0]:blocked.append('REQUIRED_PREDECESSOR_BEFORE_REGULAR_FLOOR')
    # Do not compress away an extra provider observation in the required span.
    actual=[d for d in days if calendar253[0]<=d<=calendar253[-1]]
    require(all(d in calendar253 for d in actual),'Provider date not represented by fixed reference calendar')
    out=dict(schema=SCHEMA,ticker=ticker,status='BLOCKED_PRICE_INPUT' if blocked else 'CONDITIONAL_NUMERIC_RESULT',reasons=blocked,
        calendar=deepcopy(calendar253),missing_price_dates=missing,missing_price_fields=missing_fields,regular_floor=floor,
        raw_reference=deepcopy(raw_reference),receipt_reference=deepcopy(receipt_reference),receipt_preserved=deepcopy(receipt),
        decoded_sha256=sha(decoded),tzif_sha256=sha(tzif_bytes),provider_metadata=safe(channel['meta']),returned_events=safe(events),
        returned_event_encoding='ALL_KEYS_PRESERVED_NONINTEGER_JSON_NUMBERS_AS_DECIMAL_STRINGS',bridge_row_preserved=deepcopy(bridge_row),event_policies=policies,
        provider_price_unit_assumption='SAVED_CHANNEL_SPLIT_ADJUSTED_PRICES_CONDITIONALLY_REVERSED_BY_ALL_LATER_ORDINARY_EVENTS_NOT_CERTIFIED',
        arithmetic='EXACT_FRACTION_FROM_RAW_DECIMAL;DISPLAY_DECIMAL_CONTEXT80;FLOAT_RETURNS_EXPLICIT_FITTER_BOUNDARY',
        conditional_reconstruction_performed=False,historical_retrospective_only=True,window_contract=deepcopy(window_contract),quote_rows=None,return_rows=None,training_returns=None,evaluation_returns=None,
        training_freeze_close_date=calendar253[126],evaluation_initial_close_date=calendar253[126],**FLAGS)
    if blocked:return out
    rows=[];returns=[];previous=None
    for d in calendar253:
        i=positions[d];values={k:number(quotes[k][i]) for k in ('open','high','low','close')}
        require(values['low']<=min(values['open'],values['close']) and values['high']>=max(values['open'],values['close']) and values['low']<=values['high'],'OHLC bounds invalid')
        factor=Fraction(1)
        for p in policies:
            if p['kind']=='ORDINARY_SPLIT' and p['session']>d:factor*=Fraction(p['numerator'],p['denominator'])
        row=dict(session=d,raw_row_index=i,provider_timestamp=timestamps[i],split_factor_exact=str(factor),raw_volume=safe(quotes['volume'][i]))
        if quotes['volume'][i] is not None:number(quotes['volume'][i],False)
        for k in ('open','close'):
            nominal=values[k]*factor;row['raw_'+k]=safe(quotes[k][i]);row['nominal_'+k+'_exact']=str(nominal);row['nominal_'+k]=decimal_text(nominal)
        if previous is not None:
            gross=values['close']/previous['raw_close'];r=gross-1
            equivalent=(values['close']*factor)/(previous['raw_close']*previous['factor'])*(previous['factor']/factor)
            require(gross==equivalent,'Split-only sharefactor equivalence failure')
            float_return=float(r);require(math.isfinite(float_return) and float_return>-1,'Fitter return float boundary invalid')
            returns.append(dict(previous_session=previous['session'],session=d,split_only_return_exact=str(r),split_only_return_float=float_return,dividends_included=False))
        previous=dict(session=d,raw_close=values['close'],factor=factor);rows.append(row)
    out.update(quote_rows=rows,return_rows=returns,training_returns=returns[:126],evaluation_returns=returns[126:],conditional_reconstruction_performed=True)
    out['quote_rows_sha256']=digest(rows);out['training_returns_sha256']=digest(returns[:126]);out['evaluation_returns_sha256']=digest(returns[126:])
    return out
