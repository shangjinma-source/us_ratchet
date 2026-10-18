"""Current SEC reported CIK/ticker/exchange facts; no historical security join."""
from datetime import datetime,timedelta
import gzip,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/cache/research/current_nine_identity_capture_20260919_v1'
MANIFEST=FOLDER/'manifest.json'
MANIFEST_SHA='adef593e19ec56acc4468ccddcc0d5177deb3b5c40d19a7db7ef3af947225c9c'
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('Duplicate JSON key')
        value[key]=item
    return value
def loads(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def merge(a,b):
    for p,h in b.items():
        if p in a and a[p]!=h:raise ValueError('Source collision')
        a[p]=h
def read(path,expected,sources):
    path=Path(path).resolve();raw=path.read_bytes()
    if sha(raw)!=expected:raise ValueError('Bound bytes changed')
    merge(sources,{str(path):expected});return loads(raw)
def parse_identity(raw,requested_cik):
    body=loads(raw)
    if type(requested_cik) is not str or not re.fullmatch(r'[0-9]{10}',requested_cik) or body.get('cik')!=requested_cik:raise ValueError('Reported CIK differs from exact request')
    tickers=body.get('tickers');exchanges=body.get('exchanges')
    if (type(tickers) is not list or type(exchanges) is not list or len(tickers)!=len(exchanges)
        or any(type(t) is not str or not t for t in tickers+exchanges) or len(set(tickers))!=len(tickers)
        or type(body.get('name')) is not str or not body['name']):raise ValueError('Unambiguous positional ticker/exchange arrays required')
    return dict(reported_cik=body['cik'],reported_name=body['name'],reported_tickers=tickers,reported_exchanges=exchanges,
        former_names_diagnostic_only=body.get('formerNames',[]),former_names_are_ticker_effective_dates=False)
def match_candidates(plan_rows,identities):
    result=[]
    if len(plan_rows)!=9 or len({r['ticker'] for r in plan_rows})!=9:raise ValueError('Exact nine distinct planned tickers required')
    for row in plan_rows:
        candidates=row['candidate_ciks'];ticker=row['ticker'];matches=[];excluded=[]
        if len(set(candidates))!=len(candidates):raise ValueError('Duplicate candidate')
        for cik in candidates:
            fact=identities[cik]
            positions=[i for i,t in enumerate(fact['reported_tickers']) if t==ticker]
            if len(positions)==1 and fact['reported_exchanges'][positions[0]]=='Nasdaq':matches.append((fact,positions[0]))
            else:excluded.append(dict(cik=cik,reported_name=fact['reported_name'],reported_tickers=fact['reported_tickers'],reported_exchanges=fact['reported_exchanges'],reason='NO_EXACT_POSITIONAL_REQUESTED_TICKER_NASDAQ_MATCH'))
        if len(matches)!=1:raise ValueError('Exactly one reported ticker/Nasdaq candidate required')
        fact,position=matches[0]
        result.append(dict(ticker=ticker,current_reported_cik=fact['reported_cik'],current_reported_name=fact['reported_name'],reported_ticker_exchange_position=position,
            reported_exchange=fact['reported_exchanges'][position],matched_candidate=fact,excluded_candidates=excluded,current_issuer_ticker_exchange_observed=True,
            name_used_as_ticker_binding=False,historical_cusip_verified=False,provider_price_identity_bound=False,historical_alias_join_allowed=False,point_in_time_verified=False))
    return result
def build():
    sources={str(SOURCE):LOADED};manifest=read(MANIFEST,MANIFEST_SHA,sources)
    if manifest['schema']!='CURRENT_NINE_CANDIDATE_IDENTITY_RAW_CAPTURE_V1' or Path(manifest['plan_path'])!=FOLDER/'plan.json':raise ValueError('Bound capture schema/plan differs')
    plan=read(manifest['plan_path'],manifest['plan_sha256'],sources)
    if plan['schema']!='CURRENT_NINE_CANDIDATE_IDENTITY_QUERY_PLAN_V1':raise ValueError('Original plan required')
    merge(sources,manifest['source_hashes']);merge(sources,plan['source_hashes'])
    candidates=sorted({c for row in plan['rows'] for c in row['candidate_ciks']})
    if candidates!=plan['query_ciks'] or len(candidates)!=11 or [r['name'] for r in manifest['captures']]!=candidates:raise ValueError('Exact original eleven captures required')
    identities={}
    for capture in manifest['captures']:
        cik=capture['name'];url='https://data.sec.gov/submissions/CIK'+cik+'.json'
        if (capture['request_url']!=url or capture['final_url']!=url or capture['request_method']!='GET'
            or capture['credentials_sent'] is not False or type(capture['attempt_count']) is not int or capture['attempt_count']!=1
            or type(capture['http_status']) is not int or capture['http_status']!=200 or capture.get('error_type') is not None
            or Path(capture['raw_path'])!=FOLDER/(cik+'.response.bin')):raise ValueError('Actual SEC request/status/address differs')
        start=datetime.fromisoformat(capture['started_at_utc']);received=datetime.fromisoformat(capture['received_at_utc'])
        if any(d.tzinfo is None or d.utcoffset()!=timedelta(0) for d in (start,received)) or received<start:raise ValueError('Actual UTC receipt ordering differs')
        raw=Path(capture['raw_path']).read_bytes()
        if sha(raw)!=capture['raw_sha256'] or len(raw)!=capture['raw_bytes']:raise ValueError('Raw body binding differs')
        encoding=capture['response_headers'].get('Content-Encoding')
        if encoding not in (None,'','identity','gzip'):raise ValueError('Unsupported content encoding')
        decoded=gzip.decompress(raw) if encoding=='gzip' or raw[:2]==b'\x1f\x8b' else raw
        if sha(decoded)!=capture['decoded_sha256']:raise ValueError('Decoded body binding differs')
        merge(sources,{capture['raw_path']:capture['raw_sha256']})
        identities[cik]=dict(parse_identity(decoded,cik),request_url=url,raw_path=capture['raw_path'],raw_sha256=capture['raw_sha256'],decoded_sha256=capture['decoded_sha256'],received_at_utc=capture['received_at_utc'])
    rows=match_candidates(plan['rows'],identities)
    report=dict(schema='CURRENT_SEC_NINE_ISSUER_TICKER_EXCHANGE_FACTS_V1',rows=rows,candidate_facts=identities,planned_ticker_count=9,candidate_count=11,matched_count=len(rows),
        source_hashes=sources,current_issuer_ticker_exchange_observed=True,source_is_sec_submissions_http=True,
        current_observation_is_historical_membership=False,historical_cusip_verified=False,provider_price_identity_bound=False,former_names_are_ticker_effective_dates=False,
        historical_alias_join_allowed=False,point_in_time_verified=False,promotion_allowed=False)
    for path,digest in sources.items():
        if sha(Path(path).read_bytes())!=digest:raise ValueError('Source closure changed')
    return report
if __name__=='__main__':
    report=build();path=FOLDER/'current_identity_facts.json'
    with path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    for p,h in report['source_hashes'].items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Source changed after publication')
    print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()),matched=report['matched_count'])))
