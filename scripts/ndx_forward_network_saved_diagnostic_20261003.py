"""Offline V2 diagnostic of a failed, immutable network receipt. No network code."""
import argparse
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import types
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/forward_network_day_receipt_20261003_v1'
OUTPUT=ROOT/'data/cache/research/forward_network_saved_diagnostic_20261003_v2'
CORE=ROOT/'backtest/ndx_sina_saved_day_response_v2_research.py';CORE_SHA='1e56dbd4967d466747331778b24eaa6bc814d8d4e2054a0fc6542d2ad0d328b7'
PINS={
 'raw_QQQ':('QQQ.response.bin','6a7e79a370cae5ffc12eb28114c36b6ee1685d67dd6f9870bca6e0958ddb0bfd'),
 'raw_SPY':('SPY.response.bin','52ae32da20c44d6e99f024c978acb830c84e139fcd617122c8d5644c35495b4d'),
 'receipt_QQQ':('QQQ.receipt.json','a3d45e941845709f5982fad3f55d8b0d5be81b972af8279ad8f0b136d04982a9'),
 'receipt_SPY':('SPY.receipt.json','f14a43f2b60e1728ac1c0d70a98b446b9ae59c91187393e901f2f91e0d975c01'),
 'failure':('failure.json','ad49de29fe9e7c8976f745a62a1ef172fbf5c8f455b5a96b493a5f277a49739e'),
 'started':('started.json','3fe92ce0796928544123e77389edd76fbb904218efaa14df4165257d2974be34')}
OTHER={
 'baseline_QQQ':('data/cache/research/observation_gap_classification_20261002_v1/QQQ.csv','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'baseline_SPY':('data/cache/research/observation_gap_classification_20261002_v1/SPY.csv','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'),
 'old_producer':('scripts/ndx_forward_network_day_receipt_20261003.py','b1fb48b1e23e34b6bdb026f2382f0b421dab543890e12ccb85cd7cd97ac948f3'),
 'old_core':('backtest/ndx_sina_saved_day_response_research.py','31417bc61f2471a8d92afede8eb85ff17cd92aadf71e439a9a72339987b80a36')}
PARENT_FALSE=('observable_csv_derived','bridge_authorized','provider_basis_compatibility_verified','source_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','fresh_observation','point_in_time_verified','live_cache_written','old_capture_modified','oos_recovery_completed','clock_authenticity_verified')
FLAGS=dict.fromkeys((*PARENT_FALSE,'network_request_performed','parent_failure_repaired','timeliness_evaluated'),False)
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False).encode()
def guard(sources):
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def save(path,v):
    raw=encode(v)
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Written bytes changed');return dict(path=str(path),sha256=sha(raw))
def exact(a,b):require(encode(a)==encode(b),'Exact saved metadata binding')
def utc(v):
    d=datetime.fromisoformat(v);require(d.tzinfo is not None and d.utcoffset().total_seconds()==0,'Aware UTC');return d

def validate(raw,refs):
    start=json.loads(raw['started']);failure=json.loads(raw['failure'])
    require(start['schema']=='FORWARD_NETWORK_DAY_RECEIPT_STARTED_V1' and failure['schema']=='FORWARD_NETWORK_DAY_RECEIPT_FAILURE_V1','Original schemas')
    require(failure['type']=='ValueError' and failure['message']=='Unsupported JSONP envelope; retain raw and block' and failure['retry_allowed'] is False,'Original failure retained')
    require(start['target_session']=='2026-10-02' and start['tickers']==['QQQ','SPY'],'Original target')
    for obj in (start,failure):
        for key in PARENT_FALSE:require(obj[key] is False,'Parent authority unchanged')
    exact(start['source_hashes'],{refs[r]['path']:refs[r]['sha256'] for r in OTHER})
    exact(start['baseline_references'],{t:refs['baseline_'+t] for t in ('QQQ','SPY')})
    receipts={};previous=utc(start['started_at_utc'])
    for t in ('QQQ','SPY'):
        receipt=json.loads(raw['receipt_'+t]);exact(receipt['raw_reference'],refs['raw_'+t]);require(receipt['ticker']==t,'Receipt ticker')
        require(type(receipt['saved_byte_count']) is int and receipt['saved_byte_count']==len(raw['raw_'+t]),'Receipt bytes')
        require(type(receipt['network_attempt_count']) is int and receipt['network_attempt_count']==1 and type(receipt['http_status']) is int and receipt['http_status']==200,'One HTTP200')
        require(receipt['response_complete'] is True and receipt['transport_error'] is None and receipt['retry_allowed'] is False and receipt['redirects_allowed'] is False,'Original complete response')
        url='https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_='+t+'_day/US_MinKService.getDailyK?symbol='+t
        require(receipt['request_url']==receipt['final_url']==url,'Fixed original provider URL')
        require(previous<=utc(receipt['started_at_utc'])<=utc(receipt['completed_at_utc'])<=utc(failure['failed_at_utc']),'Original sequential request clock')
        previous=utc(receipt['completed_at_utc']);receipts[t]=receipt
    return start,failure,receipts

def load():
    require({p.name for p in PARENT.iterdir()}=={v[0] for v in PINS.values()},'Exact failed parent six files')
    raw={};refs={};sources={str(SOURCE):LOADED,str(CORE):CORE_SHA}
    for role,(relative,h) in {**PINS,**OTHER}.items():
        path=(PARENT if role in PINS else ROOT)/relative;b=path.read_bytes();require(sha(b)==h,'Fixed source bytes');raw[role]=b;refs[role]=dict(path=str(path),sha256=h);sources[str(path)]=h
    validate(raw,refs);guard(sources);code=CORE.read_bytes();require(sha(code)==CORE_SHA,'Fresh V2core')
    core=types.ModuleType('_saved_sina_v2');core.__file__=str(CORE);exec(compile(code,str(CORE),'exec'),core.__dict__)
    return raw,refs,sources,core

def run(*,execute=False):
    require(type(execute) is bool,'Explicit execute')
    if not execute:return dict(status='NOT_EXECUTED',**FLAGS)
    require(not OUTPUT.exists(),'Create-only no retry');raw,refs,sources,core=load();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=save(OUTPUT/'started.json',dict(schema='SAVED_NETWORK_DIAGNOSTIC_STARTED_V2',source_hashes=sources,input_references=refs,**FLAGS))
        parent,failure,receipts=validate(raw,refs);rows=[]
        for t in ('QQQ','SPY'):
            rows.append(dict(ticker=t,original_receipt=receipts[t],raw_reference=refs['raw_'+t],receipt_reference=refs['receipt_'+t],diagnostic=core.inspect_response(raw_bytes=raw['raw_'+t],ticker=t,baseline_csv_bytes=raw['baseline_'+t])))
        result=dict(schema='SAVED_NETWORK_DAY_DIAGNOSTIC_V2',status='BLOCKED_PROVIDER_BASIS_COMPATIBILITY_NO_BRIDGE_AUTHORIZATION',input_references=refs,source_hashes=sources,original_started=parent,original_failure=failure,rows=rows,new_session_sets_symmetric=rows[0]['diagnostic']['new_provider_sessions']==rows[1]['diagnostic']['new_provider_sessions'],original_http_charset_preserved_not_used_to_guess_decoding=True,**FLAGS)
        output=save(OUTPUT/'diagnostic.json',result);pub=save(OUTPUT/'publication.json',dict(schema='SAVED_NETWORK_DAY_DIAGNOSTIC_PUBLICATION_V2',status='PUBLISHED_OFFLINE_DIAGNOSTIC_ONLY',diagnostic_reference=output,source_hashes=sources,**FLAGS));guard(sources)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','diagnostic.json','publication.json'},'Exact output files')
        for r in (started,output,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final saved bytes')
        return pub
    except Exception as error:
        save(OUTPUT/'failure.json',dict(type=type(error).__name__,message=str(error),retry_allowed=False,**FLAGS));raise
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
