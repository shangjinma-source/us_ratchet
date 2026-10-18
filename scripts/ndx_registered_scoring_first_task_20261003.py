"""One fixed first registered BACKWARD job; fresh CLI only, never retry."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,platform,re,shutil,sys,traceback,types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest();FRESH_CLI=False
TASK_ID='75ad5a6a98d6056d4f13962d31b43debc809d9d663f719639fd1ea5e80fd4598'
OUTPUT=ROOT/'data/cache/research/registered_scoring_first_task_20261003_v1'/TASK_ID
BOUND={
 'budget':('data/cache/research/multidecision_scoring_budget_20261003_v1/plan.json','f99843ce3d28829f6c258e608a7e3c2ee8605e2432eaaa890299dc1f9edb6d04'),
 'budget_publication':('data/cache/research/multidecision_scoring_budget_20261003_v1/publication.json','e9b9108018332ec7260cbcabc00b2fb751bbb393b7a50930be6d7f0e32a75f82'),
 'budget_audit':('data/cache/research/multidecision_scoring_budget_independent_readback_20261003_v1/independent_readback.json','38446edc13b175845e364906a52c8117ebf5f53ed0abf13b459d55664178846c'),
 'budget_reader':('scripts/ndx_multidecision_scoring_budget_independent_readback_20261003.py','d2b64714902481ed3bcbcbf495cae1bd545e5237544de96282a2d78d6c2d0ade')}
CODES={
 'assembler':('backtest/ndx_registered_scoring_job_inputs_research.py','75313406656ad536a14e848a6a8f3bec9218f900529f84b21740176b62140ec2'),
 'rolling':('backtest/ndx_multidecision_rolling_fit_research.py','9d7ca29bf6eff9be6e42747e98a9060e4cb1d44f7c7c6fb4af96cba9b4f67492'),
 'reducer':('backtest/ndx_multidecision_window_scoring_research.py','7f9d4b6573998f036b93154ff4547b83f90b2112f4e003542057040ec503f137'),
 'inspector':('backtest/ndx_multidecision_window_scoring_inspection_research.py','cceb0cb4ed97d4b4f94fe049558c67d0b2501090cdfd4da65f59104490416bf8')}
FLAGS=dict.fromkeys(('point_in_time_verified','promotion_allowed','account_executed','whole_queue_completed','winner_selected','outer_lane_prior_applied','whole_lot_gate_evaluated','formal_benchmark_passed','old_fit_weights_reused','old_audit_repeated','runtime_binary_closure_verified','full_transitive_source_closure_reverified'),False)


def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,msg):require(encoded(a)==encoded(b),msg)
def reference(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def loads(b):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate key');result[k]=v
        return result
    def reject(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(b,object_pairs_hook=pairs,parse_constant=reject)
def file_hash(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def merge(s,p,h):
    p=str(Path(p).resolve());require(type(h) is str and re.fullmatch('[a-f0-9]{64}',h),'SHA')
    require(p not in s or s[p]==h,'Source hash conflict');s[p]=h

def take(r,s):
    p=Path(r['path']).resolve();require(not (p.parent/'failure.json').exists(),'Failed source namespace')
    b=p.read_bytes();require(sha(b)==r['sha256'],'Source bytes differ '+str(p));merge(s,p,r['sha256']);return b

def guard(s):
    require(file_hash(SOURCE)==LOADED_SHA,'Loaded wrapper drift')
    for p,h in s.items():
        require(not (Path(p).parent/'failure.json').exists(),'Parent failure appeared')
        require(file_hash(p)==h,'Bound source drift '+p)

def runtime():
    import numpy,pandas,scipy
    return dict(python=sys.version,numpy=numpy.__version__,pandas=pandas.__version__,scipy=scipy.__version__)
def worker_environment():
    require(os.environ.get('PYTHONHASHSEED')=='0' and sys.flags.hash_randomization==0,'New worker process requires PYTHONHASHSEED=0 before startup')
    return dict(PYTHONHASHSEED=os.environ['PYTHONHASHSEED'],sys_flags_hash_randomization=sys.flags.hash_randomization)
def private(role,s):
    relative,h=CODES[role];p=(ROOT/relative).resolve();b=take(reference(p,h),s)
    module=types.ModuleType('_registered_first_'+role);module.__file__=str(p);exec(compile(b,str(p),'exec'),module.__dict__);return module

def validate_budget(docs,refs):
    d=docs['budget'];p=docs['budget_publication'];a=docs['budget_audit']
    require(d['schema']=='MULTIDECISION_SCORING_BUDGET_DOCUMENT_V1' and p['schema']=='MULTIDECISION_SCORING_BUDGET_PUBLICATION_V1' and a['schema']=='MULTIDECISION_SCORING_BUDGET_INDEPENDENT_READBACK_V1','Registered budget schemas')
    require(d['status']==p['status']=='REGISTERED_BEFORE_CANDIDATE_SCORING_NOT_DISPATCH_AUTHORITY' and a['status']=='PASS','Actual registered/readback status')
    exact(p['plan_reference'],refs['budget'],'Published plan');exact(a['plan_reference'],refs['budget'],'Audited plan');exact(a['publication_reference'],refs['budget_publication'],'Audited publication')
    require(a['reader_sha256']==refs['budget_reader']['sha256'],'Fixed independent reader')
    exact(p['source_hashes'],d['source_hashes'],'Plan source claims');exact(a['raw_plan_reference'],d['raw_plan_reference'],'Audited raw plan')
    for value in (d,p,a):
        for key in ('point_in_time_verified','promotion_allowed','fit_performed','score_computed','score_dispatch_authorized'):require(value[key] is False,'Original research authority')
    plan=d['plan'];require(plan['content_sha256']==sha(encoded({k:v for k,v in plan.items() if k!='content_sha256'})),'Plan content hash')
    require(len(plan['rows'])==6 and len(plan['full_universe_preserved'])==77,'Six periods/full inventory')
    node=plan['rows'][0]['mode_plans'][1];job=node['tasks'][0]
    require(job['job_id']==TASK_ID and job['identity']['cutoff']=='2026-03-31' and job['identity']['fx_mode']=='BACKWARD_LATEST_VALID_FX' and job['identity']['weight_spec']=='equal_weight' and type(job['position']['k']) is int and job['position']['k']==4,'Fixed first registered task, not selected by result')
    return plan,node,job


def load_inputs():
    require(all(type(h) is str and len(h)==64 for p,h in list(BOUND.values())+list(CODES.values())),'Actual external anchors pending')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        r=reference(ROOT/relative,h);b=take(r,sources);refs[role]=r
        if role!='budget_reader':docs[role]=loads(b)
    plan,node,job=validate_budget(docs,refs);parent=docs['budget']
    for role in ('history_index','history_publication','history_audit','history_reader','original8_inputs','original8_publication','original8_audit','original8_reader','target_inputs','target_index','target_publication','target_audit','target_reader','rolling_fitter_manifest','policy'):
        r=parent['input_references'][role];refs[role]=deepcopy(r);b=take(r,sources)
        if not role.endswith('_reader'):docs[role]=loads(b)
        require(docs['budget_audit']['source_hashes'][r['path']]==r['sha256'],'Budget audit input source '+role)
    for role,key,document in (('history','index_reference','history_index'),('original8','inputs_reference','original8_inputs'),('target','index_reference','target_index')):
        audit=docs[role+'_audit'];pub=docs[role+'_publication']
        require(audit['status']=='PASS' and audit['reader_sha256']==refs[role+'_reader']['sha256'],'Input saved independent readback')
        exact(audit[key],refs[document],'Input audit object');exact(audit['publication_reference'],refs[role+'_publication'],'Input audit publication');exact(pub[key],refs[document],'Input publication')
    exact(docs['target_index']['target_inputs_reference'],refs['target_inputs'],'Actual target input payload')
    manifest=docs['rolling_fitter_manifest'];exact(manifest, parent['rolling_fitter_manifest_preserved'],'Registered frozen rolling numerical contract')
    exact(manifest['policy_reference'],refs['policy'],'Fixed policy ref');require(len(manifest['source_hashes'])==25,'Full numerical source closure')
    for p,h in manifest['source_hashes'].items():take(reference(p,h),sources)
    for role in ('rolling','reducer'):require(manifest['source_hashes'][str(ROOT/CODES[role][0])]==CODES[role][1],'Fixed numeric implementation')
    index=docs['history_index'];by={r['coordinate']['security_id']:r for r in index['rows']};require(len(by)==77,'Full history inventory')
    bindings=[]
    for sid in job['identity']['security_ids']:
        row=by[sid];r=row['channel_reference'];channel=loads(take(r,sources))
        i=row['index'];audited=docs['history_audit']['rows'][i];exact(audited['channel_reference'],r,'Selected channel readback bytes');exact(audited['coordinate'],row['coordinate'],'Selected channel readback identity');require(audited['inspection']['status']=='PASS','Selected channel audited')
        bindings.append(dict(coordinate=deepcopy(row['coordinate']),reference=deepcopy(r),channel=channel))
    args=dict(registered_job=deepcopy(job),registered_mode_plan=deepcopy(node),decision_inputs=deepcopy(plan['decision_inputs_preserved'][0]),universe=deepcopy(plan['full_universe_preserved']),channel_bindings=bindings,original8_inputs=docs['original8_inputs']['scoring_inputs'],original8_reference=refs['original8_inputs'],target_inputs=docs['target_inputs'],target_reference=refs['target_inputs'],fitter_manifest=manifest,fitter_reference=refs['rolling_fitter_manifest'],budget_reference=refs['budget'])
    for relative,h in CODES.values():take(reference(ROOT/relative,h),sources)
    assembler=private('assembler',sources)
    guard(sources)
    return dict(args=args,refs=refs,sources=sources,manifest=manifest,assembler=assembler)


def space(n):
    p=OUTPUT.parent
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=5*1024**3+n,'5GiB resource reserve plus bytes')
def save_bytes(path,b,emergency=False):
    if not emergency:space(len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes');return reference(path,sha(b))
def save(path,value,emergency=False):return save_bytes(path,encoded(value),emergency)

def call_and_preserve(stage,function,kwargs,inputs_reference,context,written):
    result=None;error=None;returned=False;space(0)
    dispatch_runtime=runtime();dispatch_environment=worker_environment()
    try:result=function(**kwargs);returned=True
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    raw=dict(schema='REGISTERED_SCORING_RAW_'+stage.upper()+'_V1',job_id=TASK_ID,stage=stage,call_invoked=True,returned=returned,returned_call_count=int(returned),internal_optimizer_call_count=None,result=result,error=error,inputs_reference=inputs_reference,source_hashes=deepcopy(context['sources']),runtime=dispatch_runtime,worker_environment=dispatch_environment,result_preserved_as_json=True,**FLAGS)
    try:blob=encoded(raw)
    except Exception as exc:
        representation=(type(result).__module__+'.'+type(result).__qualname__+chr(10)+repr(result)).encode('utf-8',errors='backslashreplace')
        rr=save_bytes(OUTPUT/('raw_'+stage+'_representation.bin'),representation,True);written.append(rr)
        raw.update(result=None,result_preserved_as_json=False,raw_representation_reference=rr,serialization_error=dict(type=type(exc).__name__,message=str(exc)));blob=encoded(raw)
    rr=save_bytes(OUTPUT/('raw_'+stage+'.json'),blob,True);written.append(rr)
    return raw,rr


def run(*,execute=False):
    require(type(execute) is bool,'Exact execute')
    if not execute:return dict(status='NOT_EXECUTED',job_id=TASK_ID)
    require(FRESH_CLI,'Execute only in fresh command-line worker process');worker_environment()
    require(not OUTPUT.exists(),'Immutable attempt exists; no retry')
    context=load_inputs();exact(runtime(),context['manifest']['runtime_versions'],'Registered runtime versions')
    space(0);OUTPUT.mkdir(parents=True,exist_ok=False);written=[];stage='ASSEMBLE';outcome='VALIDATION_FAILURE';inputs_ref=None;fit_ref=None;score_ref=None;inspection_ref=None
    try:
        written.append(save(OUTPUT/'started.json',dict(schema='REGISTERED_SCORING_FIRST_TASK_STARTED_V1',job_id=TASK_ID,started_at_utc=datetime.now(timezone.utc).isoformat(),registered_task_pointer='/plan/rows/0/mode_plans/1/tasks/0',input_references=context['refs'],source_hashes=deepcopy(context['sources']),runtime=runtime(),worker_environment=worker_environment(),retry_allowed=False,whole_queue_task_count=19584,**FLAGS)))
        guard(context['sources']);inputs=context['assembler'].assemble_registered_scoring_job_inputs(**context['args'])
        require(inputs['job_id']==TASK_ID and inputs['registered_job_preserved']==context['args']['registered_job'],'Assembler returned original registered job')
        inputs_ref=save(OUTPUT/'inputs.json',dict(schema='REGISTERED_SCORING_FIRST_TASK_INPUTS_DOCUMENT_V1',job_id=TASK_ID,assembled=inputs,input_references=context['refs'],source_hashes=deepcopy(context['sources']),**FLAGS));written.append(inputs_ref)
        if inputs['status']=='SOURCE_BLOCKED':outcome='SOURCE_BLOCKED'
        else:
            require(inputs['status']=='ASSEMBLED_NOT_DISPATCHED','Valid complete assembler output')
            rolling=private('rolling',context['sources']);reducer=private('reducer',context['sources']);inspector=private('inspector',context['sources'])
            exact(rolling.source_hashes(),context['manifest']['source_hashes'],'Private fitter complete source closure')
            guard(context['sources']);stage='FIT'
            rawfit,fit_ref=call_and_preserve('fit',rolling.fit_causal_scoring_windows,inputs['rolling_inputs'],inputs_ref,context,written)
            exact(runtime(),rawfit['runtime'],'Runtime drift after fit');exact(worker_environment(),rawfit['worker_environment'],'Worker environment drift after fit')
            if not rawfit['returned']:outcome='NUMERICAL_EXCEPTION';raise RuntimeError('Fitting raised; raw exception preserved')
            require(rawfit['result_preserved_as_json'] and type(rawfit['result']) is dict,'Fit returned invalid structure');fit=rawfit['result']
            require(fit['schema']=='MULTIDECISION_CAUSAL_ROLLING_FITS_V1' and len(fit['windows'])==13,'Complete thirteen fitted targets')
            require(fit['cutoff']==inputs['cutoff'] and fit['weight_spec']==inputs['rolling_inputs']['weight_spec'],'Returned fit coordinate')
            exact(fit['securities'],inputs['rolling_inputs']['securities'],'Returned fit column order')
            for key in ('source_bytes_authenticated','outer_lane_prior_applied','score_computed','point_in_time_verified','account_executed','promotion_allowed'):require(fit[key] is False,'Returned fit authority')
            exact(fit['source_hashes'],context['manifest']['source_hashes'],'Returned fitter closure');guard(context['sources'])
            stage='SCORE';score_args=dict(deepcopy(inputs['reducer_inputs']),fitted_windows=fit['windows'])
            rawscore,score_ref=call_and_preserve('score',reducer.reduce_fitted_scoring_windows,score_args,inputs_ref,context,written)
            exact(runtime(),rawscore['runtime'],'Runtime drift after score');exact(worker_environment(),rawscore['worker_environment'],'Worker environment drift after score')
            if not rawscore['returned']:outcome='NUMERICAL_EXCEPTION';raise RuntimeError('Scoring raised; raw exception preserved')
            require(rawscore['result_preserved_as_json'] and type(rawscore['result']) is dict,'Score returned invalid structure');guard(context['sources'])
            stage='INDEPENDENT_SCORE_INSPECTION';report=inspector.inspect_fitted_scoring_windows(**score_args,saved_score=rawscore['result']);require(report['status']=='PASS','Saved scoring arithmetic inspection')
            inspection_ref=save(OUTPUT/'score_inspection.json',dict(schema='REGISTERED_SCORING_SCORE_INSPECTION_DOCUMENT_V1',job_id=TASK_ID,inspection=report,inputs_reference=inputs_ref,raw_fit_reference=fit_ref,raw_score_reference=score_ref,inspector_reference=reference(ROOT/CODES['inspector'][0],CODES['inspector'][1]),source_hashes=deepcopy(context['sources']),**FLAGS));written.append(inspection_ref);outcome='SCORED_PENDING_INDEPENDENT_READBACK'
        guard(context['sources']);stage='POSTCHECK'
        post=save(OUTPUT/'postcheck.json',dict(schema='REGISTERED_SCORING_FIRST_TASK_POSTCHECK_V1',job_id=TASK_ID,outcome=outcome,inputs_reference=inputs_ref,raw_fit_reference=fit_ref,raw_score_reference=score_ref,score_inspection_reference=inspection_ref,saved_references=deepcopy(written),source_hashes=deepcopy(context['sources']),runtime=runtime(),worker_environment=worker_environment(),retry_allowed=False,whole_queue_task_count=19584,attempted_job_count=1,**FLAGS));written.append(post)
        guard(context['sources']);require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in written},'Exact attempt files')
        for r in written:require(file_hash(r['path'])==r['sha256'],'Final output drift')
        return post
    except Exception as exc:
        failure=dict(schema='REGISTERED_SCORING_FIRST_TASK_FAILURE_V1',job_id=TASK_ID,status='FAILED_DO_NOT_CONSUME_AS_COMPLETED',outcome=outcome,stage=stage,error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()),inputs_reference=inputs_ref,raw_fit_reference=fit_ref,raw_score_reference=score_ref,score_inspection_reference=inspection_ref,saved_references=written,source_hashes=deepcopy(context['sources']),retry_allowed=False,**FLAGS)
        if not (OUTPUT/'postcheck.json').exists():written.append(save(OUTPUT/'postcheck.json',dict(failure,schema='REGISTERED_SCORING_FIRST_TASK_POSTCHECK_V1'),True))
        save(OUTPUT/'failure.json',failure,True);raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');FRESH_CLI=True;print(json.dumps(run(execute=parser.parse_args().execute)))
