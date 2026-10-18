"""Independent fixed multi-k queue readback; no producer or fitter imports."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_multik_materialization_independent_readback_research as batch
from scripts import ndx_new_cutoff_materialization_independent_readback_20260924 as single
codec=single.codec
SOURCE=Path(__file__).resolve();BASE=ROOT/'data/cache/research'
PRODUCER=ROOT/'scripts/ndx_new_cutoff_multik_materialize_20260924.py';PRODUCER_SHA='4ded8519deab67f159cff4a8b604486c8a87dd7a381c935646768173edd5cd70'
CANDIDATE=BASE/'new_cutoff_multik_materialization_20260924_v1/queue.json';CANDIDATE_SHA='bc6d6a05b349b790a252041b677a763643e3ac6589b6f1cba4d72347a2d4b52e'
OUTPUT=CANDIDATE.with_name('independent_readback.json')
BOUND={
 'completed_index':('new_cutoff_completed_task_index_20260924_v1/index.json','bd104f712a006d9427384929718a49bf6b229ed1b3dc2a3fdc227a8d40a3c369'),
 'old_materialized':('new_cutoff_bounded_materialization_20260924_v1/materialized.json','ce8b3c7545b8123c63eeabd0db138c11689d4d535643e58bde720b5a955fc9e0'),
 'old_materialization_audit':('new_cutoff_bounded_materialization_20260924_v1/independent_materialization_readback.json','a2c996e2f681ad959d0290de2592093e25c31ddfa458d5012713f009b402e8dc'),
 **single.BOUND}
BATCH_SHA='f00b044d311197b7993427431259d7a9691750d7f3dd9b6bb9383410653dae61'
SINGLE_SHA='e4ec2a13c597df6d7294fbc1fc685b2dcea7f9c233dfcb7914d510a85564e4d8'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(batch.__file__).resolve(),Path(single.__file__).resolve())}
FALSE=single.FALSE


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])
def merge(a,b):
    for p,h in b.items():require(p not in a or a[p]==h,'Source conflict');a[p]=h


def reused_reference(documents):
    index=documents['completed_index'];old=documents['old_materialized']['materialization'];audit=documents['old_materialization_audit']
    require(index['schema']=='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1' and index['input_references']==dict(plan=ref('plan'),materialized=ref('old_materialized'),materialization_audit=ref('old_materialization_audit')),'Completion lineage')
    counts=dict(completed_task_count=3,completed_combination_count=1,completed_original_risk_pass_count=3,completed_original_risk_failure_count=0,original_plan_task_denominator=2355300,remaining_plan_task_count=2355297,original_plan_combination_denominator=785100,remaining_plan_combination_count=785099)
    require(all(type(index[k]) is int and index[k]==v for k,v in counts.items()),'External/full-pool denominators')
    for flag in ('fit_performed','task_readback_repeated','materialization_repeated','all_plan_tasks_completed','full_shard_completed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','anchor_alias_equivalence_verified','economic_comparison_performed'):
        require(index[flag] is False,'Completion scope')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('old_materialized'),'Old materialization audit binding')
    require(len(old['combinations'])==1,'One external combination');combo=old['combinations'][0]
    require(combo['k']==4 and combo['rank']==0 and index['completed_coordinate']==dict(k=4,rank=0,prefix_security_ids=combo['prefix_security_ids']),'Old coordinate')
    rows=index['completed_tasks'];require(len(rows)==len(combo['tasks'])==3,'Three full completed tasks')
    for i,(row,task) in enumerate(zip(rows,combo['tasks'])):
        require(batch.pure.exact(row['full_task'],task) and row['numerical_task_id']==task['numerical_task_id'] and row['weight_spec']==task['numerical_identity']['weight_spec'] and row['fit_data_sha256']==combo['fit_data_sha256'] and row['status']=='COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED','Full externally audited task')
        require(row['task_reference']==dict(ref('old_materialized'),json_pointer='/materialization/combinations/0/tasks/'+str(i)),'Old task pointer')
        equal=row['weight_spec']=='equal_weight';expected=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)
        require(batch.pure.exact(row['operation_counts'],expected),'Old observed operation counts')
        for key,name in [('started_reference','started.json'),('raw_reference','raw.json'),('postcheck_reference','postcheck.json'),('independent_readback_reference','independent_readback.json')]:
            r=row[key];batch.pure.reference(r)
            require(r['path']==str(BASE/'new_cutoff_single_task_20260924_v1'/row['numerical_task_id']/name) and index['source_hashes'].get(r['path'])==r['sha256'],'Exact old evidence path/hash')
        selected=task['numerical_identity']['selected'];require(set(row['targets'])==set(selected),'External target denominator')
        for sid,target in row['targets'].items():require(all(target[k]==selected[sid][k] for k in ('ticker','issuer_id')),'External target identity')
    return dict(completed_index_reference=ref('completed_index'),materialized_reference=ref('old_materialized'),materialization_audit_reference=ref('old_materialization_audit'),completed_coordinate=deepcopy(index['completed_coordinate']),numerical_task_ids=[r['numerical_task_id'] for r in rows],completed_tasks=deepcopy(rows))


def producer_sources(documents):
    sources={str(PRODUCER):PRODUCER_SHA}
    for mapping in (documents['plan']['source_hashes'],documents['completed_index']['source_hashes'],batch.pure.MATERIALIZER_SOURCES,codec.LOADED):merge(sources,mapping)
    merge(sources,{ref(k)['path']:ref(k)['sha256'] for k in BOUND})
    for p,h in documents['plan']['plan']['fitter_source_hashes'].items():require(sources.get(p)==h,'Full25 fitter closure')
    return sources


def verify_document(value,documents):
    args=single.project({k:documents[k] for k in single.BOUND})
    reused=reused_reference(documents);plan=args['plan']
    require([c['k'] for c in plan['cardinalities']]==list(range(1,20)),'All19 cardinalities retained')
    require(type(plan['all_k_combination_count']) is int and plan['all_k_combination_count']==786431 and type(plan['necessary_bound_excluded_combination_count']) is int and plan['necessary_bound_excluded_combination_count']==1331 and type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==2355300,'Hard full-pool denominator')
    for k in range(4,20):require(not plan['cardinalities'][k-1]['necessary_bound_certificates'] and plan['cardinalities'][k-1]['combination_count']>=2,'Fixed requested k available')
    expected=dict(schema='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_BOUNDED_PREFIX_BATCH_NOT_SEARCH_SELECTION',new_materializations=value['new_materializations'],reused_completed_reference=reused,input_references={k:ref(k) for k in BOUND},source_hashes=producer_sources(documents),complete_cardinalities=deepcopy(plan['cardinalities']),all_k_combination_count=786431,necessary_bound_excluded_combination_count=1331,full_pool_planned_task_count=2355300,new_combination_count=31,new_task_count=93,externally_completed_combination_count=1,externally_completed_task_count=3,batch_combination_count=32,batch_task_count=96,new_completed_task_count=0,materializer_invocation_count=16,enumerated_combination_count=31,actual_fitter_invocation_count=0,selection_rule='FIRST_TWO_PREFIX_RANKS_PER_K_4_THROUGH_19_FIXED_WITHOUT_SCORES',complete_observed_provenance_and_missing=deepcopy(documents['plan']['complete_observed_provenance_and_missing']),preserved_evidence_sidecar_reference=deepcopy(documents['plan']['preserved_evidence_sidecar_reference']),preserved_incremental_evidence_sidecar_reference=deepcopy(documents['plan']['preserved_incremental_evidence_sidecar_reference']),score_filtering_performed=False,completed_combination_resliced=False,**dict.fromkeys(FALSE,False))
    require(batch.pure.exact(value,expected),'Entire batch envelope/counts/certificates/sidecars/source map')
    detail=batch.verify_slices(materializations=value['new_materializations'],plan=plan,plan_reference=ref('plan'),panel=args['panel'],expected_fitter_source_hashes=args['expected_fitter_source_hashes'],old_materialization=documents['old_materialized']['materialization'],completed_task_ids=reused['numerical_task_ids'])
    return detail,expected['source_hashes']


def guard(sources):
    require(BATCH_SHA is not None and LOADED[str(Path(batch.__file__).resolve())]==BATCH_SHA and LOADED[str(Path(single.__file__).resolve())]==SINGLE_SHA,'Frozen independent reader pins')
    expected=dict(sources)
    for mapping in (LOADED,batch.LOADED,single.LOADED,codec.LOADED):merge(expected,mapping)
    for p,h in expected.items():require(codec.sha(Path(p).read_bytes())==h,'Source drift')


def build():
    require(PRODUCER_SHA is not None and CANDIDATE_SHA is not None and BOUND['completed_index'][1] is not None,'Actual external anchors pending')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        r=ref(role);blob=Path(r['path']).read_bytes();require(codec.sha(blob)==r['sha256'],'Hard parent bytes');documents[role]=codec.loads(blob);sources[r['path']]=r['sha256']
    blob=CANDIDATE.read_bytes();require(codec.sha(blob)==CANDIDATE_SHA,'Hard candidate bytes');sources[str(CANDIDATE)]=CANDIDATE_SHA
    expected=producer_sources(documents);merge(sources,expected);guard(sources)
    detail,verified=verify_document(codec.loads(blob),documents);require(verified==expected,'Source closure changed')
    for mapping in (batch.LOADED,single.LOADED,codec.LOADED):merge(sources,mapping)
    result=dict(schema='NEW_CUTOFF_MULTIK_MATERIALIZATION_INDEPENDENT_READBACK_V1',status='PASSED',candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),input_references={k:ref(k) for k in BOUND},source_hashes=sources,independent_batch_readback_count=1,pure_readback=detail,old_task_audits_repeated=False,old_combination_materialization_repeated=False,producer_called=False,actual_fitter_invocation_count=0,**dict.fromkeys(FALSE,False))
    guard(sources);return result


def publish():
    require(not OUTPUT.exists() and OUTPUT.parent.is_dir() and {p.name for p in OUTPUT.parent.iterdir()}=={'queue.json'},'Exact unfinalized queue namespace')
    result=build();guard(result['source_hashes']);blob=codec.pretty(result)
    with OUTPUT.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    guard(result['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'queue.json',OUTPUT.name},'Audit output/namespace readback')
    return dict(path=str(OUTPUT),sha256=codec.sha(blob))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');a=p.parse_args()
    require(a.publish,'Explicit --publish required');print(json.dumps(publish()))
