"""V2 full saved-score readback with strict original recovery-branch evidence.

The failed V1 audit and all diagnostic outputs stay immutable. No fitting,
scoring, certificate optimization or old audit publication is rerun."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import builtins,hashlib,json,os,re,sys,types
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_registered_scoring_first_task_20261003.py'
PRODUCER_SHA='fdf6426845766f34d43c7bc613f85e947dd050edb2d656e941d5f0b0cd31b80b'
REQUEST_RESULT_PATH='E:\\Git\\us_ratchet\\data\\cache\\research\\registered_scoring_queue_worker_20261003_v1\\requests\\99e7d62348d64ddbacd5b38307c2a050\\result.json'
REQUEST_RESULT_SHA='4e162f87a383a90ddcf087c1342d06bd39df38d84e7d6dd85b748aa5668b7c5e'
INSPECTOR=ROOT/'backtest/ndx_registered_scoring_result_inspection_v2_research.py'
INSPECTOR_SHA='15c651b96964c4dc20bb416712c94b20aab591b8c90a90b9657617bde0aa187b'
TASK_ID='75ad5a6a98d6056d4f13962d31b43debc809d9d663f719639fd1ea5e80fd4598'
BOUND={'budget': ('data/cache/research/multidecision_scoring_budget_20261003_v1/plan.json', 'f99843ce3d28829f6c258e608a7e3c2ee8605e2432eaaa890299dc1f9edb6d04'), 'budget_publication': ('data/cache/research/multidecision_scoring_budget_20261003_v1/publication.json', 'e9b9108018332ec7260cbcabc00b2fb751bbb393b7a50930be6d7f0e32a75f82'), 'budget_audit': ('data/cache/research/multidecision_scoring_budget_independent_readback_20261003_v1/independent_readback.json', '38446edc13b175845e364906a52c8117ebf5f53ed0abf13b459d55664178846c'), 'budget_reader': ('scripts/ndx_multidecision_scoring_budget_independent_readback_20261003.py', 'd2b64714902481ed3bcbcbf495cae1bd545e5237544de96282a2d78d6c2d0ade')}
CODES={'assembler': ('backtest/ndx_registered_scoring_job_inputs_research.py', '75313406656ad536a14e848a6a8f3bec9218f900529f84b21740176b62140ec2'), 'rolling': ('backtest/ndx_multidecision_rolling_fit_research.py', '9d7ca29bf6eff9be6e42747e98a9060e4cb1d44f7c7c6fb4af96cba9b4f67492'), 'reducer': ('backtest/ndx_multidecision_window_scoring_research.py', '7f9d4b6573998f036b93154ff4547b83f90b2112f4e003542057040ec503f137'), 'inspector': ('backtest/ndx_multidecision_window_scoring_inspection_research.py', 'cceb0cb4ed97d4b4f94fe049558c67d0b2501090cdfd4da65f59104490416bf8')}

PARENT=ROOT/'data/cache/research/registered_scoring_first_task_20261003_v1'/TASK_ID
OUTPUT=ROOT/'data/cache/research/registered_scoring_queue_independent_readback_20261003_v2'
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
def save(p,d):
    b=enc(d)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved output bytes');return ref(p,sha(b))



WORKER=ROOT/'scripts/ndx_registered_scoring_queue_worker_20261003.py'
WORKER_SHA='f14dc39a6f729dca1a62b0c624ed747cfe285a6d6d61cc673c20b6071fdeb7b8'
QUEUE_ROOT=ROOT/'data/cache/research/registered_scoring_queue_worker_20261003_v1'
FIRST_AUDIT=ROOT/'data/cache/research/registered_scoring_first_task_independent_readback_20261003_v1'/TASK_ID/'independent_readback.json'
FIRST_AUDIT_SHA='b227474d150f25eb742d0c549df01cd628cd88d5b38507e751651aebeac4ff7f'
FIRST_READER=ROOT/'scripts/ndx_registered_scoring_first_task_independent_readback_20261003.py'
FIRST_READER_SHA='0ae6d1ef179723133784f55cf92fde42c491b5392f4ab41f84546fef5d382f2d'
QUEUE_CODE=ROOT/'backtest/ndx_registered_scoring_queue_research.py'
QUEUE_SHA='7e0b171d4a38348a072be7379d07db795dcd56558250ed4f998a41b37afd0fa8'
JOURNAL_CODE=ROOT/'backtest/ndx_registered_scoring_journal_research.py'
JOURNAL_SHA='4f1d3537cb0319d01e148f6e49b91e86c05dbfdb58dbf73cc7796b5f2ca602b7'
JOURNAL_INSPECTOR=ROOT/'backtest/ndx_registered_scoring_journal_inspection_research.py'
JOURNAL_INSPECTOR_SHA='84da96c950f5c0b1c2169c631a833f5d68ca7185cf1e1a569980f431bc54caae'
FALSE=dict.fromkeys(('automatic_retry_allowed','point_in_time_verified','promotion_allowed','account_executed','winner_selected','outer_lane_prior_applied','whole_lot_gate_evaluated','formal_benchmark_passed','full_transitive_source_closure_reverified','runtime_binary_closure_verified','continuous_source_monitoring_claimed'),False)
SUCCESS='SCORED_PENDING_INDEPENDENT_READBACK'

def check_flags(d):
    for k in FALSE:require(d[k] is False,'No authority '+k)
def count(d,k,n):require(type(d[k]) is int and d[k]==n,'Exact denominator '+k)
def digest(v):return sha(enc(v))
def filehash(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def guard(s):
    require(filehash(SOURCE)==LOADED_SHA,'Loaded independent reader changed')
    for p,h in s.items():require(not (Path(p).parent/'failure.json').exists() and filehash(p)==h,'Fixed source changed '+p)
def take_attempt(r,s):
    # Explicitly anchored STOPPED evidence may coexist with its failure marker.
    valid(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Attempt consumed bytes');merge(s,r);return b
def guard_attempt(s):
    for p,h in s.items():require(filehash(p)==h,'Saved attempt changed '+p)
def utc(v):
    require(type(v) is str and datetime.fromisoformat(v).utcoffset().total_seconds()==0,'UTC declaration')
def private_module(path,h,s):
    m=types.ModuleType('_independent_'+path.stem);m.__file__=str(path);exec(compile(take(ref(path,h),s),str(path),'exec'),m.__dict__);return m
def load_common():
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
    bindings={}
    require(len(h['rows'])==len(parents['history_audit']['rows'])==77,'Complete77 source rows')
    for i,row in enumerate(h['rows']):
        r=row['channel_reference'];channel=loads(take(r,producer_sources));a=parents['history_audit']['rows'][i]
        require(type(row['index']) is int and row['index']==i,'Original source index')
        exact(a['channel_reference'],r,'Audited channel');exact(a['coordinate'],row['coordinate'],'Audited coordinate');require(a['inspection']['status']=='PASS','Saved numeric readback')
        sid=row['coordinate']['security_id'];require(sid not in bindings,'Unique channel SID')
        bindings[sid]=dict(coordinate=deepcopy(row['coordinate']),reference=deepcopy(r),channel=channel)
    take(ref(PRODUCER,PRODUCER_SHA),producer_sources)
    for p,h in CODES.values():take(ref(ROOT/p,h),producer_sources)
    for path,h in ((WORKER,WORKER_SHA),(QUEUE_CODE,QUEUE_SHA),(JOURNAL_CODE,JOURNAL_SHA),(FIRST_READER,FIRST_READER_SHA)):
        take(ref(path,h),producer_sources)
    first=loads(take(ref(FIRST_AUDIT,FIRST_AUDIT_SHA),producer_sources))
    require(first['schema']=='REGISTERED_SCORING_FIRST_TASK_INDEPENDENT_READBACK_V1' and first['status']=='PASS' and first['job_id']==TASK_ID and first['reader_sha256']==FIRST_READER_SHA,'First accepted independent evidence')
    firstrefs=deepcopy(first['evidence_references']);require(set(firstrefs)=={'postcheck','started','inputs','raw_fit','raw_score','score_inspection'},'First six evidence refs')
    exact(first['postcheck_reference'],firstrefs['postcheck'],'First post anchor')
    for r in firstrefs.values():take(r,producer_sources)
    firstrefs['independent_readback']=ref(FIRST_AUDIT,FIRST_AUDIT_SHA)
    require(first['inspection']['status']=='PASS' and first['inspection']['job_id']==TASK_ID,'First same numerical inspection role')
    return dict(parents=parents,refs=input_refs,producer_sources=producer_sources,bindings=bindings,firstrefs=firstrefs,first=first)


def private_inspector(sources):
    path,h=CODES['inspector'];b=take(ref(ROOT/path,h),sources);arithmetic=types.ModuleType('_registered_readback_arithmetic');arithmetic.__file__=str(ROOT/path);exec(compile(b,str(ROOT/path),'exec'),arithmetic.__dict__)
    original=builtins.__import__
    def importer(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest' and tuple(fromlist)==('ndx_multidecision_window_scoring_inspection_research',):return types.SimpleNamespace(ndx_multidecision_window_scoring_inspection_research=arithmetic)
        require(not name.startswith('backtest'),'Unexpected project dependency');return original(name,globals,locals,fromlist,level)
    core=types.ModuleType('_registered_readback_core');core.__file__=str(INSPECTOR);core.__dict__['__builtins__']=dict(vars(builtins),__import__=importer)
    exec(compile(take(ref(INSPECTOR,INSPECTOR_SHA),sources),str(INSPECTOR),'exec'),core.__dict__);return core



def inspect_queue(queue,plan,budget_reference):
    require(queue['schema']=='REGISTERED_SCORING_FULL_QUEUE_V1','Queue schema')
    require(queue['content_sha256']==digest({k:v for k,v in queue.items() if k!='content_sha256'}),'Queue content digest')
    exact(queue['budget_reference'],budget_reference,'Registered budget bytes');require(queue['budget_content_sha256']==plan['content_sha256'],'Registered content')
    for k,n in (('logical_job_count',19584),('executable_job_count',9792),('source_blocked_job_count',9792),('shard_count',306),('maximum_jobs_per_shard',32)):count(queue,k,n)
    for k in ('first_probe_removed_from_registered_domain','source_bytes_authenticated','economic_results_used_for_ordering','score_computed','fit_performed','account_executed','automatic_retry_allowed','execution_authorized','point_in_time_verified','promotion_allowed'):require(queue[k] is False,'Queue authority')
    require(queue['reuse_requires_explicit_external_completed_audit'] is True and queue['shard_size_is_engineering_only'] is True,'Explicit reference reuse/engineering')
    require(len(queue['logical_jobs'])==19584 and len(queue['shards'])==306 and len(queue['coordinates'])==12,'Whole arrays')
    universe=plan['full_universe_preserved'];require(len(universe)==77 and len({s['security_id'] for s in universe})==77 and len({s['issuer_id'] for s in universe})==76,'Whole77/76')
    index={s['security_id']:s for s in universe};blocked=[];executable=[];seen=set();jobs={}
    cutoffs=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
    require(len(plan['rows'])==6 and [r['cutoff'] for r in plan['rows']]==cutoffs,'Six registered clocks')
    for j,row in enumerate(plan['rows']):
        require(len(row['mode_plans'])==2 and len(row['domain_coverage'])==76,'Whole mode/k domain')
        for mi,mode in enumerate(row['mode_plans']):
            require(mode['mode']==('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')[mi] and len(mode['tasks'])==1632,'Mode and full tasks')
            state=('SOURCE_BLOCKED','PLANNED_NOT_ATTEMPTED')[mi]
            require(mode['status']==state and mode['source_preserved']['complete_thirteen_windows'] is bool(mi),'Unchanged registered source blockage')
            start=(j*2+mi)*1632
            expected_coordinate=dict(decision_index=j,mode_index=mi,cutoff=row['cutoff'],fx_mode=mode['mode'],source_status=state,logical_start=start,logical_stop=start+1632,registered_task_count=1632,source_preserved=mode['source_preserved'],all_k_domain_preserved=row['domain_coverage'])
            exact(queue['coordinates'][j*2+mi],expected_coordinate,'Complete source/domain coordinate')
            for ti,job in enumerate(mode['tasks']):
                identity=job['identity'];sid=identity['security_ids'];ordinal=start+ti
                require(job['job_id']==digest(identity) and job['job_id'] not in seen and job['status']==state,'Original unique job identity/status');seen.add(job['job_id'])
                require(len(sid)==len(set(sid))==len({index[s]['issuer_id'] for s in sid}),'No duplicate issuer or security')
                require(sid==sorted(sid,key=lambda s:(index[s]['issuer_id'],s)),'Original matrix issuer ordering')
                exact(job['position'],row['sampling']['positions'][ti//3],'Same selected composition')
                require(identity['weight_spec']==('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')[ti%3],'Original three spec order')
                d=dict(logical_ordinal=ordinal,decision_index=j,mode_index=mi,task_index=ti,job_id=job['job_id'],job_pointer=f'/plan/rows/{j}/mode_plans/{mi}/tasks/{ti}',cutoff=row['cutoff'],fx_mode=mode['mode'],holding_count=len(sid),weight_spec=identity['weight_spec'],registered_status=state,execution_ordinal=None if mi==0 else len(executable))
                exact(queue['logical_jobs'][ordinal],d,'Every logical task descriptor')
                (blocked if mi==0 else executable).append(ordinal);jobs[job['job_id']]=job
    exact(queue['source_blocked_logical_ordinals'],blocked,'All strict slots retained');exact(queue['executable_logical_ordinals'],executable,'All backward slots retained')
    for i,d in enumerate(queue['shards']):
        ordinals=executable[i*32:(i+1)*32]
        expected=dict(shard_index=i,execution_start=i*32,execution_stop=(i+1)*32,logical_ordinals=ordinals,job_ids=[queue['logical_jobs'][o]['job_id'] for o in ordinals])
        expected['content_sha256']=digest(expected);exact(d,expected,'Stable32 shard complete identity')
    exact(queue['first_executable_job'],queue['logical_jobs'][executable[0]],'Original first remains in domain')
    require(queue['first_executable_job']['job_id']==TASK_ID,'Only actual audited first')
    return jobs


def inspect_context(c,context,queue,publication,refs):
    require(context['schema']=='REGISTERED_SCORING_QUEUE_CONTEXT_V1','Context schema');check_flags(context)
    exact(context['source_hashes'],c['producer_sources'],'Independently constructed complete producer closure')
    exact(context['input_references'],c['refs'],'All fixed parent role refs');exact(context['first_external_evidence'],c['firstrefs'],'First accepted external evidence')
    require(context['queue_content_sha256']==queue['content_sha256'],'Context full queue')
    require(context['large_sources_checked_at']=='COMMON_LOAD_AND_REQUEST_BEGIN_END' and context['numeric_python_sources_checked_at']=='EACH_NUMERIC_JOB_BEFORE_AND_AFTER_CALL','Honest producer verification scope')
    exact(publication,dict(schema='REGISTERED_SCORING_QUEUE_CONTEXT_PUBLICATION_V1',status='CONTEXT_ONLY_NOT_ALL_JOBS_COMPLETE',**refs,**FALSE),'Root publication role')
    return inspect_queue(queue,c['parents']['budget']['plan'],c['refs']['budget'])


def inspect_shard_metadata(result,started,descriptor,context_hash,context_refs,inspection,journal_bytes):
    require(result['schema']=='REGISTERED_SCORING_SHARD_RESULT_V1' and result['status'] in ('COMPLETE','STOPPED'),'Explicit shard terminal')
    require(started['schema']=='REGISTERED_SCORING_SHARD_STARTED_V1','Started shard schema');utc(started['started_at_utc'])
    for d in (result,started):check_flags(d);exact(d['descriptor'],descriptor,'Registered shard identity');require(d['context_sha256']==context_hash,'Same fixed context')
    exact(started['context_references'],context_refs,'Started root refs')
    for k,n in (('logical_job_count',19584),('source_blocked_job_count',9792),('registered_executable_job_count',9792),('known_external_first_job_count',1)):count(result,k,n)
    require(result['whole_queue_completed'] is False,'Shard never entire queue')
    recovery=result['recovery'];require(recovery['schema']=='REGISTERED_SCORING_JOURNAL_RECOVERY_V1','Saved recovery schema')
    for k in ('journal_sha256','byte_count','valid_prefix_byte_count','record_count','records','tail','last_record_sha256','undispatched_task_ids','unresolved_task_ids'):exact(recovery[k],inspection[k],'Independent recovery '+k)
    require(recovery['automatic_retry_allowed'] is False and recovery['bytes_truncated'] is False and recovery['executor_called'] is False,'Recovery never retries')
    expected=[]
    for t in inspection['tasks']:
        if not t['record_indexes']:
            expected.append(dict(task_id=t['task_id'],task_position=t['task_position'],status='UNRESOLVED_DISPATCH',record_indexes=[],reason='UNKNOWN_PARTIAL_RECORD'));continue
        d=dict(task_id=t['task_id'],task_position=t['task_position'],record_indexes=t['record_indexes'],status=t['status'],fit_dispatch_observed=t['fit_dispatch_observed'],score_dispatch_observed=t['score_dispatch_observed'])
        for n in t['record_indexes']:
            meta=inspection['records'][n];r=loads(journal_bytes[meta['byte_start']:meta['byte_stop']]);d['last_stage']=r['stage']
            if r['stage']=='RAW_FIT':d['fit_returned']=r['payload']['returned']
            if r['stage']=='RAW_SCORE':d['score_returned']=r['payload']['returned']
            if r['stage']=='INSPECTION':d['inspection_passed']=r['payload']['inspection'].get('status')=='PASS' if isinstance(r['payload']['inspection'],dict) else False
        expected.append(d)
    exact(recovery['tasks'],expected,'Every producer task state independently reconstructed')
    require(recovery['complete'] is inspection['whole_shard_terminal_evidence_complete'],'Complete evidence flag')
    if result['status']=='COMPLETE':require(inspection['whole_shard_numeric_success_claims_complete'] is True and result['error'] is None,'Success requires full saved success evidence')
    else:require(type(result['error']) is dict and set(result['error'])=={'type','message','traceback'} and all(type(v) is str for v in result['error'].values()),'Technical stop original error')


def inspect_request(result,started,queue,shard_reports):
    require(result['schema']=='REGISTERED_SCORING_REQUEST_RESULT_V1' and started['schema']=='REGISTERED_SCORING_REQUEST_STARTED_V1','Request schemas')
    for d in (result,started):check_flags(d)
    utc(started['started_at_utc']);exact(started['context_references'],result['context_references'],'Request context refs');require(started['context_sha256']==result['context_sha256'],'Request context')
    initial=result['initial_completed_references'];new=result['new_shard_references'];accepted=result['completed_shard_references']
    require(all(type(v) is list for v in (initial,new,accepted)),'Explicit reference arrays');exact(started['completed_references'],initial,'Original completed prefix')
    limit=started['max_new_shards'];require(limit is None or type(limit) is int and limit>=0,'Engineering limit exact');require(limit is None or len(new)<=limit,'No unregistered dispatch beyond limit')
    require(len(accepted)<=306 and len(initial)<=len(accepted),'Prefix counts')
    exact(accepted[:len(initial)],initial,'Original accepted prefix retained')
    expected_new=accepted[len(initial):]
    current=result['unresolved_shard_index'];currentref=result['unresolved_shard_reference']
    if currentref is not None:expected_new=expected_new+[currentref]
    exact(new,expected_new,'Only consecutive complete and optional stopped result')
    require(len(shard_reports)==len(accepted)+(currentref is not None),'Every supplied shard independently inspected')
    for i,r in enumerate(shard_reports):
        count(r,'shard_index',i);exact(r['result_reference'],(accepted+[currentref])[i],'Actual result ordered prefix')
        require(r['result_status']==('COMPLETE' if i<len(accepted) else 'STOPPED'),'Original success/stop classification')
    ids=[queue['logical_jobs'][i]['job_id'] for i in queue['executable_logical_ordinals']];completeids=ids[:len(accepted)*32]
    terminal=[];unresolved=[]
    if current is not None:
        require(type(current) is int and current==len(accepted) and current<306,'One next unresolved shard')
        if currentref is not None:
            last=shard_reports[-1];terminal=last['producer_terminal_tasks'];unresolved=last['unresolved_task_ids']
        else:unresolved=[x for x in queue['shards'][current]['job_ids'] if x!=TASK_ID]
    else:require(currentref is None,'No unlocated current result')
    exact(result['current_shard_terminal_tasks'],terminal,'Original stopped terminal facts');exact(result['unresolved_task_ids'],unresolved,'Unresolved not success')
    accounted=set(completeids)|{TASK_ID}|set(unresolved)|{t['task_id'] for t in terminal}
    exact(result['undispatched_new_task_ids'],[x for x in ids if x not in accounted],'Complete unattempted partition')
    for k,n in (('known_external_first_job_count',1),('logical_job_count',19584),('source_blocked_job_count',9792),('executable_job_count',9792),('new_numerical_job_denominator',9791),('completed_new_job_count',len([x for x in completeids if x!=TASK_ID])+sum(t['status']==SUCCESS and t['task_id']!=TASK_ID for t in terminal))):count(result,k,n)
    require(result['known_external_first_job_id']==TASK_ID,'First external identity')
    status=result['status'];require(status in ('COMPLETE','ENGINEERING_BUDGET_STOP','STOPPED'),'Request terminal category')
    require(result['whole_queue_completed'] is (status=='COMPLETE' and len(accepted)==306),'Whole completion is not partial')
    if status=='COMPLETE':require(len(accepted)==306 and current is None and result['error'] is None,'Full306 completion')
    elif status=='ENGINEERING_BUDGET_STOP':require(current is None and limit is not None and len(new)==limit and len(accepted)<306 and result['error'] is None,'Engineering bound before dispatch')
    else:
        error=result['error'];require(error is None or type(error) is dict and set(error)=={'type','message','traceback'} and all(type(v) is str for v in error.values()),'Original request stop error')
        if error is None:require(currentref is not None and shard_reports[-1]['result_status']=='STOPPED','Stopped request needs a saved stop or original exception')
    return dict(logical_job_count=19584,source_blocked_job_count=9792,registered_executable_job_count=9792,externally_audited_first_job_count=1,new_numerical_job_denominator=9791,independently_verified_new_success_count=sum(r['verified_new_success_count'] for r in shard_reports),terminal_failure_count=sum(r['terminal_failure_count'] for r in shard_reports),unresolved_count=len(unresolved),undispatched_count=len(result['undispatched_new_task_ids']),unresolved_without_result_metadata_only=current is not None and currentref is None)

def verify_job_inputs(assembled,descriptor,c):
    plan=c['parents']['budget']['plan'];j=descriptor['decision_index'];mi=descriptor['mode_index'];ti=descriptor['task_index'];job=plan['rows'][j]['mode_plans'][mi]['tasks'][ti]
    exact(assembled['registered_job_preserved'],job,'Actual registered task unchanged');exact(assembled['budget_reference'],c['refs']['budget'],'Actual budget bytes')
    require(assembled['registered_task_pointer']==descriptor['job_pointer'],'Original global task location');exact(assembled['fitter_reference'],c['refs']['rolling_fitter_manifest'],'Registered numerical closure')
    identity=job['identity'];exact(assembled['source_references'],dict(history=identity['scoring_data_reference'],target=identity['target_reference'],original8=identity['first_candidate_fee_reference'],fitter=c['refs']['rolling_fitter_manifest']),'Original source-role pointers')
    exact(assembled['window_metadata'],c['parents']['target_inputs']['modes'][mi]['decisions'][j]['windows'],'Original thirteen target windows')
    return job


def inspect_numeric_tasks(blob,check,journal_reference,expected_jobs,c,numeric):
    out=[]
    for task in check['tasks']:
        if task['status']!=SUCCESS:continue
        values={};locators={}
        for number in task['record_indexes']:
            location=check['records'][number];r=loads(blob[location['byte_start']:location['byte_stop']]);values[r['stage']]=r['payload'];locators[r['stage']]=deepcopy(location)
        descriptor=expected_jobs[task['task_position']];assembled=values['INPUTS']['assembled'];job=verify_job_inputs(assembled,descriptor,c)
        report=numeric.inspect_registered_scoring_result(assembled=assembled,saved_fit=values['RAW_FIT']['result'],saved_score=values['RAW_SCORE']['result'],saved_score_inspection=values['INSPECTION']['inspection'],numerical_source_hashes=c['parents']['rolling_fitter_manifest']['source_hashes'],channel_bindings=[c['bindings'][sid] for sid in job['identity']['security_ids']],original8_inputs=c['parents']['original8_inputs']['scoring_inputs'],target_inputs=c['parents']['target_inputs'])
        require(report['status']=='PASS' and report['job_id']==task['task_id'],'Actual independent arithmetic role')
        out.append(dict(job_id=task['task_id'],outcome=SUCCESS,source_kind='JOURNAL',inspection=report,score_reference=dict(journal_reference=deepcopy(journal_reference),record_locator={k:locators['RAW_SCORE'][k] for k in ('sequence','byte_start','byte_stop','record_sha256','stage')},result_field='payload.result'),input_record_locator=locators['INPUTS'],fit_record_locator=locators['RAW_FIT']))
    return out


def audit_shard(result_ref,descriptor,c,context_refs,context_hash,queue,journal_inspector,numeric):
    directory=QUEUE_ROOT/'shards'/f"{descriptor['shard_index']:04d}";require(Path(result_ref['path'])==directory/'result.json','Original shard fixed path')
    source={};result=loads(take_attempt(result_ref,source));status=result['status']
    require(status in ('COMPLETE','STOPPED'),'Explicit shard result status')
    filenames={'started.json','journal.jsonl','result.json'}|({'failure.json'} if status=='STOPPED' else set())
    require({p.name for p in directory.iterdir()}==filenames,'Exact saved shard namespace')
    for key,name in (('started_reference','started.json'),('journal_reference','journal.jsonl')):require(Path(result[key]['path'])==directory/name,'Fixed shard member')
    started=loads(take_attempt(result['started_reference'],source));blob=take_attempt(result['journal_reference'],source)
    diagnostic=None
    if status=='STOPPED':
        b=(directory/'failure.json').read_bytes();r=ref(directory/'failure.json',sha(b));diagnostic=loads(b);merge(source,r)
        require(diagnostic['status']=='STOPPED_DO_NOT_RETRY','Explicit technical failure marker');exact(diagnostic['result_reference'],result_ref,'Failure links anchored result');check_flags(diagnostic)
    expected_jobs=[queue['logical_jobs'][i] for i in descriptor['logical_ordinals']]
    check=journal_inspector.inspect_scoring_journal(journal_bytes=blob,context_sha256=context_hash,expected_jobs=expected_jobs,shard_index=descriptor['shard_index'],expected_runtime=c['parents']['rolling_fitter_manifest']['runtime_versions'],external_first_evidence=c['firstrefs'])
    inspect_shard_metadata(result,started,descriptor,context_hash,context_refs,check,blob)
    numeric_reports=inspect_numeric_tasks(blob,check,result['journal_reference'],expected_jobs,c,numeric)
    require(len(numeric_reports)==check['numerical_success_claim_count'],'Every saved success independently checked')
    guard_attempt(source);require({p.name for p in directory.iterdir()}==filenames,'Final exact saved shard namespace')
    terminal=[t for t in result['recovery']['tasks'] if t['status']!='UNRESOLVED_DISPATCH']
    return dict(schema='REGISTERED_SCORING_SHARD_INDEPENDENT_READBACK_V1',status='PASS_EVIDENCE_CLASSIFICATION',shard_index=descriptor['shard_index'],descriptor=deepcopy(descriptor),result_reference=deepcopy(result_ref),result_status=status,started_reference=result['started_reference'],journal_reference=result['journal_reference'],source_hashes=source,inspection=check,job_inspections=numeric_reports,verified_new_success_count=len(numeric_reports),terminal_failure_count=sum(t['status'] not in (SUCCESS,'EXTERNALLY_REFERENCED') for t in terminal),producer_terminal_tasks=terminal,unresolved_task_ids=check['unresolved_task_ids'],undispatched_task_ids=check['undispatched_task_ids'],failure_marker=diagnostic,failure_marker_externally_hashed=False,optimization_rerun=False,optimized_weights_independently_verified=False,recovery_certificates_recomputed=False,**FALSE)



FAILED_PARENT=ROOT/'data/cache/research/registered_scoring_queue_independent_readback_20261003_v1'
FAILED_SNAPSHOT=ROOT/'tmp/scoring_readback_failure_20261003_v1/evidence.json'
FAILED_SNAPSHOT_SHA='73e21e1b04115d43cdabb1f3503c5e7fd54b651f53ac4f195aa44b1a1d84eb75'
FAILED_SOURCE_HASHES={
    str(ROOT/'scripts/ndx_registered_scoring_queue_independent_readback_20261003.py'):'1dbfaa95d8513b09b2a88635cb0c629c1b3b241db01da83d41cdba332c80f26b',
    str(ROOT/'backtest/ndx_registered_scoring_result_inspection_research.py'):'300712c1cd8ac838191b4eddb4feda3b5a87771f91783f0db9014f56bc14e853'}

def load_failed_predecessor():
    snapshot=loads(take_attempt(ref(FAILED_SNAPSHOT,FAILED_SNAPSHOT_SHA),{}))
    names={'started.json','failure.json',*(f'shard_{i:04d}.json' for i in range(53))}
    require(snapshot['schema']=='FAILED_SCORING_READBACK_EVIDENCE_SNAPSHOT_V1','Original failed audit evidence role')
    require(type(snapshot['original_handle']) is int and snapshot['original_handle']==20223 and type(snapshot['original_exit_code']) is int and snapshot['original_exit_code']==1,'Original terminal failed audit')
    require(snapshot['failed_output_directory']==str(FAILED_PARENT),'Original failed output path')
    exact(snapshot['exact_output_names'],sorted(names),'Whole original failed output inventory')
    exact(snapshot['source_hashes'],FAILED_SOURCE_HASHES,'Both immutable original reader sources')
    require(type(snapshot['diagnostic_shard_count']) is int and snapshot['diagnostic_shard_count']==53,'Fifty-three diagnostic-only reports')
    for key in ('original_failure_reclassified','partial_reports_are_final_authority','optimization_rerun','score_recomputed','selection_allowed'):
        require(snapshot[key] is False,'Failed audit never gains authority')
    require(set(snapshot['output_hashes'])=={str(FAILED_PARENT/name) for name in names},'Only original failed output paths')
    sources={str(FAILED_SNAPSHOT):FAILED_SNAPSHOT_SHA,**snapshot['source_hashes'],**snapshot['output_hashes']}
    for p,h in sources.items():valid(ref(p,h))
    guard_failed_predecessor(sources)
    failure=loads((FAILED_PARENT/'failure.json').read_bytes())
    exact(failure,snapshot['failure_preserved'],'Original failure preserved byte-bound')
    require(failure['status']=='FAILED_NO_RETRY_NOT_FINAL_AUTHORITY' and failure['error']=='Complete saved recovery evidence' and failure['completed_shard_audits_are_diagnostic_until_final_readback'] is True,'Original recovery-shape stop, not numeric completion')
    return snapshot,sources

def guard_failed_predecessor(sources):
    # A failure marker is mandatory in this separate diagnostic source set.
    # It is deliberately not merged into the successful numerical source set.
    guard_attempt(sources)
    require({p.name for p in FAILED_PARENT.iterdir()}=={'started.json','failure.json',*(f'shard_{i:04d}.json' for i in range(53))},'Original failed audit namespace changed')


def readback(*,execute=False):
    require(type(execute) is bool,'Execute boolean')
    if not execute:return dict(status='NOT_EXECUTED')
    require(type(REQUEST_RESULT_PATH) is str and type(REQUEST_RESULT_SHA) is str and re.fullmatch('[a-f0-9]{64}',REQUEST_RESULT_SHA) is not None,'Future external request anchor pending')
    require(type(INSPECTOR_SHA) is str and re.fullmatch('[a-f0-9]{64}',INSPECTOR_SHA) is not None,'V2 numerical inspector anchor pending')
    request_ref=ref(REQUEST_RESULT_PATH,REQUEST_RESULT_SHA);requestdir=Path(request_ref['path']).parent
    require(requestdir.parent==QUEUE_ROOT/'requests' and re.fullmatch('[a-f0-9]{32}',requestdir.name) is not None and Path(request_ref['path']).name=='result.json','Fixed request namespace')
    require(not OUTPUT.exists(),'Independent immutable attempt exists; do not retry')
    require({p.name for p in requestdir.iterdir()}=={'started.json','result.json'},'Complete externally anchored request')
    attempts={};request=loads(take(request_ref,attempts));startedref=request['request_started_reference'];require(Path(startedref['path'])==requestdir/'started.json','Request started location');started=loads(take(startedref,attempts))
    predecessor,predecessor_sources=load_failed_predecessor()
    c=load_common();sources=dict(c['producer_sources']);merge(sources,ref(SOURCE,LOADED_SHA))
    import numpy,pandas,scipy
    exact(dict(python=sys.version,numpy=numpy.__version__,pandas=pandas.__version__,scipy=scipy.__version__),c['parents']['rolling_fitter_manifest']['runtime_versions'],'Independent arithmetic same registered binary64 runtime versions')
    numeric=private_inspector(sources);protocol=private_module(JOURNAL_INSPECTOR,JOURNAL_INSPECTOR_SHA,sources)
    contextrefs=request['context_references'];require(set(contextrefs)=={'context_reference','queue_reference'},'Two root references')
    for role,name in (('context_reference','context.json'),('queue_reference','queue.json')):require(Path(contextrefs[role]['path'])==QUEUE_ROOT/name,'Fixed root filename')
    context=loads(take(contextrefs['context_reference'],sources));queue=loads(take(contextrefs['queue_reference'],sources))
    context_hash=contextrefs['context_reference']['sha256'];require(request['context_sha256']==context_hash,'External request context hash')
    # Publication is deterministically reconstructed from already external-bound refs;
    # its exact bytes are checked, not accepted as a self-signed authority.
    pubbytes=(QUEUE_ROOT/'publication.json').read_bytes();pubref=ref(QUEUE_ROOT/'publication.json',sha(pubbytes));merge(sources,pubref);publication=loads(pubbytes)
    require({p.name for p in QUEUE_ROOT.iterdir()}=={'context.json','queue.json','publication.json','shards','requests'},'Exact immutable queue root')
    inspect_context(c,context,queue,publication,contextrefs);guard(sources)
    import shutil
    require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3,'Readback resource floor before output');OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        ownstart=save(OUTPUT/'started.json',dict(schema='REGISTERED_SCORING_QUEUE_READBACK_STARTED_V1',request_reference=request_ref,reader_sha256=LOADED_SHA,retry_allowed=False,**FALSE))
        reportrefs=[];summaries=[];refs=request['completed_shard_references']+([] if request['unresolved_shard_reference'] is None else [request['unresolved_shard_reference']])
        require(len(refs)<=306,'Bounded whole registered queue')
        for i,r in enumerate(refs):
            require(shutil.disk_usage(OUTPUT).free>=5*1024**3,'Readback resource stop; existing evidence never retried')
            report=audit_shard(r,queue['shards'][i],c,contextrefs,context_hash,queue,protocol,numeric)
            report['common_source_reference']=dict(path=str(OUTPUT/'started.json'),sha256=ownstart['sha256'])
            report['common_source_verification_scope']='LOADED_ONCE_REQUEST_BEGIN_AND_END;SHARD_BYTES_BEFORE_AND_AFTER;NO_CONTINUOUS_MONITORING'
            report['reader_sha256']=LOADED_SHA
            rr=save(OUTPUT/f'shard_{i:04d}.json',report);reportrefs.append(rr)
            summaries.append({k:report[k] for k in ('shard_index','result_reference','result_status','producer_terminal_tasks','unresolved_task_ids','verified_new_success_count','terminal_failure_count')})
            for p,h in report['source_hashes'].items():merge(attempts,ref(p,h))
            del report
        counts=inspect_request(request,started,queue,summaries)
        full=request['whole_queue_completed'] is True
        report=save(OUTPUT/'independent_readback.json',dict(schema='REGISTERED_SCORING_QUEUE_INDEPENDENT_READBACK_V1',status='PASS' if full else 'PASS_PARTIAL_EVIDENCE_ONLY',request_reference=request_ref,request_started_reference=startedref,context_references=contextrefs,queue_publication_reference=pubref,reader_sha256=LOADED_SHA,common_source_hashes=sources,attempt_source_hashes=attempts,counts=counts,shard_readback_references=reportrefs,first_external_reference=c['firstrefs'],first_independent_inspection=c['first']['inspection'],request_partition_preserved=deepcopy(request),full_queue_success_independently_verified=full,optimization_rerun=False,optimized_weights_independently_verified=False,recovery_certificates_recomputed=False,missing_result_shard_bytes_authenticated=False,common_source_verification_scope='REQUEST_BEGIN_AND_END_ONLY',numeric_modules_loaded_from_verified_bytes_once=True,readback_generation='V2_ORIGINAL_GROUPED_RECOVERY_BRANCHES',predecessor_failure_reference=ref(FAILED_SNAPSHOT,FAILED_SNAPSHOT_SHA),predecessor_failure_source_hashes=predecessor_sources,predecessor_diagnostic_reports_used_as_success=False,old_failed_namespace_modified=False,fit_called=False,score_worker_called=False,**FALSE))
        guard(sources);guard_attempt(attempts)
        guard_failed_predecessor(predecessor_sources)
        for summary in summaries:
            parent=QUEUE_ROOT/'shards'/f"{summary['shard_index']:04d}"
            names={'started.json','journal.jsonl','result.json'}|({'failure.json'} if summary['result_status']=='STOPPED' else set())
            require({p.name for p in parent.iterdir()}==names,'Final complete shard namespace')
        require({p.name for p in QUEUE_ROOT.iterdir()}=={'context.json','queue.json','publication.json','shards','requests'},'Final parent root set')
        require({p.name for p in requestdir.iterdir()}=={'started.json','result.json'},'Final request set')
        for r in (ownstart,report,*reportrefs):require(filehash(r['path'])==r['sha256'],'Own output changed')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json',*(f'shard_{i:04d}.json' for i in range(len(reportrefs)))},'Exact independent output set')
        return report
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_NO_RETRY_NOT_FINAL_AUTHORITY',error_type=type(e).__name__,error=str(e),completed_shard_audits_are_diagnostic_until_final_readback=True,**FALSE));raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
