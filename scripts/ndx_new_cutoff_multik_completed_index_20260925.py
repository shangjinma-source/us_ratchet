"""Index saved independent results only; no runner, fitter or audit imports."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'new_cutoff_multik_completed_index_20260925_v1/index.json'
TASK_ROOT=BASE/'new_cutoff_multik_single_task_20260924_v1'
BOUND={
 'queue':('new_cutoff_multik_materialization_20260924_v1/queue.json','bc6d6a05b349b790a252041b677a763643e3ac6589b6f1cba4d72347a2d4b52e'),
 'queue_audit':('new_cutoff_multik_materialization_20260924_v1/independent_readback.json','d5128c97b276b1b03d38b2d84b27e86f56a1213567e99010ac006c041f3e89ca'),
 'old_index':('new_cutoff_completed_task_index_20260924_v1/index.json','bd104f712a006d9427384929718a49bf6b229ed1b3dc2a3fdc227a8d40a3c369'),
 'manifest':('new_cutoff_multik_completed_audit_references_20260925_v1/references.json','296ccfa33c5c16bdc34612fcec9c72fcaba7a7935a25e7ebb6c9c2d01b9b685e')}
PINS={str(ROOT/'scripts/ndx_new_cutoff_multik_single_task_20260924.py'):'0e4e8c9d2b3c7da1e603973a94730aabe3fd1d3bfa1f8d928a40438fb9df87cc',
 str(ROOT/'scripts/ndx_new_cutoff_multik_single_task_independent_readback_20260924.py'):'f30c874718135b07cd38d22fa68458220631a8b714e4a017c11972bab17d97f8'}
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),**PINS}
FALSE=('fit_performed','task_readback_repeated','materialization_repeated','all_plan_tasks_completed','full_shard_completed',
 'point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','economic_comparison_performed')
RISK_NAMES={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'}

def require(ok,message):
    if not ok:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def merge(sources,other):
    for path,digest in other.items():
        require(path not in sources or sources[path]==digest,'Conflicting source map');sources[path]=digest


def guard(sources):
    expected=dict(sources);merge(expected,LOADED)
    for path,digest in expected.items():require(sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def load_bound(reference,sources):
    path=Path(reference['path']);raw=path.read_bytes();require(sha(raw)==reference['sha256'],'Consumed source bytes differ')
    merge(sources,{str(path):reference['sha256']})
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'Duplicate JSON key');value[key]=item
        return value
    def fail(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=fail)


def tasks_and_references(documents):
    queue=documents['queue'];manifest=documents['manifest'];audit=documents['queue_audit'];old=documents['old_index']
    require(queue['schema']=='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1' and old['schema']=='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1','Saved queue/index schemas')
    require(type(queue['full_pool_planned_task_count']) is int and queue['full_pool_planned_task_count']==2355300 and
        type(old['original_plan_task_denominator']) is int and old['original_plan_task_denominator']==2355300 and
        type(old['completed_task_count']) is int and old['completed_task_count']==3,'Exact saved full-pool and old completion counts')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('queue'),'Queue independent audit required')
    require(queue['reused_completed_reference']['completed_tasks']==old['completed_tasks'] and len(old['completed_tasks'])==3,'Old three external completions required')
    tasks=[]
    for i,value in enumerate(queue['new_materializations']):
        for j,combo in enumerate(value['combinations']):
            for k,task in enumerate(combo['tasks']):tasks.append((task,dict(ref('queue'),json_pointer=f'/new_materializations/{i}/combinations/{j}/tasks/{k}')))
    ids=[t['numerical_task_id'] for t,p in tasks]
    require(len(ids)==len(set(ids))==93 and not set(ids)&{r['numerical_task_id'] for r in old['completed_tasks']},'Exact93 new IDs')
    require(set(manifest)=={'schema','queue_reference','task_audit_references','expected_count'} and manifest['schema']=='MULTIK_COMPLETED_AUDIT_REFERENCES_V1' and
        manifest['queue_reference']==ref('queue') and type(manifest['expected_count']) is int and manifest['expected_count']==93,'Hard external reference manifest')
    refs=manifest['task_audit_references'];require([r['numerical_task_id'] for r in refs]==ids,'Exact93 manifest order/coverage')
    for r in refs:
        require(set(r)=={'numerical_task_id','path','sha256'} and r['path']==str(TASK_ROOT/r['numerical_task_id']/'independent_readback.json') and
            type(r['sha256']) is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Canonical external task audit reference')
    return tasks,refs


def row_from_evidence(task,pointer,audit_reference,item):
    saved,started,raw,post=(item[k] for k in ('audit','started','raw','postcheck'));tid=task['numerical_task_id'];folder=TASK_ROOT/tid
    require(saved['schema']=='NEW_CUTOFF_MULTIK_SINGLE_TASK_INDEPENDENT_RAW_READBACK_V1' and saved['numerical_task_id']==tid and
        saved['independent_readback_performed'] is True and type(saved['completed_saved_task_readbacks']) is int and saved['completed_saved_task_readbacks']==1,'One saved independent readback')
    require(all(saved[k] is False for k in ('runner_called','fitter_called','optimization_repeated','promotion_allowed','execution_authorized','all_plan_tasks_completed')),'Saved authority changed')
    require(saved['input_references']['queue']==ref('queue') and saved['input_references']['audit']==ref('queue_audit') and saved['input_references']['completed_index']==ref('old_index'),'Saved lineage differs')
    require(all(saved['source_hashes'].get(p)==h and started['source_hashes'].get(p)==h for p,h in PINS.items() if 'single_task_20260924.py' in p),'Runner source closure differs')
    require(saved['source_hashes'].get(next(p for p in PINS if 'independent_readback' in p))==next(h for p,h in PINS.items() if 'independent_readback' in p),'Independent reader source differs')
    require(started['schema']=='NEW_CUTOFF_MULTIK_SINGLE_TASK_STARTED_V1' and canonical(started['task'])==canonical(task) and started['task_reference']==pointer,'Full started task/pointer mismatch')
    require(raw['schema']=='NEW_CUTOFF_MULTIK_SINGLE_TASK_RAW_V1' and raw['numerical_task_id']==tid and raw['source_hashes']==started['source_hashes'] and raw['runtime']==started['runtime'],'Raw source/runtime mismatch')
    require(raw['internal_optimizer_call_count'] is None,'Internal optimizer count remains unknown')
    require(all(saved['source_hashes'].get(p)==h for p,h in started['source_hashes'].items()),'Incomplete saved source closure')
    for name in ('started','raw'):
        r=saved[name+'_reference'];require(r['path']==str(folder/(name+'.json')) and saved['source_hashes'].get(r['path'])==r['sha256'],'Saved original reference differs')
    require(raw['started_reference']==saved['started_reference'] and post==saved['saved_postcheck'],'Raw/postcheck original binding differs')
    equal=task['numerical_identity']['weight_spec']=='equal_weight';counts=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)
    require(canonical(raw['operation_counts'])==canonical(counts) and canonical(started['planned_operation_counts'])==canonical(counts),'Exactly one external attempt')
    status=saved['status'];detail=saved['detail'];require(saved['numerical_detail_status']==detail['status'],'Detail status differs')
    allowed=('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED','NUMERICAL_EXCEPTION_NO_RETURNED_FIT','VALIDATION_FAILURE_RECORDED')
    require(status in allowed,'Unknown saved result status')
    if raw['status']=='FIT_EXCEPTION':
        require(type(raw['returned_fit_count']) is int and raw['returned_fit_count']==0 and raw['fitted'] is None and type(raw['error']) is dict and detail['status']=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT','Exception cannot become returned fit')
    else:
        require(raw['status']=='FIT_RETURNED' and type(raw['returned_fit_count']) is int and raw['returned_fit_count']==1 and raw['error'] is None and
            raw['fitted']['fit_data_sha256']==task['numerical_identity']['fit_data_sha256'],'Returned fit binding')
        checks=detail['checks'];require(type(checks) is dict and set(checks)==RISK_NAMES and all(type(v) is bool for v in checks.values()),'Exact five boolean risk results')
        require(len(raw['fitted']['source_hashes'])==25 and all(started['source_hashes'].get(p)==h for p,h in raw['fitted']['source_hashes'].items()),'Full numerical source closure')
        require(detail['status']==('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED'),'Risk failure cannot become pass')
    postref=None
    if post is not None:
        require(post['schema']=='NEW_CUTOFF_MULTIK_SINGLE_TASK_POSTCHECK_V1' and post['numerical_task_id']==tid and post['started_reference']==saved['started_reference'] and post['raw_reference']==saved['raw_reference'],'Postcheck identity')
        path=str(folder/'postcheck.json');require(path in saved['source_hashes'],'Saved postcheck SHA missing');postref=dict(path=path,sha256=saved['source_hashes'][path])
    expected='VALIDATION_FAILURE_RECORDED' if post is not None and post['error'] is not None else detail['status']
    require(status==expected,'Validation failure cannot become completed pass')
    return dict(numerical_task_id=tid,full_task=deepcopy(task),task_reference=pointer,started_reference=deepcopy(saved['started_reference']),
        raw_reference=deepcopy(saved['raw_reference']),postcheck_reference=postref,independent_readback_reference=audit_reference,
        status=status,returned_fit_count=raw['returned_fit_count'],operation_counts=counts,targets=deepcopy(raw['fitted']['targets']) if raw['fitted'] is not None else None,
        fit_data_sha256=task['numerical_identity']['fit_data_sha256'])


def assemble(documents,evidence):
    tasks,refs=tasks_and_references(documents);require(set(evidence)=={t['numerical_task_id'] for t,p in tasks},'No omitted/extra task evidence')
    rows=[row_from_evidence(t,p,{k:r[k] for k in ('path','sha256')},evidence[t['numerical_task_id']]) for (t,p),r in zip(tasks,refs)]
    counts={status:sum(r['status']==status for r in rows) for status in ('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED','NUMERICAL_EXCEPTION_NO_RETURNED_FIT','VALIDATION_FAILURE_RECORDED')}
    return dict(schema='NEW_CUTOFF_MULTIK_COMPLETED_TASK_INDEX_V1',input_references={k:ref(k) for k in BOUND},new_tasks=rows,
        old_completed_tasks=deepcopy(documents['old_index']['completed_tasks']),old_index_reference=ref('old_index'),new_independently_read_task_count=93,
        new_status_counts=counts,new_returned_fit_count=sum(r['returned_fit_count'] for r in rows),batch_saved_attempt_count=96,
        full_pool_planned_task_denominator=2355300,remaining_unattempted_plan_task_count=2355204,
        all_batch_independent_reports_present=True,all_batch_original_risks_passed=counts['FITTED_FIVE_RISKS_PASSED']==93,
        internal_optimizer_call_count=None,
        failure_is_global_infeasibility=False,**dict.fromkeys(FALSE,False))


def build():
    require(type(BOUND['manifest'][1]) is str and len(BOUND['manifest'][1])==64,'Actual93 external manifest SHA pending')
    sources=dict(LOADED);guard(sources);documents={role:load_bound(ref(role),sources) for role in BOUND}
    tasks,refs=tasks_and_references(documents);evidence={}
    for r in refs:
        tid=r['numerical_task_id'];saved=load_bound({k:r[k] for k in ('path','sha256')},sources);merge(sources,saved['source_hashes'])
        started=load_bound(saved['started_reference'],sources);raw=load_bound(saved['raw_reference'],sources);post=None
        if saved['saved_postcheck'] is not None:
            path=str(TASK_ROOT/tid/'postcheck.json');post=load_bound(dict(path=path,sha256=saved['source_hashes'][path]),sources)
        evidence[tid]=dict(audit=saved,started=started,raw=raw,postcheck=post)
    guard(sources);value=assemble(documents,evidence);value['source_hashes']=sources;guard(sources);return value


def publish():
    require(not OUTPUT.parent.exists(),'Fresh immutable namespace required')
    value=build();guard(value['source_hashes']);blob=encode(value);OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'index.json'},'Index output drift')
    return dict(path=str(OUTPUT),sha256=sha(blob))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))


