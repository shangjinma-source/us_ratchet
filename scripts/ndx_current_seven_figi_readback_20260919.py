"""Current mapping response facts, preserving all candidates; no issuer/history adjudication."""
from datetime import datetime,timedelta
from copy import deepcopy
import gzip,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_nine_identity_readback_20260919 as json_source
FOLDER=ROOT/'data/cache/research/current_seven_figi_capture_20260919_v1'
MANIFEST=FOLDER/'manifest.json';MANIFEST_SHA='1bced6a9b85827229901869e58c3941b5ccbf5915f0ce270af373a4a5bd092ab'
SOURCE=Path(__file__).resolve();LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(json_source.__file__).resolve())}
TICKERS=('TER','NBIS','LITE','RKLB','ALAB','CRWV','SPCX')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def parse_jobs(request,response):
    if type(request) is not list or type(response) is not list or len(request)!=len(response) or not request:raise ValueError('Exact positional request/response denominator required')
    rows=[]
    for position,(job,reply) in enumerate(zip(request,response)):
        if type(job) is not dict or set(job)!={'idType','idValue','exchCode','marketSecDes'} or job['idType']!='TICKER' or job['exchCode']!='US' or job['marketSecDes']!='Equity' or type(job['idValue']) is not str:raise ValueError('Exact public TICKER US Equity request required')
        if type(reply) is not dict or set(reply)-{'data','error','warning'}:raise ValueError('Known response envelope required')
        if 'error' in reply and 'data' in reply:raise ValueError('Conflicting mapping result and error')
        candidates=reply.get('data',[])
        if type(candidates) is not list:raise ValueError('Explicit candidate array required')
        observations=[]
        for ordinal,candidate in enumerate(candidates):
            if type(candidate) is not dict or candidate.get('ticker')!=job['idValue'] or candidate.get('exchCode')!='US' or candidate.get('marketSector')!='Equity':raise ValueError('Explicit response ticker/market contradicts positional request')
            for key in ('figi','compositeFIGI','shareClassFIGI'):
                if type(candidate.get(key)) is not str or re.fullmatch('[A-Z0-9]{12}',candidate[key]) is None:raise ValueError('Observed identifier shape required; no inferred FIGI')
            for key in ('name','securityType','securityType2'):
                if type(candidate.get(key)) is not str or not candidate[key]:raise ValueError('Explicit candidate name/security type required')
            cusip=candidate.get('cusip')
            if cusip is not None and (type(cusip) is not str or re.fullmatch('[A-Z0-9*@#]{9}',cusip) is None):raise ValueError('Explicit CUSIP field malformed')
            common=candidate['securityType']=='Common Stock' and candidate['securityType2']=='Common Stock'
            observations.append(dict(response_candidate_position=ordinal,raw_candidate=deepcopy(candidate),figi=candidate['figi'],composite_figi=candidate['compositeFIGI'],share_class_figi=candidate['shareClassFIGI'],
                cusip=cusip,cusip_returned=cusip is not None,common_stock_type_observed=common,security_type_is_issuer_identity_proof=False))
        n=len(observations)
        status=('NO_CANDIDATE_RETURNED' if n==0 else 'MULTIPLE_CANDIDATES_UNRESOLVED' if n>1 else
                'SINGLE_COMMON_STOCK_CANDIDATE_OBSERVED' if observations[0]['common_stock_type_observed'] else 'SINGLE_NON_COMMON_STOCK_CANDIDATE_NOT_ADMITTED')
        rows.append(dict(request_position=position,requested_ticker=job['idValue'],request=deepcopy(job),candidate_count=n,candidates=observations,mapping_observation_status=status,
            warning=reply.get('warning'),error=reply.get('error'),issuer_cik=None,issuer_cik_join_performed=False,unique_security_identity_adjudicated=False,
            provider_price_identity_bound=False,historical_ticker_interval_verified=False,point_in_time_verified=False))
    return rows
def build():
    sources=dict(LOADED);manifest=json_source.read(MANIFEST,MANIFEST_SHA,sources)
    if manifest['schema']!='CURRENT_SEVEN_FIGI_MAPPING_RAW_CAPTURE_V1' or manifest['requested_tickers']!=list(TICKERS) or [c['name'] for c in manifest['captures']]!=['batch_1','batch_2']:raise ValueError('Hard seven jobs in two original captures required')
    json_source.merge(sources,manifest['source_hashes']);rows=[]
    for offset,capture in zip((0,4),manifest['captures']):
        name=capture['name'];url='https://api.openfigi.com/v3/mapping'
        if capture['request_method']!='POST' or capture['request_url']!=url or capture.get('final_url')!=url or capture['credentials_sent'] is not False or type(capture['attempt_count']) is not int or capture['attempt_count']!=1 or type(capture['http_status']) is not int or capture['http_status']!=200 or capture.get('error_type') is not None:raise ValueError('Original successful public capture required')
        if Path(capture['request_body_path'])!=FOLDER/(name+'.request.json') or Path(capture['raw_path'])!=FOLDER/(name+'.response.bin'):raise ValueError('Original raw/request address required')
        request=json_source.read(capture['request_body_path'],capture['request_body_sha256'],sources)
        if request!=capture['json_payload'] or [r['idValue'] for r in request]!=list(TICKERS[offset:offset+4]):raise ValueError('Request bytes/declared jobs or fixed order differ')
        receipt=FOLDER/(name+'.receipt.json');rawreceipt=receipt.read_bytes()
        if json_source.loads(rawreceipt)!=capture:raise ValueError('Persisted receipt differs')
        sources[str(receipt)]=sha(rawreceipt)
        start=datetime.fromisoformat(capture['started_at_utc']);end=datetime.fromisoformat(capture['received_at_utc'])
        if any(t.tzinfo is None or t.utcoffset()!=timedelta(0) for t in (start,end)) or end<start:raise ValueError('Actual UTC receipt order differs')
        raw=Path(capture['raw_path']).read_bytes();encoding=capture['response_headers'].get('Content-Encoding')
        if sha(raw)!=capture['raw_sha256'] or len(raw)!=capture['raw_bytes'] or encoding not in (None,'','identity','gzip'):raise ValueError('Raw body/encoding differs')
        sources[capture['raw_path']]=capture['raw_sha256'];decoded=gzip.decompress(raw) if encoding=='gzip' or raw[:2]==b'\x1f\x8b' else raw
        if sha(decoded)!=capture['decoded_sha256']:raise ValueError('Decoded body differs')
        for row in parse_jobs(request,json_source.loads(decoded)):
            row.update(capture_name=name,raw_path=capture['raw_path'],raw_sha256=capture['raw_sha256'],decoded_sha256=capture['decoded_sha256'],request_body_path=capture['request_body_path'],request_body_sha256=capture['request_body_sha256'],received_at_utc=capture['received_at_utc']);rows.append(row)
    report=dict(schema='CURRENT_SEVEN_FIGI_RESPONSE_FACTS_NOT_BINDING_V1',rows=rows,request_count=7,response_candidate_count=sum(r['candidate_count'] for r in rows),source_hashes=sources,
        all_response_candidates_preserved=True,source_is_openfigi_public_mapping=True,name_join_used=False,current_issuer_figi_binding_adjudicated=False,historical_cusip_verified=False,
        provider_price_identity_bound=False,historical_alias_join_allowed=False,point_in_time_verified=False,promotion_allowed=False)
    verify(report);return report
def verify(report):
    for p,h in report['source_hashes'].items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Fact source changed')
if __name__=='__main__':
    report=build();path=FOLDER/'current_figi_response_facts.json'
    with path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    verify(report);print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()),candidates=report['response_candidate_count'])))
