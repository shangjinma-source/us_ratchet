"""Fixed official change notices; chunk-durable evidence, never full membership certification."""
import argparse
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler,Request,build_opener
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/official_ndx_change_notices_20261003_v1'
PAGES = (
 ('june_quarterly_changes', 'https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-100-indexr-june-2026-quarterly-changes'),
 ('october_future_mrna_wbd', 'https://ir.nasdaq.com/news-releases/news-release-details/moderna-inc-join-nasdaq-100-indexr-beginning-october-9-2026'),
)
DECISION_RELATION = {
 'decision_date': '2026-10-02',
 'june_quarterly_changes': {'displayed_publication_date': '2026-06-11', 'announced_effective_date': '2026-06-22', 'effective_boundary': 'BEFORE_MARKET_OPEN', 'relation': 'BEFORE_DECISION'},
 'october_future_mrna_wbd': {'displayed_publication_date': '2026-10-01', 'announced_effective_date': '2026-10-09', 'effective_boundary': 'BEFORE_MARKET_OPEN', 'relation': 'AFTER_DECISION_DO_NOT_APPLY_EARLY'},
 'date_claims_require_saved_body_readback': True,
 'september_notice_found': False,
 'missing_september_notice_does_not_prove_no_change': True,
} 
LIMIT=8*1024**2
FLAGS=dict.fromkeys(('name_symbol_bridge_machine_verified','current_listing_verified','current_ndx_membership_verified','membership_complete','membership_effective_date_verified','publication_time_verified','point_in_time_verified','candidate_seal_allowed','cohort_registration_allowed','raw_itemlist_modified','credentials_sent','prior_mapping_used','response_content_parsed','automatic_retry_allowed'),False)
def require(ok,msg):
 if not ok:raise ValueError(msg)
def now():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def reference(path):
 raw=path.read_bytes();return dict(path=str(path),sha256=sha(raw),byte_count=len(raw))
def save(name,obj):
 raw=(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();p=OUTPUT/name
 with p.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==raw,'Saved bytes');return reference(p)
def guard():require(sha(SOURCE.read_bytes())==LOADED,'Loaded capture source drift')
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def capture(name,url):
 path=OUTPUT/(name+'.response.bin');started=now();response=None;metadata=None;error=None;complete=False;total=0;interrupt=None
 # Every returned chunk is written before HTTP/size interpretation; partial prefixes survive.
 with path.open('xb')as stream:
  try:
   request=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Encoding':'identity'},method='GET')
   try:response=build_opener(NoRedirect()).open(request,timeout=30)
   except HTTPError as e:response=e
   metadata=dict(http_status=response.code,response_url=response.geturl(),headers={k:response.headers.get(k)for k in ('Content-Type','Content-Encoding','Date','Last-Modified','Location')})
   while total<=LIMIT:
    chunk=response.read(min(65536,LIMIT+1-total))
    if not chunk:complete=True;break
    stream.write(chunk);total+=len(chunk)
   require(total<=LIMIT,'Response limit: saved prefix is incomplete')
  except BaseException as e:
   error=dict(type=type(e).__name__,message=str(e));interrupt=e if not isinstance(e,Exception)else None
  finally:
   try:
    if response is not None:response.close()
   except BaseException as e:
    error=dict(type=type(e).__name__,message=str(e),stage='RESPONSE_CLOSE',prior_error=error);complete=False
    if not isinstance(e,Exception):interrupt=e
   finally:stream.flush();os.fsync(stream.fileno())
 rawref=reference(path)
 receipt=dict(schema='OFFICIAL_NDX_CHANGE_NOTICES_RECEIPT_V1',name=name,request=dict(method='GET',url=url),started_at_utc=started,completed_at_utc=now(),transport_metadata=metadata,response_reference=rawref,body_complete=complete,error=error,http_date_is_not_publication_time=True,local_capture_clock_authenticated=False,socket_timeout_seconds=30,hard_total_timeout_enforced=False,**FLAGS)
 rr=save(name+'.receipt.json',receipt)
 if interrupt is not None:raise interrupt
 return rawref,rr,complete and error is None and metadata['http_status']==200

def run(*,execute=False):
 require(execute is True,'Explicit capture required');guard();require(not OUTPUT.exists(),'Create only; no retry')
 OUTPUT.mkdir(parents=True,exist_ok=False);refs=[];current=None
 try:
  refs.append(save('started.json',dict(schema='OFFICIAL_NDX_CHANGE_NOTICES_CAPTURE_STARTED_V1',pages=[dict(name=n,url=u)for n,u in PAGES],source_reference=dict(path=str(SOURCE),sha256=LOADED),started_at_utc=now(),**FLAGS)))
  receipts=[];complete=[]
  for name,url in PAGES:
   current=name;raw,receipt,ok=capture(name,url);refs.extend((raw,receipt));receipts.append(receipt);complete.append(ok);guard()
  manifest=save('manifest.json',dict(schema='OFFICIAL_NDX_CHANGE_NOTICES_CAPTURE_V1',status='TWO_HTTP200_RESPONSES_SAVED_NOT_INTERPRETED'if all(complete)else'PARTIAL_OR_NON200_EVIDENCE_ONLY',receipts=receipts,outputs=refs,source_reference=dict(path=str(SOURCE),sha256=LOADED),successful_http200_response_count=sum(complete),notice_date_declarations=DECISION_RELATION,scope='RAW_OFFICIAL_CHANGE_NOTICES_NOT_COMPLETE_OR_PIT_MEMBERSHIP',**FLAGS));refs.append(manifest);guard()
  require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in refs},'Exact capture namespace')
  for r in refs:require(reference(Path(r['path']))==r,'Final captured bytes')
  return manifest
 except BaseException as e:
  save('failure.json',dict(schema='OFFICIAL_NDX_CHANGE_NOTICES_CAPTURE_FAILURE_V1',status='FAILED_NO_RETRY',current_page=current,retained_references=refs,preserved_files=[reference(p)for p in OUTPUT.iterdir()if p.is_file()],error=dict(type=type(e).__name__,message=str(e)),**FLAGS));raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
