"""New source-bound genesis readback; never calls old readers, policy cores or writers."""
import argparse,csv,hashlib,io,json,os
from copy import deepcopy
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research';OUTPUT=BASE/'gap_monthly_policy_history_input_readback_20261003_v1'
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
BOUND={
 'policy':('data/cache/research/gap_monthly_policy_20261002_v1/policy.json','d04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'),
 'publication':('data/cache/research/gap_monthly_policy_20261002_v1/publication.json','23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'),
 'policy_started':('data/cache/research/gap_monthly_policy_20261002_v1/started.json','775c8795d5cb1b6510b867b9474170f47d7036a7637c3c0dac790f5397c5cc8a'),
 'frontier':('data/cache/research/observation_gap_frontier_20261002_v1/frontier.json','a463539f706db1925c52cab0f8d1a4da34eb36b62e915b1842e9cbe229062170'),
 'frontier_publication':('data/cache/research/observation_gap_frontier_20261002_v1/publication.json','36c99f365a545f3c508795a8a1db39ed9afcddf4120dd4aa7ad73ad1b50abe44'),
 'frontier_started':('data/cache/research/observation_gap_frontier_20261002_v1/started.json','ac8761bdfe4b92dfe53054fa6e58438cac9f89d814c8d7dd667dcfbe9f5e0bb9'),
 'QQQ':('data/cache/research/observation_gap_classification_20261002_v1/QQQ.csv','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'SPY':('data/cache/research/observation_gap_classification_20261002_v1/SPY.csv','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'),
 'user_choice':('DYNAMIC_GAP_MONTHLY_POLICY_USER_DECISION_20261002.md','f661616a86dca8e80aa3e8bcea1b55c29b97760e993948049327fe1a38d84906'),
 'policy_core':('backtest/ndx_gap_monthly_observation_policy_research.py','aab44a1cd8c41be42ace2061b788865d90f83e9c678f6daa59560809edfc7e1b'),
 'policy_producer':('scripts/ndx_gap_monthly_policy_20261002.py','5d31121012d81118af9ad12ffd0cf9a4539032cbf0a136d8c7884a5d2cce5019'),
 'frontier_core':('backtest/ndx_observation_gap_frontier_research.py','6588c37907a281012c4573337a6ea1261db6ad869835758c4cd8347a9d33feaf'),
 'frontier_producer':('scripts/ndx_observation_gap_frontier_20261002.py','58a5f2c152230f090d8cd7f0e897349a0bb354fede828871fc528d391601ee7e'),
 'historical_reader':('scripts/ndx_gap_monthly_policy_independent_review_20261002.py','f286545c57a4eb6344df785aa04f5153f3994f227c0af5db4a9f1e1aa675aa01'),
 'historical_review_note':('DYNAMIC_GAP_MONTHLY_POLICY_INDEPENDENT_READBACK_20261002.md','8d8361682d6349be549ee31098823e09679d379f778ebb555cc6a15a274461cf')}
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','clock_authenticity_verified','provider_authenticity_verified','source_publication_time_verified','input_timeliness_verified','seal_performed','future_independent_oos','observation_created','old_audit_repeated','old_policy_recomputed','old_calendar_mutated','network_capture_performed','full_transitive_source_closure_reverified'),False)
AUTH=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed')

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n):require(type(v)is int and v==n,'Exact integer')
def reference(p,h):return dict(path=str(p),sha256=h)
def loads(raw):
 def pairs(rows):
  d={}
  for k,v in rows:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def calendar(values):
 require(values and all(type(s)is str and date.fromisoformat(s).isoformat()==s and date.fromisoformat(s).weekday()<5 for s in values),'Canonical weekday dates')
 exact(values,sorted(set(values)),'Full ordered unique calendar')
def csv_prefix(raw,dates,ref):
 require(0<len(raw)<=16*1024**2,'Bounded full CSV bytes');text=raw.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(text,newline=''))
 fields=['Date','Open','High','Low','Close','Volume'];exact(reader.fieldnames,fields,'Original CSV header');rows=list(reader);require(0<len(rows)<=20000,'Bounded full rows')
 require(all(set(r)==set(fields) and all(type(v)is str and v for v in r.values()) for r in rows),'Complete original fields')
 calendar([r['Date'] for r in rows]);positions=[i for i,r in enumerate(rows) if r['Date']>=dates[0]]
 exact([rows[i]['Date']for i in positions],dates,'Full required prefix, no missing/extra source date')
 return dict(reference=deepcopy(ref),full_csv_row_count=len(rows),full_csv_sha256=sha(raw),original_data_row_start=positions[0],original_data_row_stop_exclusive=positions[-1]+1,required_rows=[dict(original_data_row_index=i,raw_row=deepcopy(rows[i]))for i in positions],price_values_validated=False,scope='FULL_ORIGINAL_BYTES_AND_ROW_LOCATORS;NOT_PRICE_OR_PROVIDER_CERTIFICATION')

def inspect(d,refs,raws):
 p,u,f,fu=d['policy'],d['publication'],d['frontier'],d['frontier_publication']
 require(p['schema']=='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1' and p['policy_id']==POLICY,'Original policy')
 require(u['schema']=='GAP_MONTHLY_POLICY_PUBLICATION_V1' and u['status']=='PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL','Policy publication')
 require(f['schema']=='OBSERVATION_GAP_FRONTIER_RESEARCH_V1','Frontier')
 require(fu['schema']=='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1' and fu['status']=='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY','Frontier publication')
 exact(u['policy_reference'],refs['policy'],'Policy receipt');exact(fu['frontier_reference'],refs['frontier'],'Frontier receipt')
 for obj in (p,u,f,fu):
  for flag in AUTH:require(obj[flag]is False,'No inherited authority')
 for doc,pub,start in ((p,u,d['policy_started']),(f,fu,d['frontier_started'])):
  exact(pub['source_hashes'],doc['source_hashes'],'Parent publication source claims');exact(start['source_hashes'],doc['source_hashes'],'Started source claims');require(start['retry_allowed']is False,'Original no retry')
 policy_sources={refs[k]['path']:refs[k]['sha256']for k in ('frontier','frontier_publication','user_choice','policy_core','policy_producer')}
 exact(p['source_hashes'],policy_sources,'Fixed policy source closure')
 expected_input=dict(frontier=refs['frontier'],publication=refs['frontier_publication'],user_choice=refs['user_choice'],core=refs['policy_core'])
 exact(p['input_references'],expected_input,'Policy input roles');exact(p['frontier_reference'],refs['frontier'],'Frontier link');exact(p['user_choice_reference'],refs['user_choice'],'Choice link')
 require(POLICY in raws['user_choice'].decode('utf-8-sig') and '> 按首次实际观察延续：缺口不占月首机会（更贴近原合同）' in raws['user_choice'].decode('utf-8-sig'),'Explicit saved choice')
 rows=p['projection_inputs']['known_rows'];integer(len(rows),65);exact(p['projection_inputs']['policy_id'],POLICY,'Projection policy');exact(p['projection_inputs']['new_prospective_observations'],[],'No prospective history');integer(p['new_observation_count'],0);integer(p['prospective_monthly_coordinate_count'],0)
 frontier=f['known_accounted_rows'];integer(len(frontier),65);exact(p['saved_frontier_rows'],frontier,'Complete saved frontier copy')
 dates=[r['session']for r in rows];calendar(dates);exact((dates[0],dates[-1]),('2026-07-01','2026-10-01'),'Fixed genesis interval')
 for i,(r,fr) in enumerate(zip(rows,frontier)):
  gap=i>=60;kind='MISSED_OBSERVATION'if gap else 'SEALED_PARENT_OBSERVED_SESSION';integer(r['sequence'],i+1)
  exact(r,dict(sequence=i+1,session=fr['session'],kind=kind,evidence_reference=dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'),seal_status='NOT_ATTEMPTED'if gap else 'UNKNOWN'),'Original typed row and pointer')
  require(fr['kind']==kind,'Original frontier kind')
  if gap:
   exact(sorted(fr),sorted(('counts_as_observed_session','decision_eligible','gap_event_index','gap_event_sha256','kind','session')),'Exact saved gap row schema')
   require(fr['counts_as_observed_session']is False and fr['decision_eligible']is False,'Gap not observation');integer(fr['gap_event_index'],i-60)
   require(type(fr['gap_event_sha256'])is str and len(fr['gap_event_sha256'])==64 and all(c in '0123456789abcdef' for c in fr['gap_event_sha256']),'Saved gap event hash')
  else:
   exact(sorted(fr),sorted(('eligibility_reverified','kind','parent_session_index','session')),'Exact saved observed row schema')
   require(fr['eligibility_reverified']is False,'Historical eligibility not reverified');integer(fr['parent_session_index'],i)
 exact(f['last_observed_session'],'2026-09-24','Observed cursor');exact(f['last_accounted_session'],'2026-10-01','Accounted cursor')
 exact([r['session']for r in rows[60:]],['2026-09-25','2026-09-28','2026-09-29','2026-09-30','2026-10-01'],'All five gaps preserved')
 months={}
 for row in rows:
  month=months.setdefault(row['session'][:7],dict(month=row['session'][:7],first_observed_session=None,observed_count=0,missed_count=0))
  if row['kind']=='MISSED_OBSERVATION':month['missed_count']+=1
  else:
   month['observed_count']+=1
   if month['first_observed_session']is None:month['first_observed_session']=row['session']
 exact(p['projection']['months'],list(months.values()),'Saved month input coordinates and counts')
 require(months['2026-10']==dict(month='2026-10',first_observed_session=None,observed_count=0,missed_count=1),'October gap does not consume first actual')
 baseline={t:deepcopy(refs[t])for t in ('QQQ','SPY')};details={} 
 for t in baseline:
  exact(f['input_references'][t],refs[t],'Frontier baseline role');require(f['source_hashes'].get(refs[t]['path'])==refs[t]['sha256'],'Frontier raw baseline binding');require(sha(raws[t])==refs[t]['sha256'],'Consumed original CSV bytes');details[t]=csv_prefix(raws[t],dates,refs[t])
 return dict(policy_reference=deepcopy(refs['policy']),publication_reference=deepcopy(refs['publication']),baseline_references=baseline,frontier_reference=deepcopy(refs['frontier']),frontier_publication_reference=deepcopy(refs['frontier_publication']),known_typed_rows_preserved=deepcopy(rows),saved_frontier_rows_preserved=deepcopy(frontier),known_rows_sha256=sha(enc(rows)),first_actual_observed_session_by_month={k:v['first_observed_session']for k,v in months.items()},monthly_input_coordinate_checks=list(months.values()),baseline_details=details,counts=dict(known_rows=65,observed_rows=60,gap_rows=5,new_observation_count=0),first_session=dates[0],last_observed_session=f['last_observed_session'],last_accounted_session=f['last_accounted_session'],historical_review_evidence=dict(reader_reference=refs['historical_reader'],note_reference=refs['historical_review_note'],role='HISTORICAL_TEXT_AND_COUNT_RETURNING_CODE_NOT_A_PERSISTED_MACHINE_PASS_RECEIPT'),scope='NEW_GENESIS_SOURCE_AND_PREFIX_BINDING;NOT_OLD_AUDIT_REEXECUTION_OR_PRICE_TIME_PROVIDER_AUTHENTICATION',**FLAGS)

def guard(sources):
 for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def namespaces(refs):
 for role,names in [('policy',{'started.json','policy.json','publication.json'}),('frontier',{'started.json','frontier.json','publication.json'})]:
  folder=Path(refs[role]['path']).parent;require({x.name for x in folder.iterdir()}==names,'Exact successful saved parent namespace');require(all(x.is_file() and not x.is_symlink()for x in folder.iterdir()),'Regular parent files')
def save(p,v):
 b=enc(v)
 with p.open('xb')as s:s.write(b);s.flush();os.fsync(s.fileno())
 require(p.read_bytes()==b,'Report saved bytes');return reference(p,sha(b))
def readback(*,execute=False):
 require(execute is True,'Explicit execute');require(not OUTPUT.exists(),'Create-only no retry');refs={k:reference(ROOT/p,h)for k,(p,h)in BOUND.items()};sources={str(SOURCE):LOADED};raws={}
 for k,r in refs.items():
  b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Pinned source '+k);require(r['path']not in sources or sources[r['path']]==r['sha256'],'Source conflict');sources[r['path']]=r['sha256'];raws[k]=b
 namespaces(refs);guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  save(OUTPUT/'started.json',dict(schema='GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_STARTED_V1',input_references=refs,source_hashes=sources,**FLAGS))
  docs={k:loads(raws[k])for k in ('policy','publication','policy_started','frontier','frontier_publication','frontier_started')};detail=inspect(docs,refs,raws);guard(sources);namespaces(refs)
  result=save(OUTPUT/'independent_readback.json',dict(schema='GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1',status='PASS',reader_sha256=LOADED,input_references=refs,source_hashes=sources,**detail))
  guard(sources);namespaces(refs);require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact output namespace');require(sha(Path(result['path']).read_bytes())==result['sha256'],'Final report bytes');return result
 except BaseException as error:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False,**FLAGS));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
