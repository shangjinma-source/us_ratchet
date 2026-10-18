"""Independent raw Decimal oracle for conditional channels, never identity admission."""
import gzip
import json
from datetime import date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON field')
        result[key]=value
    return result


def number(value):
    if type(value) not in (int,float,Decimal):raise ValueError('Finite nonboolean numeric value required')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Finite numeric value required')
    return result


def positive(value):
    result=number(value)
    if result<=0:raise ValueError('Positive number required')
    return result


def day(stamp):
    if type(stamp) is not int or stamp<=0:raise ValueError('Positive integer timestamp required')
    return datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat()


def exact(a,b):
    return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def audit(*,output,raw_bytes,quote_rows,calendar,event_policy,exclude_on_or_after,regular_floor=None):
    """Caller binds evidence. Recompute arithmetic without producer code or nominal prices."""
    with localcontext() as context:
        context.prec=50
        return _audit(output,raw_bytes,quote_rows,calendar,event_policy,exclude_on_or_after,regular_floor)


def _audit(output,raw_bytes,quote_rows,calendar,event_policy,exclude_on_or_after,regular_floor):
    expected_keys={'schema','ticker','cutoff','coordinate_kind','calendar','regular_floor','returned_events','event_policy','price_rows','price_returns','liquidity','maximum_nominal_reconstruction_error','minimum_median_dollar_volume_usd','event_policy_is_external_unverified_assertion','zero_unreported_events_is_explicit_research_condition','source_assertions_authenticated','security_identity_verified','volume_units_independently_certified','complete_actions_verified','exchange_calendar_verified','dividend_cash_flows_included','legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed'}
    if type(output) is not dict or set(output)!=expected_keys:raise ValueError('Exact conditional output schema required')
    if type(output['liquidity']) is not dict or set(output['liquidity'])!={'status','rows','median_dollar_volume_usd','numerical_threshold_passed','affecting_returned_events'}:raise ValueError('Exact conditional liquidity schema required')
    def iso(value):
        if type(value) is not str or date.fromisoformat(value).isoformat()!=value:raise ValueError('Canonical ISO date required')
        return value
    if type(calendar) is not list or len(calendar)!=127 or calendar!=sorted(set(calendar)):
        raise ValueError('127 unique ordered observed price sessions required')
    for d in calendar:iso(d)
    cutoff=calendar[-1]
    if cutoff>=iso(exclude_on_or_after) or regular_floor is not None and iso(regular_floor)>calendar[0]:raise ValueError('Receipt or regular boundary violated')
    ticker=output['ticker']
    if type(ticker) is not str or not ticker or ticker.strip()!=ticker:raise ValueError('Explicit ticker channel required')
    if output['schema']!='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1' or output['coordinate_kind']!='PROVIDER_TICKER_CHANNEL_NOT_SECURITY_ID' or output['cutoff']!=cutoff or output['calendar']!=calendar or output['regular_floor']!=regular_floor:raise ValueError('Exact channel schema/calendar required')
    if 'security_id' in output or 'issuer_id' in output:raise ValueError('No invented legal coordinate')
    for key in ('source_assertions_authenticated','security_identity_verified','volume_units_independently_certified','complete_actions_verified','exchange_calendar_verified','dividend_cash_flows_included','legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed'):
        if output[key] is not False:raise ValueError('Conditional scope cannot be upgraded')
    for key in ('event_policy_is_external_unverified_assertion','zero_unreported_events_is_explicit_research_condition'):
        if output[key] is not True:raise ValueError('Conditional event evidence disclosure required')
    decoded=gzip.decompress(raw_bytes) if raw_bytes[:2]==b'\x1f\x8b' else raw_bytes
    def invalid(value):raise ValueError('Nonfinite JSON constant')
    body=json.loads(decoded,object_pairs_hook=unique,parse_float=Decimal,parse_constant=invalid)
    chart=body['chart']
    if chart.get('error') is not None or len(chart['result'])!=1:raise ValueError('One successful channel required')
    raw=chart['result'][0]
    expected_meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d')
    if any(raw['meta'].get(k)!=v for k,v in expected_meta.items()):raise ValueError('Raw metadata differs')
    dates=[day(t) for t in raw['timestamp']]
    if dates!=sorted(set(dates)) or [d for d in dates if d<=cutoff][-127:]!=calendar:raise ValueError('Compressed or missing observed predecessor')
    if len(raw['indicators']['quote'])!=1:raise ValueError('One raw quote array required')
    quote=raw['indicators']['quote'][0]
    if any(len(quote[k])!=len(dates) for k in ('open','close','volume')):raise ValueError('Raw dimensions differ')
    events=raw.get('events',{})
    if type(events) is not dict or set(events)-{'splits','dividends'} or any(type(events.get(k,{})) is not dict for k in ('splits','dividends')):raise ValueError('Unknown event channel')
    retained=json.loads(decoded,object_pairs_hook=unique,parse_constant=invalid)['chart']['result'][0].get('events',{})
    if not exact(output['returned_events'],retained):raise ValueError('Full raw events must be preserved')
    parsed=[]
    for key,event in events.get('splits',{}).items():
        session=day(event['date']);ratio=Fraction(positive(event['numerator']))/Fraction(positive(event['denominator']))
        text=event['splitRatio']
        if type(text) is not str or len(text.split(':'))!=2:raise ValueError('Split ratio text required')
        a,b=text.split(':')
        if str(event['date'])!=key or Fraction(positive(Decimal(a)))/Fraction(positive(Decimal(b)))!=ratio:raise ValueError('Split ratio/date conflict')
        parsed.append(dict(session=session,numerator=ratio.numerator,denominator=ratio.denominator))
    parsed.sort(key=lambda x:x['session'])
    if len({p['session'] for p in parsed})!=len(parsed) or type(event_policy) is not list or len(event_policy)!=len(parsed) or not exact(output['event_policy'],event_policy):raise ValueError('Full event denominator differs')
    ordinary={}
    for event,policy in zip(parsed,event_policy):
        if set(policy)!={'session','numerator','denominator','kind'} or any(policy.get(k)!=v for k,v in event.items()) or any(type(policy[k]) is not int for k in ('numerator','denominator')):raise ValueError('Policy event does not match raw')
        if policy['kind']=='ORDINARY_SPLIT':ordinary[event['session']]=Fraction(event['numerator'],event['denominator'])
        elif policy['kind']!='BEFORE_PARTITION_UNMODELLED' or regular_floor is None or event['session']>regular_floor:raise ValueError('Unmodelled event crosses explicit partition')
        if calendar[0]<event['session']<=cutoff and event['session'] not in calendar:raise ValueError('Event session missing')
    if len(output['price_rows'])!=127 or len(output['price_returns'])!=126:raise ValueError('127/126 denominator required')
    saved_quotes={r['session']:r for r in quote_rows}
    if len(saved_quotes)!=len(quote_rows) or list(saved_quotes)!=sorted(saved_quotes) or any(d not in saved_quotes for d in calendar):raise ValueError('Complete unique source quote coordinates required')
    positions={d:i for i,d in enumerate(dates)};nominal={};max_price=Decimal(0);max_return=Decimal(0);max_source=Decimal(0)
    for d,row in zip(calendar,output['price_rows']):
        factor=Fraction(1)
        for event_date,ratio in ordinary.items():
            if event_date>d:factor*=ratio
        raw_close=positive(quote['close'][positions[d]]);positive(quote['open'][positions[d]])
        nominal[d]=raw_close*Decimal(factor.numerator)/Decimal(factor.denominator)
        source=saved_quotes[d];i=positions[d]
        if source['ticker']!=ticker or source['currency']!='USD' or type(source['provider_timestamp']) is not int or source['provider_timestamp']!=raw['timestamp'][i]:raise ValueError('Source quote metadata differs')
        if source['split_factor_numerator']!=str(factor.numerator) or source['split_factor_denominator']!=str(factor.denominator) or type(source['split_factor']) not in (int,float) or source['split_factor']!=float(factor) or source['later_split_effective_sessions']!=[e for e in ordinary if e>d]:raise ValueError('Source full event factor differs')
        for field in ('open','close'):
            observed=positive(quote[field][i]);expected=observed*Decimal(factor.numerator)/Decimal(factor.denominator)
            if positive(source['quote_'+field])!=observed:raise ValueError('Original source quote differs')
            error=abs(positive(source['nominal_'+field])-expected);max_source=max(max_source,error)
            if error>max(Decimal('1e-10'),abs(expected)*Decimal('1e-12')):raise ValueError('Source nominal Open/Close differs')
        if set(row)!={'session','nominal_close'} or row['session']!=d:raise ValueError('Price row coordinate differs')
        error=abs(positive(row['nominal_close'])-nominal[d]);max_price=max(max_price,error)
        if error>max(Decimal('1e-10'),abs(nominal[d])*Decimal('1e-12')):raise ValueError('Nominal factor reconstruction differs')
    for before,after,row in zip(calendar,calendar[1:],output['price_returns']):
        if set(row)!={'previous_session','session','declared_share_ratio','price_return'} or row['previous_session']!=before or row['session']!=after or row['declared_share_ratio']!=str(ordinary.get(after,Fraction(1))):raise ValueError('Return predecessor/ratio differs')
        # Split-adjusted raw prices cancel the nominal reconstruction and event ratio.
        expected=positive(quote['close'][positions[after]])/positive(quote['close'][positions[before]])-1
        error=abs(number(row['price_return'])-expected);max_return=max(max_return,error)
        if error>Decimal('1e-12'):raise ValueError('Independent raw Close price return differs')
    liquid=calendar[-63:];affected=[p for p in parsed if p['session']>=liquid[0]];saved=output['liquidity']
    if not exact(saved['affecting_returned_events'],affected):raise ValueError('Liquidity event denominator differs')
    if affected:
        if saved['status']!='BLOCKED_VOLUME_UNIT_UNKNOWN' or any(saved[k] is not None for k in ('rows','median_dollar_volume_usd','numerical_threshold_passed')):raise ValueError('Across-split volume unit cannot be silently admitted')
        median=None
    else:
        if saved['status']!='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE' or len(saved['rows'])!=63:raise ValueError('63 conditional liquidity rows required')
        dollars=[]
        for d,row in zip(liquid,saved['rows']):
            if set(row)!={'session','raw_volume','dollar_volume'}:raise ValueError('Exact liquidity row schema required')
            volume=quote['volume'][positions[d]]
            if type(volume) is not int or volume<=0 or row['session']!=d or type(row['raw_volume']) is not int or row['raw_volume']!=volume:raise ValueError('Raw volume coordinate differs')
            value=nominal[d]*volume;actual=Decimal(row['dollar_volume'])
            if not actual.is_finite() or abs(actual-value)>max(Decimal('1e-8'),abs(value)*Decimal('1e-12')):raise ValueError('Independent dollar volume differs')
            dollars.append(value)
        median=sorted(dollars)[31]
        if abs(Decimal(saved['median_dollar_volume_usd'])-median)>max(Decimal('1e-8'),abs(median)*Decimal('1e-12')) or saved['numerical_threshold_passed'] is not (median>=50000000):raise ValueError('Independent median/threshold differs')
    if type(output['minimum_median_dollar_volume_usd']) is not int or output['minimum_median_dollar_volume_usd']!=50000000:raise ValueError('Fixed numerical threshold required')
    reported=Decimal(output['maximum_nominal_reconstruction_error'])
    if type(output['maximum_nominal_reconstruction_error']) is not str or not reported.is_finite() or reported<0 or reported!=max_source:raise ValueError('Independent source Open/Close error diagnostic differs')
    return dict(schema='CONDITIONAL_CHANNEL_INDEPENDENT_RAW_DECIMAL_AUDIT_V1',ticker=ticker,price_count=127,return_count=126,liquidity_status=saved['status'],liquidity_count=0 if affected else 63,median_dollar_volume_usd=None if median is None else str(median),maximum_nominal_close_error=str(max_price),maximum_raw_close_return_error=str(max_return),returned_split_count=len(parsed),producer_called=False,security_identity_verified=False,complete_actions_verified=False,legal_training_input_admitted=False,point_in_time_verified=False,promotion_allowed=False)
