"""Full48 outer-refit coordinator; no actual source anchors registered here.

Fixed original order, durable full preparation, audited immediate predecessors,
explicit numerical reuse. Every terminal condition preserves the full denominator.
"""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,re,sys,types,uuid,shutil,traceback
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/outer_lane_cutoff_refit_coordinator_20261008_v2'
WORKER_OUTPUT=ROOT/'data/cache/research/outer_lane_cutoff_refit_worker_20261008_v2'
WORKER=ROOT/'scripts/ndx_outer_lane_refit_worker_v2_20261008.py';WORKER_SHA='81f4d0a35f049ba7642cdb3f7861b0dd8ad3e63c735b8fbf0eed474ad1bac5cd'
READER=ROOT/'scripts/ndx_outer_lane_refit_independent_readback_v2_20261008.py'
FLAGS=dict.fromkeys(('point_in_time_verified','promotion_allowed','execution_authorized','account_executed','scoring_weights_used','automatic_retry_allowed','formal_benchmark_passed','source_bytes_authenticated'),False)
SUCCESS=('REFIT_PASSED_PENDING_INDEPENDENT_READBACK','REUSED_AUDITED_NUMERICAL_RESULT')
NO_DISPATCH=('SOURCE_BLOCKED','NO_ELIGIBLE_CANDIDATE','NO_REGISTERED_CANDIDATES','INPUTS_PREPARED_PRIOR_UNRESOLVED')

LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
FRESH_CLI=False

def require(ok,msg):
 if not ok:raise ValueError(msg)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Explicit immutable reference')
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def read(r):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed source namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Consumed source bytes');return json.loads(b,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def read_current_attempt_post(r):
 """Only an explicit returned current worker post may coexist with failure evidence."""
 valid(r);p=Path(r['path']).resolve();require(p.name=='postcheck.json' and p.parent.parent==WORKER_OUTPUT.resolve()/'locations' and re.fullmatch('[a-f0-9]{64}',p.parent.name),'Fixed current attempt post path')
 b=p.read_bytes();require(sha(b)==r['sha256'],'Exact current attempt bytes');v=json.loads(b,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
 require(v['schema']=='OUTER_LANE_CUTOFF_REFIT_POSTCHECK_V1' and v['location_id']==p.parent.name,'Current attempt role/location')
 for k in ('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'):require(v[k] is False,'No current attempt authority')
 return v

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

def guard(sources):
 require(hashfile(SOURCE)==LOADED,'Coordinator code drift')
 diagnostic=lineage_members(sources)
 for p,h in sources.items():require((p in diagnostic or not (Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift '+p)
def save(path,x,emergency=False):
 b=enc(x)
 if not emergency:require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3+len(b),'RESOURCE_STOP_BEFORE_DISPATCH')
 with Path(path).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(Path(path).read_bytes()==b,'Durable exact output');return ref(path,sha(b))
def module(reference,name):
 valid(reference);b=Path(reference['path']).read_bytes();require(sha(b)==reference['sha256'],'Private code bytes');m=types.ModuleType(name);m.__file__=reference['path'];exec(compile(b,reference['path'],'exec'),m.__dict__);return m

def validate_state(state,expected_coordinates):
 require(state['schema']=='MULTIDECISION_SELECTED_LATEST126_REFIT_INPUTS_V2','Resolved full preparation schema')
 require(type(state['rows'])is list and len(state['rows'])==48,'Full48 retained')
 coordinates=[[r['cutoff'],r['fx_mode'],r['lane']] for r in state['rows']];exact(coordinates,expected_coordinates,'Original coordinate order')
 require(len({tuple(x) for x in coordinates})==48,'No duplicate coordinates')
 for i,row in enumerate(state['rows']):
  require(type(row['decision_index'])is int and row['decision_index']==i//8,'Original six cutoffs')
  if row['outer_request'] is not None:exact(row['outer_request']['coordinate'],coordinates[i],'Request coordinate')
 require(sum(state['status_counts'].values())==48,'Full state status count')
 return coordinates

def summarize(rows):
 require(len(rows)==48 and [r['coordinate_index'] for r in rows]==list(range(48)),'Every coordinate recorded exactly once')
 counts={s:sum(r['outcome']==s for r in rows) for s in sorted({r['outcome'] for r in rows})}
 return dict(coordinate_count=48,outcome_counts=counts,fit_invoked_coordinate_count=sum(r['fit_call_invoked'] is True for r in rows),audited_success_count=sum(r['outcome'] in ('AUDITED_DIRECT_SUCCESS','AUDITED_NUMERICAL_REUSE') for r in rows),explicit_reuse_count=sum(r['outcome']=='AUDITED_NUMERICAL_REUSE' for r in rows),unresolved_dispatch_count=sum(r['outcome']=='UNRESOLVED_DISPATCH' for r in rows),unprocessed_coordinate_count=sum(r['outcome']=='NOT_REACHED' for r in rows))

def execute_full48(*,prepared,expected_coordinates,reader_reference,resolve_state,dispatch,inspect_saved,read_saved,guard_sources,resource_check,persist):
 """Bounded orchestration kernel. Public CLI supplies only authenticated modules.

Callbacks are for synthetic tests and internal wiring, never CLI/user arguments.
Every callback invocation has an explicit durable pre-dispatch marker.
"""
 valid(reader_reference);require(len(prepared['rows'])==48,'Initial complete preparation')
 initial=resolve_state([]);validate_state(initial,expected_coordinates)
 prepared_ref=persist('prepared48.json',dict(schema='OUTER_LANE_FULL48_INITIAL_PREPARATION_V1',prepared=initial,**FLAGS))
 rows=[dict(coordinate_index=i,coordinate=deepcopy(expected_coordinates[i]),initial_status=r['status'],outcome='NOT_REACHED',fit_call_invoked=False,dispatch_invoked=False,postcheck_reference=None,readback_reference=None) for i,r in enumerate(initial['rows'])]
 prior=[];direct_by_numeric={};all_refs=[];failure=None
 for i in range(48):
  row=rows[i];invoked=False
  try:
   guard_sources();free=resource_check();require(type(free)is int,'Exact free storage');require(free>=5*1024**3,'RESOURCE_STOP_BEFORE_DISPATCH')
   state=resolve_state(prior);validate_state(state,expected_coordinates);item=state['rows'][i];request=item['outer_request']
   row['resolved_status']=item['status']
   if request is None:
    require(item['status'] in NO_DISPATCH or item['missing_latest_return_slots'],'Explicit blocked/unknown state only')
    row['outcome']='SOURCE_BLOCKED' if item['status']=='SOURCE_BLOCKED' else 'NO_REFIT_INPUT_OR_ADJACENT_PRIOR'
    row['blocked_state_reference']=persist(f'coordinates/{i:02d}.json',dict(schema='OUTER_LANE_COORDINATE_NOT_DISPATCHED_V1',coordinate_index=i,prepared_row=item,prior_evidence_references=deepcopy(prior),**FLAGS));continue
   numeric=request['numerical_task_id'];origin=direct_by_numeric.get(numeric);mode='REUSE' if origin is not None else 'NEW_FIT'
   marker=persist(f'coordinates/{i:02d}-dispatch.json',dict(schema='OUTER_LANE_COORDINATE_DISPATCH_STARTED_V1',coordinate_index=i,request=request,mode=mode,prior_evidence_references=deepcopy(prior),reuse_evidence_reference=deepcopy(origin),**FLAGS));row['dispatch_started_reference']=marker
   guard_sources();invoked=True;row['dispatch_invoked']=True;row['fit_call_invoked']=None
   postref=dispatch(i,deepcopy(prior),deepcopy(origin));row['postcheck_reference']=postref;post=read_saved(postref);require(type(post['current_location_call_invoked'])is bool,'Actual saved call fact');row['fit_call_invoked']=post['current_location_call_invoked']
   exact([post['numerical_task_id'],post['location_id']],[numeric,request['location_id']],'Saved result job/location')
   auditref=inspect_saved(postref);row['readback_reference']=auditref;audit=read_saved(auditref)
   exact(audit['postcheck_reference'],postref,'Audit exact post reference');exact(audit['reader_sha256'],reader_reference['sha256'],'Bound reader version')
   refs=dict(request=post['request_reference'],raw_result=post['raw_result_reference'],postcheck=postref,readback=auditref,reader=reader_reference)
   evidence=refs if origin is None else dict(references=refs,numerical_reuse_references=deepcopy(origin))
   if post['outcome'] not in SUCCESS:
    require(audit['status'] in ('PASS_SAVED_RISK_FAILURE','TECHNICAL_FAILURE_RECORDED_NOT_PRIOR') and audit['prior_eligible'] is False,'Explicit failure audit cannot advance prior')
    if post['outcome'] in ('REFIT_RISK_FAILED','REUSED_AUDITED_NUMERICAL_RISK_FAILURE'):
     require(audit['status']=='PASS_SAVED_RISK_FAILURE','Honest risk arithmetic audit')
     if origin is None:direct_by_numeric[numeric]=refs
     row['outcome']='AUDITED_RISK_FAILURE' if origin is None else 'AUDITED_REUSED_RISK_FAILURE';row['evidence_references']=evidence;all_refs.append(evidence);persist(f'coordinates/{i:02d}-accepted.json',row);continue
    require(audit['status']=='TECHNICAL_FAILURE_RECORDED_NOT_PRIOR','Technical terminal audit');row['outcome']='AUDITED_TECHNICAL_FAILURE';failure=dict(coordinate_index=i,stage='REFIT_TERMINAL',postcheck_reference=postref,readback_reference=auditref);persist(f'coordinates/{i:02d}-accepted.json',row);break
   require(audit['status']=='PASS' and audit['prior_eligible'] is True,'Only independent successful prior')
   # Validate through the next resolve before using a non-final-period result as prior.
   if i//8<5:
    next_prior=prior+[evidence];validate_state(resolve_state(next_prior),expected_coordinates);prior=next_prior
   if origin is None:direct_by_numeric[numeric]=refs
   row['outcome']='AUDITED_DIRECT_SUCCESS' if origin is None else 'AUDITED_NUMERICAL_REUSE';row['evidence_references']=evidence
   all_refs.append(evidence);persist(f'coordinates/{i:02d}-accepted.json',row)
  except BaseException as e:
   row['outcome']='UNRESOLVED_DISPATCH' if invoked else 'NOT_REACHED';failure=dict(coordinate_index=i,dispatch_invoked=invoked,type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
   persist('failure.json',dict(schema='OUTER_LANE_FULL48_FAILURE_V1',failure=failure,rows=rows,**FLAGS));break
 result=dict(schema='OUTER_LANE_FULL48_COORDINATOR_RESULT_V1',status='COMPLETED_REGISTERED_COORDINATES' if failure is None else 'STOPPED_NO_RETRY',prepared_reference=prepared_ref,rows=rows,summary=summarize(rows),accepted_evidence_references=all_refs,failure=failure,all48_registered=True,all48_successfully_refitted=False,**FLAGS)
 result_ref=persist('result.json',result);guard_sources();return result_ref

def run(*,receipt_contract_reference,execute=False):
 require(execute is True and FRESH_CLI,'Explicit fresh-process coordinator only');valid(receipt_contract_reference);require(type(WORKER_SHA)is str and re.fullmatch('[a-f0-9]{64}',WORKER_SHA),'Worker binding pending')
 contract=read(receipt_contract_reference);require(contract['schema']=='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1' and contract['source_bytes_authenticated'] is False,'Explicit receipt contract')
 reader_ref=contract['reader_reference'];valid(reader_ref);require(Path(reader_ref['path']).resolve()==READER.resolve(),'Fixed independent reader role')
 sources={str(SOURCE):LOADED,str(LINEAGE):LINEAGE_SHA,str(WORKER):WORKER_SHA,receipt_contract_reference['path']:receipt_contract_reference['sha256'],reader_ref['path']:reader_ref['sha256']};guard(sources)
 worker=module(ref(WORKER,WORKER_SHA),'_outer_coordinator_worker');reader=module(reader_ref,'_outer_coordinator_reader');worker.FRESH_CLI=True;worker.environment()
 common=worker.load_common(receipt_contract_reference=receipt_contract_reference);c=worker.context(common)
 require(not OUTPUT.exists(),'Create only no retry');require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3,'Resource reserve');OUTPUT.mkdir();(OUTPUT/'coordinates').mkdir();written=[]
 def persist(name,value):
  r=save(OUTPUT/name,value,emergency=name in ('failure.json','result.json') or name.endswith('-accepted.json'));written.append(r);return r
 def resolve(prior):
  actual_sources=dict(c['sources']);envelopes=worker.load_prior(prior,c,actual_sources);out=c['evidence'].resolve_adjacent_refit_priors(prepared=c['prepared'],prior_evidence=envelopes,receipt_contract=c['receipt_contract']);worker.guard(actual_sources);return out
 try:
  persist('started.json',dict(schema='OUTER_LANE_FULL48_COORDINATOR_STARTED_V1',input_references=c['refs'],receipt_contract_reference=receipt_contract_reference,source_hashes=dict(c['sources'],**sources),coordinate_count=48,**FLAGS))
  result=execute_full48(prepared=c['prepared'],expected_coordinates=common['coordinates'],reader_reference=reader_ref,resolve_state=resolve,dispatch=lambda i,p,r:worker.run_coordinate(i,prior_references=p,reuse_evidence_reference=r,execute=True,common=common),inspect_saved=lambda r:reader.readback(r,execute=True),read_saved=lambda r:read_current_attempt_post(r) if Path(r['path']).name=='postcheck.json' else read(r),guard_sources=lambda:guard(sources),resource_check=lambda:shutil.disk_usage(OUTPUT).free,persist=persist)
  guard(sources);worker.guard(c['sources'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Coordinator output drift')
  require({str(p.resolve()) for p in OUTPUT.rglob('*') if p.is_file()}=={r['path'] for r in written},'Exact own output inventory');return result
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():persist('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e)),**FLAGS))
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--receipt-contract',required=True);p.add_argument('--receipt-contract-sha256',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();FRESH_CLI=True
 print(json.dumps(run(receipt_contract_reference=ref(a.receipt_contract,a.receipt_contract_sha256),execute=a.execute)))
