"""Offline fixed-source diagnostic; empty public response is never an empty universe."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from urllib.parse import urlencode
import json,os,re
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/official_giw_default_weighting_20261003_v1'
OUTPUT=ROOT/'data/cache/research/official_giw_empty_response_diagnostic_20261003_v1'
MANIFEST_SHA='c242011b150a361dab3e8560d0949c5c98afe12e23060e67f3f39b8a5bedfe2f'
HTML=ROOT/'data/cache/research/official_ndx_public_access_20261003_v1/giw_weighting.response.bin'
HTML_SHA='504c195708ab0e0a43a8504ebb2591def4ac777c895c79df7b6019cc49d4e700'
PRODUCER=ROOT/'scripts/ndx_official_giw_default_weighting_capture_20261003.py'
PRODUCER_SHA='d628548c27a29040d6e0cbe02cef99aefd9e5a475eefeb8aedaa37c9375b7fcb'
NAMES={'started.json','weighting_js.response.bin','weighting_js.receipt.json','site_js.response.bin','site_js.receipt.json','default_weighting.request.json','default_weighting.response.bin','default_weighting.receipt.json'}
FALSE_FLAGS=('automatic_retry_allowed','candidate_seal_allowed','cohort_registration_allowed','credentials_sent','current_listing_verified','current_ndx_membership_verified','membership_complete','membership_effective_date_verified','name_symbol_bridge_machine_verified','point_in_time_verified','prior_mapping_used','publication_time_verified','raw_itemlist_modified','response_content_parsed')
URLS={'weighting_js':'https://indexes.nasdaqomx.com/Scripts/Weighting.js?v=2.0.0.35527','site_js':'https://indexes.nasdaqomx.com/Scripts/Site.js?v=2.0.0.35527','default_weighting':'https://indexes.nasdaqomx.com/Index/WeightingData'}
def require(ok,msg):
 if not ok:raise ValueError(msg)
def digest(raw):return sha256(raw).hexdigest()
def pairs(items):
 out={}
 for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
 return out
def parse(raw):return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def inspect(raws,htmlraw):
 m=parse(raws['manifest.json']);require(m['schema']=='OFFICIAL_GIW_DEFAULT_WEIGHTING_CAPTURE_V1','Manifest schema')
 require(m['status']=='DEFAULT_PUBLIC_RESPONSES_SAVED_NOT_INTERPRETED'and type(m['successful_http200_response_count'])is int and m['successful_http200_response_count']==3,'Complete three HTTP200 captures')
 for k in FALSE_FLAGS:require(m[k]is False,'Manifest false authority')
 request=parse(raws['default_weighting.request.json']);response=parse(raws['default_weighting.response.bin'])
 require(set(response)=={'sEcho','iTotalRecords','iTotalDisplayRecords','aaData'},'Exact response fields')
 require(type(response['sEcho'])is int and response['sEcho']==1,'Echo exact integer')
 for k in ('iTotalRecords','iTotalDisplayRecords'):require(type(response[k])is int and response[k]==0,'Empty exact integer count')
 require(type(response['aaData'])is list and response['aaData']==[],'Empty exact rows')
 clock=request['clock'];date=datetime.fromisoformat(clock['local_iso']);require(date.tzinfo is not None,'Clock explicit offset')
 require(clock['local_date']==date.date().isoformat() and type(clock['utc_offset_seconds'])is int and clock['utc_offset_seconds']==int(date.utcoffset().total_seconds()),'Clock source date/offset')
 require(clock['basis']=='WINDOWS_LOCAL_DATETIME_ASTIMEZONE_NOT_MEMBER_EFFECTIVE_DATE','Clock role')
 form=dict(id='NDX',tradeDate=clock['local_date']+'T00:00:00.000',timeOfDay='SOD')
 require(exact(request['form'],form) and request['body_ascii']==urlencode(form) and request['body_sha256']==digest(request['body_ascii'].encode('ascii')),'Original default request body')
 require(request['method']=='POST'and request['url']==URLS['default_weighting'],'Default endpoint')
 require(request['member_effective_date']is None and request['historical_date_control_disabled']is True and request['requested_time_of_day']=='SOD','No effective-date claim')
 for k in ('historical_date_override','eod_requested','export_requested','proforma_requested','js_executed'):require(request[k]is False,'Default only')
 for name,url in URLS.items():
  r=parse(raws[name+'.receipt.json']);require(r['schema']=='OFFICIAL_GIW_DEFAULT_WEIGHTING_RECEIPT_V1'and r['name']==name,'Receipt schema/name')
  for k in FALSE_FLAGS:require(r[k]is False,'Receipt false authority')
  require(r['body_complete']is True and r['error']is None and type(r['transport_metadata']['http_status'])is int and r['transport_metadata']['http_status']==200,'Complete HTTP200 receipt')
  require(r['transport_metadata']['response_url']==url,'Response URL identity')
  expected=request if name=='default_weighting'else dict(method='GET',url=url,body_ascii=None)
  require(exact(r['request'],expected),'Receipt exact request association')
  ref=r['response_reference'];require(exact(ref,next(x for x in m['outputs']if Path(x['path']).name==name+'.response.bin')),'Manifest raw role association');require(Path(ref['path']).name==name+'.response.bin'and ref['sha256']==digest(raws[name+'.response.bin'])and type(ref['byte_count'])is int and ref['byte_count']==len(raws[name+'.response.bin']),'Receipt raw bytes')
 html=htmlraw.decode('utf-8');weight=raws['weighting_js.response.bin'].decode('utf-8-sig');site=raws['site_js.response.bin'].decode('utf-8-sig')
 for token in ('id="symbol"','>NDX</a>','<option value="SOD">Start of Day</option>','$("#tradeDate").attr("disabled", "true")'):require(token in html,'Saved HTML default controls')
 for name in ('weighting_js','site_js'):require(URLS[name].split('nasdaqomx.com')[1]in html,'Explicit JS link')
 for token in ('new Date()','datepicker("setDate", today)','$("#timeOfDay").val("SOD")','url: "/Index/WeightingData"','type: "POST"','tradeDate: tradeDate.toISONonUtcString()','function GetFreeColumns'):
  require(token in weight,'Saved weighting default semantics')
 for token in ('Date.prototype.toISONonUtcString = function','getFullYear()','getMonth() + 1','getDate()','getHours()','getMinutes()','getSeconds()','getMilliseconds()'):require(token in site,'Saved local formatter')
 links=[]
 for name,text in [('weighting_js',weight),('site_js',site)]:
  for n,line in enumerate(text.splitlines(),1):
   for match in re.finditer(r'["\'](/Index/[A-Za-z/]+)["\']',line):links.append(dict(source_role=name,line=n,path=match.group(1)))
 return dict(status='EMPTY_PUBLIC_RESPONSE_NOT_EMPTY_UNIVERSE',observed_response=response,request_preserved=request,capture_interval=[parse(raws['default_weighting.receipt.json'])[k]for k in ('started_at_utc','completed_at_utc')],member_effective_date=None,empty_response_reason='UNKNOWN_NOT_INFERRED_FROM_WEEKEND_OR_ACCESS_POLICY',universe_empty=False,alternative_complete_free_default_endpoint_established=False,explicit_script_routes=links,route_scope='WeightingData is the default already observed; ExportWeightings is only a generated link and was not enabled/called; Proforma/Forecast routes are not established free current membership; favorites are mutations and excluded.',network_called=False,membership_complete=False,point_in_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)
def save(name,value):
 p=OUTPUT/name;b=(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 return dict(path=str(p),sha256=digest(b),byte_count=len(b))
def run():
 require(not OUTPUT.exists(),'Create only diagnostic')
 sources={str(SOURCE):LOADED,str(HTML):HTML_SHA,str(PRODUCER):PRODUCER_SHA,str(PARENT/'manifest.json'):MANIFEST_SHA};raws={}
 for path,h in sources.items():
  b=Path(path).read_bytes();require(digest(b)==h,'Fixed source SHA')
  if Path(path).name=='manifest.json':raws['manifest.json']=b
  if Path(path)==HTML:html=b
 m=parse(raws['manifest.json']);require(exact(m['source_reference'],dict(path=str(PRODUCER),sha256=PRODUCER_SHA))and exact(m['html_reference'],dict(path=str(HTML),sha256=HTML_SHA)),'Manifest source roles')
 require(type(m['outputs'])is list and len(m['outputs'])==len(NAMES),'Output inventory count')
 seen=set()
 for r in m['outputs']:
  p=Path(r['path']);require(p.parent==PARENT and p.name in NAMES and p.name not in seen,'Fixed output path');seen.add(p.name)
  b=p.read_bytes();require(digest(b)==r['sha256']and type(r['byte_count'])is int and len(b)==r['byte_count'],'Same bytes output authentication');sources[str(p)]=r['sha256'];raws[p.name]=b
 require(exact(m['receipts'],[next(r for r in m['outputs']if Path(r['path']).name==name+'.receipt.json')for name in URLS]),'Manifest receipt roles')
 def guard():
  require({p.name for p in PARENT.iterdir()}==NAMES|{'manifest.json'},'Exact source namespace')
  for p,h in sources.items():require(digest(Path(p).read_bytes())==h,'Source drift')
 guard();OUTPUT.mkdir(parents=True)
 try:
  report=dict(schema='OFFICIAL_GIW_EMPTY_RESPONSE_DIAGNOSTIC_V1',inspection=inspect(raws,html),source_hashes=sources,manifest_reference=dict(path=str(PARENT/'manifest.json'),sha256=MANIFEST_SHA))
  ref=save('diagnostic.json',report);guard();require(digest(Path(ref['path']).read_bytes())==ref['sha256'],'Own output drift');require({p.name for p in OUTPUT.iterdir()}=={'diagnostic.json'},'Exact diagnostic namespace');return ref
 except BaseException as e:save('failure.json',dict(status='FAILED_NO_RETRY',error=dict(type=type(e).__name__,message=str(e))));raise
if __name__=='__main__':print(json.dumps(run()))
