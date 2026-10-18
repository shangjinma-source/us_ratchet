"""Offline fixed official-response diagnostic, no network or PIT membership grant."""
from pathlib import Path
from html import unescape
from datetime import datetime
import hashlib,json,os,re
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/official_missing_ticker_bridge_capture_20261003_v1'
ORIGINAL=ROOT/'data/cache/research/official_ndx_public_access_20261003_v1'
OUTPUT=ROOT/'data/cache/research/official_missing_ticker_bridge_diagnostic_20261003_v1'
MANIFEST_SHA='31883b9508322dc52fd686022d1d8192715daf297b48ced53633d61480db7757'
COMPANIES_SHA='85e45efcd7c85c80b5fb198e131d717be48fb97940c2d6a343f333afa8a41561'
CAPTURE_SHA='6027f9b194faaab32bd4505a9fe44706fae12ce3789eea66de0eabda166e4e28'
NAMES=((36,'ELECTRONIC ARTS INC'),(67,'MICRON TECHNOLOGY'),(101,'ZSCALER, INC. CMN'))
PAGES=(('ea_name_symbol','https://news.ea.com/press-releases/press-releases-details/2011/Electronic-Arts-to-Change-Nasdaq-Ticker-Symbol-to-EA-Effective-December-20-2011/default.aspx'),('mu_name_symbol','https://investors.micron.com/news/press-release/2026/Micron-Accelerates-U-S--Investments-Pours-First-Concrete-at-New-York-Fab/default.aspx'),('zs_name_symbol','https://ir.zscaler.com/news-releases/news-release-details/zscaler-announces-strong-third-quarter-fiscal-2026-results'),('ea_suspension','https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-545'))
FLAGS=dict.fromkeys(('current_listing_verified','current_ndx_membership_verified','membership_complete','membership_effective_date_verified','publication_time_verified','point_in_time_verified','candidate_seal_allowed','cohort_registration_allowed','raw_itemlist_modified','prior_mapping_used','network_called','orders_executed','account_executed','automatic_retry_allowed'),False)
PARENT_FALSE=tuple(k for k in FLAGS if k not in ('network_called','orders_executed','account_executed'))+('name_symbol_bridge_machine_verified','credentials_sent','response_content_parsed')
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def decode(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON');d[k]=v
  return d
 return json.loads(b.decode('utf-8'),object_pairs_hook=pairs)
def ref(p,b):return dict(path=str(p),sha256=sha(b),byte_count=len(b))
def load(r,sources):
 require(type(r['path'])is str and len(r['sha256'])==64,'External reference');b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Exact consumed bytes')
 if 'byte_count'in r:require(type(r['byte_count'])is int and len(b)==r['byte_count'],'Exact byte length')
 require(r['path']not in sources or sources[r['path']]==r['sha256'],'Source collision');sources[r['path']]=r['sha256'];return b
def locate(raw,start,stop):return dict(byte_start=start,byte_stop=stop,fragment_sha256=sha(raw[start:stop]),line_number_one_based=raw[:start].count(b'\n')+1)
def text(fragment):return ' '.join(unescape(re.sub(r'<[^>]+>',' ',fragment.decode('utf-8'))).split())
def one(matches,label):
 matches=list(matches);require(len(matches)==1,'Unique '+label);return matches[0]
def original_rows(raw):
 found=[]
 for m in re.finditer(rb'<script\b[^>]*>(.*?)</script>',raw,re.S|re.I):
  if b'ItemList'not in m[1]:continue
  d=decode(m[1])
  for i,v in enumerate(d.get('@graph',[])):
   if v.get('@type')=='ItemList':found.append((m,i,v))
 m,i,g=one(found,'original ItemList');rows=g['itemListElement'];require(len(rows)==101 and all(type(v['position'])is int and v['position']==j+1 for j,v in enumerate(rows)),'Original101 positions')
 out=[]
 for pos,name in NAMES:
  row=rows[pos-1];require(row=={'@type':'ListItem','position':pos,'name':name},'Exact original missing ticker row')
  out.append(dict(original_position=pos,original_name=name,original_item=row,original_location={**locate(raw,m.start(1),m.end(1)), 'json_pointer':f'/@graph/{i}/itemListElement/{pos-1}'}))
 return out

def diagnose(companies,raws,receipts):
 rows=original_rows(companies);sources=[]
 for name,url in PAGES:
  r=receipts[name];require(r['schema']=='OFFICIAL_MISSING_TICKER_BRIDGE_RECEIPT_V1' and r['name']==name and r['request']==dict(method='GET',url=url),'Receipt exact role')
  require(all(r[k]is False for k in PARENT_FALSE),'Original permission flags');require(sha(raws[name])==r['response_reference']['sha256'] and len(raws[name])==r['response_reference']['byte_count'],'Raw/receipt binding')
  sources.append(dict(role=name,url=url,raw_reference=r['response_reference'],http_status=r['transport_metadata']['http_status'],body_complete=r['body_complete'],capture_started_at_utc=r['started_at_utc'],capture_completed_at_utc=r['completed_at_utc'],http_headers_preserved=r['transport_metadata']['headers'],error=r['error'],status='SAVED_HTTP_RESPONSE_ONLY'))
 def available(name):
  r=receipts[name];return type(r['transport_metadata']['http_status'])is int and r['transport_metadata']['http_status']==200 and r['body_complete']is True and r['error']is None
 for row in rows:row.update(ticker=None,status='NO_HTTP200_NAME_SYMBOL_EVIDENCE',evidence=[],published_at_verified=None,**FLAGS)
 if available('ea_suspension'):
  raw=raws['ea_suspension'];fields={}
  for label in ('Company/Issue:','CUSIP#:','Symbol:','Last Trading Date:','Marketplace Effective Date for Suspension:'):
   m=one((m for m in re.finditer(rb'<tr\b[^>]*>.*?</tr>',raw,re.S|re.I)if label in text(m[0])),'EA table '+label)
   cells=list(re.finditer(rb'<t[hd]\b[^>]*>(.*?)</t[hd]>',m[0],re.S|re.I));require(len(cells)==2 and text(cells[0][1])==label,'EA labeled row')
   fields[label]=dict(display_value=text(cells[1][1]),location=locate(raw,m.start(),m.end()))
  require(fields['Company/Issue:']['display_value']=='Electronic Arts Inc. Common Stock' and fields['Symbol:']['display_value']=='EA','EA security name/symbol')
  last=datetime.strptime(fields['Last Trading Date:']['display_value'],'%B %d, %Y').date().isoformat();suspend=datetime.strptime(fields['Marketplace Effective Date for Suspension:']['display_value'],'%B %d, %Y').date().isoformat();require(last<suspend,'EA event order')
  date=one(re.finditer(rb'Friday, July 31, 2026',raw),'EA displayed header date');require(b'UPDATED: Merger closed'in raw,'Updated header retained')
  rows[0].update(ticker='EA',status='NAME_SYMBOL_OBSERVED_WITH_CURRENT_LISTING_CONFLICT',evidence=[dict(role='ea_suspension',raw_reference=receipts['ea_suspension']['response_reference'],fields=fields,page_display_date=dict(literal=date[0].decode(),location=locate(raw,date.start(),date.end())),updated_marker_present=True,last_trading_date=last,suspension_effective_date=suspend,conflict='COMPANIES_ITEMLIST_PRESENCE_DOES_NOT_ESTABLISH_CURRENT_LISTING_OR_NDX_MEMBERSHIP',available_at=None)])
 if available('zs_name_symbol'):
  raw=raws['zs_name_symbol'];m=one(re.finditer(rb'Zscaler, Inc\.\xc2\xa0\(Nasdaq: ZS\)',raw),'ZS literal name symbol')
  d=one(re.finditer(rb'<div class="field__item">May 26, 2026</div>',raw),'ZS visible date')
  rows[2].update(ticker='ZS',status='NAME_SYMBOL_OBSERVED_ONLY',evidence=[dict(role='zs_name_symbol',raw_reference=receipts['zs_name_symbol']['response_reference'],literal=m[0].decode(),location=locate(raw,m.start(),m.end()),page_display_date=dict(literal='May 26, 2026',location=locate(raw,d.start(),d.end())),available_at=None)])
 # MU's only captured bridge is non-200. No web-search memory/old map fallback.
 require(not available('mu_name_symbol') and not available('ea_name_symbol'),'This bounded diagnostic expects saved403 issuer responses')
 return dict(schema='OFFICIAL_MISSING_TICKER_BRIDGE_DIAGNOSTIC_V1',status='PARTIAL_NAME_BRIDGES_AND_EA_LISTING_CONFLICT_NOT_MEMBERSHIP',original_itemlist_count=101,diagnosed_count=3,observed_name_symbol_count=sum(r['ticker']is not None for r in rows),rows=rows,saved_responses=sources,scope='FIXED_CAPTURE_BYTES_ONLY_NO_HISTORICAL_AVAILABLE_TIME_OR_COMPLETE_UNIVERSE',**FLAGS)

def save(name,v):
 p=OUTPUT/name;b=enc(v)
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Output bytes');return ref(p,b)
def run(*,execute=False):
 require(execute is True,'Explicit offline diagnosis');require(not OUTPUT.exists(),'Create only no retry');sources={str(SOURCE):LOADED}
 mr=dict(path=str(PARENT/'manifest.json'),sha256=MANIFEST_SHA);manifest=decode(load(mr,sources));require(manifest['schema']=='OFFICIAL_MISSING_TICKER_BRIDGE_CAPTURE_V1' and all(manifest[k]is False for k in PARENT_FALSE),'Capture manifest')
 cr=dict(path=str(ROOT/'scripts/ndx_official_missing_ticker_bridge_capture_20261003.py'),sha256=CAPTURE_SHA);require(manifest['source_reference']==cr,'Fixed capture source');load(cr,sources)
 inventory={Path(r['path']).name:r for r in manifest['outputs']};expected={'started.json'}|{n+s for n,u in PAGES for s in ('.response.bin','.receipt.json')};require(set(inventory)==expected and len(manifest['outputs'])==9,'Full capture inventory')
 blobs={}
 for name,r in inventory.items():require(r['path']==str(PARENT/name),'Fixed parent paths');blobs[name]=load(r,sources)
 require(manifest['receipts']==[inventory[n+'.receipt.json']for n,u in PAGES],'All receipt roles')
 receipts={n:decode(blobs[n+'.receipt.json'])for n,u in PAGES}
 for n,u in PAGES:require(receipts[n]['response_reference']==inventory[n+'.response.bin'],'Receipt original raw role')
 companiesref=dict(path=str(ORIGINAL/'companies.response.bin'),sha256=COMPANIES_SHA);companies=load(companiesref,sources)
 def guard():
  require(sha(SOURCE.read_bytes())==LOADED,'Loaded diagnostic source');require({p.name for p in PARENT.iterdir()}==expected|{'manifest.json'},'Capture namespace')
  for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
 guard();OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
 try:
  saved.append(save('started.json',dict(schema='OFFICIAL_MISSING_TICKER_OFFLINE_STARTED_V1',manifest_reference=mr,companies_reference=companiesref,source_hashes=sources,**FLAGS)))
  result=diagnose(companies,{n:blobs[n+'.response.bin']for n,u in PAGES},receipts);result.update(manifest_reference=mr,companies_reference=companiesref,source_hashes=sources)
  saved.append(save('diagnostic.json',result));guard()
  for r in saved:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final diagnostic bytes')
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','diagnostic.json'},'Exact output namespace');return saved[-1]
 except BaseException as e:save('failure.json',dict(status='FAILED_NO_RETRY',error=dict(type=type(e).__name__,message=str(e)),saved_references=saved,**FLAGS));raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
