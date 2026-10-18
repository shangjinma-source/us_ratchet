"""Offline LEGACY twelve-ticker prices only; no identity, schedule, fit or execution admission."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive

BASE=ROOT/'data/cache/research'
SOURCE=Path(__file__).resolve()
OUTPUT=BASE/'legacy_twelve_price_only_20260923_v1'
SCHEMA='LEGACY_TWELVE_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1'
NY_SOURCE=Path(str(files('tzdata.zoneinfo.America').joinpath('New_York'))).resolve()
NY_BYTES=NY_SOURCE.read_bytes();NY=ZoneInfo.from_file(BytesIO(NY_BYTES),key='America/New_York')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,archive.SOURCE,Path(archive.drift.__file__).resolve())}
LOADED[str(NY_SOURCE)]=hashlib.sha256(NY_BYTES).hexdigest()
OLD=('ADBE','AVGO','BKR','ENPH','FTNT','GOOG','GOOGL')
NEW=('QCOM','DDOG','ADI','TXN','TEAM')
TICKERS=tuple(sorted(OLD+NEW))
BOUND={
 'parent':('return_eight_price_only_20260923_v1/raw_assembly.json','e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'),
 'parent_final':('return_eight_price_only_20260923_v1/finalization.json','5f5714e66b906d02c33006e7b556177cd20945c0afca0a4d400df4e2073e2b9a'),
 'enph':('drawdown_four_input_assembly_20260923_v1/assembly.json','cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'),
 'benchmark':('return_six_period_benchmarks_20260923_v1/benchmarks.json','ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
}
RAW_HASHES=dict(QCOM='8a9eab309be68d1185fca2bc3ba1e48ff36d8ec617eca471df369bcea46a1fb7',DDOG='97b3eba54dc94b45bcad8be212b3901541eed8d0029ff1b91919519722741217',ADI='59fb8913d083da7c38f2307d00b49e014b573bd7a6c0ad5785f1a77d712799fb',TXN='4974473a2aac45e4b610fc8e4dc1710606bde9d98fad222513e933a16fdf8e90',TEAM='0f935128e485c06d2da223949d00409a0aa6505bd75bb97f35afc5455f2f77d7')
META_HASHES=dict(QCOM='b81b39ee8e10dcedd28a18ff143e6018a948f7404e68b4445be0d9b6eb3fea08',DDOG='512685ba20962f7ff19c12ea4e660ec0f38947070783ced9cd71240b0adee159',ADI='c3c72f8e05f5ca06b271d95689117b91f669bee502390cb6d0e72f991386a4e4',TXN='66c1612e5be97aa970ef6b5b5d560ac0067d04f5b45cc7f8f8f6155aa41d5ee9',TEAM='585d98d57dea33d6ad70e5e52add59ab6e43971e98bedb388ee7bd956c240edb')
PERIOD2=dict(QCOM=1789755207,DDOG=1789755250,ADI=1789755221,TXN=1789755231,TEAM=1789155251)
for _ticker in NEW:
    _folder='legacy_pool_remaining_split_probe_20260912_v1' if _ticker=='TEAM' else 'current79_new_asof_capture_20260919_v1'
    BOUND[_ticker+'_raw']=(_folder+'/'+_ticker+'.response.bin',RAW_HASHES[_ticker])
    BOUND[_ticker+'_meta']=(_folder+'/'+_ticker+('.metadata.json' if _ticker=='TEAM' else '.receipt.json'),META_HASHES[_ticker])
FALSE=('new_http_performed','fit_performed','execution_performed','execution_authorized','orders_generated','returns_generated',
 'security_identity_verified','continuous_identity_interval_verified','provider_binding_verified','point_in_time_verified',
 'promotion_allowed','target_schedule_built','target_schedule_validity_verified','execution_risk_chain_union_verified',
 'corporate_action_completeness_verified','dividend_cash_flows_modelled','quote_basis_independently_authenticated',
 'exchange_calendar_completeness_verified','historical_full_source_closure_verified')


def require(ok,message):
    if not ok:raise ValueError(message)


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def loads(raw,decimal=False):
    def invalid(value):raise ValueError('Nonfinite JSON token')
    return json.loads(raw,parse_float=Decimal if decimal else float,parse_constant=invalid,object_pairs_hook=unique)


def encoded(value):
    def default(value):
        if isinstance(value,Decimal):return str(value)
        raise TypeError(type(value).__name__)
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False,default=default)+'\n').encode()


def reference(role):
    path,sha=BOUND[role]
    return dict(path=str(BASE/path),sha256=sha)


def price(value,strings=False):
    require(type(value) in ((str,) if strings else (int,Decimal)),'Exact nonboolean numeric required')
    number=Decimal(value)
    require(number.is_finite() and number>0,'Positive finite value required')
    require(len(number.as_tuple().digits)<=64 and abs(number.as_tuple().exponent)<=64,'Bounded numeric required')
    return str(number)


def check_calendar(calendar):
    require(type(calendar) is list and len(calendar)==107 and calendar==sorted(set(calendar)) and
        (calendar[0],calendar[-1])==('2023-03-31','2023-09-01'),'Exact 107-session window required')
    for day in calendar:require(datetime.strptime(day,'%Y-%m-%d').date().isoformat()==day,'Canonical date required')


def day(timestamp):
    require(type(timestamp) is int,'Integer timestamp required')
    return datetime.fromtimestamp(timestamp,timezone.utc).astimezone(NY).date().isoformat()


def request_url(ticker):
    events='div%2Csplits' if ticker=='TEAM' else 'div,splits'
    return f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=1640995200&period2={PERIOD2[ticker]}&interval=1d&events={events}'


def decode(ticker,raw,metadata,calendar):
    archive.strict(LOADED);check_calendar(calendar);require(ticker in NEW,'Fixed new ticker required')
    transport=hashlib.sha256(raw).hexdigest()
    require(transport==reference(ticker+'_raw')['sha256'],'Hard raw bytes differ')
    legacy=ticker=='TEAM'
    require(metadata['http_status']==200,'Successful receipt required')
    require(metadata['response_sha256' if legacy else 'raw_sha256']==transport and
        type(metadata['response_bytes' if legacy else 'raw_bytes']) is int and
        metadata['response_bytes' if legacy else 'raw_bytes']==len(raw) and
        metadata['response_path' if legacy else 'raw_path']==reference(ticker+'_raw')['path'],'Transport receipt differs')
    request=metadata['request'] if legacy else dict(method=metadata['request_method'],credentials_sent=metadata['credentials_sent'],url=metadata['request_url'])
    require(request['method']=='GET' and request['credentials_sent'] is False and
        request['url']==metadata['final_url']==request_url(ticker),'Exact original public GET URL required')
    started,received=[datetime.fromisoformat(metadata[k]) for k in ('started_at_utc','received_at_utc')]
    require(all(t.tzinfo is not None and t.utcoffset().total_seconds()==0 for t in (started,received)) and started<=received,'Aware ordered UTC receipt required')
    if legacy:require(metadata['transport_success'] is True,'Successful transport required')
    else:
        require(metadata['ticker']==ticker and type(metadata['attempt_count']) is int and metadata['attempt_count']==1 and
            metadata['period2_utc_epoch']==PERIOD2[ticker] and int(started.timestamp())==PERIOD2[ticker] and
            metadata['completed_training_excludes_dates_on_or_after']==received.astimezone(NY).date().isoformat(),
            'Original request clock differs')
        require(metadata['promotion_allowed'] is False and metadata['historical_identity_verified'] is False,'Receipt scope upgrade')
    require(PERIOD2[ticker]<=received.timestamp() and calendar[-1]<received.astimezone(NY).date().isoformat(),'Receipt horizon differs')
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    chart=loads(decoded,decimal=True)['chart']
    require(chart['error'] is None and type(chart['result']) is list and len(chart['result'])==1,'Unique chart required')
    result=chart['result'][0];meta=result['meta']
    require(all(meta[k]==v for k,v in dict(symbol=ticker,currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d').items()),'Exact USD NY daily equity required')
    events=result.get('events',{})
    require(type(events) is dict and set(events)<= {'splits','dividends'} and events.get('splits',{})=={},'No returned splits; unknown actions blocked')
    dividends=events.get('dividends',{});require(type(dividends) is dict,'Dividend object required')
    event_rows=[];event_dates=set()
    for key,event in dividends.items():
        require(type(event) is dict and set(event)=={'date','amount'} and type(event['date']) is int and key==str(event['date']),'Exact dividend event required')
        session=day(event['date']);require(session not in event_dates,'Duplicate dividend session');event_dates.add(session)
        require(1640995200<=event['date']<PERIOD2[ticker],'Returned dividend outside request horizon')
        event_rows.append(dict(timestamp_utc=event['date'],session=session,amount=price(event['amount']),in_window=calendar[0]<=session<=calendar[-1]))
    stamps=result['timestamp'];require(type(stamps) is list and all(type(t) is int for t in stamps) and stamps==sorted(set(stamps)),'Unique ordered timestamps required')
    dates=[day(t) for t in stamps];require(len(dates)==len(set(dates)),'Duplicate NY session')
    require(all(1640995200<=t<PERIOD2[ticker] for t in stamps),'Quote outside request horizon')
    quote=result['indicators']['quote'];require(type(quote) is list and len(quote)==1,'Unique quote required');quote=quote[0]
    require(all(type(quote[k]) is list and len(quote[k])==len(stamps) for k in ('open','close')),'Quote lengths differ')
    indices=[i for i,d in enumerate(dates) if calendar[0]<=d<=calendar[-1]]
    require([dates[i] for i in indices]==calendar,'Exact benchmark calendar mismatch')
    rows=[dict(session=dates[i],timestamp_utc=stamps[i],open=price(quote['open'][i]),close=price(quote['close'][i]),factor_numerator='1',factor_denominator='1') for i in indices]
    archive.strict(LOADED)
    return dict(ticker=ticker,rows=rows,cells_checked=214,raw_reference=reference(ticker+'_raw'),metadata_reference=reference(ticker+'_meta'),
        transport_sha256=transport,decoded_sha256=hashlib.sha256(decoded).hexdigest(),transport_encoding='gzip' if raw[:2]==b'\x1f\x8b' else 'identity',
        request=deepcopy(request),received_at_utc=metadata['received_at_utc'],all_returned_raw_events=loads(encoded(events)),
        raw_events_field_present='events' in result,returned_event_counts=dict(splits=0,dividends=len(dividends)),dividend_events=sorted(event_rows,key=lambda x:x['timestamp_utc']),
        window_dividend_events=sorted([x for x in event_rows if x['in_window']],key=lambda x:x['timestamp_utc']),
        event_scope='ALL_RETURNED_EVENTS_NOT_COMPLETE_ACTION_HISTORY',adjusted_close_used=False,dividends_applied_to_quote=False,
        nominal_price_status='CONDITIONAL_NO_RETURNED_SPLITS_FACTOR_ONE_NOT_AUTHENTICATED')


def assemble(documents,raws):
    archive.strict(LOADED)
    parent,final,enph,benchmark=[documents[k] for k in ('parent','parent_final','enph','benchmark')]
    require(parent['schema']=='RETURN_EIGHT_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1' and
        enph['schema']=='DRAWDOWN_FOUR_SECURITY_107_SESSION_CONDITIONAL_INPUT_V1','Hard parent schemas differ')
    require(final['raw_reference']==reference('parent') and final['price_cell_count']==1712,'Parent finalization link differs')
    for obj in (parent,final,enph,benchmark):
        require(obj['point_in_time_verified'] is False and obj['promotion_allowed'] is False,'Parent admission upgrade')
    calendar=benchmark['calendar'];check_calendar(calendar)
    require(parent['calendar']==enph['calendar']==calendar,'Parent calendars differ')
    channels=[];matrices={kind:{d:{} for d in calendar} for kind in ('open','close')}
    for ticker in OLD:
        source=enph['price_projection'] if ticker=='ENPH' else parent
        selected=[x for x in source['channels'] if x['ticker']==ticker]
        require(len(selected)==1,'Unique inherited channel required');channel=deepcopy(selected[0])
        require([r['session'] for r in channel['rows']]==calendar and channel['cells_checked']==214,'Inherited channel denominator differs')
        for kind in matrices:
            require(set(source['matrices'][kind])==set(calendar),'Parent matrix dates differ')
            for row in channel['rows']:
                value=source['matrices'][kind][row['session']][ticker];price(value,strings=True)
                require(type(row[kind]) is str and row[kind]==value,'Parent row/matrix exact string mismatch')
                matrices[kind][row['session']][ticker]=value
        channels.append(channel)
    require(set(raws)==set(NEW),'Complete five raw denominator required')
    for ticker in NEW:
        channel=decode(ticker,raws[ticker],documents[ticker+'_meta'],calendar);channels.append(channel)
        for row in channel['rows']:
            for kind in matrices:matrices[kind][row['session']][ticker]=row[kind]
    require(all(set(row)==set(TICKERS) for matrix in matrices.values() for row in matrix.values()),'Twelve ticker denominator differs')
    return dict(schema=SCHEMA,calendar=deepcopy(calendar),tickers=list(TICKERS),ticker_count=12,session_count=107,price_cell_count=2568,
        inherited_price_cell_count=1498,new_raw_decoded_price_cell_count=1070,matrices=matrices,channels=sorted(channels,key=lambda c:c['ticker']),
        parent_references={k:reference(k) for k in BOUND},matrix_value_encoding='EXACT_DECIMAL_STRINGS',
        source_mode='SEVEN_SEALED_CHANNELS_REUSED_FIVE_HARD_RAW_CHANNELS_INDEPENDENTLY_DECODED',
        inherited_split_factors_reapplied=False,adjusted_close_used=False,nominal_price_status='CONDITIONAL_RECONSTRUCTION_NOT_AUTHENTICATED',
        calendar_status='EXACT_HARD_BENCHMARK_107_OBSERVED_SESSIONS_NOT_EXCHANGE_CERTIFICATION',
        downstream_status='IDENTITY_AND_FINAL_TARGET_SCHEDULE_NOT_BOUND_OR_VERIFIED',**dict.fromkeys(FALSE,False))


def build():
    archive.strict(LOADED);sources=dict(LOADED);documents={};raws={}
    for role in BOUND:
        ref=reference(role);content=Path(ref['path']).read_bytes()
        require(hashlib.sha256(content).hexdigest()==ref['sha256'],'Hard input bytes differ')
        archive.merge(sources,{ref['path']:ref['sha256']})
        if role.endswith('_raw'):raws[role[:-4]]=content;continue
        documents[role]=loads(content)
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in documents[role]:archive.merge(sources,documents[role][key])
    # These receipts externally pin their original started evidence; keep that edge.
    for ticker in NEW:
        if ticker=='TEAM':continue
        receipt=documents[ticker+'_meta'];p=Path(reference(ticker+'_meta')['path']).with_name(ticker+'.started.json')
        content=p.read_bytes();require(hashlib.sha256(content).hexdigest()==receipt['started_sha256'],'Started bytes differ')
        start=loads(content)
        require(all(start[k]==receipt[k] for k in start),'Started/receipt fields differ')
        archive.merge(sources,{str(p):receipt['started_sha256']})
    contract=archive.load_contract();resolution=archive.verify_expected_sources(sources,contract)
    value=assemble(documents,raws)
    archive.strict(LOADED);require(archive.verify_expected_sources(sources,contract)==resolution,'Sources drifted during assembly')
    return dict(value,historical_expected_source_hashes=sources,archive_resolution=resolution)


def publish():
    require(not OUTPUT.exists(),'Fresh fixed namespace required')
    value=build();contract=archive.load_contract()
    def guard():
        archive.strict(LOADED)
        require(archive.verify_expected_sources(value['historical_expected_source_hashes'],contract)==value['archive_resolution'],'Publication source drift')
    guard();OUTPUT.mkdir(parents=True,exist_ok=False);path=OUTPUT/'prices.json';raw=encoded(value)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard();require(path.read_bytes()==raw and {p.name for p in OUTPUT.iterdir()}=={'prices.json'},'Publication bytes/directory differ')
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    if args.publish:print(json.dumps(publish()))
    else:print(json.dumps(dict(schema=SCHEMA,publication_requested=False,output=str(OUTPUT),**dict.fromkeys(FALSE,False))))
