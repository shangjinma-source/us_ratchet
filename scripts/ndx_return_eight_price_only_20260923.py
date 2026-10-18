"""Eight sealed ticker channels, 107 observed sessions; conditional price reconstruction only."""
import argparse
import gzip
import hashlib
import json
import os
import sys
from io import BytesIO
from importlib.resources import files
from datetime import datetime, date
from decimal import Decimal, Context, localcontext
from fractions import Fraction
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE=ROOT/'data/cache/research'
NY_SOURCE=Path(str(files('tzdata.zoneinfo.America').joinpath('New_York'))).resolve()
NY_BYTES=NY_SOURCE.read_bytes()
NY=ZoneInfo.from_file(BytesIO(NY_BYTES),key='America/New_York')
CALENDAR=BASE/'corrected_explicit_path_20260919_v1/calendar.json'
CALENDAR_SHA='57ac5d3187c656694a5351fda4cde7ce4331f9e471bcfc8881930c8b9984fa1c'
HASHES=dict(AMAT='37af86d8a7d6f4cc2d6c6a0e22b2ac84c9fd3695bb9f8bdfdfe8ffa9123fe50b',
 AVGO='8851ad1efe647afb59c62f5cc8845448d17e3f28d898de321ad216fdad1f018a',
 BKR='596508af4b88d009ab687b297bdbc9b1f782a5a2eaaeaf24e5bef7c7b5bc682b',
 CDNS='266128aa22c917dc8588e18282695101608383c71d1245ec150e7461bca905e3',
 FTNT='8827ade2f5cf2081086892f57b079a3c115b931829746e090db0baa083e82166',
 GOOG='b09abf53841453aacfbd12ff86d361316899efc8fbce3c9f04dc86203fbb0480',
 ADBE='25ea498f59c693a4d983321f08046a21c8fc05b12dc7d6b06b7c7e2691269daa',
 GOOGL='300b8ea27094a7355aac8ed03e54d5fc555e2058c966f8c7bea1d9c2d267fd4f')
PATHS={t:BASE/f'current101_conditional_prices_20260919_v1/{t}.json' for t in HASHES}
BASIS='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS'
EXPECTED_EVENTS={'AVGO':[('2024-07-15',Fraction(10))],'FTNT':[('2022-06-23',Fraction(5))],
 'GOOG':[('2022-07-18',Fraction(20))],'GOOGL':[('2022-07-18',Fraction(20))]}
FLAGS=('security_identity_verified','point_in_time_verified','promotion_allowed','execution_authorized','orders_generated',
 'fit_performed','returns_generated','corporate_action_completeness_verified','dividend_cash_flows_modelled',
 'quote_basis_independently_authenticated','exchange_calendar_completeness_verified','historical_full_source_closure_verified')
SOURCE=Path(__file__).resolve()
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),str(NY_SOURCE):hashlib.sha256(NY_BYTES).hexdigest()}
PARENT=BASE/'dynamic_frozen_v2/preference_retrospective_accounting_20260912.json'
PARENT_SHA='3b0fd632ba5c53839b90199d7edf74dafdc73bdc9b3369d09bef24fdae177e59'
OUTPUT=BASE/'return_eight_price_only_20260923_v1'
SCHEMA='RETURN_EIGHT_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1'


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result


def loads(raw):
    def invalid(value):
        raise ValueError('Nonfinite JSON number: '+value)
    return json.loads(raw,parse_float=Decimal,parse_constant=invalid,object_pairs_hook=unique)


def encoded(value):
    # Decimal strings retain original base-ten prices without a float roundtrip.
    return (json.dumps(value,sort_keys=True,indent=2,default=lambda x:str(x) if isinstance(x,Decimal) else (_ for _ in ()).throw(TypeError(type(x).__name__)))+'\n').encode()


def verify_sources(sources):
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Source drift: '+path)


def canonical(value):
    return loads(encoded(value))


def positive(value):
    if type(value) not in (int,float,Decimal):raise ValueError('Positive nonboolean numeric required')
    value=Decimal(str(value))
    if not value.is_finite() or value<=0:raise ValueError('Positive finite numeric required')
    if len(value.as_tuple().digits)>64 or abs(value.as_tuple().exponent)>64:raise ValueError('Numeric precision/range exceeds bounded price contract')
    return value


def day(stamp):
    if type(stamp) is not int:raise ValueError('Integer epoch required')
    return datetime.fromtimestamp(stamp,NY).date().isoformat()


def inspect_channel(*,ticker,raw,raw_sha256,request,received_at_utc,calendar,rows,basis):
    """Independent scalar arithmetic; never calls a producer/guard/reconstruction function."""
    if ticker not in HASHES or basis!=BASIS:raise ValueError('Explicit supported ticker and conditional basis required')
    if len(calendar)!=107 or calendar!=sorted(set(calendar)) or calendar[0]!='2023-03-31' or calendar[-1]!='2023-09-01':raise ValueError('Exact 107-session bounded calendar required')
    if hashlib.sha256(raw).hexdigest()!=raw_sha256:raise ValueError('Original compressed bytes differ')
    url=urlparse(request['url']);query=parse_qs(url.query,keep_blank_values=True)
    if request['method']!='GET' or request['credentials_sent'] is not False or url.scheme!='https' or url.netloc!='query1.finance.yahoo.com' or url.path!='/v8/finance/chart/'+ticker or url.fragment or set(query)!={'period1','period2','events','interval'} or query['events']!=['div,splits'] or query['interval']!=['1d'] or any(len(query[k])!=1 or not query[k][0].isdigit() for k in ('period1','period2')):raise ValueError('Original public daily request differs')
    start,end=(int(query[k][0]) for k in ('period1','period2'));received=datetime.fromisoformat(received_at_utc)
    if received.tzinfo is None or received.utcoffset().total_seconds()!=0 or not start<end<=received.timestamp() or day(end)!=received.astimezone(NY).date().isoformat() or day(start)>calendar[0] or day(end)<=calendar[-1]:raise ValueError('Full receipt-day event horizon required')
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    obj=loads(decoded);chart=obj['chart']
    if chart['error'] is not None or len(chart['result'])!=1:raise ValueError('Unique successful chart required')
    data=chart['result'][0];meta=data['meta']
    if meta['symbol']!=ticker or meta['currency']!='USD' or meta['instrumentType']!='EQUITY' or meta['exchangeTimezoneName']!='America/New_York' or meta['dataGranularity']!='1d':raise ValueError('Raw channel coordinates differ')
    times=data['timestamp'];dates=[day(t) for t in times]
    if dates!=sorted(set(dates)) or any(not start<=t<end for t in times) or [d for d in dates if calendar[0]<=d<=calendar[-1]]!=calendar:raise ValueError('Missing/duplicate/out-of-horizon quote sessions')
    quote,=data['indicators']['quote']
    if any(len(quote[k])!=len(times) for k in ('open','close')):raise ValueError('Quote array dimensions differ')
    events=data.get('events',{})
    if type(events) is not dict or set(events)-{'splits','dividends'}:raise ValueError('Unsupported complex event channel')
    splits=[]
    for kind,group in events.items():
        if type(group) is not dict:raise ValueError('Original event map required')
        for key,event in group.items():
            stamp=event['date'];date=day(stamp)
            if str(stamp)!=key or not start<=stamp<end:raise ValueError('Event key/horizon differs')
            if kind=='dividends':positive(event['amount']);continue
            ratio=Fraction(positive(event['numerator']))/Fraction(positive(event['denominator']))
            parts=event['splitRatio'].split(':')
            if len(parts)!=2 or Fraction(positive(Decimal(parts[0])))/Fraction(positive(Decimal(parts[1])))!=ratio or date not in dates:raise ValueError('Split ratio/date contradiction')
            if calendar[0]<=date<=calendar[-1]:raise ValueError('Window action cannot enter PRICE_ONLY action-free interval')
            splits.append((date,ratio))
    if sorted(splits)!=EXPECTED_EVENTS.get(ticker,[]):raise ValueError('Unmatched/duplicate/complex returned split-like event')
    bounded=[r for r in rows if calendar[0]<=r['session']<=calendar[-1]]
    if [r['session'] for r in bounded]!=calendar:raise ValueError('Sealed quote window denominator differs')
    maximum=Decimal(0);output=[]
    with localcontext(Context(prec=160)) as context:
        for date,saved in zip(calendar,bounded):
            factor=Fraction(1);later=[]
            for event,ratio in splits:
                if event>date:factor*=ratio;later.append(event)
            if saved['ticker']!=ticker or saved['currency']!='USD' or saved['provider_timestamp']!=times[dates.index(date)] or type(saved['provider_timestamp']) is not int or positive(saved['split_factor'])!=Decimal(factor.numerator)/factor.denominator or saved['split_factor_numerator']!=str(factor.numerator) or saved['split_factor_denominator']!=str(factor.denominator) or saved['later_split_effective_sessions']!=later:raise ValueError('Saved factor/identity/receipt row differs')
            out={'session':date,'factor_numerator':str(factor.numerator),'factor_denominator':str(factor.denominator),'later_split_effective_sessions':later}
            for field in ('open','close'):
                observed=positive(quote[field][dates.index(date)]);nominal=observed*factor.numerator/factor.denominator
                error=max(abs(positive(saved['quote_'+field])-observed),abs(positive(saved['nominal_'+field])-nominal));maximum=max(maximum,error)
                if error>Decimal('1e-10'):raise ValueError('Independent Decimal nominal/quote mismatch')
                out[field]=str(nominal)
            output.append(out)
    return dict(ticker=ticker,rows=output,cells_checked=214,maximum_absolute_decimal_error=str(maximum),raw_sha256=raw_sha256,
        decoded_sha256=hashlib.sha256(decoded).hexdigest(),request=request,received_at_utc=received_at_utc,
        all_returned_raw_events=events,
        returned_event_counts={k:len(events.get(k,{})) for k in ('splits','dividends')},
        window_event_counts={k:sum(calendar[0]<=day(e['date'])<=calendar[-1] for e in events.get(k,{}).values()) for k in ('splits','dividends')},
        event_scope='ALL_RAW_RETURNED_EVENT_OBJECTS_NOT_COMPLETE_ACTION_HISTORY',quote_field_basis=basis)


def build():
    """Read pinned observations only. Does not publish, fetch, fit or run an account."""
    verify_sources(LOADED)
    sources=dict(LOADED)
    def read(path,sha,decode=True):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Hard source mismatch: '+path)
        if path in sources and sources[path]!=sha:raise ValueError('Conflicting source hash')
        sources[path]=sha
        return loads(raw) if decode else raw
    envelope=read(CALENDAR,CALENDAR_SHA)
    if envelope['source']!={'path':str(PARENT),'sha256':PARENT_SHA}:raise ValueError('Calendar parent reference differs')
    parent=read(PARENT,PARENT_SHA)
    full=envelope['calendar']
    if full!=[r['session'] for r in parent['execution']['daily']] or full!=sorted(set(full)) or any(type(d) is not str or date.fromisoformat(d).isoformat()!=d for d in full):raise ValueError('Complete observed calendar differs')
    calendar=[d for d in full if '2023-03-31'<=d<='2023-09-01']
    if len(calendar)!=107:raise ValueError('Observed 107-day denominator differs')
    channels=[]
    for ticker in sorted(HASHES):
        doc=read(PATHS[ticker],HASHES[ticker]);result=doc['result'];reconstruction=result['reconstruction']
        if doc['ticker']!=ticker or doc['status']!='CONDITIONAL_PRICE_NOT_IDENTITY' or any(doc[k] is not False for k in ('point_in_time_verified','price_identity_verified','promotion_allowed','returns_generated','training_performed')):raise ValueError('Conditional source scope differs')
        rawpath=Path(doc['raw_path']);rawsha=doc['raw_sha256']
        if reconstruction['quote_field_basis']!=BASIS or reconstruction['dividends_applied_to_quote'] is not False or reconstruction['adjclose_used'] is not False:raise ValueError('Reconstruction contract differs')
        channel=inspect_channel(ticker=ticker,raw=read(rawpath,rawsha,False),raw_sha256=rawsha,
            request=result['original_request'],received_at_utc=result['original_received_at_utc'],
            calendar=calendar,rows=reconstruction['rows'],basis=result['conditional_quote_basis'])
        if channel['decoded_sha256']!=reconstruction['raw_sha256']:raise ValueError('Decoded reconstruction SHA differs')
        channel.update(raw_path=str(rawpath.resolve()),sealed_quote_reference={'path':str(PATHS[ticker]),'sha256':HASHES[ticker]})
        channels.append(channel)
    matrices={kind:{day:{c['ticker']:c['rows'][i][kind] for c in channels} for i,day in enumerate(calendar)} for kind in ('open','close')}
    value=dict(schema=SCHEMA,calendar=calendar,tickers=sorted(HASHES),matrices=matrices,channels=channels,
        ticker_count=8,session_count=107,price_cell_count=1712,source_hashes=sources,
        source_mode='SEALED_CONDITIONAL_QUOTES_INDEPENDENT_RAW_DECIMAL',
        nominal_price_status='CONDITIONAL_RECONSTRUCTION_NOT_AUTHENTICATED',
        matrix_value_encoding='EXACT_RAW_DECIMAL_TIMES_DECLARED_LATER_SPLIT_FACTOR_AS_DECIMAL_STRING',
        event_denominator='ALL_RETURNED_SPLITS_AND_DIVIDENDS_OVER_ORIGINAL_REQUEST_HORIZON; WINDOW_COUNTS_SEPARATE; NO_COMPLETENESS_CLAIM',
        calendar_status='HARD_PINNED_COMPLETE_OBSERVED_PARENT_CALENDAR_NOT_EXCHANGE_CERTIFICATION',
        **dict.fromkeys(FLAGS,False))
    verify_sources(sources)
    return canonical(value)


def verify(value):
    """Replay all 1,712 cells and event denominators from pinned original bytes."""
    expected=build()
    if canonical(value)!=expected:raise ValueError('Artifact differs from independent raw reconstruction')
    return expected


def publish(path,value,sources):
    verify_sources(sources)
    raw=encoded(value)
    with Path(path).open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if Path(path).read_bytes()!=raw:raise ValueError('Published bytes differ')
    verify_sources(sources)
    return {'path':str(Path(path).resolve()),'sha256':hashlib.sha256(raw).hexdigest()}


def run(output=OUTPUT):
    output=Path(output)
    if output.exists():raise ValueError('Single-attempt output namespace already exists')
    verify_sources(LOADED)
    output.mkdir(parents=True,exist_ok=False)
    started=publish(output/'started.json',{'schema':SCHEMA+'_STARTED','loaded_sources':LOADED},LOADED)
    value=build()
    sources=dict(value['source_hashes']);sources[started['path']]=started['sha256']
    raw=publish(output/'raw_assembly.json',value,sources)
    sources[raw['path']]=raw['sha256']
    final=publish(output/'finalization.json',{'schema':SCHEMA+'_FINAL','status':'CONDITIONAL_RAW_PRICE_RECONSTRUCTION_PASSED',
        'started_reference':started,'raw_reference':raw,'source_hashes':sources,
        'price_cell_count':1712,**dict.fromkeys(FLAGS,False)},sources)
    verify_sources(dict(sources,**{final['path']:final['sha256']}))
    return final


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(OUTPUT))
    parser.add_argument('--verify',help='Read-only raw_assembly.json verification; requires external SHA')
    parser.add_argument('--expected-sha256')
    args=parser.parse_args()
    if args.verify:
        data=Path(args.verify).read_bytes()
        if not args.expected_sha256 or hashlib.sha256(data).hexdigest()!=args.expected_sha256:raise ValueError('External artifact SHA required')
        verify(loads(data))
        if Path(args.verify).read_bytes()!=data:raise ValueError('Artifact drift during readback')
        print('CONDITIONAL_RAW_PRICE_READBACK_PASSED')
    else:
        if args.expected_sha256:raise ValueError('Unexpected verification SHA')
        print(json.dumps(run(args.output)))

