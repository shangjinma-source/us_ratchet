"""ENPH conditional factor-one O/C for 21 observed sessions; no provider identity claim."""
import argparse,gzip,hashlib,json,sys
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research';FOLDER=BASE/'legacy_pool_remaining_split_probe_20260912_v1'
CALENDAR=BASE/'corrected_explicit_path_20260919_v1/calendar.json';CALENDAR_SHA='57ac5d3187c656694a5351fda4cde7ce4331f9e471bcfc8881930c8b9984fa1c'
REPORT=FOLDER/'report.json';REPORT_SHA='b3b7d00fc7f8698d4bf7d10783277b2203962a9ae20324c0462b889a87baff7d'
RAW=FOLDER/'ENPH.response.bin';RAW_SHA='9674ec83b89380b9f22fccb864d5e61bb3b9f270ee93b69a0b75f2250054c45f'
META=FOLDER/'ENPH.metadata.json';META_SHA='e0b7eb2e6e26b63f51f7ccc675217b87b41dd5e60d25313aa37322eb8adff0ce'
START='2023-03-31';END='2023-05-01';NY=ZoneInfo('America/New_York')
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,Path(publish.__code__.co_filename).resolve())}
FLAGS=('provider_security_identity_verified','price_basis_independently_authenticated','corporate_action_completeness_verified','calendar_exchange_completeness_verified','historical_full_source_closure_verified','dividend_cash_flows_simulated','training_returns_generated','fit_performed','orders_generated','execution_authorized','point_in_time_verified','promotion_allowed')


def unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('Duplicate JSON key')
        out[k]=v
    return out


def day(stamp):
    if type(stamp) is not int:raise ValueError('Integer provider timestamp required')
    return datetime.fromtimestamp(stamp,NY).date().isoformat()


def positive(value):
    if type(value) not in (int,float,Decimal):raise ValueError('Positive nonboolean quote required')
    d=Decimal(str(value))
    if not d.is_finite() or d<=0:raise ValueError('Positive finite quote required')
    return d


def calculate(raw,metadata,calendar):
    if len(calendar)!=21 or calendar!=sorted(set(calendar)) or calendar[0]!=START or calendar[-1]!=END:raise ValueError('Exact bounded 21-session calendar required')
    if hashlib.sha256(raw).hexdigest()!=metadata['response_sha256'] or metadata['response_bytes']!=len(raw) or metadata['http_status']!=200 or metadata['transport_success'] is not True:raise ValueError('Successful original raw binding required')
    req=metadata['request'];url=urlparse(req['url']);q=parse_qs(url.query,keep_blank_values=True)
    if req['method']!='GET' or req['credentials_sent'] is not False or url.scheme!='https' or url.netloc!='query1.finance.yahoo.com' or url.path!='/v8/finance/chart/ENPH' or set(q)!={'period1','period2','interval','events'} or q['interval']!=['1d'] or q['events']!=['div,splits'] or any(len(q[k])!=1 or not q[k][0].isdigit() for k in ('period1','period2')):raise ValueError('Exact original daily event request required')
    begin=int(q['period1'][0]);end=int(q['period2'][0]);started=datetime.fromisoformat(metadata['started_at_utc']);received=datetime.fromisoformat(metadata['received_at_utc'])
    if any(t.tzinfo is None or t.utcoffset()!=timedelta(0) for t in (started,received)) or received<started or begin!=1640995200 or end!=int(started.timestamp()) or end>received.timestamp() or day(end)!=received.astimezone(NY).date().isoformat() or END>=day(end):raise ValueError('Original receipt/event horizon differs')
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    obj=json.loads(decoded,object_pairs_hook=unique,parse_float=Decimal)
    if obj['chart']['error'] is not None or len(obj['chart']['result'])!=1:raise ValueError('Single successful chart required')
    data=obj['chart']['result'][0];meta=data['meta']
    if meta['symbol']!='ENPH' or meta['currency']!='USD' or meta['exchangeTimezoneName']!='America/New_York' or meta['instrumentType']!='EQUITY':raise ValueError('Observed ENPH US equity channel required')
    events=data.get('events',{})
    if set(events)-{'splits','dividends'} or events.get('splits',{}):raise ValueError('Bound factor-one zero returned split channel only')
    for name,group in events.items():
        if type(group) is not dict:raise ValueError('Original event mapping required')
        for key,event in group.items():
            stamp=event['date']
            if type(stamp) is not int or str(stamp)!=key or not begin<=stamp<=end:raise ValueError('Original event horizon/key differs')
            if name=='dividends':positive(event['amount'])
    times=data['timestamp'];dates=[day(t) for t in times]
    if dates!=sorted(set(dates)) or any(t<begin or t>end for t in times):raise ValueError('Unique original observation date/horizon required')
    if [d for d in dates if START<=d<=END]!=calendar:raise ValueError('No missing/extra bounded observed sessions allowed')
    quote,=data['indicators']['quote']
    if any(len(quote[k])!=len(times) for k in ('open','close')):raise ValueError('Complete original quote dimensions required')
    rows=[];maximum=Decimal(0)
    for d in calendar:
        i=dates.index(d);row=dict(ticker='ENPH',session=d,currency='USD',provider_timestamp=times[i],split_factor=1,split_factor_numerator='1',split_factor_denominator='1',later_split_effective_sessions=[])
        for field in ('open','close'):
            value=positive(quote[field][i]);out=float(value)
            error=abs(Decimal(str(out))-value);maximum=max(maximum,error)
            if error>Decimal('1e-12'):raise ValueError('Independent Decimal output serialization differs')
            row['quote_'+field]=out;row['nominal_'+field]=out
        rows.append(row)
    return dict(rows=rows,calendar=calendar,row_count=21,quote_field_basis='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS',nominal_basis_status='CONDITIONAL_FACTOR_ONE_NO_RETURNED_SPLIT',received_at_utc=metadata['received_at_utc'],excluded_on_or_after=day(end),decoded_sha256=hashlib.sha256(decoded).hexdigest(),returned_events=json.loads(decoded,object_pairs_hook=unique)['chart']['result'][0].get('events',{}),full_provider_observed_session_count=len(dates),decimal_open_close_count=42,maximum_decimal_serialization_error=str(maximum))


def build():
    sources=dict(LOADED)
    def read(path,sha,decode=True):
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Hard evidence bytes differ')
        archive.merge(sources,{str(path):sha});return json.loads(raw,object_pairs_hook=unique) if decode else raw
    report=read(REPORT,REPORT_SHA);metadata=read(META,META_SHA);calendar=read(CALENDAR,CALENDAR_SHA)
    archive.merge(sources,report['source_hashes']);ref=calendar['source'];upstream=read(Path(ref['path']),ref['sha256'])
    for key in ('source_hashes','historical_expected_source_hashes'):
        if key in upstream:archive.merge(sources,upstream[key])
    probe,=[r for r in report['probes'] if r['name']=='yahoo_enph_remaining_old_pool']
    if probe!=metadata or metadata['response_path']!=str(RAW) or metadata['response_sha256']!=RAW_SHA:raise ValueError('Hard report/metadata/raw chain differs')
    full=calendar['calendar']
    if full!=sorted(set(full)):raise ValueError('Original calendar order differs')
    days=[d for d in full if START<=d<=END];raw=read(RAW,RAW_SHA,False)
    contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    result=calculate(raw,metadata,days)
    value=dict(schema='ENPH_BOUNDED_CONDITIONAL_NOMINAL_QUOTE_V1',ticker='ENPH',start=START,end=END,result=result,historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),identity_coordinate_assigned=False,receipt_backdated=False,**dict.fromkeys(FLAGS,False))
    verify(value);return value


def verify(value):
    required=dict(LOADED,**{str(CALENDAR):CALENDAR_SHA,str(REPORT):REPORT_SHA,str(META):META_SHA,str(RAW):RAW_SHA})
    if value['schema']!='ENPH_BOUNDED_CONDITIONAL_NOMINAL_QUOTE_V1' or any(value[k] is not False for k in FLAGS+('identity_coordinate_assigned','receipt_backdated')):raise ValueError('Conditional bounded scope differs')
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Required evidence omitted')
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition differs')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();value=build();verify(value);saved=publish(args.output,value);verify(value);print(json.dumps(saved))
