"""Create-only Sina raw receipt. No CSV derivation, cache write, or observation."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import types
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_sina_saved_day_response_research.py'
CORE_SHA='31417bc61f2471a8d92afede8eb85ff17cd92aadf71e439a9a72339987b80a36'
OUTPUT=ROOT/'data/cache/research/forward_network_day_receipt_20261003_v1'
BOUND={
 'QQQ':('data/cache/research/observation_gap_classification_20261002_v1/QQQ.csv','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'SPY':('data/cache/research/observation_gap_classification_20261002_v1/SPY.csv','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf')}
MAX_BYTES=16*1024*1024;SOCKET_TIMEOUT_SECONDS=30;REQUEST_BUDGET_SECONDS=90
FLAGS=dict.fromkeys(('observable_csv_derived','bridge_authorized','provider_basis_compatibility_verified','source_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','fresh_observation','point_in_time_verified','live_cache_written','old_capture_modified','oos_recovery_completed','clock_authenticity_verified'),False)
SAFE_HEADERS={'content-type','content-length','content-encoding','date','last-modified','etag'}

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def encode(v):return json.dumps(v,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False).encode('utf-8')
def write(path,raw):
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Persisted bytes differ');return dict(path=str(path),sha256=sha(raw))
def save(path,v):return write(path,encode(v))
def guard(sources):
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def load():
    sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA};baseline={};refs={}
    for ticker,(p,h) in BOUND.items():
        path=ROOT/p;raw=path.read_bytes();require(sha(raw)==h,'Baseline bytes differ');sources[str(path)]=h;baseline[ticker]=raw;refs[ticker]=dict(path=str(path),sha256=h)
    guard(sources);code=CORE.read_bytes();require(sha(code)==CORE_SHA,'Fresh core bytes')
    core=types.ModuleType('_isolated_sina_saved_response');core.__file__=str(CORE);exec(compile(code,str(CORE),'exec'),core.__dict__)
    return sources,baseline,refs,core

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def receive(ticker,path):
    """One network attempt; original/partial bytes durable before any parsing."""
    url='https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_='+ticker+'_day/US_MinKService.getDailyK?symbol='+ticker
    receipt=dict(ticker=ticker,request_url=url,started_at_utc=now(),completed_at_utc=None,http_status=None,final_url=None,response_headers={},transport_error=None,response_complete=False,network_attempt_count=1,socket_timeout_seconds=SOCKET_TIMEOUT_SECONDS,request_budget_seconds=REQUEST_BUDGET_SECONDS,maximum_saved_bytes=MAX_BYTES+1,requested_accept_encoding='identity',redirects_allowed=False,retry_allowed=False,timeout_semantics='SOCKET_TIMEOUT_AND_LOOP_WALL_CHECK_NOT_HARD_PREEMPTION')
    start=time.monotonic();response=None
    with path.open('xb') as f:
        try:
            request=Request(url,headers={'User-Agent':'Mozilla/5.0 research-receipt','Accept':'*/*','Accept-Encoding':'identity','Referer':'https://finance.sina.com.cn/'})
            opener=build_opener(ProxyHandler({}),NoRedirect())
            try:response=opener.open(request,timeout=SOCKET_TIMEOUT_SECONDS)
            except HTTPError as error:response=error
            receipt['http_status']=response.code;receipt['final_url']=response.geturl()
            receipt['response_headers']={k.lower():v for k,v in response.headers.items() if k.lower() in SAFE_HEADERS}
            count=0
            while True:
                require(time.monotonic()-start<=REQUEST_BUDGET_SECONDS,'Request wall budget exceeded')
                chunk=response.read(min(65536,MAX_BYTES+1-count))
                if chunk:f.write(chunk);count+=len(chunk)
                require(count<=MAX_BYTES,'Response exceeds byte limit; retained bounded prefix')
                require(time.monotonic()-start<=REQUEST_BUDGET_SECONDS,'Request wall budget exceeded after read')
                if not chunk:receipt['response_complete']=True;break
        except Exception as error:receipt['transport_error']=dict(type=type(error).__name__,message=str(error))
        finally:
            try:
                if response is not None:response.close()
            except Exception as error:
                receipt['close_error']=dict(type=type(error).__name__,message=str(error))
                if receipt['transport_error'] is None:receipt['transport_error']=receipt['close_error']
            finally:
                f.flush();os.fsync(f.fileno());receipt['completed_at_utc']=now()
    raw=path.read_bytes();receipt['raw_reference']=dict(path=str(path),sha256=sha(raw));receipt['saved_byte_count']=len(raw)
    return receipt

def run(*,execute=False):
    require(type(execute) is bool,'Explicit execute boolean')
    if not execute:return dict(status='NOT_EXECUTED',**FLAGS)
    require(not OUTPUT.exists(),'Namespace already exists; no retry')
    sources,baseline,refs,core=load();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started_ref=save(OUTPUT/'started.json',dict(schema='FORWARD_NETWORK_DAY_RECEIPT_STARTED_V1',source_hashes=sources,baseline_references=refs,target_session='2026-10-02',tickers=['QQQ','SPY'],started_at_utc=now(),**FLAGS))
        rows=[];received=[]
        for ticker in ('QQQ','SPY'):
            guard(sources);receipt=receive(ticker,OUTPUT/(ticker+'.response.bin'))
            receipt_ref=save(OUTPUT/(ticker+'.receipt.json'),receipt)
            received.append((ticker,receipt,receipt_ref))
        # Both attempts are preserved even if the first response cannot be parsed.
        for ticker,receipt,receipt_ref in received:
            # Receipt and raw must exist durably before parser is reached.
            require(receipt['transport_error'] is None and receipt['response_complete'] is True and receipt['http_status']==200,'Transport incomplete or non-200; raw retained')
            require(receipt['final_url']==receipt['request_url'],'No provider/URL fallback')
            require(receipt['response_headers'].get('content-encoding','identity').lower() in ('identity',''),'Unexpected content encoding; raw retained')
            raw=(OUTPUT/(ticker+'.response.bin')).read_bytes();require(sha(raw)==receipt['raw_reference']['sha256'],'Raw changed before parse')
            diagnostic=core.inspect_response(raw_bytes=raw,ticker=ticker,baseline_csv_bytes=baseline[ticker])
            rows.append(dict(ticker=ticker,receipt_reference=receipt_ref,raw_reference=receipt['raw_reference'],diagnostic=diagnostic))
        guard(sources)
        result=dict(schema='FORWARD_NETWORK_DAY_RECEIPT_DIAGNOSTIC_V1',status='RAW_RECEIVED_DIAGNOSED_NO_BRIDGE_NO_OBSERVATION',target_session='2026-10-02',rows=rows,baseline_references=refs,source_hashes=sources,network_request_count=2,new_session_sets_symmetric=rows[0]['diagnostic']['new_provider_sessions']==rows[1]['diagnostic']['new_provider_sessions'],both_exact_single_target=all(r['diagnostic']['exact_single_new_target'] for r in rows),timeliness_evaluated=False,**FLAGS)
        result_ref=save(OUTPUT/'diagnostic.json',result)
        pub=save(OUTPUT/'publication.json',dict(schema='FORWARD_NETWORK_DAY_RECEIPT_PUBLICATION_V1',status='PUBLISHED_RAW_DIAGNOSTIC_ONLY',diagnostic_reference=result_ref,source_hashes=sources,**FLAGS))
        guard(sources)
        expected={'started.json','diagnostic.json','publication.json',*[t+suffix for t in ('QQQ','SPY') for suffix in ('.response.bin','.receipt.json')]}
        require({p.name for p in OUTPUT.iterdir()}==expected,'Exact receipt namespace')
        for r in [started_ref,result_ref,pub,*[r[k] for r in rows for k in ('receipt_reference','raw_reference')]]:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final evidence drift')
        return pub
    except Exception as error:
        save(OUTPUT/'failure.json',dict(schema='FORWARD_NETWORK_DAY_RECEIPT_FAILURE_V1',type=type(error).__name__,message=str(error),failed_at_utc=now(),retry_allowed=False,**FLAGS))
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute),ensure_ascii=False))
