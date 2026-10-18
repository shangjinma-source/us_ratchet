"""Read saved official FX bytes independently; no capture, conversion or account."""
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, date
from decimal import Decimal
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/official_fx_capture_20261003_v1'
MANIFEST='9e14efd21143687374425e7759c1f468a8cd99009164167f5b60f43fa96898e4'
HISTORY='f3a317fd00800fe025003479358a6798cd893d4305511bcb1c39eb73ae94e2f5'
URLS={'country_data':'https://www.federalreserve.gov/releases/h10/Hist/',
 'china_history':'https://www.federalreserve.gov/releases/h10/Hist/dat00_ch.htm',
 'fred_series':'https://fred.stlouisfed.org/series/DEXCHUS'}
def check(ok,msg):
 if not ok: raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(ref):
 raw=(ROOT/ref['path']).read_bytes();check(sha(raw)==ref['sha256'],'SHA '+ref['path']);return raw
def timestamp(value):
 parsed=datetime.fromisoformat(value);check(parsed.tzinfo is not None,'Aware time');return parsed
class Table(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.active=False;self.cell=None;self.row=None;self.rows=[];self.tables=0;self.text=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='table' and 'pubtables' in a.get('class','').split():self.active=True;self.tables+=1
  if self.active and tag=='tr':self.row=[];self.line=self.getpos()[0]
  if self.active and self.row is not None and tag in ('th','td'):self.cell=[]
 def handle_data(self,data):
  self.text.append(data)
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ('th','td') and self.cell is not None:
   self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
  if tag=='tr' and self.active and self.row is not None:self.rows.append((self.line,self.row));self.row=None
  if tag=='table':self.active=False
def verify():
 manifest=json.loads(read({'path':str((BASE/'manifest.json').relative_to(ROOT)),'sha256':MANIFEST}))
 check(manifest['schema']=='OFFICIAL_FX_SOURCE_CAPTURE_V1' and manifest['status']=='SAVED_SOURCE_ONLY','Manifest')
 for k in ('historical_available_at_verified','point_in_time_verified','benchmark_qualified','execution_authorized','promotion_allowed','rates_parsed'):check(manifest[k] is False,k)
 check(sha((ROOT/'scripts/ndx_official_fx_capture_20261003.py').read_bytes())==manifest['source_sha256'],'Capture code')
 start=json.loads((BASE/'started.json').read_bytes());check(start['source_sha256']==manifest['source_sha256'] and start['requested_urls']==list(URLS.values()),'Started')
 check({p.name for p in BASE.iterdir()}=={'started.json','manifest.json'}|{n+s for n in URLS for s in ('.html','.receipt.json')},'Namespace')
 prior=timestamp(start['started_at']);docs={};refs={};receipts={}
 check([x['name'] for x in manifest['sources']]==list(URLS),'Sources')
 for entry in manifest['sources']:
  name=entry['name'];raw=read(entry['raw']);r=json.loads(read(entry['receipt']))
  check(r['raw_reference']==entry['raw'] and r['bytes']==len(raw),'Receipt bytes')
  check(r['requested_url']==r['final_url']==URLS[name] and type(r['http_status']) is int and r['http_status']==200,'URL/status')
  check(r['content_type'].startswith('text/html'),'HTML')
  begin,end=timestamp(r['read_started_at']),timestamp(r['read_completed_at'])
  check(prior<=begin<=end<=timestamp(manifest['completed_at']),'Clock order');prior=end
  docs[name]=raw.decode('utf-8');refs[name]=entry;receipts[name]=r
 clauses={'direction':'Rates in Chinese yuan per U.S. dollar','release':'Bilateral exchange rate data are updated every Monday at 4:15 p.m. Data are available up through Friday of the previous business week.',
 'definition':'The data are noon buying rates in New York for cable transfers payable in foreign currencies.'}
 locators={}
 for kind,quote in clauses.items():
  name='china_history' if kind=='direction' else 'country_data';p=Table();p.feed(docs[name]);text=' '.join(' '.join(p.text).split())
  check(quote in text,'Official clause '+kind);locators[kind]={'quote':quote,'source_reference':refs[name]['raw'],'normalized_text_codepoint_offset':text.index(quote)}
 check('DEXCHUS' in docs['fred_series'],'FRED series')
 p=Table();p.feed(docs['china_history']);check(p.tables==1,'Single rate table')
 rows=[];previous=''
 for index,(line,cells) in enumerate(p.rows):
  check(len(cells)==2,'Date/rate cells');literal,value=cells
  check(re.fullmatch(r'\d{1,2}-[A-Z]{3}-\d{2}',literal) is not None,'Date grammar')
  day=datetime.strptime(literal,'%d-%b-%y').date().isoformat();check(day>previous,'Date order/duplicate');previous=day
  number=None if value=='ND' else Decimal(value)
  check(number is None or number.is_finite() and number>0,'Finite positive rate')
  rows.append({'date':day,'date_literal':literal,'rate_literal':value,'rate_decimal':None if number is None else str(number),'status':'NOT_AVAILABLE_ND' if number is None else 'REPORTED_RATE',
   'source_reference':dict(refs['china_history']['raw'],table_row_index=index,html_line=line),'historical_available_at':None})
 h=json.loads(read({'path':'data/cache/research/bulk_history_requirements_20261003_v1/requirements.json','sha256':HISTORY}))
 s=[x for x in h['requirements']['scenarios'] if x['price_window_length']==253];check(len(s)==1,'253 scenario')
 days=s[0]['required_reference_price_dates'];check(len(days)==253 and days==sorted(set(days)),'253 calendar')
 bydate={r['date']:r for r in rows};window=[]
 for day in days:window.append({'session':day,'rate_row':bydate.get(day),'status':'DATE_ABSENT' if day not in bydate else bydate[day]['status']})
 counts={v:sum(r['status']==v for r in window) for v in ('REPORTED_RATE','NOT_AVAILABLE_ND','DATE_ABSENT')}
 release=re.search(r'Release Date:\s*([^<]+)',docs['china_history']);check(release is not None,'Release label')
 result={'schema':'OFFICIAL_FX_INDEPENDENT_SAVED_READBACK_V1','status':'PASS','manifest_sha256':MANIFEST,'history_requirements_sha256':HISTORY,'reader_sha256':sha(Path(__file__).read_bytes()),'source_references':refs,'receipts':receipts,'official_clauses':locators,'page_release_label':release.group(1).strip(),
  'rate_direction':'CNY_PER_USD','frequency':'DAILY_OBSERVATION_WEEKLY_PUBLICATION','table_rows':rows,'window_253':window,'summary':dict(table_row_count=len(rows),table_first=rows[0]['date'],table_last=rows[-1]['date'],table_nd_count=sum(r['rate_decimal'] is None for r in rows),window_first=days[0],window_last=days[-1],window_count=len(days),**counts),'historical_available_at_verified':False,'point_in_time_verified':False,'benchmark_qualified':False,'fx_conversion_performed':False,'account_executed':False,'capture_repeated':False,
  'limitations':['CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE','OBSERVATION_DATE_NOT_PUBLICATION_TIMESTAMP','NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX','NO_FILL_FOR_ND_OR_ABSENT_DATES','FRED_PAGE_CORROBORATES_SERIES_ONLY_NOT_INDEPENDENT_RATE_DOWNLOAD']}
 return result
if __name__=='__main__':
 result=verify();out=ROOT/'DYNAMIC_OFFICIAL_FX_INDEPENDENT_READBACK_20261003.json'
 with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
 print(json.dumps({'status':result['status'],'reader_sha256':result['reader_sha256'],'summary':result['summary'],'output_sha256':sha(out.read_bytes())},indent=2))
