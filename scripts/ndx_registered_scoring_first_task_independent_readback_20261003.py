"""Independent complete first-job readback; no fitter/assembler/producer execution."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import builtins,hashlib,json,os,re,sys,types
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_registered_scoring_first_task_20261003.py'
PRODUCER_SHA='fdf6426845766f34d43c7bc613f85e947dd050edb2d656e941d5f0b0cd31b80b'
POSTCHECK_SHA='bf6654e496555e8437939960efab63a38d3390efbb91d991886054330a1bf053'
INSPECTOR=ROOT/'backtest/ndx_registered_scoring_result_inspection_research.py'
INSPECTOR_SHA='300712c1cd8ac838191b4eddb4feda3b5a87771f91783f0db9014f56bc14e853'
TASK_ID='75ad5a6a98d6056d4f13962d31b43debc809d9d663f719639fd1ea5e80fd4598'
BOUND={'budget': ('data/cache/research/multidecision_scoring_budget_20261003_v1/plan.json', 'f99843ce3d28829f6c258e608a7e3c2ee8605e2432eaaa890299dc1f9edb6d04'), 'budget_publication': ('data/cache/research/multidecision_scoring_budget_20261003_v1/publication.json', 'e9b9108018332ec7260cbcabc00b2fb751bbb393b7a50930be6d7f0e32a75f82'), 'budget_audit': ('data/cache/research/multidecision_scoring_budget_independent_readback_20261003_v1/independent_readback.json', '38446edc13b175845e364906a52c8117ebf5f53ed0abf13b459d55664178846c'), 'budget_reader': ('scripts/ndx_multidecision_scoring_budget_independent_readback_20261003.py', 'd2b64714902481ed3bcbcbf495cae1bd545e5237544de96282a2d78d6c2d0ade')}
CODES={'assembler': ('backtest/ndx_registered_scoring_job_inputs_research.py', '75313406656ad536a14e848a6a8f3bec9218f900529f84b21740176b62140ec2'), 'rolling': ('backtest/ndx_multidecision_rolling_fit_research.py', '9d7ca29bf6eff9be6e42747e98a9060e4cb1d44f7c7c6fb4af96cba9b4f67492'), 'reducer': ('backtest/ndx_multidecision_window_scoring_research.py', '7f9d4b6573998f036b93154ff4547b83f90b2112f4e003542057040ec503f137'), 'inspector': ('backtest/ndx_multidecision_window_scoring_inspection_research.py', 'cceb0cb4ed97d4b4f94fe049558c67d0b2501090cdfd4da65f59104490416bf8')}

PARENT=ROOT/'data/cache/research/registered_scoring_first_task_20261003_v1'/TASK_ID
OUTPUT=ROOT/'data/cache/research/registered_scoring_first_task_independent_readback_20261003_v1'/TASK_ID
PARENT_ROLES=('history_index','history_publication','history_audit','history_reader','original8_inputs','original8_publication','original8_audit','original8_reader','target_inputs','target_index','target_publication','target_audit','target_reader','rolling_fitter_manifest','policy')
FILES=('started.json','inputs.json','raw_fit.json','raw_score.json','score_inspection.json','postcheck.json')
FLAGS=dict.fromkeys(('point_in_time_verified','promotion_allowed','account_executed','whole_queue_completed','winner_selected','outer_lane_prior_applied','whole_lot_gate_evaluated','formal_benchmark_passed','old_fit_weights_reused','old_audit_repeated','runtime_binary_closure_verified','full_transitive_source_closure_reverified'),False)

def require(ok,m):
    if not ok:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def valid(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and Path(r['path']).is_absolute() and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']) is not None,'External exact reference')
def merge(s,r):
    valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def take(r,s):
    valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed source namespace')
    b=p.read_bytes();require(sha(b)==r['sha256'],'Exact consumed source bytes');merge(s,r);return b

def loads(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded reader drift')
    require({p.name for p in PARENT.iterdir()}==set(FILES),'Complete successful six-file parent only')
    for p,h in s.items():take(ref(p,h),{})
def save(p,d):
    b=enc(d)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved output bytes');return ref(p,sha(b))


def inspect_envelopes(documents,refs,input_refs,producer_sources,manifest):
    post=documents['postcheck'];require(post['schema']=='REGISTERED_SCORING_FIRST_TASK_POSTCHECK_V1' and post['outcome']=='SCORED_PENDING_INDEPENDENT_READBACK','Complete scored evidence required; failures are not successful readbacks')
    for key,n in (('whole_queue_task_count',19584),('attempted_job_count',1)):require(type(post[key]) is int and post[key]==n,'Exact attempt denominator')
    require(post['retry_allowed'] is False,'No retry')
    expected_saved=[refs[k] for k in ('started','inputs','raw_fit','raw_score','score_inspection')]
    exact(post['saved_references'],expected_saved,'Whole six-file causal reference order')
    for key,role in (('inputs_reference','inputs'),('raw_fit_reference','raw_fit'),('raw_score_reference','raw_score'),('score_inspection_reference','score_inspection')):exact(post[key],refs[role],'Postcheck saved file binding')
    for role,document in documents.items():
        require(document['job_id']==TASK_ID,'Same fixed registered job')
        exact(document['source_hashes'],producer_sources,'Independently constructed producer closure')
        for key in FLAGS:require(document[key] is False,'No authority '+key)
    started=documents['started'];require(started['schema']=='REGISTERED_SCORING_FIRST_TASK_STARTED_V1' and started['retry_allowed'] is False,'Started context')
    require(type(started['whole_queue_task_count']) is int and started['whole_queue_task_count']==19584,'Queue denominator')
    require(started['registered_task_pointer']=='/plan/rows/0/mode_plans/1/tasks/0','Fixed first pointer')
    require(type(started['started_at_utc']) is str and datetime.fromisoformat(started['started_at_utc']).utcoffset().total_seconds()==0,'Actual UTC declaration')
    exact(started['input_references'],input_refs,'Attempt fixed input references')
    inputs=documents['inputs'];require(inputs['schema']=='REGISTERED_SCORING_FIRST_TASK_INPUTS_DOCUMENT_V1','Inputs document')
    exact(inputs['input_references'],input_refs,'Persisted inputs context')
    expected_runtime=manifest['runtime_versions'];expected_environment=dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0)
    for role in ('started','raw_fit','raw_score','postcheck'):
        exact(documents[role]['runtime'],expected_runtime,'Registered runtime versions')
        exact(documents[role]['worker_environment'],expected_environment,'Required fresh-worker hash seed')
    for stage in ('fit','score'):
        d=documents['raw_'+stage]
        require(d['schema']=='REGISTERED_SCORING_RAW_'+stage.upper()+'_V1' and d['stage']==stage,'Raw stage identity')
        require(d['call_invoked'] is True and d['returned'] is True and type(d['returned_call_count']) is int and d['returned_call_count']==1,'One saved returned call')
        require(d['internal_optimizer_call_count'] is None,'Unknown inner optimizer count preserved')
        require(d['error'] is None and d['result_preserved_as_json'] is True and type(d['result']) is dict,'Successful complete JSON body, not exception/repr/None')
        exact(d['inputs_reference'],refs['inputs'],'Raw input reference')
    scoreaudit=documents['score_inspection'];require(scoreaudit['schema']=='REGISTERED_SCORING_SCORE_INSPECTION_DOCUMENT_V1','Saved arithmetic report')
    for key,role in (('inputs_reference','inputs'),('raw_fit_reference','raw_fit'),('raw_score_reference','raw_score')):exact(scoreaudit[key],refs[role],'Arithmetic input reference')
    exact(scoreaudit['inspector_reference'],ref(ROOT/CODES['inspector'][0],CODES['inspector'][1]),'Fixed independent arithmetic source')


def load_context():
    producer_sources={};parents={};input_refs={}
    for role,(path,h) in BOUND.items():
        r=ref(ROOT/path,h);b=take(r,producer_sources);input_refs[role]=r
        if role!='budget_reader':parents[role]=loads(b)
    budget=parents['budget'];pub=parents['budget_publication'];audit=parents['budget_audit']
    require(budget['schema']=='MULTIDECISION_SCORING_BUDGET_DOCUMENT_V1' and audit['schema']=='MULTIDECISION_SCORING_BUDGET_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Registered budget independently accepted')
    exact(pub['plan_reference'],input_refs['budget'],'Plan publication');exact(audit['plan_reference'],input_refs['budget'],'Budget independent reference');exact(audit['publication_reference'],input_refs['budget_publication'],'Budget publication audit')
    require(audit['reader_sha256']==input_refs['budget_reader']['sha256'],'Fixed budget reader')
    plan=budget['plan'];require(plan['content_sha256']==sha(enc({k:v for k,v in plan.items() if k!='content_sha256'})),'Plan digest')
    job=plan['rows'][0]['mode_plans'][1]['tasks'][0]
    require(job['job_id']==TASK_ID and job['job_id']==sha(enc(job['identity'])) and job['status']=='PLANNED_NOT_ATTEMPTED','Fixed unattempted job')
    require(job['identity']['cutoff']=='2026-03-31' and job['identity']['fx_mode']=='BACKWARD_LATEST_VALID_FX' and job['identity']['weight_spec']=='equal_weight' and type(job['position']['k']) is int and job['position']['k']==4,'Registered fixed role')
    for role in PARENT_ROLES:
        r=budget['input_references'][role];require(audit['source_hashes'][r['path']]==r['sha256'],'Audited full input closure')
        input_refs[role]=deepcopy(r);b=take(r,producer_sources)
        if not role.endswith('_reader'):parents[role]=loads(b)
    for role,key,parentkey in (('history','index_reference','history_index'),('original8','inputs_reference','original8_inputs'),('target','index_reference','target_index')):
        a=parents[role+'_audit'];p=parents[role+'_publication']
        require(a['status']=='PASS' and a['reader_sha256']==input_refs[role+'_reader']['sha256'],'Source saved audit')
        exact(a[key],input_refs[parentkey],'Source audit object');exact(a['publication_reference'],input_refs[role+'_publication'],'Source audit receipt');exact(p[key],input_refs[parentkey],'Source published object')
    exact(parents['target_index']['target_inputs_reference'],input_refs['target_inputs'],'Actual target payload')
    manifest=parents['rolling_fitter_manifest'];exact(manifest,budget['rolling_fitter_manifest_preserved'],'Registered complete fitter source contract')
    exact(manifest['policy_reference'],input_refs['policy'],'Policy binding')
    require(len(manifest['source_hashes'])==25,'Full registered fitter25')
    for p,h in manifest['source_hashes'].items():take(ref(p,h),producer_sources)
    for role in ('rolling','reducer'):require(manifest['source_hashes'][str(ROOT/CODES[role][0])]==CODES[role][1],'Original rolling/reducer source')
    h=parents['history_index'];by={r['coordinate']['security_id']:r for r in h['rows']};require(len(by)==77,'Full inventory')
    bindings=[]
    for sid in job['identity']['security_ids']:
        row=by[sid];r=row['channel_reference'];channel=loads(take(r,producer_sources));a=parents['history_audit']['rows'][row['index']]
        exact(a['channel_reference'],r,'Audited selected channel');exact(a['coordinate'],row['coordinate'],'Audited selected coordinate');require(a['inspection']['status']=='PASS','Saved numeric readback')
        bindings.append(dict(coordinate=deepcopy(row['coordinate']),reference=deepcopy(r),channel=channel))
    take(ref(PRODUCER,PRODUCER_SHA),producer_sources)
    for p,h in CODES.values():take(ref(ROOT/p,h),producer_sources)
    return parents,input_refs,producer_sources,bindings,job


def private_inspector(sources):
    path,h=CODES['inspector'];b=take(ref(ROOT/path,h),sources);arithmetic=types.ModuleType('_registered_readback_arithmetic');arithmetic.__file__=str(ROOT/path);exec(compile(b,str(ROOT/path),'exec'),arithmetic.__dict__)
    original=builtins.__import__
    def importer(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest' and tuple(fromlist)==('ndx_multidecision_window_scoring_inspection_research',):return types.SimpleNamespace(ndx_multidecision_window_scoring_inspection_research=arithmetic)
        require(not name.startswith('backtest'),'Unexpected project dependency');return original(name,globals,locals,fromlist,level)
    core=types.ModuleType('_registered_readback_core');core.__file__=str(INSPECTOR);core.__dict__['__builtins__']=dict(vars(builtins),__import__=importer)
    exec(compile(take(ref(INSPECTOR,INSPECTOR_SHA),sources),str(INSPECTOR),'exec'),core.__dict__);return core


def readback(*,execute=False):
    require(type(execute) is bool,'Execute boolean')
    if not execute:return dict(status='NOT_EXECUTED',job_id=TASK_ID)
    require(type(POSTCHECK_SHA) is str and re.fullmatch('[a-f0-9]{64}',POSTCHECK_SHA) is not None and type(PRODUCER_SHA) is str and re.fullmatch('[a-f0-9]{64}',PRODUCER_SHA) is not None,'Final external anchors pending')
    require(not OUTPUT.exists(),'Immutable readback namespace already exists')
    sources={str(SOURCE):LOADED_SHA};guard({});refs={'postcheck':ref(PARENT/'postcheck.json',POSTCHECK_SHA)}
    documents={'postcheck':loads(take(refs['postcheck'],sources))};post=documents['postcheck']
    require(post.get('outcome')=='SCORED_PENDING_INDEPENDENT_READBACK','Not complete successful evidence; no retry permitted')
    require(type(post['saved_references']) is list and len(post['saved_references'])==5,'Complete five prior files')
    for role,r in zip(('started','inputs','raw_fit','raw_score','score_inspection'),post['saved_references']):
        require(Path(r['path'])==PARENT/(role+'.json'),'Fixed causal evidence filename');refs[role]=r;documents[role]=loads(take(r,sources))
    parents,input_refs,producer_sources,bindings,job=load_context()
    inspect_envelopes(documents,refs,input_refs,producer_sources,parents['rolling_fitter_manifest'])
    assembled=documents['inputs']['assembled'];exact(assembled['registered_job_preserved'],job,'Actual selected registered job');exact(assembled['budget_reference'],input_refs['budget'],'Persisted budget identity')
    require(assembled['registered_task_pointer']=='/plan/rows/0/mode_plans/1/tasks/0','Actual selected pointer')
    exact(assembled['fitter_reference'],input_refs['rolling_fitter_manifest'],'Persisted fitter identity')
    identity=job['identity']
    exact(assembled['source_references'],dict(history=identity['scoring_data_reference'],target=identity['target_reference'],original8=identity['first_candidate_fee_reference'],fitter=input_refs['rolling_fitter_manifest']),'All preserved input source pointers')
    exact(assembled['window_metadata'],parents['target_inputs']['modes'][1]['decisions'][0]['windows'],'Original thirteen target-window definitions')
    for p,h in producer_sources.items():merge(sources,ref(p,h))
    core=private_inspector(sources);guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        start=save(OUTPUT/'started.json',dict(schema='REGISTERED_SCORING_FIRST_TASK_READBACK_STARTED_V1',job_id=TASK_ID,postcheck_reference=refs['postcheck'],retry_allowed=False,**FLAGS))
        detail=core.inspect_registered_scoring_result(assembled=assembled,saved_fit=documents['raw_fit']['result'],saved_score=documents['raw_score']['result'],saved_score_inspection=documents['score_inspection']['inspection'],numerical_source_hashes=parents['rolling_fitter_manifest']['source_hashes'],channel_bindings=bindings,original8_inputs=parents['original8_inputs']['scoring_inputs'],target_inputs=parents['target_inputs'])
        report=save(OUTPUT/'independent_readback.json',dict(schema='REGISTERED_SCORING_FIRST_TASK_INDEPENDENT_READBACK_V1',status='PASS',job_id=TASK_ID,postcheck_reference=refs['postcheck'],evidence_references=refs,reader_sha256=LOADED_SHA,source_hashes=sources,inspection=detail,producer_called=False,fit_called=False,optimization_rerun=False,recovery_certificates_recomputed=False,**FLAGS))
        guard(sources)
        for r in (start,report):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Readback output drift')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact readback namespace');return report
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',job_id=TASK_ID,error_type=type(e).__name__,error=str(e),retry_allowed=False,**FLAGS));raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
