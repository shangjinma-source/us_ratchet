"""Offline direct JSON-LD inspection; missing ticker fields are never backfilled."""
from pathlib import Path
from hashlib import sha256
from html.parser import HTMLParser
import json,os,re
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
PARENT=ROOT/'data/cache/research/official_ndx_public_access_20261003_v1'
OUTPUT=ROOT/'data/cache/research/official_ndx_public_jsonld_diagnostic_20261003_v1'
PINS={'manifest.json':'7b4cde9d1426ceb2339c5b5681661588ce0092f2eabb64db50d56fb4f13ca6b3','companies.response.bin':'85e45efcd7c85c80b5fb198e131d717be48fb97940c2d6a343f333afa8a41561','companies.receipt.json':'af6b731db81f16d2613592f3fba0efd559c26a51d68742221ee3122fe46e8095'}
class Parser(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=False);self.active=False;self.fragments=[];self.documents=[]
 def handle_starttag(self,t,a):
  if t=='script':self.active=dict(a).get('type')=='application/ld+json';self.fragments=[]
 def handle_data(self,s):
  if self.active:self.fragments.append(s)
 def handle_endtag(self,t):
  if t=='script'and self.active:self.documents.append(''.join(self.fragments));self.active=False
def require(ok,msg):
 if not ok:raise ValueError(msg)
def inspect(raw):
 p=Parser();p.feed(raw.decode('utf-8'));found=[]
 def walk(v,path,script_index):
  if type(v)is dict:
   if v.get('@type')=='ItemList':found.append((script_index,path,v))
   for k,x in v.items():walk(x,path+'/'+k.replace('~','~0').replace('/','~1'),script_index)
  elif type(v)is list:
   for i,x in enumerate(v):walk(x,path+'/'+str(i),script_index)
 for i,t in enumerate(p.documents):walk(json.loads(t),'',i)
 require(len(found)==1,'Exactly one direct ItemList');i,ptr,node=found[0];items=node['itemListElement'];require(type(items)is list,'Rows')
 rows=[];seen=set()
 for j,item in enumerate(items):
  require(type(item.get('position'))is int and item['position']==j+1,'Complete source positions')
  require(type(item.get('name'))is str and item['name'].strip(),'Source name')
  ticker=item.get('description');valid=type(ticker)is str and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}',ticker)is not None
  if valid:require(ticker not in seen,'Duplicate direct ticker');seen.add(ticker)
  rows.append(dict(position=j+1,original_item=item,json_pointer=ptr+'/itemListElement/'+str(j),ticker=ticker,ticker_status='DIRECT_SOURCE_FIELD'if valid else'MISSING_OR_INVALID_SOURCE_FIELD'))
 return dict(jsonld_script_index=i,jsonld_script_text_sha256=sha256(p.documents[i].encode()).hexdigest(),itemlist_json_pointer=ptr,itemlist_original=node,rows=rows,row_count=len(rows),direct_unique_ticker_count=len(seen),missing_ticker_positions=[r['position']for r in rows if r['ticker_status']!='DIRECT_SOURCE_FIELD'],symbol_inventory_complete=len(seen)==len(rows),direct_multiple_share_class_symbols=[x for x in ('GOOG','GOOGL')if x in seen],multiple_share_class_note='Symbols retained separately; shared issuer identity not inferred here.',date_fields_on_itemlist={k:v for k,v in node.items()if any(w in k.lower()for w in ('date','time','effective'))},publication_date=None,membership_effective_date=None)
def run():
 require(not OUTPUT.exists(),'Create-only supplemental diagnostic');sources={str(SOURCE):sha256(SOURCE.read_bytes()).hexdigest()};raws={}
 for name,h in PINS.items():
  p=PARENT/name;b=p.read_bytes();require(sha256(b).hexdigest()==h,'Fixed source hash');sources[str(p)]=h;raws[name]=b
 m=json.loads(raws['manifest.json']);r=json.loads(raws['companies.receipt.json']);require(r['response_reference']['sha256']==PINS['companies.response.bin']and r['body_complete']is True,'Receipt body association')
 require(next(x for x in m['outputs']if Path(x['path']).name=='companies.receipt.json')['sha256']==PINS['companies.receipt.json'],'Manifest receipt association')
 result=inspect(raws['companies.response.bin'])
 report=dict(schema='OFFICIAL_NDX_SAVED_JSONLD_DIAGNOSTIC_V1',status='PARTIAL_SYMBOL_INVENTORY_DIRECT_OFFICIAL_PAGE',inspection=result,source_hashes=sources,capture_interval=[r['started_at_utc'],r['completed_at_utc']],correction='Earlier HTML-table-only diagnostic does not establish absence of a JSON-LD list. Actual saved body contains 101 names/positions, with some ticker fields missing; do not backfill.',network_called=False,old_mapping_used=False,membership_complete=False,point_in_time_verified=False,publication_time_verified=False,membership_effective_date_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)
 OUTPUT.mkdir(parents=True);out=OUTPUT/'diagnostic.json';b=(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
 with out.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 for p,h in sources.items():require(sha256(Path(p).read_bytes()).hexdigest()==h,'Source drift')
 require(out.read_bytes()==b,'Output drift');return dict(path=str(out),sha256=sha256(b).hexdigest(),row_count=result['row_count'],unique_tickers=result['direct_unique_ticker_count'],missing=result['missing_ticker_positions'])
if __name__=='__main__':print(json.dumps(run()))
