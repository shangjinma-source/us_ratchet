"""Public default GIW request only; raw JS gates, no historical-date override or login."""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,re
from urllib.parse import urlencode
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler,Request,build_opener
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/official_giw_default_weighting_20261003_v1'
PAGES=(('weighting_js','https://indexes.nasdaqomx.com/Scripts/Weighting.js?v=2.0.0.35527'),('site_js','https://indexes.nasdaqomx.com/Scripts/Site.js?v=2.0.0.35527'))
HTML=ROOT/'data/cache/research/official_ndx_public_access_20261003_v1/giw_weighting.response.bin'
HTML_SHA='504c195708ab0e0a43a8504ebb2591def4ac777c895c79df7b6019cc49d4e700'
DATA_URL='https://indexes.nasdaqomx.com/Index/WeightingData'
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
def guard():
 require(sha(SOURCE.read_bytes())==LOADED,'Loaded capture source drift')
 require(sha(HTML.read_bytes())==HTML_SHA,'Saved HTML drift')
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def capture(name,url,request_document=None):
 path=OUTPUT/(name+'.response.bin');started=now();response=None;metadata=None;error=None;complete=False;total=0;interrupt=None
 # Every returned chunk is written before HTTP/size interpretation; partial prefixes survive.
 with path.open('xb')as stream:
  try:
   request_document=request_document or dict(method='GET',url=url,body_ascii=None)
   body=request_document['body_ascii']
   headers={'User-Agent':'Mozilla/5.0','Accept':'*/*','Accept-Encoding':'identity'}
   if body is not None:headers['Content-Type']='application/x-www-form-urlencoded; charset=UTF-8'
   request=Request(url,data=None if body is None else body.encode('ascii'),headers=headers,method=request_document['method'])
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
 receipt=dict(schema='OFFICIAL_GIW_DEFAULT_WEIGHTING_RECEIPT_V1',name=name,request=request_document,started_at_utc=started,completed_at_utc=now(),transport_metadata=metadata,response_reference=rawref,body_complete=complete,error=error,http_date_is_not_publication_time=True,local_capture_clock_authenticated=False,socket_timeout_seconds=30,hard_total_timeout_enforced=False,**FLAGS)
 rr=save(name+'.receipt.json',receipt)
 if interrupt is not None:raise interrupt
 return rawref,rr,complete and error is None and metadata['http_status']==200

def local_clock():
 d=datetime.now().astimezone()
 return dict(local_iso=d.isoformat(),timezone_name=d.tzname(),utc_offset_seconds=int(d.utcoffset().total_seconds()),local_date=d.date().isoformat(),basis='WINDOWS_LOCAL_DATETIME_ASTIMEZONE_NOT_MEMBER_EFFECTIVE_DATE')

def validate_public_code(html,weighting,site):
 # Authenticate original bytes before this structural gate; never evaluate returned JavaScript.
 require('id="symbol"' in html and '>NDX</a>' in html,'Original NDX symbol')
 require('<option value="SOD">Start of Day</option>' in html,'Explicit SOD control')
 require('$("#tradeDate").attr("disabled", "true")' in html,'Saved free historical date control disabled')
 for _,url in PAGES:require(url.split('nasdaqomx.com')[1] in html,'JS actually linked by saved HTML')
 for token in ('function GetFreeColumns', '"Name"', '"Symbol"', 'new Date()', 'datepicker("setDate", today)', '$("#timeOfDay").val("SOD")', 'url: "/Index/WeightingData"', 'type: "POST"', 'tradeDate: tradeDate.toISONonUtcString()', 'timeOfDay: $("#timeOfDay").val()'):
  require(token in weighting,'Expected public default JS semantics: '+token)
 for token in ('Date.prototype.toISONonUtcString = function', 'getFullYear()', 'getMonth() + 1', 'getDate()', 'getHours()', 'getMinutes()', 'getSeconds()', 'getMilliseconds()'):
  require(token in site,'Expected local-date formatter: '+token)
 return dict(historical_date_control_disabled=True,requested_time_of_day='SOD',eod_requested=False,export_requested=False,proforma_requested=False,js_executed=False)

def run(*,execute=False):
 require(execute is True,'Explicit capture required');guard();require(not OUTPUT.exists(),'Create only; no retry')
 htmlraw=HTML.read_bytes();require(sha(htmlraw)==HTML_SHA,'Consumed HTML same bytes')
 OUTPUT.mkdir(parents=True,exist_ok=False);refs=[];current=None
 try:
  refs.append(save('started.json',dict(schema='OFFICIAL_GIW_DEFAULT_WEIGHTING_CAPTURE_STARTED_V1',pages=[dict(name=n,url=u)for n,u in PAGES],source_reference=dict(path=str(SOURCE),sha256=LOADED),html_reference=dict(path=str(HTML),sha256=HTML_SHA),started_at_utc=now(),**FLAGS)))
  receipts=[];complete=[];scripts=[]
  for name,url in PAGES:
   current=name;raw,receipt,ok=capture(name,url);refs.extend((raw,receipt));receipts.append(receipt);complete.append(ok);guard()
   require(ok,'JS response must be complete HTTP200 before any data request')
   body=Path(raw['path']).read_bytes();require(sha(body)==raw['sha256'],'JS consumed same authenticated bytes');scripts.append(body.decode('utf-8-sig'))
  controls=validate_public_code(htmlraw.decode('utf-8'),*scripts)
  sampled=local_clock();date=datetime.fromisoformat(sampled['local_iso']).date().isoformat()
  require(date==sampled['local_date'],'Local date sampling coherent')
  form=dict(id='NDX',tradeDate=date+'T00:00:00.000',timeOfDay='SOD')
  body=urlencode(form)
  request=dict(method='POST',url=DATA_URL,body_ascii=body,body_sha256=sha(body.encode('ascii')),form=form,clock=sampled,member_effective_date=None,historical_date_override=False,**controls)
  refs.append(save('default_weighting.request.json',request));current='default_weighting'
  raw,receipt,ok=capture(current,DATA_URL,request);refs.extend((raw,receipt));receipts.append(receipt);complete.append(ok);guard()
  manifest=save('manifest.json',dict(schema='OFFICIAL_GIW_DEFAULT_WEIGHTING_CAPTURE_V1',status='DEFAULT_PUBLIC_RESPONSES_SAVED_NOT_INTERPRETED'if all(complete)else'PARTIAL_OR_NON200_EVIDENCE_ONLY',receipts=receipts,outputs=refs,source_reference=dict(path=str(SOURCE),sha256=LOADED),html_reference=dict(path=str(HTML),sha256=HTML_SHA),successful_http200_response_count=sum(complete),requested_date_is_not_member_effective_date=True,body_semantics_not_interpreted=True,scope='PUBLIC_DEFAULT_SOD_REQUEST_ONLY_NO_HISTORICAL_OVERRIDE',**FLAGS));refs.append(manifest);guard()
  require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in refs},'Exact capture namespace')
  for r in refs:require(reference(Path(r['path']))==r,'Final captured bytes')
  return manifest
 except BaseException as e:
  save('failure.json',dict(schema='OFFICIAL_GIW_DEFAULT_WEIGHTING_CAPTURE_FAILURE_V1',status='FAILED_NO_RETRY',current_page=current,retained_references=refs,preserved_files=[reference(p)for p in OUTPUT.iterdir()if p.is_file()],error=dict(type=type(e).__name__,message=str(e)),**FLAGS));raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
