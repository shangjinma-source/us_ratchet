"""One explicitly selected conditional task; exclusive attempt, durable raw, no retry."""
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

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
OUTPUT_ROOT=BASE/'new_cutoff_multik_single_task_20260924_v1'
OLD_OUTPUT_ROOT=BASE/'new_cutoff_single_task_20260924_v1'
BOUND={
 'queue':('new_cutoff_multik_materialization_20260924_v1/queue.json','bc6d6a05b349b790a252041b677a763643e3ac6589b6f1cba4d72347a2d4b52e'),
 'audit':('new_cutoff_multik_materialization_20260924_v1/independent_readback.json','d5128c97b276b1b03d38b2d84b27e86f56a1213567e99010ac006c041f3e89ca'),
 'completed_index':('new_cutoff_completed_task_index_20260924_v1/index.json','bd104f712a006d9427384929718a49bf6b229ed1b3dc2a3fdc227a8d40a3c369'),
 'panel':('new_cutoff_conditional_panel_20260924_v2/panel.json','6dcd97bd87dfabab272dc50f9ac7d06e11410e1bf63d305596317236a348d412'),
 'plan':('new_cutoff_shard_prepare_20260924_v2/plan.json','50b3c661325bc4c2c4337cdb3d520413aa51f4dc94a869af9f94fdbd5bb0bceb')}
PINS={str(Path(fitter.__file__).resolve()):'4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75',
 str(Path(codec.__file__).resolve()):'0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
 (SOURCE,Path(fitter.__file__).resolve(),Path(codec.__file__).resolve(),Path(np.__file__).resolve(),Path(pd.__file__).resolve(),Path(scipy.__file__).resolve())}
FALSE=('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified',
 'independent_readback_performed','full_shard_completed','all_plan_tasks_completed','retry_allowed',
 'runtime_binary_closure_verified','full_transitive_source_closure_reverified')


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])
def merge(target,other):
    for path,sha in other.items():
        require(path not in target or target[path]==sha,'Source conflict');target[path]=sha


def runtime():
    return dict(python=sys.version,implementation=platform.python_implementation(),executable=str(Path(sys.executable).resolve()),platform=platform.platform(),
        numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)


def guard(sources):
    require(all(LOADED[p]==h for p,h in PINS.items()),'Loaded implementation differs')
    expected=dict(sources);merge(expected,LOADED)
    for path,sha in expected.items():require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,'Source drift: '+path)


def counts(task):
    equal=task['numerical_identity']['weight_spec']=='equal_weight'
    return dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)


def validate_inputs(documents,task_id,numerical):
    queue,audit,paneldoc,plan,index=(documents[k] for k in ('queue','audit','panel','plan','completed_index'))
    require(queue['schema']=='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1' and
        audit['schema']=='NEW_CUTOFF_MULTIK_MATERIALIZATION_INDEPENDENT_READBACK_V1' and audit['status']=='PASSED' and
        audit['candidate_reference']==ref('queue'),'Hard independent queue audit required')
    require(type(audit['independent_batch_readback_count']) is int and audit['independent_batch_readback_count']==1 and
        type(audit['actual_fitter_invocation_count']) is int and audit['actual_fitter_invocation_count']==0,'Saved operation counts differ')
    require(index['schema']=='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1' and queue['reused_completed_reference']['completed_index_reference']==ref('completed_index') and
        queue['reused_completed_reference']['completed_tasks']==index['completed_tasks'],'Exact external completed rows')
    old_ids=[row['numerical_task_id'] for row in index['completed_tasks']]
    require(len(old_ids)==len(set(old_ids))==3 and task_id not in old_ids,'Previously completed task is permanently excluded')
    require(all(type(queue[key]) is int and queue[key]==expected for key,expected in dict(new_combination_count=31,new_task_count=93,new_completed_task_count=0,
        externally_completed_task_count=3,batch_task_count=96,full_pool_planned_task_count=2355300).items()),'Exact batch denominator')
    values=queue['new_materializations'];require(len(values)==16,'Sixteen saved intervals required')
    found=[];seen=set(old_ids);locations=set();combination_count=0
    specs=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
    for slice_index,value in enumerate(values):
        k=slice_index+4;start=1 if k==4 else 0
        require(all(type(value[key]) is int for key in ('k','start','stop','combination_count','materialized_task_count','completed_task_count')) and
            (value['k'],value['start'],value['stop'])==(k,start,2) and value['combination_count']==2-start and
            value['materialized_task_count']==3*(2-start) and value['completed_task_count']==0,'Exact unattempted slice')
        require(value['plan_reference']==ref('plan') and value['panel_reference']==ref('panel') and value['fitter_source_hashes']==numerical,'Slice lineage/source differs')
        require(len(value['combinations'])==2-start,'Combination cardinality differs')
        for combo_index,combination in enumerate(value['combinations']):
            require(type(combination['k']) is int and type(combination['rank']) is int and combination['k']==k and combination['rank']==start+combo_index and
                [t['numerical_identity']['weight_spec'] for t in combination['tasks']]==specs,'Exact rank/three spec order')
            combination_count+=1
            for spec_index,task in enumerate(combination['tasks']):
                tid=task['numerical_task_id'];require(tid not in seen and digest(task['numerical_identity'])==tid and digest(task['location_identity'])==task['location_id'],'Duplicate or invalid numerical/location identity');seen.add(tid)
                location=task['location_identity']
                require(all(type(location[key]) is int for key in ('k','rank','spec_index')) and task['location_id'] not in locations and (location['k'],location['rank'],location['spec_index'])==(k,start+combo_index,spec_index) and
                    location['plan_reference']==ref('plan') and location['weight_spec']==specs[spec_index] and task['numerical_identity']['requested_previous_target_weights'] is None,'Exact unique location and first-decision prior');locations.add(task['location_id'])
                if tid==task_id:found.append((value,combination,task,f'/new_materializations/{slice_index}/combinations/{combo_index}/tasks/{spec_index}'))
    require(len(seen)==96 and combination_count==31 and len(found)==1,'Explicit unique new task required')
    value,combination,task,pointer=found[0];identity=task['numerical_identity']
    require(len(numerical)==25 and numerical==value['fitter_source_hashes']==plan['plan']['fitter_source_hashes'],'Exact 25 fitter sources required')
    require(digest(identity)==task_id and digest(task['location_identity'])==task['location_id'],'Task identity checksum')
    require(identity['fitter_source_fingerprint']==digest(numerical),'Numerical source fingerprint')
    panel=codec.decode_frames(paneldoc['panel']);frame=panel['returns']
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V2' and panel['panel_content_sha256']==value['panel_content_sha256'],'Panel checksum differs')
    groups={}
    for row in panel['universe'].to_dict('records'):groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    require([dict(issuer_id=issuer,security_ids=sorted(sids)) for issuer,sids in sorted(groups.items())]==plan['plan']['canonical_groups'],'Complete universe grouping differs')
    require(len(frame)==126 and frame.index.is_unique and frame.index.is_monotonic_increasing and
        all(d.tzinfo is None and d==d.normalize() for d in frame.index) and frame.index[-1].date().isoformat()==identity['cutoff'],'126 cutoff observations required')
    require(all(not isinstance(v,(bool,np.bool_)) and isinstance(v,(int,float,np.integer,np.floating)) and math.isfinite(float(v)) and float(v)>-1 for v in frame.to_numpy().flat),'Complete finite returns greater than -1 required')
    selected=identity['selected'];ordered=sorted(selected);rows={r['security_id']:r for r in panel['universe'].to_dict('records')}
    require(all(selected[sid]=={k:rows[sid][k] for k in ('ticker','issuer_id','risk_chain')} for sid in selected) and
        len({r['issuer_id'] for r in selected.values()})==len(selected),'Exact selected SID coordinates')
    tickers=[selected[s]['ticker'] for s in ordered]
    payload=dict(dates=[d.date().isoformat() for d in frame.index],tickers=tickers,returns=frame[tickers].to_numpy().tolist())
    require(payload==combination['fit_matrix'] and digest(payload)==identity['fit_data_sha256']==combination['fit_data_sha256'],'Original fitter matrix mismatch')
    require(identity['parameters']==plan['plan']['context']['parameters'] and identity['requested_previous_target_weights']==plan['plan']['context']['previous_target_weights'],'Full request context differs')
    prior=identity['requested_previous_target_weights']
    if prior is not None:
        require(type(prior) is dict and prior and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in prior.values()) and math.isclose(sum(map(float,prior.values())),1,abs_tol=1e-12,rel_tol=0),'Original fitter prior mass gate')
    require(identity['requested_previous_target_weights'] is None,'Hard first decision plan requires None prior')
    return dict(task=deepcopy(task),combination_identity={k:deepcopy(v) for k,v in combination.items() if k!='tasks'},returns=frame.copy(),
        queue_reference=ref('queue'),queue_audit_reference=ref('audit'),completed_index_reference=ref('completed_index'),task_reference=dict(ref('queue'),json_pointer=pointer))


def preflight(numerical_task_id):
    require(type(numerical_task_id) is str and len(numerical_task_id)==64 and all(c in '0123456789abcdef' for c in numerical_task_id),'Explicit canonical numerical task SHA required')
    require(not (OUTPUT_ROOT/numerical_task_id).exists(),'Attempt evidence already exists; no retry or recovery here')
    require(not (OLD_OUTPUT_ROOT/numerical_task_id).exists(),'Old namespace evidence blocks another attempt')
    sources=dict(LOADED);guard(sources);documents={}
    for role in BOUND:
        r=ref(role);raw=Path(r['path']).read_bytes();require(hashlib.sha256(raw).hexdigest()==r['sha256'],'Hard input changed')
        sources[r['path']]=r['sha256'];documents[role]=codec.loads(raw)
        merge(sources,documents[role].get('source_hashes',{}))
    numerical=fitter._sources();merge(sources,numerical);merge(sources,codec.LOADED)
    state=validate_inputs(documents,numerical_task_id,numerical)
    state.update(input_references={k:ref(k) for k in BOUND},source_hashes=sources,runtime=runtime())
    guard(sources);return state


def save(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable evidence readback mismatch')
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def postflight(state,fitted):
    identity=state['task']['numerical_identity'];p=identity['parameters'];selected=identity['selected']
    require(fitted['schema']=='ndx_dynamic_cutoff_refit_research_v2' and fitted['fit_data_sha256']==identity['fit_data_sha256'] and
        fitted['cutoff']==identity['cutoff'] and fitted['weight_spec']==identity['weight_spec'],'Returned numerical binding differs')
    require(fitted['source_hashes']==fitter._sources() and fitted['previous_target_weights']==(identity['requested_previous_target_weights'] or {}),'Returned source/prior differs')
    require(set(fitted['targets'])==set(selected),'Returned target set differs')
    weights=[];chains={}
    for sid in sorted(selected):
        row=fitted['targets'][sid]
        w=row['target_weight'];require(type(w) in (int,float) and math.isfinite(w) and w>=0 and row['ticker']==selected[sid]['ticker'] and row['issuer_id']==selected[sid]['issuer_id'],'Returned target invalid')
        weights.append(w);chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,0)+w
    require(math.isclose(sum(weights),1,abs_tol=1e-9,rel_tol=0),'Returned simplex invalid');ordered=sorted(weights,reverse=True)
    checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=p['max_single_weight']+1e-9,MIN_SINGLE_WEIGHT=ordered[-1]>=p['min_single_weight']-1e-9,
        SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=p['top_weight_cap']+1e-9,MINIMUM_EFFECTIVE_N=1/sum(w*w for w in weights)>=len(weights)*p['minimum_effective_n_ratio']-1e-9,
        RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=p['risk_chain_top1_cap']+1e-9)
    require(type(fitted['declared_constraint_checks']) is dict and all(type(v) is bool for v in fitted['declared_constraint_checks'].values()) and
        fitted['declared_constraint_checks']==checks and type(fitted['declared_constraints_passed']) is bool and fitted['declared_constraints_passed']==all(checks.values()),'Original risk declarations differ')
    return checks


def run(numerical_task_id,*,execute=False):
    require(type(execute) is bool,'Exact execute boolean required');state=preflight(numerical_task_id)
    if not execute:return dict(status='PREFLIGHT_ONLY',numerical_task_id=numerical_task_id,wrapper_call_attempt_count=0)
    destination=OUTPUT_ROOT/numerical_task_id
    guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed before attempt')
    destination.mkdir(parents=True,exist_ok=False)
    started=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_STARTED_V1',**{k:v for k,v in state.items() if k!='returns'},planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    started_ref=save(destination/'started.json',started)
    identity=state['task']['numerical_identity'];fitted=None;error=None
    try:
        fitted=fitter.refit_dynamic_cutoff_weights(returns=state['returns'],cutoff=identity['cutoff'],selected=deepcopy(identity['selected']),
            weight_spec=identity['weight_spec'],previous_target_weights=deepcopy(identity['requested_previous_target_weights']),**identity['parameters'])
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
    raw=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_RAW_V1',started_reference=started_ref,numerical_task_id=numerical_task_id,
        status='FIT_EXCEPTION' if error else 'FIT_RETURNED',operation_counts=counts(state['task']),fitted=fitted,error=error,
        returned_fit_count=0 if error else 1,internal_optimizer_call_count=None,
        source_hashes=state['source_hashes'],runtime=state['runtime'],**dict.fromkeys(FALSE,False))
    raw_ref=save(destination/'raw.json',raw)
    checks=None;post_error=error
    try:
        require({p.name for p in destination.iterdir()}=={'started.json','raw.json'},'Unexpected attempt evidence')
        require(hashlib.sha256((destination/'started.json').read_bytes()).hexdigest()==started_ref['sha256'],'Started drift')
        guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed during attempt')
        if error is None:checks=postflight(state,fitted)
        guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed during postflight')
        require({p.name for p in destination.iterdir()}=={'started.json','raw.json'},'Unexpected postflight evidence')
        for evidence in (started_ref,raw_ref):
            require(hashlib.sha256(Path(evidence['path']).read_bytes()).hexdigest()==evidence['sha256'],'Attempt evidence changed during postflight')
    except Exception as exc:post_error=dict(type=type(exc).__name__,message=str(exc))
    status='NUMERICAL_OR_VALIDATION_FAILURE' if post_error else ('ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' if all(checks.values()) else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK')
    return save(destination/'postcheck.json',dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_POSTCHECK_V1',status=status,started_reference=started_ref,raw_reference=raw_ref,
        numerical_task_id=numerical_task_id,checks=checks,error=post_error,**dict.fromkeys(FALSE,False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--numerical-task-id',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.numerical_task_id,execute=args.execute)))
