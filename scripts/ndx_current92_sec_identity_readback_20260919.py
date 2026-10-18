"""Hard captured current SEC issuer observations; no historical price identity claims."""
from datetime import datetime,timedelta
import gzip,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_current92_sec_identity_research as core
from scripts import ndx_current_nine_identity_readback_20260919 as nine
BASE=ROOT/'data/cache/research';FOLDER=BASE/'current_92_sec_submissions_capture_20260919_v1'
MANIFEST=FOLDER/'manifest.json';MANIFEST_SHA='dd7e767031ad6902944d6a540c63e901319d7bca4cc20cfb34f6d2e2b46bf743'
MAP=BASE/'current101_conditional_issuer_map_20260919_v1/issuer_map.json';MAP_SHA='491a46b575cff58df7c53886a47d1325c2184dcd033b2b357928678d92143890'
OLD=BASE/'current_nine_identity_capture_20260919_v1/current_identity_facts.json';OLD_SHA='33eb7055e9072431def42f0a9fa88a0f03c245efd8664844c620955ca576fa32'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(core.__file__).resolve(),Path(nine.__file__).resolve())}


def build():
    sources=dict(LOADED);manifest=nine.read(MANIFEST,MANIFEST_SHA,sources);mapping=nine.read(MAP,MAP_SHA,sources);old=nine.read(OLD,OLD_SHA,sources)
    for doc in (manifest,mapping,old):nine.merge(sources,doc['source_hashes'])
    expected=core.expected_refresh(mapping)
    if manifest['schema']!='CURRENT_92_SEC_SUBMISSIONS_RAW_CAPTURE_V1' or Path(manifest['plan_path'])!=FOLDER/'plan.json':raise ValueError('Original capture schema/address differs')
    plan=nine.read(manifest['plan_path'],manifest['plan_sha256'],sources);nine.merge(sources,plan['source_hashes'])
    if (plan['schema']!='CURRENT_92_SEC_SUBMISSIONS_QUERY_PLAN_V1' or plan['rows']!=[dict(ticker=t,candidate_cik=c) for t,c in expected.items()] or
        plan['query_ciks']!=sorted(set(expected.values())) or [c['name'] for c in manifest['captures']]!=plan['query_ciks']):raise ValueError('Exact 91 planned captures required')
    decoded={};references={}
    for capture in manifest['captures']:
        cik=capture['name'];url='https://data.sec.gov/submissions/CIK'+cik+'.json'
        if (capture['request_url']!=url or capture['final_url']!=url or capture['request_method']!='GET' or capture['credentials_sent'] is not False or
            type(capture['attempt_count']) is not int or capture['attempt_count']!=1 or type(capture['http_status']) is not int or capture['http_status']!=200 or
            capture.get('error_type') is not None or Path(capture['raw_path'])!=FOLDER/(cik+'.response.bin')):raise ValueError('Original successful SEC request coordinate differs')
        start=datetime.fromisoformat(capture['started_at_utc']);received=datetime.fromisoformat(capture['received_at_utc'])
        if any(v.tzinfo is None or v.utcoffset()!=timedelta(0) for v in (start,received)) or received<start:raise ValueError('Original UTC receipt differs')
        raw=Path(capture['raw_path']).read_bytes();encoding=capture['response_headers'].get('Content-Encoding')
        if hashlib.sha256(raw).hexdigest()!=capture['raw_sha256'] or len(raw)!=capture['raw_bytes'] or encoding not in (None,'','identity','gzip'):raise ValueError('Original raw binding/encoding differs')
        body=gzip.decompress(raw) if encoding=='gzip' or raw[:2]==b'\x1f\x8b' else raw
        if hashlib.sha256(body).hexdigest()!=capture['decoded_sha256']:raise ValueError('Decoded original body differs')
        nine.merge(sources,{capture['raw_path']:capture['raw_sha256']});decoded[cik]=body
        references[cik]=dict(request_url=url,raw_path=capture['raw_path'],raw_sha256=capture['raw_sha256'],decoded_sha256=capture['decoded_sha256'],received_at_utc=capture['received_at_utc'])
    refreshed=core.refresh_identity_rows(mapping,decoded)
    for fact in refreshed['candidate_facts'].values():fact.update(references[fact['reported_cik']])
    refreshed.update(schema='CURRENT92_REFRESHED_SEC_ISSUER_OBSERVATIONS_BOUND_V1',input_artifact_binding_verified=True,source_is_sec_submissions_http_verified=True)
    if old!=nine.build():raise ValueError('Original nine facts no longer reproduce')
    by_ticker={r['ticker']:dict(r,evidence_cohort='NEW_91_CIK_CAPTURE_92_TICKERS') for r in refreshed['rows']}
    for row in old['rows']:
        if row['ticker'] in by_ticker:raise ValueError('Old nine were requested again')
        by_ticker[row['ticker']]=dict(row,conditional_issuer_id='issuer:'+row['current_reported_cik'],evidence_cohort='PREEXISTING_11_CIK_CAPTURE_9_TICKERS')
    rows=[by_ticker[r['ticker']] for r in mapping['rows']]
    if len(rows)!=101 or len(by_ticker)!=101:raise ValueError('Full original 101 required')
    issuers={}
    for row in rows:issuers.setdefault(row['conditional_issuer_id'],[]).append(row['ticker'])
    if len(issuers)!=100:raise ValueError('Original 100 distinct issuer denominator differs')
    for p,h in sources.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Full source closure changed')
    return dict(schema='CURRENT101_SEC_ISSUER_OBSERVATIONS_V1',rows=rows,new_response_cik_count=91,refreshed_ticker_count=92,reused_prior_current_ticker_count=9,ticker_count=101,issuer_count=100,issuer_to_observed_tickers=issuers,
        source_hashes=sources,all_current_ciks_match_july_candidate_ciks=True,current_issuer_ticker_exchange_observed=True,current_observation_is_historical_membership=False,
        historical_cusip_verified=False,provider_price_identity_bound=False,historical_alias_join_allowed=False,point_in_time_verified=False,promotion_allowed=False,live_registry_modified=False,network_requests_in_readback=0)


if __name__=='__main__':
    from scripts.ndx_current_22_price_capture_20260919 import save
    report=build();path=FOLDER/'current101_issuer_facts.json';sha=save(path,report)
    for p,h in report['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Published source differs')
    print(json.dumps(dict(path=str(path),sha256=sha,tickers=report['ticker_count'],issuers=report['issuer_count'])))
