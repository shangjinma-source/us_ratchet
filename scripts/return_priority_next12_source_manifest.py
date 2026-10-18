"""Create a source-only next12 manifest; never produce strategy arguments."""
import csv,gzip,hashlib,json,math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/next12_candidate_source_manifest_20261014_v1.json'
def prepare():
 pins={};cache={}
 def read(path,expected=None):
  p=Path(path);p=p if p.is_absolute() else ROOT/p
  raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if expected and digest!=expected:raise ValueError('SOURCE_CHANGED:'+str(path))
  pins[p.relative_to(ROOT).as_posix()]=digest
  return raw
 def document(path):return json.loads(read(path))
 paths=[f'tmp/next12_monthly_source_scope_20261014_v{i}.json' for i in (1,2,3)]
 old,updated,latest=[document(p) for p in paths]
 identity_path='tmp/current_ten_identity_source_supplement_20261014_v2.json';identities=document(identity_path)
 bridge_path='tmp/next12_identity_action_review_20261014_v1.json';bridges=document(bridge_path)
 ea_path='tmp/next12_ea_alternate_source_20261014_v1/web_observation.json';ea=document(ea_path)
 for doc in (old,updated,latest,identities,bridges,ea):
  for p,h in doc.get('source_hashes',doc.get('source_pins',{})).items():read(p,h)
 identity_extra={r['ticker']:r for r in identities['rows']}
 new={r['ticker']:r for r in latest['new_member_coverage']}
 def source(path,ticker):
  if path in cache:return cache[path]
  raw=read(path);events=[];meta={}
  if path.endswith('.csv'):
   rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()));values={r['Date']:[r[k] for k in ('Open','High','Low','Close')] for r in rows};basis='ARCHIVE_COORDINATE_REVIEW_REQUIRED'
  else:
   body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw);channel=body['chart']['result'][0];meta=channel['meta']
   if meta['symbol']!=ticker:raise ValueError('SYMBOL_MISMATCH')
   zone=ZoneInfo(meta['exchangeTimezoneName']);day=lambda t:datetime.fromtimestamp(t,zone).date().isoformat();q=channel['indicators']['quote'][0]
   values={day(t):[q[k][i] for k in ('open','high','low','close')] for i,t in enumerate(channel.get('timestamp',[]))}
   events=[dict(kind=k,session=day(e['date']),payload=e) for k,records in channel.get('events',{}).items() for e in records.values()];basis='PROVIDER_QUOTE_COORDINATE_REVIEW_REQUIRED'
  cache[path]=(values,events,meta,basis);return cache[path]
 def valid(row,ohlc):
  try:
   v=[float(x) for x in row]
   return all(math.isfinite(x) and x>0 for x in v) and (not ohlc or v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1])
  except (TypeError,ValueError):return False
 windows=[]
 for base,membership in zip(old['windows'],updated['corrected_conditional_members']):
  assert base['decision_date']==membership['decision_date']
  oldrows={r['ticker']:r for r in base['candidates']};rows=[]
  for ticker in membership['members']:
   previous=oldrows.get(ticker,{})
   choices=[s['path'] for s in previous.get('source_candidates',[]) if s['path'].endswith(('.bin','.csv'))]
   current=f'data/cache/research/current_raw_capture_20261014_v1/{ticker}.response.bin'
   if (ROOT/current).exists():choices.insert(0,current)
   if ticker=='INSM':choices.insert(0,updated['insm']['raw_path'])
   sources=[]
   for p in dict.fromkeys(choices):
    values,events,meta,basis=source(p,ticker)
    sources.append(dict(path=p,sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),basis=basis,metadata={k:meta.get(k) for k in ('symbol','currency','instrumentType','exchangeTimezoneName')},missing_training_dates=[d for d in base['training_dates'] if not valid(values.get(d),False)],missing_execution_dates=[d for d in base['execution_dates'] if not valid(values.get(d),True)],returned_events=events,source_is_whole=True))
   alternate=None
   if ticker=='EA' and base['decision_date']=='2026-06-30':
    alternate=dict(path=ea_path,role='ENTIRE_EXECUTION_WINDOW_ONLY',missing_dates=sorted(set(base['execution_dates'])-{r['date'] for r in ea['rows']}),status='CONDITIONAL_WEB_OBSERVATION_REQUIRES_ADMISSION',overlap_differences=ea['archive_overlap_differences'],raw_http_authenticated=False)
   rows.append(dict(ticker=ticker,membership_status='DATED_OFFICIAL_EVENT_CHAIN_CONDITIONAL',identity_candidates=previous.get('identity_candidates',[]),prior_reviewed_identity_candidates=previous.get('prior_reviewed_identity_candidates',[]),additional_identity_evidence=identity_extra.get(ticker),period_identity_review=[b for b in bridges['identity_bridges'] if b['ticker']==ticker],source_candidates=sources,execution_alternate=alternate,training_numeric_complete=any(not s['missing_training_dates'] for s in sources),execution_numeric_complete=any(not s['missing_execution_dates'] for s in sources) or bool(alternate and not alternate['missing_dates']),identity_reviewed=False,coordinate_reviewed=False,status='PENDING_DATED_IDENTITY_AND_COORDINATE_ADMISSION'))
  windows.append(dict(decision_date=base['decision_date'],active_date=base['active_date'],training_dates=base['training_dates'],execution_dates=base['execution_dates'],members=membership['members'],member_count=len(rows),candidates=rows,membership_completeness_certified=False))
 return dict(schema='NEXT12_SOURCE_CANDIDATE_MANIFEST_V1',status='SOURCE_MANIFEST_NOT_EXECUTABLE_INPUT',windows=windows,hona_membership_sensitivity=dict(membership='UNRESOLVED_PRIMARY_INDEX_EFFECTIVE_DATE',if_member='EXCLUDED_TRAINING_RULE_ONLY_AFTER_NEW_ISSUANCE_IDENTITY_REVIEW',if_not_member='NOT_A_CANDIDATE',coverage=new['HONA'],parent_history_must_not_be_inherited=True,eligible_domain_equivalence='CONDITIONAL_ON_NEW_ISSUANCE_NO_PREDECESSOR_HISTORY_REVIEW',passive_hon_distribution_rights='SEPARATE_REQUIRED_ACCOUNTING'),source_hashes=pins,limitations=['No gross/search_arguments/decision nominal cost generated.','Source coverage never removes members based on future availability.','Identity observations later than decision are not backdated.','Empty provider events do not prove action completeness.','Cash dividends and distributed rights are not included by raw parent Close.'],economic_search_calls=0,book_calls=0)
if __name__=='__main__':
 if OUT.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
 result=prepare()
 with OUT.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
 print(json.dumps(dict(path=str(OUT),sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),windows=[dict(date=w['decision_date'],members=w['member_count'],training_missing=[r['ticker'] for r in w['candidates'] if not r['training_numeric_complete']],execution_missing=[r['ticker'] for r in w['candidates'] if not r['execution_numeric_complete']]) for w in result['windows']]),ensure_ascii=False))
