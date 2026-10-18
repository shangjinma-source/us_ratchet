"""Seven sealed ticker channels, 21 sessions: independent raw Decimal price audit only."""
import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research';NY=ZoneInfo('America/New_York')
CALENDAR=BASE/'corrected_explicit_path_20260919_v1/calendar.json'
CALENDAR_SHA='57ac5d3187c656694a5351fda4cde7ce4331f9e471bcfc8881930c8b9984fa1c'
HASHES=dict(AMAT='37af86d8a7d6f4cc2d6c6a0e22b2ac84c9fd3695bb9f8bdfdfe8ffa9123fe50b',
 AVGO='8851ad1efe647afb59c62f5cc8845448d17e3f28d898de321ad216fdad1f018a',
 BKR='596508af4b88d009ab687b297bdbc9b1f782a5a2eaaeaf24e5bef7c7b5bc682b',
 CDNS='266128aa22c917dc8588e18282695101608383c71d1245ec150e7461bca905e3',
 FTNT='8827ade2f5cf2081086892f57b079a3c115b931829746e090db0baa083e82166',
 ADI='669e09dfad56e2a75065563f6de9ed436956940dd2e97965b6ca364f8c1b93aa',
 ENPH='8345c6fb971f3ef9b22ca9477a57ece9ab35b98a4dc7b7a84ae285142479cc84')
PATHS={t:BASE/(f'current101_conditional_prices_20260919_v1/{t}.json' if t!='ENPH' else 'enph_bounded_nominal_quote_20260919_v1/quote.json') for t in HASHES}
BASIS='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS'
EXPECTED_EVENTS={'AVGO':[('2024-07-15',Fraction(10))],'FTNT':[('2022-06-23',Fraction(5))]}
FLAGS=('security_identity_verified','point_in_time_verified','promotion_allowed','execution_authorized','orders_generated',
 'fit_performed','returns_generated','corporate_action_completeness_verified','dividend_cash_flows_modelled',
 'quote_basis_independently_authenticated','exchange_calendar_completeness_verified','historical_full_source_closure_verified')
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,Path(publish.__code__.co_filename).resolve())}


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result


def positive(value):
    if type(value) not in (int,float,Decimal):raise ValueError('Positive nonboolean numeric required')
    value=Decimal(str(value))
    if not value.is_finite() or value<=0:raise ValueError('Positive finite numeric required')
    return value


def day(stamp):
    if type(stamp) is not int:raise ValueError('Integer epoch required')
    return datetime.fromtimestamp(stamp,NY).date().isoformat()


def inspect_channel(*,ticker,raw,raw_sha256,request,received_at_utc,calendar,rows,basis):
    """Independent scalar arithmetic; never calls a producer/guard/reconstruction function."""
    if ticker not in HASHES or basis!=BASIS:raise ValueError('Explicit supported ticker and conditional basis required')
    if len(calendar)!=21 or calendar!=sorted(set(calendar)) or calendar[0]!='2023-03-31' or calendar[-1]!='2023-05-01':raise ValueError('Exact 21-session bounded calendar required')
    if hashlib.sha256(raw).hexdigest()!=raw_sha256:raise ValueError('Original compressed bytes differ')
    url=urlparse(request['url']);query=parse_qs(url.query,keep_blank_values=True)
    if request['method']!='GET' or request['credentials_sent'] is not False or url.scheme!='https' or url.netloc!='query1.finance.yahoo.com' or url.path!='/v8/finance/chart/'+ticker or url.fragment or set(query)!={'period1','period2','events','interval'} or query['events']!=['div,splits'] or query['interval']!=['1d'] or any(len(query[k])!=1 or not query[k][0].isdigit() for k in ('period1','period2')):raise ValueError('Original public daily request differs')
    start,end=(int(query[k][0]) for k in ('period1','period2'));received=datetime.fromisoformat(received_at_utc)
    if received.tzinfo is None or received.utcoffset().total_seconds()!=0 or not start<end<=received.timestamp() or day(end)!=received.astimezone(NY).date().isoformat() or day(start)>calendar[0] or day(end)<=calendar[-1]:raise ValueError('Full receipt-day event horizon required')
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    obj=json.loads(decoded,parse_float=Decimal,object_pairs_hook=unique);chart=obj['chart']
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
    with localcontext() as context:
        context.prec=50
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
                out[field]=saved['nominal_'+field]
            output.append(out)
    return dict(ticker=ticker,rows=output,cells_checked=42,maximum_absolute_decimal_error=str(maximum),raw_sha256=raw_sha256,
        decoded_sha256=hashlib.sha256(decoded).hexdigest(),request=request,received_at_utc=received_at_utc,
        all_returned_raw_events=json.loads(decoded,object_pairs_hook=unique)['chart']['result'][0].get('events',{}),
        event_scope='ALL_RAW_RETURNED_EVENT_OBJECTS_NOT_COMPLETE_ACTION_HISTORY',quote_field_basis=basis)


def build():
    sources=dict(LOADED)
    def read(path,sha,decode=True):
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Hard source mismatch')
        archive.merge(sources,{str(Path(path).resolve()):sha});return json.loads(raw,object_pairs_hook=unique) if decode else raw
    envelope=read(CALENDAR,CALENDAR_SHA);calendar=[d for d in envelope['calendar'] if '2023-03-31'<=d<='2023-05-01']
    parent=read(envelope['source']['path'],envelope['source']['sha256'])
    for key in ('source_hashes','historical_expected_source_hashes'):
        if key in parent:archive.merge(sources,parent[key])
    channels=[]
    for ticker in sorted(HASHES):
        doc=read(PATHS[ticker],HASHES[ticker]);result=doc['result']
        if ticker=='ENPH':
            if doc['schema']!='ENPH_BOUNDED_CONDITIONAL_NOMINAL_QUOTE_V1' or doc['identity_coordinate_assigned'] is not False:raise ValueError('ENPH price-only schema differs')
            archive.merge(sources,doc['historical_expected_source_hashes'])
            rawpath=BASE/'legacy_pool_remaining_split_probe_20260912_v1/ENPH.response.bin';metapath=rawpath.with_name('ENPH.metadata.json')
            metadata=read(metapath,sources[str(metapath)]);rawsha=metadata['response_sha256'];request=metadata['request'];receipt=metadata['received_at_utc'];rows=result['rows'];basis=result['quote_field_basis']
        else:
            if doc['ticker']!=ticker or doc['status']!='CONDITIONAL_PRICE_NOT_IDENTITY' or any(doc[k] is not False for k in ('point_in_time_verified','price_identity_verified','promotion_allowed','returns_generated','training_performed')):raise ValueError('Sealed conditional channel scope differs')
            archive.merge(sources,result['historical_expected_source_hashes']);rawpath=Path(doc['raw_path']);rawsha=doc['raw_sha256'];request=result['original_request'];receipt=result['original_received_at_utc'];rows=result['reconstruction']['rows'];basis=result['conditional_quote_basis']
        raw=read(rawpath,rawsha,False)
        channel=inspect_channel(ticker=ticker,raw=raw,raw_sha256=rawsha,request=request,received_at_utc=receipt,calendar=calendar,rows=rows,basis=basis)
        channel.update(raw_path=str(rawpath),sealed_quote_reference={'path':str(PATHS[ticker]),'sha256':HASHES[ticker]});channels.append(channel)
    contract=archive.load_contract();resolution=archive.verify_expected_sources(sources,contract)
    matrices={kind:{date:{c['ticker']:c['rows'][i][kind] for c in channels} for i,date in enumerate(calendar)} for kind in ('open','close')}
    value=dict(schema='SEVEN_TICKER_21_SESSION_PRICE_ONLY_V1',calendar=calendar,tickers=sorted(HASHES),matrices=matrices,channels=channels,
        ticker_count=7,session_count=21,price_cell_count=294,source_mode='SEALED_CONDITIONAL_QUOTES_INDEPENDENT_RAW_DECIMAL',
        historical_expected_source_hashes=sources,archive_resolution=resolution,**dict.fromkeys(FLAGS,False))
    verify(value);return value


def verify(value):
    required=dict(LOADED,**{str(CALENDAR):CALENDAR_SHA},**{str(PATHS[t]):h for t,h in HASHES.items()})
    if value['schema']!='SEVEN_TICKER_21_SESSION_PRICE_ONLY_V1' or any(value[k] is not False for k in FLAGS):raise ValueError('PRICE_ONLY scope differs')
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Required source omitted')
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition changed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    value=build();verify(value);saved=publish(args.output,value);verify(value);print(json.dumps(saved))
