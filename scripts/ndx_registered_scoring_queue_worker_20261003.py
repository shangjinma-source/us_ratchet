"""Registered scoring shards: durable raw journals, explicit completed reuse only."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,json,os,re,shutil,sys,traceback,types,uuid
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve()
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest();FRESH_CLI=False
OUTPUT=ROOT/'data/cache/research/registered_scoring_queue_worker_20261003_v1'
FIRST_ID='75ad5a6a98d6056d4f13962d31b43debc809d9d663f719639fd1ea5e80fd4598'
FIRST_AUDIT_PATH=ROOT/'data/cache/research/registered_scoring_first_task_independent_readback_20261003_v1'/FIRST_ID/'independent_readback.json'
FIRST_AUDIT_SHA='b227474d150f25eb742d0c549df01cd628cd88d5b38507e751651aebeac4ff7f';FIRST_READER_SHA='0ae6d1ef179723133784f55cf92fde42c491b5392f4ab41f84546fef5d382f2d'
FIRST_READER=ROOT/'scripts/ndx_registered_scoring_first_task_independent_readback_20261003.py'
QUEUE=ROOT/'backtest/ndx_registered_scoring_queue_research.py';QUEUE_SHA='7e0b171d4a38348a072be7379d07db795dcd56558250ed4f998a41b37afd0fa8'
JOURNAL=ROOT/'backtest/ndx_registered_scoring_journal_research.py';JOURNAL_SHA='4f1d3537cb0319d01e148f6e49b91e86c05dbfdb58dbf73cc7796b5f2ca602b7'
FIRST_WORKER=ROOT/'scripts/ndx_registered_scoring_first_task_20261003.py';FIRST_WORKER_SHA='fdf6426845766f34d43c7bc613f85e947dd050edb2d656e941d5f0b0cd31b80b'
_COMMON={}
FALSE=dict.fromkeys(('automatic_retry_allowed','point_in_time_verified','promotion_allowed','account_executed','winner_selected','outer_lane_prior_applied','whole_lot_gate_evaluated','formal_benchmark_passed','full_transitive_source_closure_reverified','runtime_binary_closure_verified','continuous_source_monitoring_claimed'),False)
SUCCESS='SCORED_PENDING_INDEPENDENT_READBACK'


def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(enc(v))
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def valid(h):return type(h) is str and re.fullmatch('[a-f0-9]{64}',h) is not None
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def filehash(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def loads(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    def reject(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=reject)
def take(r,s):
    p=Path(r['path']).resolve();h=r['sha256'];require(valid(h) and (str(p) not in s or s[str(p)]==h),'Fixed source SHA conflict')
    require(not (p.parent/'failure.json').exists(),'Parent failure');b=p.read_bytes();require(sha(b)==h,'Source changed '+str(p));s[str(p)]=h;return b

def read_attempt_result(r):
    # A STOPPED shard deliberately has failure.json; retain its actual partition.
    p=Path(r['path']);b=p.read_bytes();require(valid(r['sha256']) and sha(b)==r['sha256'],'Attempt result bytes drift');return loads(b)


def compile_source(path,h,s):
    b=take(ref(path,h),s);m=types.ModuleType('_queue_private_'+path.stem);m.__file__=str(path);exec(compile(b,str(path),'exec'),m.__dict__);return m

def environment():
    require(os.environ.get('PYTHONHASHSEED')=='0' and sys.flags.hash_randomization==0,'New process PYTHONHASHSEED0 required')
    return dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0)
def guard_sources(s):
    require(filehash(SOURCE)==LOADED_SHA,'Loaded worker drift')
    for p,h in s.items():require(not (Path(p).parent/'failure.json').exists() and filehash(p)==h,'Source drift '+p)
def code_guard(c):
    guard_sources(c['code_sources']);environment();exact(c['first'].runtime(),c['manifest']['runtime_versions'],'Runtime drift')
def common_guard(c):
    guard_sources(c['sources']);code_guard(c)
def space(n=0):
    p=OUTPUT.parent
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=5*1024**3+n,'RESOURCE_STOP_BEFORE_DISPATCH')
def save(p,v,emergency=False):
    b=enc(v)
    if not emergency:space(len(b))
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved output');return ref(p,sha(b))


def load_common():
    require(all(valid(h) for h in (FIRST_AUDIT_SHA,FIRST_READER_SHA,QUEUE_SHA,JOURNAL_SHA,FIRST_WORKER_SHA)),'Final queue/first audit pins pending')
    s={str(SOURCE):LOADED_SHA};first=compile_source(FIRST_WORKER,FIRST_WORKER_SHA,s);docs={};refs={}
    for role,(path,h) in first.BOUND.items():
        r=ref(ROOT/path,h);b=take(r,s);refs[role]=r
        if role!='budget_reader':docs[role]=loads(b)
    plan,node,job=first.validate_budget(docs,refs)
    for role,r in docs['budget']['input_references'].items():
        if role not in ('fitter_container','mapping','mdv_result','mdv_report'):
            refs[role]=deepcopy(r);b=take(r,s)
            if not role.endswith('_reader'):docs[role]=loads(b)
    for role,key,document in (('history','index_reference','history_index'),('original8','inputs_reference','original8_inputs'),('target','index_reference','target_index')):
        a=docs[role+'_audit'];pub=docs[role+'_publication']
        require(a['status']=='PASS' and a['reader_sha256']==refs[role+'_reader']['sha256'],'Independent parent readback')
        exact(a[key],refs[document],'Parent audited object');exact(a['publication_reference'],refs[role+'_publication'],'Parent audited publication');exact(pub[key],refs[document],'Parent publication object')
    for role,r in refs.items():
        if role in docs['budget']['input_references']:require(docs['budget_audit']['source_hashes'][r['path']]==r['sha256'],'Audited registered input')
    exact(docs['target_index']['target_inputs_reference'],refs['target_inputs'],'Registered target payload')
    manifest=docs['rolling_fitter_manifest'];exact(manifest,docs['budget']['rolling_fitter_manifest_preserved'],'Registered fitter contract')
    exact(manifest['policy_reference'],refs['policy'],'Numerical policy');require(len(manifest['source_hashes'])==25,'Full registered numerical closure')
    for p,h in manifest['source_hashes'].items():take(ref(p,h),s)
    firstaudit=loads(take(ref(FIRST_AUDIT_PATH,FIRST_AUDIT_SHA),s));take(ref(FIRST_READER,FIRST_READER_SHA),s)
    require(firstaudit['schema']=='REGISTERED_SCORING_FIRST_TASK_INDEPENDENT_READBACK_V1' and firstaudit['status']=='PASS' and firstaudit['job_id']==FIRST_ID and firstaudit['reader_sha256']==FIRST_READER_SHA,'Actual first independent PASS')
    firstrefs=deepcopy(firstaudit['evidence_references']);require(set(firstrefs)=={'postcheck','started','inputs','raw_fit','raw_score','score_inspection'},'Complete external first evidence')
    exact(firstaudit['postcheck_reference'],firstrefs['postcheck'],'External postcheck link')
    firstpost=None
    for role,r in firstrefs.items():
        b=take(r,s)
        if role=='postcheck':firstpost=loads(b)
    require(firstpost['job_id']==FIRST_ID and firstpost['outcome']==SUCCESS,'First completed result')
    firstrefs['independent_readback']=ref(FIRST_AUDIT_PATH,FIRST_AUDIT_SHA)
    channels={};index=docs['history_index'];audit=docs['history_audit'];require(len(index['rows'])==len(audit['rows'])==77,'All77 history channels')
    for i,row in enumerate(index['rows']):
        exact(audit['rows'][i]['coordinate'],row['coordinate'],'Audited source identity');exact(audit['rows'][i]['channel_reference'],row['channel_reference'],'Audited source ref');require(audit['rows'][i]['inspection']['status']=='PASS','Independent channel result')
        sid=row['coordinate']['security_id'];require(sid not in channels,'Unique SID');channels[sid]=dict(coordinate=deepcopy(row['coordinate']),reference=deepcopy(row['channel_reference']),channel=loads(take(row['channel_reference'],s)))
    queuecore=compile_source(QUEUE,QUEUE_SHA,s);journal=compile_source(JOURNAL,JOURNAL_SHA,s)
    queue=queuecore.build_registered_scoring_queue(budget_plan=plan,budget_reference=refs['budget'])
    require(queue['logical_job_count']==19584 and queue['source_blocked_job_count']==queue['executable_job_count']==9792 and queue['first_executable_job']['job_id']==FIRST_ID,'Complete registered logical domain')
    modules={}
    for role,(relative,h) in first.CODES.items():modules[role]=compile_source(ROOT/relative,h,s)
    exact(modules['rolling'].source_hashes(),manifest['source_hashes'],'Same registered private numerical closure')
    c=dict(first=first,docs=docs,refs=refs,plan=plan,manifest=manifest,channels=channels,queue=queue,journal=journal,modules=modules,sources=s,first_refs=firstrefs,code_sources={p:h for p,h in s.items() if Path(p).suffix=='.py'})
    common_guard(c);handle=uuid.uuid4().hex;_COMMON[handle]=c;return handle

def context(handle):
    require(type(handle) is str and handle in _COMMON,'Only a private same-process common handle');return _COMMON[handle]

def job_arguments(c,descriptor):
    j=descriptor['decision_index'];mi=descriptor['mode_index'];ti=descriptor['task_index'];plan=c['plan'];node=plan['rows'][j]['mode_plans'][mi];job=node['tasks'][ti]
    require(job['job_id']==descriptor['job_id'] and job['status']=='PLANNED_NOT_ATTEMPTED','Exact registered dispatch coordinate')
    refs=c['refs'];return dict(registered_job=job,registered_mode_plan=node,decision_inputs=plan['decision_inputs_preserved'][j],universe=plan['full_universe_preserved'],channel_bindings=[c['channels'][sid] for sid in job['identity']['security_ids']],original8_inputs=c['docs']['original8_inputs']['scoring_inputs'],original8_reference=refs['original8_inputs'],target_inputs=c['docs']['target_inputs'],target_reference=refs['target_inputs'],fitter_manifest=c['manifest'],fitter_reference=refs['rolling_fitter_manifest'],budget_reference=refs['budget'])


class Journal:
    def __init__(self,path,core,context_hash):
        self.path=path;self.core=core;self.context_hash=context_hash;self.sequence=0;self.previous='0'*64;self.failed=False
        self.file=path.open('xb')
    def append(self,position,taskid,stage,payload):
        row=self.core.make_record(sequence=self.sequence,previous_hash=self.previous,context_sha256=self.context_hash,task_id=taskid,task_position=position,stage=stage,payload=payload)
        require(not self.failed,'Failed journal cannot be appended or repaired')
        b=enc(row)+b'\n'
        try:self.file.write(b);self.file.flush();os.fsync(self.file.fileno())
        except Exception:self.failed=True;raise
        self.sequence+=1;self.previous=row['record_sha256'];return dict(sequence=row['sequence'],record_sha256=row['record_sha256'])
    def close(self):self.file.close()


def call_numeric(function,kwargs,metadata):
    result=None;error=None;returned=False
    try:result=function(**kwargs);returned=True
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    raw=dict(call_invoked=True,returned=returned,returned_call_count=int(returned),internal_optimizer_call_count=None,result=result,error=error,result_preserved_as_json=True,dispatch_metadata=metadata)
    try:enc(raw)
    except Exception as exc:
        try:representation=repr(result)
        except Exception as repr_exc:representation='REPR_FAILED '+type(repr_exc).__name__
        blob=(type(result).__module__+'.'+type(result).__qualname__+chr(10)+representation).encode('utf-8',errors='backslashreplace')
        raw.update(result=None,result_preserved_as_json=False,representation_utf8_base64=base64.b64encode(blob).decode(),representation_sha256=sha(blob),serialization_error=dict(type=type(exc).__name__,message=str(exc)))
    return raw


def execute_descriptor(c,descriptor,position,journal):
    tid=descriptor['job_id'];outcome='VALIDATION_FAILURE';stage='START';recordrefs=[]
    def append(name,payload):recordrefs.append(journal.append(position,tid,name,payload))
    append('TASK_STARTED',dict(descriptor=descriptor,started_at_utc=datetime.now(timezone.utc).isoformat(),fit_call_invoked=False,score_call_invoked=False))
    try:
        code_guard(c);args=job_arguments(c,descriptor);assembled=c['modules']['assembler'].assemble_registered_scoring_job_inputs(**args)
        append('INPUTS',dict(assembled=assembled));require(assembled['job_id']==tid and assembled['status']=='ASSEMBLED_NOT_DISPATCHED','Registered available input')
        code_guard(c);space();metadata=dict(runtime=c['first'].runtime(),environment=environment())
        stage='FIT';append('FIT_DISPATCH',metadata)
        rawfit=call_numeric(c['modules']['rolling'].fit_causal_scoring_windows,assembled['rolling_inputs'],metadata);append('RAW_FIT',rawfit)
        if not rawfit['returned']:outcome='NUMERICAL_EXCEPTION';raise RuntimeError('Saved fit exception')
        require(rawfit['result_preserved_as_json'] and type(rawfit['result']) is dict,'Invalid fit return');fit=rawfit['result'];code_guard(c)
        require(fit['schema']=='MULTIDECISION_CAUSAL_ROLLING_FITS_V1' and len(fit['windows'])==13,'All13 fits');exact(fit['securities'],assembled['ordered_securities'],'Fit columns');require(fit['cutoff']==descriptor['cutoff'] and fit['weight_spec']==descriptor['weight_spec'],'Fit coordinate');exact(fit['source_hashes'],c['manifest']['source_hashes'],'Returned fitter closure')
        for key in ('source_bytes_authenticated','outer_lane_prior_applied','score_computed','point_in_time_verified','account_executed','promotion_allowed'):require(fit[key] is False,'Returned fit authority')
        scoreargs=dict(deepcopy(assembled['reducer_inputs']),fitted_windows=fit['windows']);space();metadata=dict(runtime=c['first'].runtime(),environment=environment())
        stage='SCORE';append('SCORE_DISPATCH',metadata)
        rawscore=call_numeric(c['modules']['reducer'].reduce_fitted_scoring_windows,scoreargs,metadata);append('RAW_SCORE',rawscore)
        if not rawscore['returned']:outcome='NUMERICAL_EXCEPTION';raise RuntimeError('Saved score exception')
        require(rawscore['result_preserved_as_json'] and type(rawscore['result']) is dict,'Invalid score return');code_guard(c)
        stage='INSPECTION';report=c['modules']['inspector'].inspect_fitted_scoring_windows(**scoreargs,saved_score=rawscore['result']);append('INSPECTION',dict(inspection=report));require(report['status']=='PASS','Score inspection')
        outcome=SUCCESS;append('POSTCHECK',dict(outcome=outcome,record_references=recordrefs,whole_queue_completed=False,**FALSE));return outcome
    except Exception as exc:
        if journal.failed:raise
        append('POSTCHECK',dict(outcome=outcome,failed_stage=stage,error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()),record_references=recordrefs,whole_queue_completed=False,**FALSE));return outcome



def ensure_root(c):
    context_value=dict(schema='REGISTERED_SCORING_QUEUE_CONTEXT_V1',queue_content_sha256=c['queue']['content_sha256'],input_references=c['refs'],source_hashes=c['sources'],first_external_evidence=c['first_refs'],large_sources_checked_at='COMMON_LOAD_AND_REQUEST_BEGIN_END',numeric_python_sources_checked_at='EACH_NUMERIC_JOB_BEFORE_AND_AFTER_CALL',continuous_source_monitoring_claimed=False,**{k:v for k,v in FALSE.items() if k!='continuous_source_monitoring_claimed'})
    ch=digest(context_value);expected=dict(context_reference=ref(OUTPUT/'context.json',ch),queue_reference=ref(OUTPUT/'queue.json',digest(c['queue'])))
    if not OUTPUT.exists():
        space();OUTPUT.mkdir(parents=True,exist_ok=False)
        try:
            save(OUTPUT/'context.json',context_value);save(OUTPUT/'queue.json',c['queue']);(OUTPUT/'shards').mkdir();(OUTPUT/'requests').mkdir()
            save(OUTPUT/'publication.json',dict(schema='REGISTERED_SCORING_QUEUE_CONTEXT_PUBLICATION_V1',status='CONTEXT_ONLY_NOT_ALL_JOBS_COMPLETE',**expected,**FALSE))
        except Exception as exc:
            save(OUTPUT/'failure.json',dict(status='FAILED_CONTEXT_DO_NOT_RETRY',error=str(exc),**FALSE),True);raise
    require(not (OUTPUT/'failure.json').exists(),'Failed context cannot resume')
    exact(loads((OUTPUT/'context.json').read_bytes()),context_value,'Same immutable queue execution context')
    require(filehash(OUTPUT/'queue.json')==expected['queue_reference']['sha256'],'Full blocked/executable domain queue')
    pub=loads((OUTPUT/'publication.json').read_bytes());exact(pub,dict(schema='REGISTERED_SCORING_QUEUE_CONTEXT_PUBLICATION_V1',status='CONTEXT_ONLY_NOT_ALL_JOBS_COMPLETE',**expected,**FALSE),'Root context publication')
    require({p.name for p in OUTPUT.iterdir()}=={'context.json','queue.json','publication.json','shards','requests'},'Unexpected context files')
    return ch,expected


def verify_completed(c,descriptor,external_reference,context_hash):
    directory=OUTPUT/'shards'/f"{descriptor['shard_index']:04d}"
    require(Path(external_reference['path'])==directory/'result.json','Explicit completed result location')
    require({p.name for p in directory.iterdir()}=={'started.json','journal.jsonl','result.json'},'Failed or partial shard cannot be resumed')
    result=loads(take(external_reference,{}));require(result['status']=='COMPLETE' and result['context_sha256']==context_hash,'Only externally bound complete shard')
    require(result['schema']=='REGISTERED_SCORING_SHARD_RESULT_V1' and result['whole_queue_completed'] is False,'Shard result role')
    for key in FALSE:require(result[key] is False,'Saved result authority')
    for key,expected in (('logical_job_count',c['queue']['logical_job_count']),('source_blocked_job_count',c['queue']['source_blocked_job_count']),('registered_executable_job_count',c['queue']['executable_job_count']),('known_external_first_job_count',1)):
        require(type(result[key]) is int and result[key]==expected,'Complete result denominator')
    exact(result['descriptor'],descriptor,'Unchanged complete descriptor')
    startedref=result['started_reference'];require(Path(startedref['path'])==directory/'started.json','Started path')
    started=loads(take(startedref,{}));require(started['context_sha256']==context_hash,'Completed source context');exact(started['descriptor'],descriptor,'Original started descriptor')
    require(started['schema']=='REGISTERED_SCORING_SHARD_STARTED_V1','Started schema')
    for key in FALSE:require(started[key] is False,'Started authority')
    exact(started['context_references'],dict(context_reference=ref(OUTPUT/'context.json',context_hash),queue_reference=ref(OUTPUT/'queue.json',digest(c['queue']))),'Started immutable root refs')
    journalref=result['journal_reference'];require(Path(journalref['path'])==directory/'journal.jsonl','Journal path');raw=take(journalref,{})
    check=c['journal'].inspect_journal(raw,context_sha256=context_hash,ordered_task_ids=descriptor['job_ids']);require(check['complete'] is True,'No partial journal reuse')
    for task in check['tasks']:require(task['status'] in (SUCCESS,'EXTERNALLY_REFERENCED'),'No failed task reused')
    external=0
    for row in raw.splitlines():
        record=loads(row)
        if record['stage']=='EXTERNAL_REFERENCE':
            require(record['task_id']==FIRST_ID and record['task_position']==0,'Only first independently audited task reusable');exact(record['payload'],c['first_refs'],'Exact first external evidence');external+=1
    require(external==int(FIRST_ID in descriptor['job_ids']),'First never numerically repeated')
    exact(result['recovery'],check,'Saved full partition/recovery')
    return external_reference


def run_shard(shard_index,*,common,execute=False,completed_reference=None,request_large_guard=True):
    require(type(execute) is bool and type(shard_index) is int,'Exact shard index/execute')
    if not execute:return dict(status='NOT_EXECUTED',shard_index=shard_index)
    require(FRESH_CLI,'Fresh CLI worker only');environment();c=context(common)
    require(0<=shard_index<len(c['queue']['shards']),'Original shard range')
    if request_large_guard:common_guard(c)
    ch,base=ensure_root(c);descriptor=c['queue']['shards'][shard_index];directory=OUTPUT/'shards'/f'{shard_index:04d}'
    if directory.exists():
        require(completed_reference is not None,'Existing attempt requires external complete result; never retry')
        result=verify_completed(c,descriptor,completed_reference,ch)
        if request_large_guard:common_guard(c)
        return result
    require(completed_reference is None,'Cannot bind absent result');space();directory.mkdir(exist_ok=False)
    started=None;journal=None;status='STOPPED';error=None
    try:
        started=save(directory/'started.json',dict(schema='REGISTERED_SCORING_SHARD_STARTED_V1',descriptor=descriptor,context_sha256=ch,context_references=base,started_at_utc=datetime.now(timezone.utc).isoformat(),**FALSE))
        journal=Journal(directory/'journal.jsonl',c['journal'],ch)
        for position,logical in enumerate(descriptor['logical_ordinals']):
            task=c['queue']['logical_jobs'][logical]
            if task['job_id']==FIRST_ID:
                require(position==0 and shard_index==0,'Fixed first reuse position');journal.append(position,FIRST_ID,'EXTERNAL_REFERENCE',c['first_refs']);continue
            space();code_guard(c)
            outcome=execute_descriptor(c,task,position,journal)
            if outcome!=SUCCESS:raise RuntimeError('STOP_AFTER_'+outcome)
        status='COMPLETE'
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    finally:
        if journal is not None:journal.close()
    try:
        require(started is not None and (directory/'journal.jsonl').exists(),'Incomplete shard start cannot be retried')
        blob=(directory/'journal.jsonl').read_bytes();recovery=c['journal'].inspect_journal(blob,context_sha256=ch,ordered_task_ids=descriptor['job_ids'])
        require(status!='COMPLETE' or recovery['complete'],'Complete status requires all32')
        code_guard(c)
        if request_large_guard:common_guard(c)
        result=dict(schema='REGISTERED_SCORING_SHARD_RESULT_V1',status=status,descriptor=descriptor,context_sha256=ch,started_reference=started,journal_reference=ref(directory/'journal.jsonl',sha(blob)),recovery=recovery,error=error,logical_job_count=c['queue']['logical_job_count'],source_blocked_job_count=c['queue']['source_blocked_job_count'],registered_executable_job_count=c['queue']['executable_job_count'],known_external_first_job_count=1,whole_queue_completed=False,**FALSE)
        saved=save(directory/'result.json',result,True);require({p.name for p in directory.iterdir()}=={'started.json','journal.jsonl','result.json'},'Exact shard namespace')
        for r in (started,result['journal_reference'],saved):require(filehash(r['path'])==r['sha256'],'Final shard output drift')
        code_guard(c)
        if status!='COMPLETE':save(directory/'failure.json',dict(status='STOPPED_DO_NOT_RETRY',result_reference=saved,**FALSE),True)
        return saved
    except Exception as exc:
        if not (directory/'failure.json').exists():save(directory/'failure.json',dict(status='FAILED_DO_NOT_RETRY',error_type=type(exc).__name__,error=str(exc),started_reference=started,**FALSE),True)
        raise



def run_batch(*,execute=False,common=None,max_new_shards=None,completed_references=None):
    require(type(execute) is bool,'Exact execute flag')
    require(max_new_shards is None or type(max_new_shards) is int and max_new_shards>=0,'Exact engineering shard limit')
    completed_references=[] if completed_references is None else completed_references
    require(type(completed_references) is list,'Explicit completed prefix references')
    if not execute:return dict(status='NOT_EXECUTED')
    require(FRESH_CLI,'Fresh CLI only');environment()
    handle=load_common() if common is None else common;c=context(handle);common_guard(c);ch,base=ensure_root(c)
    require(len(completed_references)<=len(c['queue']['shards']),'Completed prefix within full domain')
    for i,r in enumerate(completed_references):verify_completed(c,c['queue']['shards'][i],r,ch)
    request=OUTPUT/'requests'/uuid.uuid4().hex;request.mkdir(exist_ok=False)
    started=save(request/'started.json',dict(schema='REGISTERED_SCORING_REQUEST_STARTED_V1',context_sha256=ch,context_references=base,completed_references=completed_references,max_new_shards=max_new_shards,started_at_utc=datetime.now(timezone.utc).isoformat(),**FALSE),True)
    accepted=list(completed_references);new=[];current=None;error=None;status='COMPLETE';current_ref=None
    try:
        for i in range(len(completed_references),len(c['queue']['shards'])):
            if max_new_shards is not None and len(new)>=max_new_shards:status='ENGINEERING_BUDGET_STOP';break
            space();current=i;current_ref=run_shard(i,common=handle,execute=True,request_large_guard=False)
            result=read_attempt_result(current_ref);new.append(current_ref)
            if result['status']!='COMPLETE':status='STOPPED';break
            accepted.append(current_ref);current=None;current_ref=None
            if len(accepted)%10==0:print(json.dumps(dict(completed_shards=len(accepted),total_shards=len(c['queue']['shards']))),flush=True)
    except Exception as exc:status='STOPPED';error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
    try:
        common_guard(c)
        full_ids=[c['queue']['logical_jobs'][i]['job_id'] for i in c['queue']['executable_logical_ordinals']]
        completed_ids=[]
        for i in range(len(accepted)):completed_ids.extend(c['queue']['shards'][i]['job_ids'])
        pending_current=[];terminal_current=[]
        if current is not None:
            if current_ref is not None:
                r=read_attempt_result(current_ref);terminal_current=[t for t in r['recovery']['tasks'] if t['status']!='UNRESOLVED_DISPATCH'];pending_current=r['recovery']['unresolved_task_ids']
            else:
                current_directory=OUTPUT/'shards'/f'{current:04d}'
                if current_directory.exists():pending_current=[t for t in c['queue']['shards'][current]['job_ids'] if t!=FIRST_ID]
                else:current=None
        accounted=set(completed_ids)|{FIRST_ID}|set(pending_current)|{t['task_id'] for t in terminal_current}
        result=dict(schema='REGISTERED_SCORING_REQUEST_RESULT_V1',status=status,request_started_reference=started,context_sha256=ch,context_references=base,initial_completed_references=completed_references,new_shard_references=new,completed_shard_references=accepted,unresolved_shard_index=current,unresolved_shard_reference=current_ref,unresolved_task_ids=pending_current,current_shard_terminal_tasks=terminal_current,undispatched_new_task_ids=[t for t in full_ids if t not in accounted],known_external_first_job_count=1,known_external_first_job_id=FIRST_ID,logical_job_count=c['queue']['logical_job_count'],source_blocked_job_count=c['queue']['source_blocked_job_count'],executable_job_count=c['queue']['executable_job_count'],new_numerical_job_denominator=c['queue']['executable_job_count']-1,completed_new_job_count=len([t for t in completed_ids if t!=FIRST_ID])+sum(t['status']==SUCCESS and t['task_id']!=FIRST_ID for t in terminal_current),error=error,whole_queue_completed=status=='COMPLETE' and len(accepted)==len(c['queue']['shards']),**FALSE)
        r=save(request/'result.json',result,True);common_guard(c)
        require({p.name for p in request.iterdir()}=={'started.json','result.json'},'Exact request evidence')
        for value in (started,r):require(filehash(value['path'])==value['sha256'],'Final request bytes changed')
        return r
    except Exception as exc:
        save(request/'failure.json',dict(status='FAILED_REQUEST_DO_NOT_RETRY',error_type=type(exc).__name__,error=str(exc),request_started_reference=started,completed_shard_references=accepted,new_shard_references=new,unresolved_shard_index=current,unresolved_shard_reference=current_ref,**FALSE),True);raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--max-new-shards',type=int);parser.add_argument('--completed-references-file')
    a=parser.parse_args();FRESH_CLI=True
    completed=[] if a.completed_references_file is None else loads(Path(a.completed_references_file).read_bytes())
    print(json.dumps(run_batch(execute=a.execute,max_new_shards=a.max_new_shards,completed_references=completed)))
