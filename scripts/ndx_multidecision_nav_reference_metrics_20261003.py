"""Source-bound 120-point external NAV reference; no fund or stock accounts."""
from pathlib import Path
from copy import deepcopy
import builtins,hashlib,json,os,re,shutil,traceback,types
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_nav_reference_metrics_20261003_v1'
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
BOUND={
 'alignment':('data/cache/research/nav_usd_observation_alignment_20261003_v1/alignment.json','ddd36e3bd3236d1494d9e42e08e66ce88e09d06c6c16f133c0214a951d54d90a'),
 'alignment_publication':('data/cache/research/nav_usd_observation_alignment_20261003_v1/publication.json','f1c1e0c75fbdd1da09d590a3e534fb8bb39671f2cdd6d4c796c6ba9f86080878'),
 'alignment_audit':('DYNAMIC_NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_20261003.json','53cba7de3d78cbf6b0fff8d00e77daf429ac497b75a021f0a8e2db7da1fe1ca9'),
 'alignment_reader':('scripts/ndx_nav_usd_alignment_independent_review_20261003.py','8bf0f70985932f2413144c6135ec0b5df81c619172b5baa24ffd49d4e8449675'),
 'account_inputs':('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json','c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'),
 'account_publication':('data/cache/research/multidecision_account_inputs_20261003_v1/publication.json','64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'),
 'account_audit':('data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1/independent_readback.json','8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'),
 'account_reader':('scripts/ndx_multidecision_account_inputs_independent_readback_20261003.py','85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d')}
CODE={
 'ndx_multidecision_reference_metrics_research':'0a1ef7ff8590538fdb29ce013027bd2ebd0ed17a816f405bc43bb0eef9489e62',
 'ndx_same_window_nav_reference_metrics_research':'bfb582e72dd3a23da5da4898d633d5afa310af0132aa16bb6896ebcac0d82a4f',
 'ndx_cash_fork_reference_window_research':'0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'}
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_executed','account_metrics_calculated','subscription_redemption_modeled','fit_performed','selection_performed','point_in_time_verified','historical_available_at_verified','benchmark_qualified','formal_admission_allowed','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','mode_selected_using_results','calendar_compressed','missing_values_filled','execution_authorized','promotion_allowed','automatic_retry_allowed','alignment_conversion_reaudited','future_independent_oos','untouched_holdout'),False)
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX']

def require(x,m):
 if not x:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def merge(s,r):
 require(type(r)is dict and set(r)=={'path','sha256'} and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Immutable absolute reference')
 require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def decode(raw):
 def pairs(items):
  out={}
  for k,v in items:require(k not in out,'Duplicate key');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def load(r,s,json_body=True):
 merge(s,r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed input namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Same consumed bytes');return decode(b) if json_body else b
def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s,refs):
 require(hashfile(SOURCE)==LOADED,'Publisher drift')
 for role,name in (('alignment','alignment.json'),('account_inputs','inputs.json')):require({p.name for p in Path(refs[role]['path']).parent.iterdir()}=={'started.json',name,'publication.json'},'Exact original parent namespace')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or not (Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift/failure '+p)
def private_core(s):
 blobs={n:load(ref(ROOT/'backtest'/f'{n}.py',h),s,False) for n,h in CODE.items()};cache={}
 def imp(name,globals=None,locals=None,fromlist=(),level=0):
  if name=='backtest':return types.SimpleNamespace(**{k:module(k) for k in fromlist})
  if name.startswith('backtest.'):require(level==0 and fromlist,'Explicit fixed helper');return module(name.split('.',1)[1])
  return builtins.__import__(name,globals,locals,fromlist,level)
 def module(n):
  require(n in blobs,'Unregistered numerical helper')
  if n not in cache:
   m=types.ModuleType('_nav_reference_'+n);m.__file__=str(ROOT/'backtest'/f'{n}.py');m.__dict__['__builtins__']=dict(vars(builtins),__import__=imp);cache[n]=m;exec(compile(blobs[n],m.__file__,'exec'),m.__dict__)
  return cache[n]
 return module('ndx_multidecision_reference_metrics_research')

def project_inputs(d,r):
 outer=d['alignment'];pub=d['alignment_publication'];audit=d['alignment_audit']
 require(outer['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1' and pub['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_CONVERSION_ONLY','Original253 conditional alignment')
 exact(pub['alignment_reference'],r['alignment'],'Original alignment publication');exact(pub['source_hashes'],outer['source_hashes'],'Original alignment closure')
 require(audit['schema']=='NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['alignment_sha256']==r['alignment']['sha256'] and audit['publication_sha256']==r['alignment_publication']['sha256'] and audit['reader_sha256']==r['alignment_reader']['sha256'],'Original independent alignment evidence')
 for o in (outer,pub):
  for k in ('point_in_time_verified','benchmark_qualified','execution_authorized'):require(o[k] is False,'No alignment publication authority')
 for k in ('point_in_time_verified','benchmark_qualified','account_executed'):require(audit[k] is False,'No alignment audit authority')
 doc=d['account_inputs'];ap=d['account_publication'];aa=d['account_audit']
 require(doc['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1' and ap['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1' and ap['status']=='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Audited account input role, no executed account')
 exact(ap['inputs_reference'],r['account_inputs'],'Input publication anchor');exact(doc['source_hashes'],ap['source_hashes'],'Input publisher closure')
 require(aa['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1' and aa['status']=='PASS' and aa['reader_sha256']==r['account_reader']['sha256'] and aa['scope']=='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION','Independent full-domain input evidence')
 exact(aa['inputs_reference'],r['account_inputs'],'Input audit anchor');exact(aa['publication_reference'],r['account_publication'],'Input audit receipt')
 for o in (doc,ap):
  for k in ('account_simulation_performed','point_in_time_verified','execution_authorized','formal_benchmark_passed','promotion_allowed'):require(o[k] is False,'No account input authority')
 for k in ('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'):require(aa[k] is False,'No input audit upgrade')
 inputs=doc['inputs'];require(inputs['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1' and inputs['content_sha256']==sha(enc({k:v for k,v in inputs.items() if k!='content_sha256'})),'Complete saved input object')
 for k,n in (('lane_count',8),('track_count',16),('coordinate_count',48)):
  require(type(inputs[k])is int and inputs[k]==n and type(aa['inspection'][k])is int and aa['inspection'][k]==n,'Full account calendar domain')
 require(len(inputs['rows'])==8,'Eight original lanes');calendar=inputs['rows'][0]['tracks'][0]['stateful_input']['calendar'];pointers=[]
 for i,row in enumerate(inputs['rows']):
  require(len(row['tracks'])==2,'Both input tracks')
  for j,t in enumerate(row['tracks']):
   exact(t['stateful_input']['calendar'],calendar,'All16 same complete window')
   for field in ('opens','closes'):exact(t['stateful_input'][field]['index'],calendar,'No price calendar compression')
   pointers.append(f'/inputs/rows/{i}/tracks/{j}/stateful_input/calendar')
 require(len(calendar)==120 and calendar[0]=='2026-03-31' and calendar[-1]=='2026-09-21','Declared account120 price119 interval window')
 require(len(outer['alignment']['session_dates'])==253,'Use253 alignment through09-21, not scoring610 ending08-31')
 full=outer['alignment']['session_dates'];require(calendar[0] in full and calendar==full[full.index(calendar[0]):],'Complete contiguous original alignment suffix')
 return dict(alignment=deepcopy(outer['alignment']),alignment_reference=deepcopy(r['alignment']),reference_calendar=dict(dates=deepcopy(calendar),source_reference=dict(r['account_inputs'],json_pointer=pointers[0]),all_track_calendar_pointers=pointers,role='SAME_CALENDAR_EXTERNAL_NAV_REFERENCE_NOT_SUBSCRIPTION_ACCOUNT'))

def load_inputs():
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for _,h in BOUND.values()),'Account calendar source anchors pending; no IO')
 refs={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()};s={str(SOURCE):LOADED,str(LINEAGE):LINEAGE_SHA};d={}
 for k,r in refs.items():
  value=load(r,s,not k.endswith('_reader'))
  if type(value)is dict:
   d[k]=value
   for p,h in value.get('source_hashes',{}).items():merge(s,dict(path=p,sha256=h))
 for role in ('alignment_publication','account_publication'):
  if 'started_reference' in d[role]:load(d[role]['started_reference'],s)
 args=project_inputs(d,refs);core=private_core(s);guard(s,refs);return dict(docs=d,refs=refs,sources=s,args=args,core=core)
def resource(size=0):
 p=OUTPUT.parent
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+size,'Resource reserve')
def save(name,obj,emergency=False):
 b=enc(obj)
 if not emergency:resource(len(b))
 p=OUTPUT/name
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Output drift');return ref(p,sha(b))
def validate_result(v,args):
 require(type(v)is dict and v['schema']=='MULTIDECISION_CONTIGUOUS_NAV_REFERENCE_METRICS_V1','New explicit window metrics only')
 exact(v['alignment_reference'],args['alignment_reference'],'Original exact values source');exact(v['reference_calendar'],args['reference_calendar'],'Unchanged120 calendar')
 require(set(v['modes'])==set(MODES),'Both FX modes separately preserved')
 for mode in MODES:
  m=v['modes'][mode];require(len(m['observations'])==120,'No discarded reference slots')
  exact([x['original_alignment_row']['session'] for x in m['observations']],args['reference_calendar']['dates'],'Same individual dates')
  require((m['status']=='BLOCKED_MISSING_REFERENCE_INPUT' and bool(m['missing_sessions']) and m['metrics'] is None) or (m['status']=='HISTORICAL_METRICS_COMPUTED' and m['missing_sessions']==[] and m['metrics']['observation_count']==120 and m['metrics']['interval_count']==119),'No mode borrowing or126 assumption')
 for k in ('source_bytes_authenticated','account_executed','fit_performed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','point_in_time_verified','formal_admission_allowed','mode_selected_using_results'):require(v[k] is False,'Result reference authority')

def run(*,execute=False):
 require(execute is True,'Explicit historical NAV reference preparation');require(not OUTPUT.exists(),'Create only, no retry');c=load_inputs();resource();OUTPUT.mkdir(parents=True);written=[]
 try:
  written.append(save('started.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_STARTED_V1',input_references=c['refs'],source_hashes=c['sources'],**FLAGS)))
  guard(c['sources'],c['refs']);value=None;error=None;returned=False
  try:value=c['core'].reference_metrics(**c['args']);returned=True
  except BaseException as e:error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
  raw=dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_RAW_RETURN_V1',returned=returned,call_invoked=True,returned_call_count=int(returned),result=None,error=error,original_return_is_json=None,diagnostic_reference=None,repr_error=None,input_references=c['refs'],source_hashes=c['sources'],**FLAGS)
  if returned:
   try:enc(value);raw['result']=value;raw['original_return_is_json']=True
   except BaseException:
    raw['original_return_is_json']=False
    try:b=repr(value).encode('utf-8',errors='backslashreplace')
    except BaseException as e:b=b'REPR_FAILED';raw['repr_error']=dict(type=type(e).__name__,message=str(e))
    p=OUTPUT/'unserializable_return.bin'
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    raw['diagnostic_reference']=ref(p,sha(b));written.append(raw['diagnostic_reference'])
  rr=save('raw_result.json',raw,True);written.append(rr);require(returned and raw['original_return_is_json'] is True,'Original numerical return/error retained');validate_result(value,c['args']);guard(c['sources'],c['refs'])
  mr=save('metrics.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_DOCUMENT_V1',metrics=value,raw_reference=rr,input_references=c['refs'],source_hashes=c['sources'],original_nav_manifest=deepcopy(c['docs']['alignment']['nav_manifest_preserved']),original_nav_snapshot=deepcopy(c['docs']['alignment']['nav_snapshot_preserved']),original_fx_capture_manifest=deepcopy(c['docs']['alignment']['fx_capture_manifest_preserved']),independent_readback_status='PENDING',**FLAGS));written.append(mr)
  written.append(save('publication.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_PUBLICATION_V1',status='PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY_PENDING_READBACK',metrics_reference=mr,raw_reference=rr,started_reference=written[0],input_references=c['refs'],source_hashes=c['sources'],**FLAGS)))
  guard(c['sources'],c['refs'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Final output drift')
  require({str(p.resolve()) for p in OUTPUT.iterdir()}=={r['path'] for r in written},'Exact namespace');return mr
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**FLAGS),True)
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
