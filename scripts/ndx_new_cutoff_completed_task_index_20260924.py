"""Index three already audited task results without repeating any fit or readback."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'new_cutoff_completed_task_index_20260924_v1/index.json'
TASK_ROOT=BASE/'new_cutoff_single_task_20260924_v1'
BOUND={
 'plan':('new_cutoff_shard_prepare_20260924_v2/plan.json','50b3c661325bc4c2c4337cdb3d520413aa51f4dc94a869af9f94fdbd5bb0bceb'),
 'materialized':('new_cutoff_bounded_materialization_20260924_v1/materialized.json','ce8b3c7545b8123c63eeabd0db138c11689d4d535643e58bde720b5a955fc9e0'),
 'materialization_audit':('new_cutoff_bounded_materialization_20260924_v1/independent_materialization_readback.json','a2c996e2f681ad959d0290de2592093e25c31ddfa458d5012713f009b402e8dc')}
AUDITS={
 '23f52d49af488c1d742ed8c906c0d53b93fee11bef6e75624066a5a63463562e':'e7fd63d8eaecd0569d266d93f1f5c295ebd3340821607212e4357a73774f27c8',
 '797a39ffa47540b5882ad26a7023310c0d5fcfcc319d7a228c81e42f904336cf':'5980f216f2812e53daf0bad8143d95ec83409beae8feb67f82d7ed299b7ed734',
 'f17a50638e6b3c9b5344bdd4f2ca84b9ec6ac25c4fa9bae239f724605cfd3c59':'9c58439f05e35bdfaa64c2b063115501e9a1ac865074906c209d4de2edcf49c5'}
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
FALSE=('fit_performed','task_readback_repeated','materialization_repeated','all_plan_tasks_completed','full_shard_completed',
 'point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified',
 'anchor_alias_equivalence_verified','economic_comparison_performed')


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])
def audit_ref(task):return dict(path=str(TASK_ROOT/task/'independent_readback.json'),sha256=AUDITS[task])


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


def assemble(documents,evidence):
    plan=documents['plan']['plan'];materialized=documents['materialized']['materialization'];audit=documents['materialization_audit']
    require(all(type(materialized[key]) is int for key in ('combination_count','materialized_task_count')) and
        type(audit['actual_fitter_invocation_count']) is int,'Exact integer saved operation counts')
    require(documents['plan']['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V2' and
        materialized['plan_reference']==ref('plan') and materialized['combination_count']==1 and materialized['materialized_task_count']==3,'Bound original materialization')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('materialized') and audit['actual_fitter_invocation_count']==0,'Saved task-input audit')
    combo=materialized['combinations'][0];tasks=combo['tasks']
    require(type(combo['k']) is int and type(combo['rank']) is int and combo['k']==4 and combo['rank']==0 and
        [task['numerical_task_id'] for task in tasks]==list(AUDITS),'Exact original three tasks/order')
    require(set(evidence)==set(AUDITS),'No omitted or additional task evidence')
    rows=[];total=dict(wrapper_call_attempt_count=0,deterministic_generation_request_count=0,numerical_fit_request_count=0,import_count=0)
    for index,task in enumerate(tasks):
        task_id=task['numerical_task_id'];item=evidence[task_id];saved=item['audit'];started=item['started'];raw=item['raw'];post=item['postcheck']
        folder=TASK_ROOT/task_id
        require(saved['schema']=='NEW_CUTOFF_SINGLE_TASK_INDEPENDENT_RAW_READBACK_V1' and saved['status']=='FITTED_FIVE_RISKS_PASSED' and
            saved['numerical_task_id']==task_id and saved['detail']['status']=='FITTED_FIVE_RISKS_PASSED' and
            saved['independent_readback_performed'] is True and type(saved['completed_saved_task_readbacks']) is int and
            saved['completed_saved_task_readbacks']==1,'Complete independent task readback')
        require(saved['input_references']['materialized']==ref('materialized') and saved['input_references']['audit']==ref('materialization_audit') and
            saved['input_references']['plan']==ref('plan'),'Final audit parent lineage')
        require(all(saved[key] is False for key in ('runner_called','fitter_called','optimization_repeated','promotion_allowed','point_in_time_verified',
            'execution_authorized','all_plan_tasks_completed','full_shard_completed')),'Audit scope changed')
        for name in ('started','raw'):
            reference=saved[name+'_reference'];require(reference['path']==str(folder/(name+'.json')) and
                saved['source_hashes'][reference['path']]==reference['sha256'],'Exact task evidence reference')
        require(canonical(started['task'])==canonical(task) and raw['numerical_task_id']==task_id and raw['status']=='FIT_RETURNED' and
            type(raw['returned_fit_count']) is int and raw['returned_fit_count']==1 and raw['error'] is None,'Actual single returned task')
        require(raw['started_reference']==saved['started_reference'] and post==saved['saved_postcheck'] and
            post['raw_reference']==saved['raw_reference'] and post['status']=='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' and post['error'] is None,'Saved successful postcheck lineage')
        equal=task['numerical_identity']['weight_spec']=='equal_weight'
        expected=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)
        require(canonical(raw['operation_counts'])==canonical(expected),'Exact observed request counts')
        for key,count in expected.items():total[key]+=count
        require(set(saved['detail']['checks'])=={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'} and
            all(type(check) is bool and check for check in saved['detail']['checks'].values()),'Five original risks passed')
        rows.append(dict(numerical_task_id=task_id,weight_spec=task['numerical_identity']['weight_spec'],full_task=deepcopy(task),
            task_reference=dict(ref('materialized'),json_pointer='/materialization/combinations/0/tasks/'+str(index)),
            started_reference=deepcopy(saved['started_reference']),raw_reference=deepcopy(saved['raw_reference']),
            postcheck_reference=dict(path=str(folder/'postcheck.json'),sha256=saved['source_hashes'][str(folder/'postcheck.json')]),
            independent_readback_reference=audit_ref(task_id),status='COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED',
            operation_counts=expected,targets=deepcopy(raw['fitted']['targets']),fit_data_sha256=raw['fitted']['fit_data_sha256']))
    require(type(plan['planned_canonical_task_count']) is int and type(plan['planned_combination_count']) is int and
        plan['planned_canonical_task_count']==2355300 and plan['planned_combination_count']==785100,'Complete original plan denominator')
    return dict(schema='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1',scope='EXTERNAL_COMPLETION_REFERENCES_NOT_REFIT',
        input_references={role:ref(role) for role in BOUND},completed_tasks=rows,completed_task_count=3,
        completed_combination_count=1,completed_original_risk_pass_count=3,completed_original_risk_failure_count=0,
        original_plan_task_denominator=2355300,remaining_plan_task_count=2355297,
        original_plan_combination_denominator=785100,remaining_plan_combination_count=785099,
        observed_completed_operation_counts=total,internal_optimizer_call_count=None,
        completed_coordinate=dict(k=4,rank=0,prefix_security_ids=deepcopy(combo['prefix_security_ids'])),
        **dict.fromkeys(FALSE,False))


def build():
    sources=dict(LOADED);guard(sources);documents={role:load_bound(ref(role),sources) for role in BOUND};evidence={}
    for task_id in AUDITS:
        saved=load_bound(audit_ref(task_id),sources);merge(sources,saved['source_hashes'])
        evidence[task_id]=dict(audit=saved,started=load_bound(saved['started_reference'],sources),raw=load_bound(saved['raw_reference'],sources),
            postcheck=load_bound(dict(path=str(TASK_ROOT/task_id/'postcheck.json'),sha256=saved['source_hashes'][str(TASK_ROOT/task_id/'postcheck.json')]),sources))
    guard(sources);value=assemble(documents,evidence);value['source_hashes']=sources;guard(sources);return value


def publish():
    require(not OUTPUT.parent.exists(),'Fresh immutable completion index namespace required')
    value=build();guard(value['source_hashes']);raw=encode(value);OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw and {p.name for p in OUTPUT.parent.iterdir()}=={'index.json'},'Index readback differs')
    return dict(path=str(OUTPUT),sha256=sha(raw))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
