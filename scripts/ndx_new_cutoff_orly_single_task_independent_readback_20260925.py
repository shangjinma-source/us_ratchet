"""External-SHA, raw-only task finalization. No runner/fitter imports or retries."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
import scipy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_single_task_raw_readback_research as pure
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
SOURCE=Path(__file__).resolve();BASE=ROOT/'data/cache/research'
RUNNER=ROOT/'scripts/ndx_new_cutoff_orly_single_task_20260925.py';RUNNER_SHA='e8f466b0cb83f90c73cbdf0d7414bf0692e0784107a2f3799daac5cd3f1308b2';PURE_SHA='f4ac1f2ced3d73601bdf43850951063fc347401cb301c928e48c589ba5f8a72a'
OUTPUT_ROOT=BASE/'new_cutoff_orly_single_task_20260925_v1'
BOUND={
 'queue':('new_cutoff_orly_combination_materialization_20260925_v1/queue.json','cde70b4b1e38491997b7f8bec7ac6c9e8e5419d80bded20843f558638f6aadce'),
 'audit':('new_cutoff_orly_combination_materialization_20260925_v1/independent_readback.json','da8afe3018b91db7bf66bb48b8835e7d79faa4e5e42374e3ee9dee11bfcc9936'),
 'rebinding':('new_cutoff_v5_completed_task_rebinding_20260925_v1/rebinding.json','c64888a62744c1ee8c6acb08c37d96350fe4e58546320d5a1957f90eedfb63b7'),
 'rebinding_audit':('new_cutoff_v5_completed_task_rebinding_20260925_v1/independent_readback.json','06a9b1b024bdc43e091bcadd6fa112fce34446a815a1cdf3f99f5a7f88612dbf'),
 'panel':('new_cutoff_conditional_panel_20260925_v5/panel.json','3ad3e6c47611b6bc9818df63756d9a6f06aacaded5d2aada3d743dfcf3343e14'),
 'plan':('new_cutoff_shard_prepare_20260925_v5/plan.json','ca110466d6a40adabed4ddd35b45fa980951cda421958fc8648697e5c5594f56')}
ORLY='security:0000898173:67103H107'
FALSE=('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified','independent_readback_performed','full_shard_completed','all_plan_tasks_completed','retry_allowed','runtime_binary_closure_verified','full_transitive_source_closure_reverified')
LIBRARIES=(np,pd,scipy)
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(pure.__file__).resolve(),Path(codec.__file__).resolve(),*[Path(m.__file__).resolve() for m in LIBRARIES])}


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])
def merge(left,right):
    for p,h in right.items():require(p not in left or left[p]==h,'Source conflict');left[p]=h


def runtime():return dict(python=sys.version,implementation=platform.python_implementation(),executable=str(Path(sys.executable).resolve()),platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)


def counts(task):
    equal=task['numerical_identity']['weight_spec']=='equal_weight'
    return dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)


def expected_state(documents,task_id):
    queue,audit,rebound,previous,paneldoc,plan=(documents[k] for k in ('queue','audit','rebinding','rebinding_audit','panel','plan'))
    require(queue['schema']=='NEW_CUTOFF_ORLY_COMBINATION_MATERIALIZATION_V1' and audit['schema']=='NEW_CUTOFF_ORLY_COMBINATION_INDEPENDENT_READBACK_V1' and audit['status']=='PASSED' and audit['candidate_reference']==ref('queue'),'Hard ORLY queue audit')
    require(all(type(audit[k]) is int and audit[k]==v for k,v in dict(independent_readback_count=1,actual_fitter_invocation_count=0,new_task_count=102,new_combination_count=34).items()),'Complete zero-fit queue readback')
    require(rebound['schema']=='NEW_CUTOFF_V5_COMPLETED_TASK_REBINDING_V1' and rebound['input_references']['plan']==ref('plan') and previous['status']=='PASSED' and previous['candidate_reference']==ref('rebinding') and previous['numerical_contracts_unchanged'] is True,'Audited old300 rebinding')
    old_ids=[r['numerical_task_id'] for r in rebound['rows']]
    require(len(old_ids)==len(set(old_ids))==300 and old_ids==previous['verified_numerical_task_ids'] and task_id not in old_ids,'No repeated old300 task')
    require(queue['reused_completed_reference']==dict(rebinding_reference=ref('rebinding'),independent_readback_reference=ref('rebinding_audit'),numerical_task_ids=old_ids),'Exact old300 reference')
    require(all(type(queue[k]) is int and queue[k]==v for k,v in dict(new_combination_count=34,new_task_count=102,external_completed_task_count=300,new_completed_task_count=0,actual_fitter_invocation_count=0,full_plan_task_denominator=18868155).items()),'Complete102/pool scope')
    require(all(queue[k] is False for k in ('fit_performed','full_shard_completed','all_plan_tasks_completed','old_completed_tasks_rematerialized','promotion_allowed','execution_authorized')),'Conditional pending inputs')
    require(pure.exact(queue['complete_observed_provenance_and_missing'],plan['complete_observed_provenance_and_missing']) and pure.exact(queue['preserved_sidecar_references'],[plan[key] for key in ('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference','preserved_v5_incremental_evidence_sidecar_reference')]),'Full101 gaps and all five sidecars')
    values=queue['new_materializations'];selections=queue['selections'];require(queue['forced_sid']==ORLY and len(values)==len(selections)==34,'34 forced singleton slices')
    numerical=plan['plan']['fitter_source_hashes'];require(len(numerical)==25,'Full25 fitter sources')
    matches=[];ids=[];locations=[];combos=set()
    specs=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
    for i,(value,selection) in enumerate(zip(values,selections)):
        k=4+i//2;local=i%2;rank=selection['full_rank']
        require(all(type(selection[key]) is int for key in ('k','forced_local_rank','full_rank')) and selection['k']==k and selection['forced_local_rank']==local,'Exact k/forced position/fullrank metadata')
        require(all(type(value[key]) is int and value[key]==v for key,v in dict(k=k,start=rank,stop=rank+1,combination_count=1,materialized_task_count=3,completed_task_count=0).items()),'Exact singleton/pending count')
        require(value['plan_reference']==ref('plan') and value['panel_reference']==ref('panel') and value['fitter_source_hashes']==numerical and value['shard_id']==selection['shard_id'],'Every slice lineage')
        require(value['status']=='MATERIALIZED_NOT_ATTEMPTED' and all(value[x] is False for x in ('fit_performed','full_shard_completed','all_plan_tasks_completed')),'Pending slice metadata')
        require(len(value['combinations'])==1,'One combination per slice');combo=value['combinations'][0];prefix=combo['prefix_security_ids']
        require(type(combo['k']) is int and combo['k']==k and type(combo['rank']) is int and combo['rank']==rank and prefix==selection['prefix_security_ids'] and ORLY in prefix and len(prefix)==len(set(prefix))==k and tuple(prefix) not in combos,'Complete distinct ORLY combinations');combos.add(tuple(prefix))
        require([t['numerical_identity']['weight_spec'] for t in combo['tasks']]==specs,'All three specs preserved')
        for spec_index,task in enumerate(combo['tasks']):
            identity=task['numerical_identity'];location=task['location_identity']
            require(task['status']=='MATERIALIZED_NOT_ATTEMPTED' and type(task['wrapper_call_attempt_count']) is int and task['wrapper_call_attempt_count']==0 and task['fit_performed'] is False and task['anchor_alias_equivalence_verified'] is False and task['expected_fitter_previous_target_weights']=={},'Zero attempt task metadata')
            require(identity['requested_previous_target_weights'] is None and set(identity['selected'])==set(prefix) and pure.digest(identity)==task['numerical_task_id'] and pure.digest(location)==task['location_id'],'All102 full selection/dual IDs')
            require(all(type(location[key]) is int and location[key]==v for key,v in dict(k=k,rank=rank,spec_index=spec_index).items()) and location['plan_reference']==ref('plan') and location['plan_id']==value['plan_id'] and location['shard_id']==value['shard_id'] and location['weight_spec']==identity['weight_spec'],'All102 exact task locations')
            ids.append(task['numerical_task_id']);locations.append(task['location_id'])
            if task['numerical_task_id']==task_id:matches.append((value,combo,task,i,spec_index))
    require(len(combos)==34 and len(ids)==len(set(ids))==len(locations)==len(set(locations))==102 and not set(ids)&set(old_ids) and len(matches)==1,'102 distinct new tasks not300old')
    require(ids==audit['verified_numerical_task_ids'] and locations==audit['verified_location_ids'],'Complete saved audit identity ordering')
    value,combo,task,i,spec_index=matches[0];tasks=[task]
    task_reference=dict(ref('queue'),json_pointer=f'/new_materializations/{i}/combinations/0/tasks/{spec_index}')
    task=tasks[0];ident=task['numerical_identity'];require(pure.digest(ident)==task_id and pure.digest(task['location_identity'])==task['location_id'],'Task identities')
    location=task['location_identity']
    require(all(type(location[key]) is int and location[key]==v for key,v in dict(k=combo['k'],rank=combo['rank'],spec_index=spec_index).items()) and location['plan_reference']==ref('plan') and location['plan_id']==value['plan_id'] and location['shard_id']==value['shard_id'] and location['weight_spec']==ident['weight_spec'],'Task pointer/location exact')
    require(type(ident['holding_count']) is int and ident['holding_count']==combo['k']==len(ident['selected']) and task['status']=='MATERIALIZED_NOT_ATTEMPTED' and type(task['wrapper_call_attempt_count']) is int and task['wrapper_call_attempt_count']==0 and task['fit_performed'] is False,'New pending task exact holding count')
    require(ident['fitter_source_fingerprint']==pure.digest(numerical),'Fitter source fingerprint')
    panel=codec.decode_frames(paneldoc['panel']);frame=panel['returns']
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V5' and panel['panel_content_sha256']==value['panel_content_sha256'] and all(panel[k] is False for k in codec.PANEL_FALSE),'Conditional typed panel binding')
    require(type(panel['conditional_security_count']) is int and panel['conditional_security_count']==23 and type(panel['conditional_issuer_count']) is int and panel['conditional_issuer_count']==22 and frame.shape==(126,23),'Full23/22 panel')
    require(len(frame)==126 and frame.index.is_unique and frame.index.is_monotonic_increasing and all(d.tzinfo is None and d==d.normalize() for d in frame.index) and frame.index[-1].date().isoformat()==ident['cutoff'],'Exact126 dates')
    for row in frame.values.tolist():
        for v in row:require(type(v) in (int,float) and math.isfinite(v) and v>-1,'Complete full panel numbers')
    groups={}
    for row in panel['universe'].to_dict('records'):groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    require([dict(issuer_id=issuer,security_ids=sorted(sids)) for issuer,sids in sorted(groups.items())]==plan['plan']['canonical_groups'],'Complete panel issuer/SID groups')
    require(plan['plan']['context']['previous_target_weights'] is None,'Hard first-decision None prior')
    selected=ident['selected'];by={r['security_id']:r for r in panel['universe'].to_dict('records')}
    require(all(s in by and selected[s]=={k:by[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in selected) and len({r['issuer_id'] for r in selected.values()})==len(selected),'Hard fullpanel selected coordinates')
    tickers=[selected[s]['ticker'] for s in sorted(selected)]
    matrix=dict(dates=[d.date().isoformat() for d in frame.index],tickers=tickers,returns=frame[tickers].values.tolist())
    require(pure.exact(matrix,combo['fit_matrix']) and pure.digest(matrix)==combo['fit_data_sha256']==ident['fit_data_sha256'],'126 matrix exact')
    require(pure.exact(ident['parameters'],plan['plan']['context']['parameters']) and pure.exact(ident['requested_previous_target_weights'],plan['plan']['context']['previous_target_weights']),'All8 parameters/fullprior context')
    prior=ident['requested_previous_target_weights']
    if prior is not None:
        require(type(prior) is dict and prior and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in prior.values()) and math.isclose(sum(float(v) for v in prior.values()),1.,abs_tol=1e-12,rel_tol=0),'Full prior mass')
    source_map={str(RUNNER):RUNNER_SHA,str(ROOT/'backtest/ndx_dynamic_cutoff_refit_v2_research.py'):'4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75',str(Path(codec.__file__).resolve()):'0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'}
    merge(source_map,{str(Path(m.__file__).resolve()):LOADED[str(Path(m.__file__).resolve())] for m in LIBRARIES})
    for role,doc in documents.items():merge(source_map,{ref(role)['path']:ref(role)['sha256']});merge(source_map,doc.get('source_hashes',{}))
    merge(source_map,numerical);merge(source_map,codec.LOADED)
    return dict(queue_reference=ref('queue'),queue_audit_reference=ref('audit'),rebinding_reference=ref('rebinding'),rebinding_audit_reference=ref('rebinding_audit'),task_reference=task_reference,task=deepcopy(task),combination_identity={k:deepcopy(v) for k,v in combo.items() if k!='tasks'},input_references={k:ref(k) for k in BOUND},source_hashes=source_map,runtime=runtime())


def inspect_envelopes(*,started,raw,state,started_reference,numerical_sources):
    expected=dict(schema='NEW_CUTOFF_ORLY_SINGLE_TASK_STARTED_V1',**state,planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    require(pure.exact(started,expected),'Started must equal hard-authorized task/full matrix/runtime/source contract')
    require(set(raw)=={'schema','started_reference','numerical_task_id','status','operation_counts','fitted','error','returned_fit_count','internal_optimizer_call_count','source_hashes','runtime'}|set(FALSE),'Raw schema')
    require(raw['schema']=='NEW_CUTOFF_ORLY_SINGLE_TASK_RAW_V1' and raw['started_reference']==started_reference and raw['numerical_task_id']==state['task']['numerical_task_id'],'Raw task/started binding')
    require(pure.exact(raw['operation_counts'],counts(state['task'])) and raw['internal_optimizer_call_count'] is None,'Exact single wrapper request, internal calls unknown')
    require(raw['source_hashes']==state['source_hashes'] and raw['runtime']==state['runtime'] and all(raw[k] is False for k in FALSE),'Raw source/runtime/authority')
    require(type(raw['returned_fit_count']) is int,'Returned fit exact count')
    if raw['status']=='FIT_EXCEPTION':
        require(raw['fitted'] is None and raw['returned_fit_count']==0 and type(raw['error']) is dict and set(raw['error'])=={'type','message'} and type(raw['error']['type']) is str and raw['error']['type'] and type(raw['error']['message']) is str,'Exception preserves no returned fit')
        return dict(status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',error=deepcopy(raw['error']),checks=None,numerical_failure_is_economic_infeasibility=False,optimizer_call_count_unknown=True,fitter_called=False,promotion_allowed=False)
    require(raw['status']=='FIT_RETURNED' and raw['error'] is None and raw['returned_fit_count']==1,'Returned result status')
    return pure.inspect_fitted(task=state['task'],combination=state['combination_identity'],fitted=raw['fitted'],numerical_sources=numerical_sources)


def validate_postcheck(post,started_reference,raw_reference,task_id,detail):
    require(set(post)=={'schema','status','started_reference','raw_reference','numerical_task_id','checks','error'}|set(FALSE),'Postcheck exact schema')
    require(post['schema']=='NEW_CUTOFF_ORLY_SINGLE_TASK_POSTCHECK_V1' and post['started_reference']==started_reference and post['raw_reference']==raw_reference and post['numerical_task_id']==task_id and all(post[k] is False for k in FALSE),'Postcheck bindings')
    if post['status']=='NUMERICAL_OR_VALIDATION_FAILURE':
        require(type(post['error']) is dict and set(post['error'])=={'type','message'} and all(type(v) is str for v in post['error'].values()),'Saved validation error')
        if post['checks'] is not None:require(pure.exact(post['checks'],detail.get('checks')),'Saved checks disagree')
    else:
        status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' if detail['status']=='FITTED_FIVE_RISKS_PASSED' else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK'
        require(detail['status'] in ('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED') and post['status']==status and post['error'] is None and pure.exact(post['checks'],detail['checks']),'Postcheck numerical/risk state')


def summary_status(detail,post):
    if post is None or post['error'] is None:return detail['status']
    if detail['status']=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT' and pure.exact(post['error'],detail['error']):return detail['status']
    return 'VALIDATION_FAILURE_RECORDED'


def guard(sources):
    require(RUNNER_SHA is not None and PURE_SHA is not None and LOADED[str(Path(pure.__file__).resolve())]==PURE_SHA,'Frozen source pins pending')
    expected=dict(sources);merge(expected,LOADED);merge(expected,codec.LOADED)
    for p,h in expected.items():require(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Source drift')


def build(numerical_task_id,started_sha256,raw_sha256):
    for v in (numerical_task_id,started_sha256,raw_sha256):require(type(v) is str and len(v)==64 and set(v)<=set('0123456789abcdef'),'Explicit external SHA required')
    folder=OUTPUT_ROOT/numerical_task_id
    require((folder/'started.json').is_file() and (folder/'raw.json').is_file(),'Started without raw is blocked; no retry or inferred completion')
    require({p.name for p in folder.iterdir()} in ({'started.json','raw.json'},{'started.json','raw.json','postcheck.json'}),'Exact unfinalized attempt namespace')
    require(all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Hard input anchors pending')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        r=ref(role);rawbytes=Path(r['path']).read_bytes();require(codec.sha(rawbytes)==r['sha256'],'Hard parent bytes differ');documents[role]=codec.loads(rawbytes);sources[r['path']]=r['sha256']
    state=expected_state(documents,numerical_task_id);merge(sources,state['source_hashes']);guard(sources)
    evidence={};refs={}
    for name,h in [('started',started_sha256),('raw',raw_sha256)]:
        path=folder/(name+'.json');blob=path.read_bytes();require(codec.sha(blob)==h,'External evidence hash differs');evidence[name]=codec.loads(blob);refs[name]=dict(path=str(path),sha256=h);sources[str(path)]=h
    detail=inspect_envelopes(started=evidence['started'],raw=evidence['raw'],state=state,started_reference=refs['started'],numerical_sources=documents['plan']['plan']['fitter_source_hashes'])
    post=None
    if (folder/'postcheck.json').exists():
        path=folder/'postcheck.json';blob=path.read_bytes();post=codec.loads(blob);sources[str(path)]=codec.sha(blob);validate_postcheck(post,refs['started'],refs['raw'],numerical_task_id,detail)
    guard(sources);require(runtime()==state['runtime'],'Runtime changed during readback')
    validation_failed=post is not None and post['error'] is not None
    final_status=summary_status(detail,post)
    return dict(schema='NEW_CUTOFF_ORLY_SINGLE_TASK_INDEPENDENT_RAW_READBACK_V1',status=final_status,numerical_detail_status=detail['status'],saved_postcheck_failure_preserved=validation_failed,saved_postcheck_failure_kind=('NUMERICAL_EXCEPTION_RECORDED' if final_status=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT' else 'VALIDATION_FAILURE_RECORDED') if validation_failed else None,numerical_task_id=numerical_task_id,started_reference=refs['started'],raw_reference=refs['raw'],detail=detail,saved_postcheck=post,postcheck_required_for_recovery=False,input_references={k:ref(k) for k in BOUND},source_hashes=sources,runtime=state['runtime'],completed_saved_task_readbacks=1,new_materialized_task_denominator=102,remaining_other_new_tasks_not_inferred=101,externally_completed_task_count=300,batch_task_denominator=402,full_pool_planned_task_denominator=18868155,independent_readback_performed=True,raw_only_recovery=True,runner_called=False,fitter_called=False,optimization_repeated=False,risk_projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,**{k:False for k in FALSE if k!='independent_readback_performed'})


def finalize(numerical_task_id,started_sha256,raw_sha256):
    folder=OUTPUT_ROOT/numerical_task_id;output=folder/'independent_readback.json'
    require(not output.exists(),'Single immutable finalization already exists')
    value=build(numerical_task_id,started_sha256,raw_sha256);guard(value['source_hashes']);blob=codec.pretty(value)
    with output.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    guard(value['source_hashes']);require(runtime()==value['runtime'] and output.read_bytes()==blob,'Final runtime/output drift')
    require({p.name for p in folder.iterdir()}=={'started.json','raw.json','independent_readback.json'}|({'postcheck.json'} if value['saved_postcheck'] is not None else set()),'Unexpected final namespace')
    return dict(path=str(output),sha256=codec.sha(blob))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('numerical-task-id','started-sha256','raw-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(finalize(a.numerical_task_id,a.started_sha256,a.raw_sha256)))
