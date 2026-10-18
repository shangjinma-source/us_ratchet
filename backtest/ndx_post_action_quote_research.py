"""Conditional quote copies after an evidenced action boundary; never split arithmetic."""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
from backtest import ndx_post_action_interval_research as interval

BASIS='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS'
NY=ZoneInfo('America/New_York')


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON field')
        result[key]=value
    return result


def epoch(value):
    if type(value) is not int or value<=0:raise ValueError('Positive integer timestamp required')
    return datetime.fromtimestamp(value,timezone.utc)


def positive(value):
    if type(value) not in (int,float) or not Decimal(str(value)).is_finite() or value<=0:
        raise ValueError('Finite positive nonboolean quote or ratio required')
    return value


def reconstruct_post_action_quote(*,raw,ticker,calendar,official_boundary,request,received_at_utc,quote_field_basis):
    if type(raw) is not bytes or quote_field_basis!=BASIS:raise ValueError('Raw bytes and explicit conditional quote basis required')
    if ticker not in interval.SUPPORTED:raise ValueError('Only four explicit action intervals supported')
    received=datetime.fromisoformat(received_at_utc)
    if received.tzinfo is None or received.utcoffset().total_seconds()!=0:raise ValueError('UTC receipt required')
    excluded=received.astimezone(NY).date().isoformat()
    if request.get('method')!='GET' or request.get('credentials_sent') is not False:raise ValueError('Public GET required')
    url=urlparse(request['url']);query=parse_qs(url.query,keep_blank_values=True)
    if (url.scheme!='https' or url.netloc!='query1.finance.yahoo.com' or url.path!='/v8/finance/chart/'+ticker or url.fragment
            or set(query)!={'period1','period2','interval','events'} or query['interval']!=['1d'] or query['events']!=['div,splits']
            or any(len(query[k])!=1 or re.fullmatch('[0-9]+',query[k][0]) is None for k in ('period1','period2'))):
        raise ValueError('Exact request channel/horizon required')
    start,end=(int(query[k][0]) for k in ('period1','period2'))
    if epoch(start)>=epoch(end) or epoch(end)>received or epoch(end).astimezone(NY).date()!=received.astimezone(NY).date():
        raise ValueError('Request must reach receipt market date without future horizon')
    chart=json.loads(raw,object_pairs_hook=unique)['chart']
    if chart.get('error') is not None or type(chart.get('result')) is not list or len(chart['result'])!=1:raise ValueError('One successful chart required')
    data=chart['result'][0];meta=data['meta']
    if any(meta.get(k)!=v for k,v in dict(symbol=ticker,currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d').items()):
        raise ValueError('Response channel/USD/equity coordinates differ')
    stamps=data['timestamp'];quotes=data['indicators']['quote']
    if type(stamps) is not list or not stamps or type(quotes) is not list or len(quotes)!=1:raise ValueError('Complete quote arrays required')
    quote=quotes[0]
    if any(type(quote.get(k)) is not list or len(quote[k])!=len(stamps) for k in ('open','close')):raise ValueError('Full quote denominator differs')
    daily={};last=None
    for i,t in enumerate(stamps):
        instant=epoch(t);day=instant.astimezone(NY).date().isoformat()
        if not start<=t<end or instant>received or day in daily or last is not None and t<=last:raise ValueError('Unordered/duplicate/future/outside-request quote')
        daily[day]=dict(timestamp=t,open=positive(quote['open'][i]),close=positive(quote['close'][i]));last=t
    events=data.get('events',{})
    if type(events) is not dict or set(events)-{'splits','dividends'}:raise ValueError('Unrecognized returned corporate event channel')
    split_like=[]
    for kind,items in events.items():
        if type(items) is not dict:raise ValueError('Event map required')
        seen=set()
        for key,event in items.items():
            t=event['date'];instant=epoch(t);day=instant.astimezone(NY).date().isoformat()
            if key!=str(t) or not start<=t<end or instant>received or day in seen or day not in daily:raise ValueError('Event date/key/coverage conflict')
            seen.add(day)
            if kind=='splits':
                n,d=positive(event['numerator']),positive(event['denominator']);text=event['splitRatio']
                if type(text) is not str or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?:[0-9]+(?:\.[0-9]+)?',text) is None:raise ValueError('Explicit provider ratio text required')
                a,b=text.split(':')
                if Fraction(b)<=0 or Fraction(a)<=0 or Fraction(a)/Fraction(b)!=Fraction(str(n))/Fraction(str(d)):raise ValueError('Provider ratio fields conflict')
                split_like.append(dict(provider_event_key=key,session=day,provider_fields=event))
            else:positive(event['amount'])
    proposal=interval.propose_interval(ticker=ticker,calendar=calendar,returned_events=split_like,official_boundary=official_boundary,completed_before=excluded)
    expected=[day for day in daily if proposal['first_post_action_session']<=day<excluded]
    if calendar!=expected:raise ValueError('Full completed post-boundary provider calendar required; no silent row selection')
    rows=[dict(ticker=ticker,session=day,currency='USD',provider_timestamp=daily[day]['timestamp'],
        quote_open=daily[day]['open'],quote_close=daily[day]['close'],nominal_open=daily[day]['open'],nominal_close=daily[day]['close'],
        factor_numerator='1',factor_denominator='1',factor=1,returned_later_split_like_events=[],
        coordinate_scope='CONDITIONAL_POST_ACTION_PROVIDER_CHANNEL_NOT_SECURITY_IDENTITY') for day in calendar]
    return dict(schema='POST_ACTION_CONDITIONAL_QUOTE_V1',ticker=ticker,rows=rows,row_count=len(rows),
        full_provider_row_count=len(daily),post_action_interval=proposal,returned_events=events,returned_split_like_events=split_like,
        returned_split_like_events_were_share_multipliers=False,decoded_sha256=hashlib.sha256(raw).hexdigest(),
        quote_field_basis=quote_field_basis,quote_basis_independently_authenticated=False,original_request=request,received_at_utc=received_at_utc,
        incomplete_receipt_day_excluded=excluded,pre_boundary_provider_dates=[day for day in daily if day<proposal['first_post_action_session']],
        receipt_or_later_dates_excluded=[day for day in daily if day>=excluded],all_original_raw_events_retained=True,
        adjclose_used=False,dividends_applied=False,returns_generated=False,first_session_return_generated=False,
        complete_corporate_actions_verified=False,absence_of_later_events_proves_no_actions=False,
        historical_identity_join_performed=False,provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False)


def decimal_quote_audit(raw,result):
    """Independent lexical-decimal comparison: no action multipliers or production rows reused."""
    data=json.loads(raw,object_pairs_hook=unique,parse_float=Decimal,parse_int=Decimal)['chart']['result'][0]
    quote=data['indicators']['quote'][0]
    source={datetime.fromtimestamp(int(t),timezone.utc).astimezone(NY).date().isoformat():i for i,t in enumerate(data['timestamp'])}
    ticker=result['ticker'];floor=interval.SUPPORTED[ticker][0]
    received=datetime.fromisoformat(result['received_at_utc']);excluded=received.astimezone(NY).date().isoformat()
    expected_days=[d for d in source if floor<=d<excluded]
    if ([r['session'] for r in result['rows']]!=expected_days or result['row_count']!=len(expected_days)
            or data['meta']['symbol']!=ticker):raise ValueError('Independent full post-action calendar differs')
    maximum=Decimal(0)
    for row in result['rows']:
        i=source[row['session']]
        if (row['factor_numerator'],row['factor_denominator'],row['factor'])!=('1','1',1):raise ValueError('Post-last-action factor must remain one')
        for field in ('open','close'):
            expected=quote[field][i];actual=Decimal(str(row['nominal_'+field]));error=abs(actual-expected)
            if row['ticker']!=ticker or Decimal(str(row['quote_'+field]))!=actual:raise ValueError('Quote copy/coordinate differs')
            maximum=max(maximum,error)
            if error>Decimal('0.000000000001'):raise ValueError('Independent decimal raw quote mismatch')
    return dict(rows_checked=len(result['rows']),cells_checked=2*len(result['rows']),maximum_absolute_decimal_error=str(maximum),
        tolerance='0.000000000001',share_multiplier_applied=False,dividend_adjustment_applied=False)
