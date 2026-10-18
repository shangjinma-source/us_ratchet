"""Create-only variable-history local cache capture. No network or observation append."""
import argparse,hashlib,json,os,shutil,types
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/variable_prefix_source_capture_20261003_v1'
PARENT_BOUND={
 'reference':('data/cache/research/prospective_observation_parent_history_20261003_v1/history.json','bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'),
 'publication_reference':('data/cache/research/prospective_observation_parent_history_20261003_v1/publication.json','648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'),
 'readback_reference':('data/cache/research/prospective_observation_parent_history_independent_readback_20261003_v1/independent_readback.json','c6f9a113b1b5f00128befa74a415e6604012d47ac17eb7db2048dafa8a31a86a'),
 'reader_reference':('scripts/ndx_prospective_observation_parent_history_independent_readback_20261003.py','876094538679db3216f69cf3035101baf91498d5296512cbef4b2911486d7aef')}
PINS={
 'core':('backtest/ndx_variable_prefix_capture_research.py','9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039'),
 'scoped':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
 'base':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'tzif':('D:/python/Lib/site-packages/tzdata/zoneinfo/America/New_York','d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9')}
# Exact current-cache paths from the frozen scoped capture writer, not guessed endpoints.
CURRENT={t:ROOT/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')}
FLAGS=dict.fromkeys(('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified','timeliness_verified','filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','partial_recovery_performed','missed_events_created','network_quote_refresh_performed','old_audit_repeated','full_transitive_source_closure_reverified'),False)
MIN_FREE=5*1024**3

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(enc(a)==enc(b),'Exact saved values/types')
def ref(p,h):
 require(type(p)is str and p and p.strip()==p and type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'Pending immutable anchor');return dict(path=p,sha256=h)
def configured(bound):
 out={}
 for k,v in bound.items():require(type(v)is tuple and len(v)==2,'Pending immutable anchor');out[k]=ref(str(ROOT/v[0]),v[1])
 return out
def merge(s,r):
 ref(r['path'],r['sha256']);require(r['path']not in s or s[r['path']]==r['sha256'],'Conflicting source');s[r['path']]=r['sha256']
def loads(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def read(r,s):
 merge(s,r);p=Path(r['path']);require(p.is_file()and not p.is_symlink(),'Regular source');b=p.read_bytes();require(sha(b)==r['sha256'],'Source SHA');return b
def guard(s):
 require(sha(SOURCE.read_bytes())==LOADED,'Loaded source drift')
 for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def guard_capture(s,live):
 guard(s)
 for r in live.values():require(sha(Path(r['path']).read_bytes())==r['sha256'],'Current cache drift during capture')
def reject_live_claims(s):
 live={p.resolve()for p in CURRENT.values()}
 require(all(Path(p).resolve()not in live for p in s),'UNSUPPORTED_PARENT_LIVE_CACHE_SOURCE_CLAIM')
def resource_gate(n=0):
 require(type(n)is int and n>=0,'Exact reserve');require(shutil.disk_usage(Path(OUTPUT.anchor)).free>=MIN_FREE+n,'RESOURCE_STOP_BEFORE_WRITE')
def save_bytes(p,b):
 if p.name!='failure.json':resource_gate(len(b))
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved bytes');return ref(str(p),sha(b))
def save(p,v):return save_bytes(p,enc(v))
def now():return datetime.now(timezone.utc).isoformat()
def namespace(p,names):
 items=list(p.iterdir());exact(sorted(x.name for x in items),sorted(names));require(all(x.is_file()and not x.is_symlink()for x in items),'Complete regular namespace')
def private_core(raw):
 modules={}
 for key in ('base','scoped','core'):
  require(sha(raw[key])==PINS[key][1],'Immediate code SHA');module=types.ModuleType('_capture_'+key);module.__file__=str(ROOT/PINS[key][0]);code=raw[key].decode('utf-8-sig')
  if key=='scoped':
   line='from backtest import ndx_forward_source_capture_research as capture';require(code.count(line)==1,'Explicit scoped dependency');code=code.replace(line,'');module.capture=modules['base']
  if key=='core':
   line='from backtest.ndx_forward_source_capture_scoped_research import scoped_csv';require(code.count(line)==1,'Explicit parser dependency');code=code.replace(line,'');module.scoped_csv=modules['scoped'].scoped_csv
  exec(compile(code,module.__file__,'exec'),module.__dict__);modules[key]=module
 require(modules['core'].SCOPED_PARSER_SHA256==PINS['scoped'][1]and modules['core'].PARSER_DEPENDENCY_SHA256==PINS['base'][1],'Dependency declarations')
 return modules['core']
def load():
 parentrefs=configured(PARENT_BOUND);refs=configured(PINS) # All pending gates before any reads.
 s={str(SOURCE):LOADED};raw={k:read(r,s)for k,r in refs.items()};parent=dict(parentrefs)
 for key,role in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
  r=parentrefs[role];require(not (Path(r['path']).parent/'failure.json').exists(),'Failed parent');parent[key]=loads(read(r,s))
  for p,h in parent[key]['source_hashes'].items():merge(s,ref(p,h))
 read(parentrefs['reader_reference'],s);reject_live_claims(s)
 folder=Path(parentrefs['reference']['path']).parent
 exact(parentrefs['publication_reference']['path'],str(folder/'publication.json'));exact(parentrefs['reference']['path'],str(folder/'history.json'));namespace(folder,('started.json','history.json','publication.json'))
 core=private_core(raw);h,_,_,_=core.inspect_parent(parent)
 baseline={t:read(h['baseline_references'][t],s)for t in ('QQQ','SPY')};guard(s)
 return parent,parentrefs,refs,raw,baseline,s,core

def validate_plan(plan,parent,snapshots,start,end):
 exact(plan['schema'],'COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1');exact(plan['parent_history_reference'],parent['reference']);exact(plan['parent_publication_reference'],parent['publication_reference']);exact(plan['parent_readback_reference'],parent['readback_reference'])
 exact(plan['known_typed_rows_preserved'],parent['document']['known_typed_rows']);exact(plan['parent_attempt_inventory_preserved'],parent['document']['parent_attempt_inventory']);exact(plan['baseline_references'],parent['document']['baseline_references']);exact(plan['capture_started_at'],start);exact(plan['capture_completed_at'],end)
 for key in FLAGS:
  if key not in ('network_quote_refresh_performed','old_audit_repeated','full_transitive_source_closure_reverified'):require(plan[key]is False,'No upgraded authority')
 for t in ('QQQ','SPY'):exact(plan['source_evidence'][t]['source_reference'],snapshots[t]);exact(plan['source_evidence'][t]['baseline_reference'],parent['document']['baseline_references'][t])
 require(plan['status']in ('ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED','NO_NEW_SESSION','BLOCKED_SOURCE_DIAGNOSTICS'),'Plan status')

def run(*,execute=False):
 require(execute is True,'Explicit capture');parent,pr,refs,raw,baseline,s,core=load();require(not OUTPUT.exists(),'Create-only no retry');resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  save(OUTPUT/'started.json',dict(schema='VARIABLE_PREFIX_CAPTURE_STARTED_V1',parent_references=pr,input_references=refs,source_hashes=dict(s),retry_allowed=False,**FLAGS));guard(s)
  start=now();current={t:CURRENT[t].read_bytes()for t in ('QQQ','SPY')};end=now()
  live={t:ref(str(CURRENT[t]),sha(b))for t,b in current.items()}
  reject_live_claims(s)
  guard_capture(s,live);snapshots={t:save_bytes(OUTPUT/f'{t}.csv',b)for t,b in current.items()};tz=save_bytes(OUTPUT/'New_York.tzif',raw['tzif'])
  for r in [*snapshots.values(),tz]:merge(s,r)
  plan=core.plan_history_capture(parent=parent,source_bytes=current,source_references=snapshots,baseline_bytes=baseline,capture_started_at=start,capture_completed_at=end,tzif_bytes=raw['tzif'],tzif_reference=tz)
  validate_plan(plan,parent,snapshots,start,end);guard_capture(s,live)
  capture=save(OUTPUT/'capture.json',dict(schema='SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1',plan=plan,parent_references=pr,input_references=refs,captured_artifacts=dict(snapshots,tzif=tz),current_cache_references=live,current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',source_hashes=dict(s),capture_started_at=start,capture_completed_at=end,clock_captured_by_runner=True,external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',**FLAGS))
  pub=save(OUTPUT/'publication.json',dict(schema='VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=capture,source_hashes=dict(s),**FLAGS));guard_capture(s,live)
  for r in (capture,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final artifact bytes')
  namespace(OUTPUT,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'));return dict(capture_reference=capture,publication_reference=pub)
 except BaseException as e:
  save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),retry_allowed=False,**FLAGS));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
