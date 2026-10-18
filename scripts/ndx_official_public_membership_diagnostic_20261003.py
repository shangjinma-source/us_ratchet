"""Offline independent inspection of two externally anchored public HTML responses."""
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib.parse import urljoin
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/official_ndx_public_access_20261003_v1'
OUTPUT=ROOT/'data/cache/research/official_ndx_public_access_diagnostic_20261003_v1'
MANIFEST_SHA='7b4cde9d1426ceb2339c5b5681661588ce0092f2eabb64db50d56fb4f13ca6b3'
PRODUCER_SHA='d49ec401987ed7cbefc5bbf02a70753572a8cd10ea40175a0f6081433bd0c8d4'
def require(ok,msg):
 if not ok:raise ValueError(msg)
def read(ref,s):
 p=Path(ref['path']);raw=p.read_bytes();h=sha256(raw).hexdigest()
 require(h==ref['sha256'],'Source SHA');require('byte_count'not in ref or len(raw)==ref['byte_count'],'Source size')
 require(str(p)not in s or s[str(p)]==h,'Source conflict');s[str(p)]=h;return raw
class Parser(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.scripts=[];self.links=[];self.tables=[];self.text=[];self.inline=[];self.active_table=None;self.script=False;self.script_text=[];self.attrs=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='script':
   self.script=True;self.script_text=[]
   if a.get('src'):self.scripts.append(a['src'])
  if tag=='a' and a.get('href'):self.links.append(a['href'])
  if tag=='table':self.active_table={'attributes':a,'rows':0,'text':[]};self.tables.append(self.active_table)
  if tag=='tr' and self.active_table is not None:self.active_table['rows']+=1
  if any(k.startswith('data-')for k in a):self.attrs.append({'tag':tag,'attributes':{k:v for k,v in a.items()if k.startswith('data-')}})
 def handle_endtag(self,tag):
  if tag=='table':self.active_table=None
  if tag=='script':
   if self.script_text:self.inline.append(''.join(self.script_text))
   self.script=False
 def handle_data(self,t):
  if self.script:self.script_text.append(t)
  else:
   self.text.append(t)
   if self.active_table is not None:self.active_table['text'].append(t)
def run():
 require(not OUTPUT.exists(),'Create-only diagnostic');sources={str(SOURCE):LOADED}
 mp=PARENT/'manifest.json';m=json.loads(read({'path':str(mp),'sha256':MANIFEST_SHA},sources))
 require(m['schema']=='OFFICIAL_NDX_PUBLIC_ACCESS_EVIDENCE_V1','Manifest schema')
 require(m['source_reference']=={'path':str(ROOT/'scripts/ndx_official_public_membership_capture_20261003.py'),'sha256':PRODUCER_SHA},'Fixed capture source');read(m['source_reference'],sources)
 expected={'manifest.json','started.json','companies.response.bin','companies.receipt.json','giw_weighting.response.bin','giw_weighting.receipt.json'}
 require({p.name for p in PARENT.iterdir()}==expected,'Parent exact inventory')
 original={Path(r['path']).name:read(r,sources)for r in m['outputs']};pages=[]
 for name in ('companies','giw_weighting'):
  r=json.loads(original[name+'.receipt.json']);raw=original[name+'.response.bin']
  require(r['name']==name and r['schema']=='OFFICIAL_NDX_PUBLIC_PAGE_RECEIPT_V1','Receipt role')
  require(r['body_complete']is True and r['error']is None and r['transport_metadata']['http_status']==200,'Complete successful HTML')
  require(read(r['response_reference'],sources)==raw,'Receipt same body')
  p=Parser();p.feed(raw.decode('utf-8'));text=' '.join(' '.join(p.text).split());base=r['request']['url']
  tables=[dict(attributes=t['attributes'],row_element_count=t['rows'],text=' '.join(' '.join(t['text']).split()))for t in p.tables]
  inline_hints=[]
  for script in p.inline:
   for match in re.finditer(r'.{0,90}(?:https?://[^\s<>]+|ajax|endpoint|api/|fetch\().{0,130}',script,re.I):inline_hints.append(match.group(0))
  pages.append(dict(name=name,response_reference=r['response_reference'],receipt_reference=next(x for x in m['receipts']if Path(x['path']).name==name+'.receipt.json'),
   capture_interval_utc=[r['started_at_utc'],r['completed_at_utc']],
   data_unavailable_text_present='Data is currently not available'in text,
   login_for_full_access_text_present='Log in for Full Access'in text,
   displayed_dates=sorted(set(re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b',text))),
   displayed_dates_not_membership_effective_dates=True,tables=tables,
   script_references=[urljoin(base,u)for u in p.scripts],
   download_or_api_links=[urljoin(base,u)for u in p.links if any(k in u.lower()for k in ('download','csv','api','weight','component','spec'))],
   inline_public_data_hints=inline_hints,data_attributes=p.attrs,
   no_member_rows_established_by_this_inspection=True))
 report=dict(schema='OFFICIAL_NDX_SAVED_PUBLIC_PAGE_DIAGNOSTIC_V1',status='DIAGNOSED_SAVED_RESPONSES_NOT_MEMBERSHIP_CERTIFICATION',
  manifest_reference={'path':str(mp),'sha256':MANIFEST_SHA},source_hashes=sources,pages=pages,
  scope='HTML_TABLE_AND_EXPLICIT_LINK_INSPECTION_NO_JAVASCRIPT_EXECUTION',
  membership_complete=False,publication_time_verified=False,membership_effective_date_verified=False,
  point_in_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False,
  network_called=False,old_parser_or_mapping_used=False,all_public_endpoints_unavailable_proven=False,
  next_step='Only separately registered capture of actually listed data-component scripts; no guessed API or authorization bypass.')
 OUTPUT.mkdir(parents=True)
 try:
  raw=(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();out=OUTPUT/'diagnostic.json'
  with out.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
  for path,h in sources.items():require(sha256(Path(path).read_bytes()).hexdigest()==h,'Source changed')
  require({p.name for p in PARENT.iterdir()}==expected,'Parent inventory changed')
  require(out.read_bytes()==raw and {p.name for p in OUTPUT.iterdir()}=={'diagnostic.json'},'Diagnostic output changed')
  return dict(path=str(out),sha256=sha256(raw).hexdigest(),pages=[dict(name=p['name'],dates=p['displayed_dates'],tables=p['tables'])for p in pages])
 except BaseException as e:
  with (OUTPUT/'failure.json').open('x',encoding='utf-8')as f:json.dump(dict(status='FAILED_NO_RETRY',type=type(e).__name__,message=str(e)),f)
  raise
if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False))
