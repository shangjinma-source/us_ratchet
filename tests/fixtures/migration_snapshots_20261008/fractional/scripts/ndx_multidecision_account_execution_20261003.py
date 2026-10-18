"""Exclusive full-path execution of independently read-back account inputs.

This is conditional account research, not order dispatch, selection or fitting.
Blocked tracks remain blocked. Technical failures stop and retain all16 slots.
"""
from pathlib import Path
from copy import deepcopy
import builtins,hashlib,json,math,os,re,shutil,sys,traceback,types
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_account_execution_20261003_v1'
PARENT=ROOT/'data/cache/research/multidecision_account_inputs_20261003_v1'
BOUND={
 'inputs':('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json',None),
 'publication':('data/cache/research/multidecision_account_inputs_20261003_v1/publication.json',None),
 'readback':('data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1/independent_readback.json',None),
 'reader':('scripts/ndx_multidecision_account_inputs_independent_readback_20261003.py',None)}
CODE={
 'ndx_dynamic_fractional_flow_split_research':'d33937157b7b3e4aa0d031962d1a0b0669eb7aa0ded7c1f8818b5d4348291687',
 'ndx_dynamic_fractional_flow_split_research_v2':'40cda887911209e1e2b4dfd401ce702105ba7584506007a2a92cf427667be287',
 'ndx_dynamic_frozen_flow_split_research':'35c19184f08a0394838171fa61afeb781cd4f314799058063186d9c3d38376a8',
 'ndx_dynamic_whole_lot_path':'3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95',
 'ndx_dynamic_whole_lot_repair_path':'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',
 'ndx_whole_lot_repair_diagnostic':'e2f00388b92c88588acaff51c30c608830bf93a00cfc6a84ad8e20a9470381bf',
 'ndx_split_accounting_research':'11bb5225e90c76fe303e90fa9f639e34c3978fd922d230bb2a45f8f9ad24877c',
 'ndx_dynamic_frozen_execution_research':'69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b'}
ENGINES={'CONTINUOUS':('ndx_dynamic_fractional_flow_split_research_v2','simulate_dynamic_fractional_flow_split_research','DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2'),
 'WHOLE_LOT':('ndx_dynamic_frozen_flow_split_research','simulate_dynamic_frozen_flow_split_research','DYNAMIC_WHOLE_LOT_USD_FLOW_SPLIT_ACCOUNT_V1')}
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX');LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
FLAGS=dict.fromkeys(('source_bytes_authenticated','fit_performed','selection_performed','actual_orders_executed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','full_ndx_membership_verified','cash_add_only_search_performed'),False)
PARENT_FLAGS=('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed')

def require(x,m):
 if not x:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Absolute external immutable reference')
def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def decode(raw):
 def pairs(items):
  obj={}
  for k,v in items:require(k not in obj,'Duplicate JSON key');obj[k]=v
  return obj
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def load(r,s,json_body=True):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent namespace');raw=p.read_bytes();require(sha(raw)==r['sha256'],'Authenticated same consumed bytes');merge(s,r);return decode(raw) if json_body else raw

def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def guard(sources):
 require(hashfile(SOURCE)==LOADED,'Loaded worker drift')
 require({p.name for p in PARENT.iterdir()}=={'started.json','inputs.json','publication.json'},'Exact input parent namespace')
 for p,h in sources.items():require(not (Path(p).parent/'failure.json').exists() and hashfile(p)==h,'Source drift/failure '+p)
def resource(size=0):
 p=OUTPUT.parent
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+size,'RESOURCE_STOP_BEFORE_CALL_OR_WRITE')
def save(path,value,emergency=False):
 raw=enc(value)
 if not emergency:resource(len(raw))
 with Path(path).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(Path(path).read_bytes()==raw,'Output drift');return ref(path,sha(raw))
def private_engines(sources):
 """Compile every pinned local dependency from the very bytes hashed here.

No shared sys.modules backtest callable, evaluator injection or producer import.
"""
 import numpy as np
 import pandas as pd
 require((sys.version.split()[0],np.__version__,pd.__version__)==('3.13.1','2.4.6','2.2.3'),'Frozen account runtime versions')
 merge(sources,ref(sys.executable,hashfile(sys.executable)))
 for module in (np,pd):merge(sources,ref(module.__file__,hashfile(module.__file__)))
 raw={name:load(ref(ROOT/'backtest'/f'{name}.py',h),sources,False) for name,h in CODE.items()};cache={}
 def private_import(name,globals=None,locals=None,fromlist=(),level=0):
  if name=='backtest':return types.SimpleNamespace(**{n:module(n) for n in fromlist})
  if name.startswith('backtest.'):
   require(level==0 and fromlist,'Only fixed dependency from-imports');return module(name.split('.',1)[1])
  return builtins.__import__(name,globals,locals,fromlist,level)
 def module(name):
  require(name in raw,'Unregistered account dependency')
  if name not in cache:
   m=types.ModuleType('_private_account_'+name);m.__file__=str(ROOT/'backtest'/f'{name}.py');m.__dict__['__builtins__']=dict(vars(builtins),__import__=private_import);cache[name]=m;exec(compile(raw[name],m.__file__,'exec'),m.__dict__)
  return cache[name]
 engines={kind:getattr(module(spec[0]),spec[1]) for kind,spec in ENGINES.items()}
 runtime=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,implementation=sys.implementation.name)
 return engines,pd,runtime

def validate_documents(doc,pub,audit,refs):
 require(doc['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1','Account inputs document')
 require(pub['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Successful input publication')
 exact(pub['inputs_reference'],refs['inputs'],'Input publication anchor');exact(doc['input_references'],pub['input_references'],'Same original input references');exact(doc['source_hashes'],pub['source_hashes'],'Exact publisher source closure')
 require(audit['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['scope']=='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION','Specific independent projection audit')
 exact(audit['inputs_reference'],refs['inputs'],'Audit inputs anchor');exact(audit['publication_reference'],refs['publication'],'Audit publication anchor');require(audit['reader_sha256']==refs['reader']['sha256'],'Audit fixed reader')
 for obj in (doc,pub):
  for k in PARENT_FLAGS:require(obj[k] is False,'No parent authority '+k)
 for k in ('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'):require(audit[k] is False,'No independent audit execution/authority '+k)
 for k,n in (('coordinate_count',48),('lane_count',8),('track_count',16),('security_count',77),('issuer_count',76),('provenance_count',101),('sidecar_count',7)):
  require(type(audit['inspection'][k])is int and audit['inspection'][k]==n,'Audited complete projection domain')
 for p,h in doc['source_hashes'].items():require(audit['source_hashes'].get(p)==h,'Independent audit covers original publisher closure')
 inputs=doc['inputs'];require(inputs['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1','Original prepared full domain')
 body={k:v for k,v in inputs.items() if k!='content_sha256'};require(sha(enc(body))==inputs['content_sha256'],'Inputs complete content hash')
 for k,n in (('lane_count',8),('track_count',16),('coordinate_count',48)):require(type(inputs[k])is int and inputs[k]==n,'Complete fixed input domain')
 require(len(inputs['rows'])==8,'All original lanes')
 for i,row in enumerate(inputs['rows']):
  exact([row['fx_mode'],row['lane']],[MODES[i//4],LANES[i%4]],'Original8 lane order');require(len(row['tracks'])==2,'Both independent account tracks')
  for j,track in enumerate(row['tracks']):
   kind=('CONTINUOUS','WHOLE_LOT')[j];require(track['track']==kind,'Fixed track order');require(track['account_simulation_performed'] is False and track['execution_authorized'] is False and track['source_bytes_authenticated'] is False,'Prepared only')
   require(track['status'] in ('ENGINE_INPUTS_PREPARED_NOT_EXECUTED','BLOCKED_ENGINE_OR_SOURCE_INPUT'),'Explicit track preparation state')
   require(type(track['blocking_reasons'])is list and bool(track['blocking_reasons'])==(track['status']=='BLOCKED_ENGINE_OR_SOURCE_INPUT'),'No hidden source/engine blocker')
   binding=track['engine_binding'];spec=ENGINES[kind]
   exact(binding['source_reference'],dict(path='backtest/'+spec[0]+'.py',sha256=CODE[spec[0]]),'Pinned engine source declaration');require(binding['function']==spec[1],'Specific versioned engine function')
   require(binding['source_bytes_authenticated'] is False and track['one_full_path_invocation_required'] is True,'Single independent full schedule')
   exact(binding['dataframe_restoration_required'],['closes','opens'],'Only explicit matrix restoration')
 return inputs

def load_inputs():
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for _,h in BOUND.values()),'Four actual input/audit roles pending; no IO')
 refs={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()};sources={str(SOURCE):LOADED};docs={k:load(r,sources,k!='reader') for k,r in refs.items()}
 inputs=validate_documents(docs['inputs'],docs['publication'],docs['readback'],refs)
 for obj in (docs['inputs'],docs['publication'],docs['readback']):
  for p,h in obj['source_hashes'].items():merge(sources,dict(path=p,sha256=h))
 for r in refs.values():require(docs['readback']['source_hashes'].get(r['path'])==r['sha256'] if r!=refs['readback'] else True,'Audit covers direct input/reader bytes')
 startedref=docs['publication']['started_reference'];require(Path(startedref['path']).resolve()==PARENT/'started.json','Exact parent started path');started=load(startedref,sources);exact(started['source_hashes'],docs['inputs']['source_hashes'],'Parent started closure')
 engines,pd,runtime=private_engines(sources);guard(sources)
 return dict(inputs=inputs,input_references=refs,sources=sources,engines=engines,pandas=pd,runtime=runtime)

def restore_kwargs(track,pd):
 kwargs=deepcopy(track['engine_binding']['keyword_arguments'])
 for name in ('closes','opens'):
  item=kwargs[name];require(set(item)=={'index','columns','data'},'Exact saved DataFrame representation')
  require(len(item['index'])==len(item['data']) and all(len(r)==len(item['columns']) for r in item['data']),'Complete saved matrix shape')
  kwargs[name]=pd.DataFrame(item['data'],index=pd.to_datetime(item['index']),columns=item['columns'])
 return kwargs

def preserve_return(path,returned,error,value,startedref,c):
 raw=dict(schema='MULTIDECISION_ACCOUNT_RAW_RETURN_V1',returned=returned,call_invoked=True,returned_call_count=1 if returned else 0,internal_call_count_unobserved=True,result=None,error=error,original_return_is_json=None,returned_type=None if not returned else type(value).__name__,diagnostic_reference=None,repr_error=None,started_reference=startedref,input_references=c['input_references'],source_hashes=c['sources'],runtime=c['runtime'],**FLAGS)
 if returned:
  try:enc(value);raw['result']=value;raw['original_return_is_json']=True
  except BaseException:
   raw['original_return_is_json']=False
   try:b=repr(value).encode('utf-8',errors='backslashreplace')
   except BaseException as e:b=b'REPR_FAILED';raw['repr_error']=dict(type=type(e).__name__,message=str(e))
   binary=path.parent/'unserializable_return.bin'
   with binary.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
   raw['diagnostic_reference']=ref(binary,sha(b))
 return save(path,raw,emergency=True),raw

def verify_return(result,track):
 require(type(result)is dict and result['schema']==ENGINES[track['track']][2],'Original account result dictionary/schema')
 require(type(result['daily'])is list and result['daily'],'All original daily records')
 exact([r['session'] for r in result['daily']],track['stateful_input']['calendar'],'Full same source calendar, no compression')
 fields=('point_in_time_verified','promotion_allowed','formal_benchmark_passed')+ (('source_bytes_authenticated','actual_orders_executed') if track['track']=='CONTINUOUS' else ('source_authenticity_verified','broker_atomic_execution_verified','auto_replan_enabled'))
 for k in fields:require(result[k] is False,'No account authority '+k)
 enc(result)

def execute_tracks(c):
 inputs=c['inputs'];rows=[dict(track_index=i*2+j,fx_mode=r['fx_mode'],lane=r['lane'],track=t['track'],outcome='UNDISPATCHED',call_invoked=False,returned_call_count=0,started_reference=None,raw_reference=None,postcheck_reference=None,blocking_reasons=deepcopy(t['blocking_reasons'])) for i,r in enumerate(inputs['rows']) for j,t in enumerate(r['tracks'])]
 written=[];failure=None
 for i,row in enumerate(rows):
  lane=inputs['rows'][i//2];track=lane['tracks'][i%2];folder=OUTPUT/'tracks'/f'{i:02d}';stage='BEFORE_DISPATCH'
  try:
   guard(c['sources']);resource();folder.mkdir()
   original=enc(track)
   start=save(folder/'started.json',dict(schema='MULTIDECISION_ACCOUNT_TRACK_STARTED_V1',track_index=i,coordinate=[row['fx_mode'],row['lane'],row['track']],input_pointer=f'/inputs/rows/{i//2}/tracks/{i%2}',prepared_track=deepcopy(track),input_references=c['input_references'],source_hashes=c['sources'],runtime=c['runtime'],**FLAGS));written.append(start);row['started_reference']=start
   if track['status']=='BLOCKED_ENGINE_OR_SOURCE_INPUT':
    row['outcome']='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT';post=save(folder/'postcheck.json',dict(schema='MULTIDECISION_ACCOUNT_TRACK_POSTCHECK_V1',**deepcopy(row),input_references=c['input_references'],source_hashes=c['sources'],**FLAGS));row['postcheck_reference']=post;written.append(post);continue
   kwargs=restore_kwargs(track,c['pandas']);guard(c['sources']);resource();stage='CALL_DISPATCHED';row['call_invoked']=True
   value=None;error=None;returned=False
   try:value=c['engines'][track['track']](**kwargs);returned=True
   except BaseException as e:error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
   stage='RAW_SAVE';rawref,raw=preserve_return(folder/'raw_result.json',returned,error,value,start,c);row['raw_reference']=rawref;row['returned_call_count']=int(returned);written.append(rawref)
   if raw['diagnostic_reference']:written.append(raw['diagnostic_reference'])
   stage='POST_RETURN_VALIDATION';validation=None
   try:
    require(returned,'Numerical exception retained');require(raw['original_return_is_json'] is True,'Non-JSON return retained');require(enc(track)==original,'Engine mutated prepared source track');guard(c['sources']);verify_return(raw['result'],track)
    row['outcome']='ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK'
   except BaseException as e:validation=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc());row['outcome']='NUMERICAL_EXCEPTION' if not returned else 'VALIDATION_FAILURE'
   post=save(folder/'postcheck.json',dict(schema='MULTIDECISION_ACCOUNT_TRACK_POSTCHECK_V1',**deepcopy(row),error=error,validation_error=validation,input_references=c['input_references'],source_hashes=c['sources'],**FLAGS),emergency=True);row['postcheck_reference']=post;written.append(post)
   if validation:failure=dict(track_index=i,stage=stage,outcome=row['outcome'],error=error,validation_error=validation);break
  except BaseException as e:
   row['outcome']='UNRESOLVED_DISPATCH' if row['call_invoked'] else 'UNDISPATCHED';failure=dict(track_index=i,stage=stage,type=type(e).__name__,message=str(e),traceback=traceback.format_exc());break
 counts={s:sum(r['outcome']==s for r in rows) for s in sorted({r['outcome'] for r in rows})}
 result=dict(schema='MULTIDECISION_ACCOUNT_EXECUTION_RESULT_V1',status='ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK' if failure is None else 'STOPPED_NO_RETRY',rows=rows,counts=counts,track_count=16,lane_count=8,outer_coordinate_count=48,account_call_count=sum(r['call_invoked'] is True for r in rows),returned_call_count=sum(r['returned_call_count'] for r in rows),failure=failure,input_references=c['input_references'],source_hashes=c['sources'],runtime=c['runtime'],benchmark_path_status='012922_EXTERNAL_NAV_REFERENCE_ONLY_INCUMBENT_SAME_FLOW_ACCOUNT_NOT_EXECUTED',benchmark_references_by_lane=[deepcopy(r['benchmark_references']) for r in inputs['rows']],**FLAGS)
 return result,written

def run(*,execute=False):
 require(execute is True,'Explicit conditional research account execution');require(not OUTPUT.exists(),'Exclusive namespace, no retry');c=load_inputs();resource();OUTPUT.mkdir(parents=True);(OUTPUT/'tracks').mkdir();written=[]
 try:
  written.append(save(OUTPUT/'started.json',dict(schema='MULTIDECISION_ACCOUNT_EXECUTION_STARTED_V1',input_references=c['input_references'],source_hashes=c['sources'],runtime=c['runtime'],track_count=16,**FLAGS)))
  result,trackrefs=execute_tracks(c);written+=trackrefs;rr=save(OUTPUT/'result.json',result,emergency=True);written.append(rr)
  require(result['failure'] is None,'Retained technical failure, not economic infeasibility');guard(c['sources'])
  written.append(save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_ACCOUNT_EXECUTION_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK',result_reference=rr,started_reference=written[0],input_references=c['input_references'],source_hashes=c['sources'],**FLAGS)))
  guard(c['sources'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Output drift')
  require({str(p.resolve()) for p in OUTPUT.rglob('*') if p.is_file()}=={r['path'] for r in written},'Exact complete execution inventory');return rr
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save(OUTPUT/'failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**FLAGS),emergency=True)
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
