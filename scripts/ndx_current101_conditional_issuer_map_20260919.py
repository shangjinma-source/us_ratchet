"""Full current-observation issuer candidates; distinct SEC observation vintages."""
import csv,hashlib,json
from datetime import datetime,timedelta
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_nine_identity_readback_20260919 as nine
BASE=ROOT/'data/cache';SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OBS=BASE/'research/ndx_current_quote_list_capture_20260919_v1/observation.json'
OBS_SHA='50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77'
FACT=BASE/'research/current_nine_identity_capture_20260919_v1/current_identity_facts.json'
FACT_SHA='33eb7055e9072431def42f0a9fa88a0f03c245efd8664844c620955ca576fa32'
TABLES=[('candidate_pools/ndx_history/sec_company_tickers_exchange.json','9acebd84c564cb4154367ba13f965f9bed6ee40cc4e3eb69874abd34c3e81005','fdfbb15d4273f8eb26eb4460764f00ae23007bd57cd70d0feab9d4166262890c'),('candidate_pools/ndx_taxonomy_v2/incumbent_overlay/sec_company_tickers_exchange.json','2da506311a91d45c4834ff26a1144fe1c74d688bdfd9881ac1f9e7bdc4a61d5f','9cdb1dd3e4fdd85af84a5095f09fd0e24f259e08bc9e3054c4615033fdf13081')]
CURRENT=BASE/'candidate_pools/ndx_taxonomy_v2/current_review_20260713/current_target_universe.csv'
CURRENT_SHA='b7515e8c3d3237b00832a0e4d16324af053111eace630ab351f534e0a4522b6d'


def parse_table(body,tickers):
    if body.get('fields')!=['cik','name','ticker','exchange'] or type(body.get('data')) is not list:raise ValueError('Exact SEC field coordinates required')
    output={}
    for i,row in enumerate(body['data']):
        if type(row) is not list or len(row)!=4:raise ValueError('Malformed SEC row')
        if row[2] not in tickers:continue
        if row[2] in output or type(row[0]) is not int or not 0<row[0]<10**10 or row[3]!='Nasdaq' or type(row[1]) is not str or not row[1]:raise ValueError('Unique requested ticker/CIK/Nasdaq row required')
        output[row[2]]=dict(cik=str(row[0]).zfill(10),row_index=i,original_sec_row=row)
    if set(output)!=set(tickers):raise ValueError('Full ticker denominator required')
    return output


def assemble(tickers,tables,current_facts):
    if len(tickers)!=len(set(tickers)):raise ValueError('Duplicate current ticker')
    rows=[]
    for ticker in tickers:
        prior=[table[ticker] for table in tables]
        if len({p['cik'] for p in prior})!=1:raise ValueError('SEC table CIK conflict')
        cik=prior[0]['cik'];fresh=current_facts.get(ticker)
        if fresh and (fresh['current_reported_cik']!=cik or fresh['reported_exchange']!='Nasdaq'):raise ValueError('Current submission conflicts with dated table')
        rows.append(dict(ticker=ticker,conditional_issuer_id='issuer:'+cik,cik=cik,dated_sec_table_rows=prior,current_submission_fact=fresh,
            evidence_tier='SEPTEMBER_18_CURRENT_SUBMISSION_OBSERVATION' if fresh else 'JULY_DATED_SEC_CROSSWALK_OBSERVATIONS_ONLY',
            september_current_issuer_observation_available=bool(fresh),same_ticker_historical_security_join_allowed=False,current_security_identity_verified=False,
            historical_membership_verified=False,provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False))
    issuers={}
    for row in rows:issuers.setdefault(row['conditional_issuer_id'],[]).append(row['ticker'])
    return rows,issuers


def build():
    sources={str(SOURCE):LOADED,str(Path(nine.__file__).resolve()):hashlib.sha256(Path(nine.__file__).read_bytes()).hexdigest()}
    observation=nine.read(OBS,OBS_SHA,sources);fact=nine.read(FACT,FACT_SHA,sources)
    nine.merge(sources,observation['source_hashes']);nine.merge(sources,fact['source_hashes'])
    if fact!=nine.build():raise ValueError('Current nine facts must reproduce original capture')
    tickers=observation['observed_symbols']
    if len(tickers)!=101:raise ValueError('Hard current 101 required')
    tables=[];metadata=[]
    for relative,sha,sidecar_sha in TABLES:
        path=BASE/relative;body=nine.read(path,sha,sources);sidecar=nine.read(str(path)+'.manifest.json',sidecar_sha,sources)
        if sidecar['content_sha256']!=sha or sidecar['content_bytes']!=path.stat().st_size or Path(sidecar['cache_path']).resolve()!=path.resolve() or sidecar['source_locator']!='https://www.sec.gov/files/company_tickers_exchange.json':raise ValueError('Original SEC sidecar binding differs')
        received=datetime.fromisoformat(sidecar['fetched_at'])
        if received.tzinfo is None or received.utcoffset()!=timedelta(0):raise ValueError('Explicit dated UTC metadata required')
        parsed=parse_table(body,tickers)
        for row in parsed.values():row.update(source_path=str(path),source_sha256=sha,sidecar_path=str(path)+'.manifest.json',reported_fetched_at=sidecar['fetched_at'],receipt_metadata_independently_authenticated=False)
        tables.append(parsed);metadata.append(dict(path=str(path),actual_table_row_count=len(body['data']),sidecar_reported_row_count=sidecar['row_count'],sidecar_row_count_matches_actual=sidecar['row_count']==len(body['data']),reported_fetched_at=sidecar['fetched_at']))
    if hashlib.sha256(CURRENT.read_bytes()).hexdigest()!=CURRENT_SHA:raise ValueError('Derived July inventory changed')
    sources[str(CURRENT)]=CURRENT_SHA
    with CURRENT.open(encoding='utf-8-sig') as stream:
        derived={r['ticker']:r for r in csv.DictReader(stream)}
    fresh={r['ticker']:r for r in fact['rows']};rows,issuers=assemble(tickers,tables,fresh)
    for row in rows:
        if row['ticker'] not in fresh and (row['ticker'] not in derived or derived[row['ticker']]['cik']!=row['cik']):raise ValueError('Existing 92 derived CIK conflict')
    if len(fresh)!=9 or sum(not r['september_current_issuer_observation_available'] for r in rows)!=92:raise ValueError('Exact 9 current / 92 dated partition required')
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Issuer source changed')
    return dict(schema='CURRENT101_CONDITIONAL_ISSUER_MAP_V1',rows=rows,security_observation_count=101,conditional_unique_issuer_count=len(issuers),issuer_to_observed_tickers=issuers,
        current_submission_ticker_count=9,dated_crosswalk_only_ticker_count=92,dated_crosswalk_metadata=metadata,source_hashes=sources,
        complete_current_same_cutoff_sec_identity_verified=False,current_security_identity_verified=False,provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False,
        latest_sec_refresh_candidate_tickers=[r['ticker'] for r in rows if not r['september_current_issuer_observation_available']],network_requests=0,live_registry_modified=False)


if __name__=='__main__':
    from scripts.ndx_current_22_price_capture_20260919 import save
    report=build();folder=BASE/'research/current101_conditional_issuer_map_20260919_v1';folder.mkdir(exist_ok=False)
    path=folder/'issuer_map.json';sha=save(path,report)
    for p,h in report['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Published source differs')
    print(json.dumps(dict(path=str(path),sha256=sha,issuers=report['conditional_unique_issuer_count'])))
