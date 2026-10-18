"""Explicit single-location outer refit worker. Future source pins block execution.

This version is code-only until the receipt interface and actual selection anchors
are bound. No inner-window weights or accounts are consumed.
"""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,re,shutil,sys,types,uuid,traceback
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve()
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest();FRESH_CLI=False
OUTPUT=ROOT/'data/cache/research/outer_lane_cutoff_refit_worker_20261003_v1'
SEL=ROOT/'data/cache/research/registered_scoring_selection_20261003_v1'
BOUND={
 'selection':(str(SEL/'raw_selection.json'),'89a85557fe91f034ec22efba7c674ee3eef15054862ad883808a3dfb0f995a79'),
 'selection_index':(str(SEL/'index.json'),'cf5a8fc546dcc2454bf986c31dacfff60df109adecb1b0e4b4c681bd59fce6b4'),
 'selection_publication':(str(SEL/'publication.json'),'79b288a81f2431865123672b3cc6a6968cafa2cc10c72c987332e7fc65beae58'),
 'selection_audit':(str(ROOT/'data/cache/research/registered_scoring_selection_independent_readback_20261003_v1/independent_readback.json'),'6a414f3c15be6d1915294888c3e6228bb0be0acc3f5f3791ad0332403a666733'),
 'selection_reader':(str(ROOT/'scripts/ndx_registered_scoring_selection_independent_readback_20261003.py'),'494e3ffa29d88d11544b183bef7a5420cd06fbb4498bb65af7a738eb242d1aa0'),
 'history':(str(ROOT/'data/cache/research/multidecision_scoring_history_20261003_v1/index.json'),'ce4fd8a1a8f7f0c9c1ddd20cd4136c1c078e4aae81b37e61c9a1b0aae981ff2d'),
 'history_audit':(str(ROOT/'data/cache/research/multidecision_scoring_history_independent_readback_20261003_v2/independent_readback.json'),'a338dbbdfa4bc7ffdc6e83ee93bc6e55802201dd7f18049d398ae394029a5b1a'),
 'history_reader':(str(ROOT/'scripts/ndx_multidecision_scoring_history_independent_readback_v2_20261003.py'),'6ae5ca2c757badd0ebfa2fa35bf3550584b4a989155e44e7d7fd120ca61f6703'),
 'fitter':(str(ROOT/'research_contracts/multidecision_outer_cutoff_fitter_sources_20261003_v1.json'),'ca57e56d5aa2a36949be9e056ea176d68c55dec97f6b461dfb51e00c786529d3')}
CODES={'inspector':('backtest/ndx_outer_refit_result_inspection_research.py','2ed1cf88dce32f9c84359a0606325ef920c8d9addc13dcfbf0130407e62bdc5a'),
 'prepare':('backtest/ndx_multidecision_selected_refit_inputs_research.py','d1ffb2fb550dd1000a3fc8a7003230c38245238e257d3c5a4b286cc966c55b4b'),
 'evidence':('backtest/ndx_outer_lane_refit_evidence_research.py','5f91bb452cd58724b2dca85579ec499f5ecf177aad5dac146556418e19252151')}
FLAGS=dict.fromkeys(('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'),False)
_HANDLES={}

def require(ok,message):
 if not ok:raise ValueError(message)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def ref(path,h):return dict(path=str(Path(path).resolve()),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Pending or invalid source reference')
def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def loads(b):
 def pairs(xs):
  d={}
  for k,v in xs:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def filehash(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def take(r,s):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent');b=p.read_bytes();require(sha(b)==r['sha256'],'Same consumed bytes');merge(s,r);return b
def guard(s):
 require(filehash(SOURCE)==LOADED,'Worker code drift')
 for p,h in s.items():require(not (Path(p).parent/'failure.json').exists() and filehash(p)==h,'Source drift '+p)
def clock():return datetime.now(timezone.utc).isoformat()
def runtime():
 import numpy,pandas,scipy
 return dict(python=sys.version,numpy=numpy.__version__,pandas=pandas.__version__,scipy=scipy.__version__)
def environment():
 require(os.environ.get('PYTHONHASHSEED')=='0' and sys.flags.hash_randomization==0,'Fresh process PYTHONHASHSEED0 required')
 return dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0)
def space(path,n):
 p=Path(path)
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+n,'RESOURCE_STOP_BEFORE_DISPATCH')
def save(path,value,emergency=False):
 b=enc(value)
 if not emergency:space(path,len(b))
 with Path(path).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(Path(path).read_bytes()==b,'Durable saved bytes');return ref(path,sha(b))
def private(role,s):
 p,h=CODES[role];p=ROOT/p;b=take(ref(p,h),s);m=types.ModuleType('_outer_worker_'+role);m.__file__=str(p);exec(compile(b,str(p),'exec'),m.__dict__);return m

def load_common(*,receipt_contract_reference=None):
 # Every future role must be fixed before even probing a source path.
 refs={k:dict(path=p,sha256=h) for k,(p,h) in BOUND.items()};valid(receipt_contract_reference);refs['receipt_contract']=deepcopy(receipt_contract_reference)
 for r in list(refs.values())+[dict(path=str(ROOT/p),sha256=h) for p,h in CODES.values()]:valid(r)
 sources={str(SOURCE):LOADED};docs={}
 for k,r in refs.items():
  b=take(r,sources)
  if not k.endswith('_reader'):docs[k]=loads(b)
 si,sp,sa=docs['selection_index'],docs['selection_publication'],docs['selection_audit']
 require(si['schema']=='REGISTERED_SCORING_SELECTION_INDEX_V1' and sp['schema']=='REGISTERED_SCORING_SELECTION_PUBLICATION_V1','Selection publication roles')
 require(sp['status']=='PUBLISHED_CONDITIONAL_SELECTION_ONLY' and sa['status']=='PASS','Audited selection required')
 for obj in (sp,sa):exact(obj['index_reference'],refs['selection_index'],'Selection index link')
 exact(sa['publication_reference'],refs['selection_publication'],'Selection publication link')
 exact(sa['raw_selection_reference'],refs['selection'],'Audited selection raw link');exact(sp['raw_selection_reference'],refs['selection'],'Published raw link');exact(si['selection_reference'],refs['selection'],'Index raw link')
 require(docs['selection']['schema']=='REGISTERED_SCORING_SELECTION_RAW_V1','Original raw selection envelope')
 contract=docs['receipt_contract'];require(contract['schema']=='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1' and contract['source_bytes_authenticated'] is False,'Explicit separately sealed receipt contract')
 refs['outer_reader']=deepcopy(contract['reader_reference']);valid(refs['outer_reader']);require(Path(refs['outer_reader']['path']).resolve()==(ROOT/'scripts/ndx_outer_lane_refit_independent_readback_20261003.py').resolve(),'Fixed new outer independent reader role');take(refs['outer_reader'],sources)
 fitter=deepcopy(docs['fitter']);fitter['reference']=refs['fitter']
 for d in (si,sp,sa,docs['history'],docs['history_audit'],fitter):
  for p,h in d['source_hashes'].items():merge(sources,ref(p,h))
 channels=[]
 for row in docs['history']['rows']:channels.append(dict(coordinate=row['coordinate'],reference=row['channel_reference'],channel=loads(take(row['channel_reference'],sources))))
 prepare=private('prepare',sources);evidence=private('evidence',sources);inspector=private('inspector',sources)
 selection=dict(document=docs['selection']['result'],reference=refs['selection'],readback=sa,readback_reference=refs['selection_audit'],reader_reference=refs['selection_reader'])
 history=dict(document=docs['history'],reference=refs['history'],readback=docs['history_audit'],readback_reference=refs['history_audit'],reader_reference=refs['history_reader'])
 prepared=prepare.prepare_selected_cutoff_refit_inputs(selection=selection,history=history,channel_bindings=channels,fitter_contract=fitter,previous_refit_evidence=None)
 evidence.validate_fitter(fitter);guard(sources)
 token=uuid.uuid4().hex;_HANDLES[token]=dict(sources=sources,refs=refs,prepared=prepared,fitter=fitter,evidence=evidence,inspector=inspector,receipt_contract=docs['receipt_contract'])
 return dict(handle=token,coordinate_count=48,coordinates=[[r['cutoff'],r['fx_mode'],r['lane']] for r in prepared['rows']])

def context(common):
 require(type(common)is dict and set(common)=={'handle','coordinate_count','coordinates'} and common['handle'] in _HANDLES,'Only private authenticated common handle')
 c=_HANDLES[common['handle']];exact(common['coordinate_count'],48,'Full48');exact(common['coordinates'],[[r['cutoff'],r['fx_mode'],r['lane']] for r in c['prepared']['rows']],'Original ordered48');return c

def load_evidence(item,c,sources):
 require(type(item)is dict,'Explicit evidence references')
 if set(item)=={'references','numerical_reuse_references'}:
  refs=item['references'];origin=item['numerical_reuse_references'];require(type(origin)is dict and set(origin)=={'request','raw_result','postcheck','readback','reader'},'Only direct original reuse refs')
 else:refs=item;origin=None
 require(type(refs)is dict and set(refs)=={'request','raw_result','postcheck','readback','reader'},'All explicit prior roles')
 exact(refs['reader'],c['receipt_contract']['reader_reference'],'Fixed independent reader');envelope={k:loads(take(refs[k],sources)) for k in ('request','raw_result','postcheck','readback')};take(refs['reader'],sources);envelope['references']=deepcopy(refs)
 for obj in envelope.values():
  if type(obj)is dict and 'source_hashes' in obj:
   for p,h in obj['source_hashes'].items():merge(sources,ref(p,h))
 if origin is not None:envelope['numerical_reuse_evidence']=load_evidence(origin,c,sources)
 return envelope

def load_prior(items,c,sources):
 require(type(items)is list,'Explicit prior references, not directory scan')
 return [load_evidence(item,c,sources) for item in items]

def _dispatch(request,fitter,sources):
 # Private fixed source entry; no caller function or alternate import name.
 guard(sources);r=fitter['entrypoint_reference'];b=take(r,sources);module=types.ModuleType('_outer_fixed_v2');module.__file__=r['path'];exec(compile(b,r['path'],'exec'),module.__dict__)
 exact(module._sources(),fitter['source_hashes'],'Actual full numerical closure')
 import pandas as pd
 x=request['fit_matrix'];identity=request['numerical_identity'];frame=pd.DataFrame(x['returns'],index=pd.DatetimeIndex(x['dates']),columns=x['tickers'])
 return module.refit_dynamic_cutoff_weights(returns=frame,cutoff=identity['cutoff'],selected=identity['selected'],weight_spec=identity['weight_spec'],previous_target_weights=identity['requested_previous_target_weights'],**identity['parameters'])

def execute_new(request,c,location,numeric,sources):
 """Internal lifecycle, explicit original raw return before validation/guard."""
 env=environment();versions=runtime();exact(env,c['fitter']['required_worker_environment'],'Worker environment');exact(versions,c['fitter']['runtime_versions'],'Runtime version lock');guard(sources)
 require(not location.exists() and not numeric.exists(),'Any existing attempt forbids retry');space(OUTPUT,len(enc(request))+1024**2)
 location.parent.mkdir(parents=True,exist_ok=True);numeric.parent.mkdir(parents=True,exist_ok=True);location.mkdir(exist_ok=False)
 written=[];invoked=False;returned=False;result=None;error=None
 try:
  request_ref=save(location/'request.json',request);written.append(request_ref);merge(sources,request_ref)
  numeric.mkdir(exist_ok=False)
  started=save(numeric/'started.json',dict(schema='OUTER_LANE_CUTOFF_REFIT_STARTED_V1',request_reference=request_ref,numerical_task_id=request['numerical_task_id'],location_id=request['location_id'],source_hashes=sources,runtime_versions=versions,worker_environment=env,started_at_utc=clock(),input_references=c.get('refs',{}),prior_evidence_references=c.get('prior_references',[]),coordinate_inventory=c.get('coordinate_inventory',[]),**FLAGS));written.append(started)
  guard(sources);environment();exact(runtime(),versions,'Pre-dispatch runtime');invoked=True
  try:result=_dispatch(request,c['fitter'],sources);returned=True
  except BaseException as e:error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
  common=dict(request_reference=request_ref,numerical_task_id=request['numerical_task_id'],location_id=request['location_id'],source_hashes=deepcopy(sources),input_references=c.get('refs',{}),prior_evidence_references=c.get('prior_references',[]),coordinate_inventory=c.get('coordinate_inventory',[]),**FLAGS)
  raw=dict(common,schema='OUTER_LANE_CUTOFF_REFIT_RAW_RETURN_V1',call_invoked=invoked,returned=returned,returned_call_count=int(returned),internal_optimizer_call_count=None,error=error,result=result,runtime_versions=versions,worker_environment=env)
  try:enc(raw)
  except BaseException as e:
   try:representation=repr(result);repr_error=None
   except BaseException as re:representation='<repr failed>';repr_error=dict(type=type(re).__name__,message=str(re))
   diagnostic=representation.encode('utf-8',errors='backslashreplace')
   with (numeric/'unserializable_return.bin').open('xb') as f:f.write(diagnostic);f.flush();os.fsync(f.fileno())
   dr=ref(numeric/'unserializable_return.bin',sha(diagnostic));written.append(dr);raw.update(result=None,error=dict(type='RAW_SERIALIZATION_FAILURE',message=str(e)),returned_type=type(result).__module__+'.'+type(result).__qualname__,original_return_is_json=False,diagnostic_reference=dr,repr_error=repr_error)
  raw_ref=save(numeric/'raw_result.json',raw,True);written.append(raw_ref);merge(sources,raw_ref)
  inspection=None;outcome='NUMERICAL_EXCEPTION' if not returned else 'VALIDATION_FAILURE'
  try:
   guard(sources);exact(environment(),env,'Post environment');exact(runtime(),versions,'Post runtime')
   if error is None:
    require(type(result)is dict and raw['error'] is None,'Full serializable original return required')
    inspection=c['inspector'].inspect_saved_outer_result(request=request,result=result,fitter_contract=c['fitter'])
    require(inspection['status']=='PASS_SAVED_ARITHMETIC','Whole actual returned result inspected')
    if inspection['declared_risks_passed'] is False:outcome='REFIT_RISK_FAILED'
    else:c['evidence'].inspect_return(result,request,c['fitter']);outcome='REFIT_PASSED_PENDING_INDEPENDENT_READBACK'
  except BaseException as e:outcome='VALIDATION_FAILURE';error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
  post=save(location/'postcheck.json',dict(common,schema='OUTER_LANE_CUTOFF_REFIT_POSTCHECK_V1',outcome=outcome,error=error or raw['error'],raw_result_reference=raw_ref,source_hashes=sources,current_location_call_invoked=invoked,current_location_returned_call_count=int(returned),saved_result_inspection=inspection),True);written.append(post)
  if outcome!='VALIDATION_FAILURE':guard(sources)
  for r in written:require(filehash(r['path'])==r['sha256'],'Saved attempt evidence drift')
  require({p.name for p in location.iterdir()}=={'request.json','postcheck.json'},'Exact location evidence')
  require({p.name for p in numeric.iterdir()}==({'started.json','raw_result.json','unserializable_return.bin'} if (numeric/'unserializable_return.bin').exists() else {'started.json','raw_result.json'}),'Exact numeric evidence')
  if outcome=='VALIDATION_FAILURE':save(location/'failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=error,**FLAGS),True)
  return post
 except BaseException as e:
  if not (location/'failure.json').exists():save(location/'failure.json',dict(status='FAILED_NO_RETRY',call_invoked=invoked,returned=returned,saved_references=written,error=dict(type=type(e).__name__,message=str(e)),**FLAGS),True)
  raise

def validate_failed_reuse(origin,expected_request,c,sources):
 refs=origin['references'];request=origin['request'];raw=origin['raw_result'];post=origin['postcheck'];audit=origin['readback']
 exact(request,expected_request,'Actual original request in prepared48')
 for obj,schema in ((raw,'RAW_RETURN'),(post,'POSTCHECK'),(audit,'INDEPENDENT_READBACK')):
  require(obj['schema']=='OUTER_LANE_CUTOFF_REFIT_'+schema+'_V1','Original risk evidence schema')
  exact(obj['request_reference'],refs['request'],'Original risk request binding')
  exact([obj['numerical_task_id'],obj['location_id']],[request['numerical_task_id'],request['location_id']],'Original risk identity')
  for k in FLAGS:require(obj[k] is False,'Original authority false')
  for p,h in obj['source_hashes'].items():merge(sources,ref(p,h))
 require(raw['returned'] is True and raw['call_invoked'] is True and type(raw['returned_call_count'])is int and raw['returned_call_count']==1 and raw['error'] is None,'Original real risk return')
 require(raw['internal_optimizer_call_count'] is None,'Original optimizer calls unknown');exact(raw['runtime_versions'],c['fitter']['runtime_versions'],'Original runtime');exact(raw['worker_environment'],c['fitter']['required_worker_environment'],'Original environment')
 report=c['inspector'].inspect_saved_outer_result(request=request,result=raw['result'],fitter_contract=c['fitter'])
 require(report['status']=='PASS_SAVED_ARITHMETIC' and report['declared_risks_passed'] is False,'Honest complete original risk failure')
 require(post['outcome']=='REFIT_RISK_FAILED' and post['error'] is None and post['current_location_call_invoked'] is True and type(post['current_location_returned_call_count'])is int and post['current_location_returned_call_count']==1,'Only original direct risk attempt')
 require(audit['status']=='PASS_SAVED_RISK_FAILURE' and audit['prior_eligible'] is False and audit['scope']=='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION' and audit['attempt_outcome']=='REFIT_RISK_FAILED','Independent exact risk failure is never prior')
 exact(audit['postcheck_reference'],refs['postcheck'],'Risk audit post binding');exact(refs['reader'],c['receipt_contract']['reader_reference'],'Fixed independent reader');exact(audit['reader_sha256'],refs['reader']['sha256'],'Risk reader version')
 for obj in (post,audit):exact(obj['raw_result_reference'],refs['raw_result'],'Original risk raw binding')
 exact(audit['targets_preserved'],raw['result']['targets'],'Risk original targets');exact(audit['raw_result_body_sha256'],sha(enc(raw['result'])),'Risk complete body')
 required=dict(c['fitter']['source_hashes']);merge(required,c['fitter']['reference']);merge(required,refs['request'])
 for p,h in required.items():require(raw['source_hashes'].get(p)==h,'Raw risk sources')
 for p,h in raw['source_hashes'].items():require(post['source_hashes'].get(p)==h,'Post risk sources')
 for r in refs.values():merge(sources,r)
 for r in refs.values():require(audit['source_hashes'].get(r['path'])==r['sha256'] or r==refs['readback'],'Risk audit evidence closure')
 for p,h in post['source_hashes'].items():require(audit['source_hashes'].get(p)==h,'Risk audit source closure')
 return report

def execute_reuse(request,c,origin,resolved_requests,location,sources):
 """Only a previously independently accepted direct result, never a raw alias."""
 require('numerical_reuse_evidence' not in origin,'No chained numeric reuse')
 original_request=origin['request'];key=tuple(original_request['coordinate'])
 require(key in resolved_requests,'Original reuse coordinate belongs to full prepared48')
 risk_failure=origin['postcheck']['outcome']=='REFIT_RISK_FAILED'
 if risk_failure:validate_failed_reuse(origin,resolved_requests[key],c,sources)
 else:c['evidence'].inspect_prior(origin,resolved_requests[key],c['fitter'],c['receipt_contract'],sources,resolved_requests)
 exact(original_request['numerical_identity'],request['numerical_identity'],'Same entire numerical identity')
 exact(original_request['fit_matrix'],request['fit_matrix'],'Same numeric matrix and column order')
 require(original_request['location_id']!=request['location_id'],'Same-location retry forbidden')
 rawref=origin['references']['raw_result'];exact(rawref['path'],str((OUTPUT/'numerical'/request['numerical_task_id']/'raw_result.json').resolve()),'Only this worker original numeric raw')
 exact(origin['references']['request']['path'],str((OUTPUT/'locations'/original_request['location_id']/'request.json').resolve()),'Original location request')
 guard(sources);require(not location.exists(),'Any existing location forbids retry');space(OUTPUT,len(enc(request))+1024**2);location.parent.mkdir(parents=True,exist_ok=True);location.mkdir(exist_ok=False);written=[]
 try:
  rr=save(location/'request.json',request);written.append(rr);merge(sources,rr)
  post=save(location/'postcheck.json',dict(schema='OUTER_LANE_CUTOFF_REFIT_POSTCHECK_V1',request_reference=rr,numerical_task_id=request['numerical_task_id'],location_id=request['location_id'],raw_result_reference=rawref,outcome='REUSED_AUDITED_NUMERICAL_RISK_FAILURE' if risk_failure else 'REUSED_AUDITED_NUMERICAL_RESULT',error=None,current_location_call_invoked=False,current_location_returned_call_count=0,numerical_reuse_evidence_references=origin['references'],input_references=c.get('refs',{}),prior_evidence_references=c.get('prior_references',[]),coordinate_inventory=c.get('coordinate_inventory',[]),source_hashes=sources,**FLAGS));written.append(post)
  guard(sources)
  for r in written:require(filehash(r['path'])==r['sha256'],'Reuse evidence drift')
  require({p.name for p in location.iterdir()}=={'request.json','postcheck.json'},'Exact reuse location');return post
 except BaseException as e:
  save(location/'failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e)),**FLAGS),True);raise

def run_coordinate(coordinate_index,*,prior_references=None,reuse_evidence_reference=None,execute=False,common=None,receipt_contract_reference=None):
 require(type(coordinate_index)is int and 0<=coordinate_index<48,'Exact original48 ordinal')
 require(execute is True and FRESH_CLI,'Explicit fresh CLI execution only');environment()
 c=context(load_common(receipt_contract_reference=receipt_contract_reference) if common is None else common);sources=dict(c['sources']);prior=load_prior([] if prior_references is None else prior_references,c,sources)
 resolved=c['evidence'].resolve_adjacent_refit_priors(prepared=c['prepared'],prior_evidence=prior,receipt_contract=c['receipt_contract']);guard(sources)
 c=dict(c,prior_references=deepcopy([] if prior_references is None else prior_references),coordinate_inventory=[dict(coordinate_index=i,coordinate=[r['cutoff'],r['fx_mode'],r['lane']],status=r['status'],numerical_task_id=r['numerical_task_id'],location_id=r['location_id']) for i,r in enumerate(resolved['rows'])])
 row=resolved['rows'][coordinate_index];request=row['outer_request']
 if request is None:return dict(status='NOT_DISPATCHED',coordinate_index=coordinate_index,coordinate_count=48,full_status_counts=resolved['status_counts'],reason=row['status'],blocked_evidence_persisted=False,full48_registration_performed=False,coordinator_required=True,**FLAGS)
 location=OUTPUT/'locations'/request['location_id']
 if reuse_evidence_reference is not None:
  origin=load_evidence(reuse_evidence_reference,c,sources);requests={tuple(r['outer_request']['coordinate']):r['outer_request'] for r in resolved['rows'] if r['outer_request'] is not None}
  return execute_reuse(request,c,origin,requests,location,sources)
 return execute_new(request,c,OUTPUT/'locations'/request['location_id'],OUTPUT/'numerical'/request['numerical_task_id'],sources)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--coordinate-index',type=int,required=True);parser.add_argument('--evidence-manifest');parser.add_argument('--evidence-sha256');parser.add_argument('--receipt-contract',required=True);parser.add_argument('--receipt-contract-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 FRESH_CLI=True;environment();common=load_common(receipt_contract_reference=ref(args.receipt_contract,args.receipt_contract_sha256));evidence={}
 if args.evidence_manifest:
  require(args.evidence_sha256 is not None,'Externally anchored evidence manifest');evidence=loads(take(ref(args.evidence_manifest,args.evidence_sha256),context(common)['sources']))
  require(set(evidence)=={'prior_references','reuse_evidence_reference'},'Explicit evidence manifest fields')
 print(json.dumps(run_coordinate(args.coordinate_index,prior_references=evidence.get('prior_references'),reuse_evidence_reference=evidence.get('reuse_evidence_reference'),execute=args.execute,common=common)))
