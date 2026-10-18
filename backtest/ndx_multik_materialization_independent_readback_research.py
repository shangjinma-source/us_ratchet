"""Independent fixed multi-k batch coverage plus frozen per-slice task readback."""
from copy import deepcopy
import hashlib
from pathlib import Path
from backtest import ndx_issuer_materialization_independent_readback_research as pure
SOURCE=Path(__file__).resolve()
PURE_SHA='cedc4a97ad4138662df6ba95982f7432690367e9ce119a8813ad772940d6dbd1'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(pure.__file__).resolve())}
REQUESTS=tuple((k,1 if k==4 else 0,2) for k in range(4,20))


def require(ok,message):
    if not ok:raise ValueError(message)


def verify_slices(*,materializations,plan,plan_reference,panel,expected_fitter_source_hashes,old_materialization,completed_task_ids):
    """References/bytes require an outer hard anchor; no full combination enumeration."""
    require(LOADED[str(Path(pure.__file__).resolve())]==PURE_SHA,'Frozen independent pure reader required')
    require(type(materializations) is list and len(materializations)==16,'Exactly sixteen declared k slices')
    require(type(completed_task_ids) is list and len(completed_task_ids)==len(set(completed_task_ids))==3,'Three external completed IDs')
    require(all(type(old_materialization[key]) is int and old_materialization[key]==value for key,value in dict(k=4,start=0,stop=1,combination_count=1).items()),'Original rank zero reference only')
    require(old_materialization['plan_reference']==plan_reference and old_materialization['panel_reference']==panel['panel_reference'],'External old task same plan/panel')
    old_combo,=old_materialization['combinations'];old_tasks=old_combo['tasks']
    require(type(old_combo['rank']) is int and old_combo['rank']==0 and len(old_tasks)==3 and [t['numerical_identity']['weight_spec'] for t in old_tasks]==pure.SPECS,'External three specs intact')
    old_ids=[t['numerical_task_id'] for t in old_tasks]
    require(completed_task_ids==old_ids,'Completion IDs in exact original materialization order')
    for task in old_tasks:
        require(task['numerical_task_id']==pure.digest(task['numerical_identity']) and task['location_id']==pure.digest(task['location_identity']),'External task IDs')
    details=[];all_ids=[];all_locations=[];coverage=[]
    for item,(k,start,stop) in zip(materializations,REQUESTS):
        require(type(item['k']) is int and item['k']==k and type(item['start']) is int and item['start']==start and type(item['stop']) is int and item['stop']==stop,'Exact fixed multi-k intervals/order')
        shards=[s for s in plan['shards'] if s['k']==k and s['start']<=start and stop<=s['stop']]
        require(len(shards)==1 and item['shard_id']==shards[0]['shard_id'],'Unique authorized shard')
        detail=pure.verify_materialized(value=item,plan=plan,plan_reference=plan_reference,shard_id=shards[0]['shard_id'],panel=panel,start=start,stop=stop,max_materialized_combinations=stop-start,expected_fitter_source_hashes=expected_fitter_source_hashes)
        details.append(detail);coverage.append(dict(k=k,start=start,stop=stop,new_combination_count=stop-start,new_task_count=(stop-start)*3,external_completed_combination_count=int(k==4),external_completed_task_count=3 if k==4 else 0))
        for combination in item['combinations']:
            require(combination['k']==k and combination['rank']>=start and not (k==4 and combination['rank']==0),'No old rank-zero rematerialization')
            for task in combination['tasks']:all_ids.append(task['numerical_task_id']);all_locations.append(task['location_id'])
    require(len(all_ids)==len(set(all_ids))==len(all_locations)==len(set(all_locations))==93,'Ninety-three distinct new task IDs/locations')
    require(not set(old_ids)&set(all_ids),'Already completed task cannot be rematerialized')
    require(sum(r['new_combination_count'] for r in coverage)==31,'Thirty-one new combinations')
    require(type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']>96,'Bounded batch is not full pool')
    return dict(schema='ISSUER_MULTIK_MATERIALIZATION_INDEPENDENT_SLICES_V1',status='PASSED',coverage=coverage,new_combination_count=31,new_materialized_task_count=93,external_completed_combination_count=1,external_completed_task_count=3,batch_combination_count_including_external=32,batch_task_count_including_external=96,new_completed_task_count=0,external_completed_task_ids=deepcopy(old_ids),new_numerical_task_ids=all_ids,new_location_ids=all_locations,
      plan_planned_canonical_task_count=plan['planned_canonical_task_count'],full_plan_completion_inferred=False,all_plan_tasks_completed=False,full_shard_completed=False,old_tasks_rematerialized=False,source_bytes_authenticated=False,fit_performed=False,producer_called=False,production_index_called=False,production_prepare_called=False,full_combination_enumeration_performed=False,promotion_allowed=False,slice_readbacks=details)
