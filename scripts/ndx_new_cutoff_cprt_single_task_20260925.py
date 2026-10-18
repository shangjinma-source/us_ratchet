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
OUTPUT_ROOT=BASE/'new_cutoff_cprt_single_task_20260925_v1'
OLD_OUTPUT_ROOT=BASE/'new_cutoff_single_task_20260924_v1'
MULTIK_OUTPUT_ROOT=BASE/'new_cutoff_multik_single_task_20260924_v1'
BOUND={
 'queue':('new_cutoff_cprt_combination_materialization_20260925_v1/queue.json','eb4b5e3fbe4aa90797d3edfe558d38f75c957cb735209c50598789933e14d880'),
 'audit':('new_cutoff_cprt_combination_materialization_20260925_v1/independent_readback.json','e93d6d59159b11f9169c2e6af7734a54cd76061afb95c9e4dca9e1c082941409'),
 'rebinding':('new_cutoff_v3_completed_task_rebinding_20260925_v1/rebinding.json','411161ed19e8979dfa75eafda1952094c6bc0ae2f38f6e1fbcf9d6be98cde066'),
 'rebinding_audit':('new_cutoff_v3_completed_task_rebinding_20260925_v1/independent_readback.json','8295bb131a4ba6e1f2239552000f937815d007401926d160dddebdaee59b34f1'),
 'panel':('new_cutoff_conditional_panel_20260925_v3/panel.json','f577d69c27925f56a25a1e32c771eb36cdb47f9d0732dc235c767b99fdf18e0b'),
 'plan':('new_cutoff_shard_prepare_20260925_v3/plan.json','07866a10f62cc5f2abf55425248a2a9bc506690c0713a890df507c9ebbe9c56f')}
FORCED_SID='security:0000900075:217204106'

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
    queue,audit,paneldoc,plan,rebound,readback=(documents[k] for k in ('queue','audit','panel','plan','rebinding','rebinding_audit'))
    require(queue['schema']=='NEW_CUTOFF_CPRT_COMBINATION_MATERIALIZATION_V1' and audit['schema']=='NEW_CUTOFF_CPRT_COMBINATION_INDEPENDENT_READBACK_V1' and
        audit['status']=='PASSED' and audit['candidate_reference']==ref('queue'),'Hard independent CPRT queue audit required')
    require(type(audit['actual_fitter_invocation_count']) is int and audit['actual_fitter_invocation_count']==0,'Saved audit fit count')
    require(type(audit['independent_readback_count']) is int and audit['independent_readback_count']==1 and
        type(audit['new_task_count']) is int and audit['new_task_count']==102 and type(audit['new_combination_count']) is int and audit['new_combination_count']==34,'Complete saved queue readback')
    require(rebound['schema']=='NEW_CUTOFF_V3_COMPLETED_TASK_REBINDING_V1' and readback['status']=='PASSED' and readback['candidate_reference']==ref('rebinding') and
        readback['numerical_contracts_unchanged'] is True and rebound['input_references']['plan']==ref('plan'),'Audited96 old rebinding required')
    old_ids=[r['numerical_task_id'] for r in rebound['rows']]
    require(len(old_ids)==len(set(old_ids))==96 and old_ids==readback['verified_numerical_task_ids'] and task_id not in old_ids,'Previously completed96 permanently excluded')
    require(queue['reused_completed_reference']==dict(rebinding_reference=ref('rebinding'),independent_readback_reference=ref('rebinding_audit'),numerical_task_ids=old_ids),'External completed reference binding')
    require(all(type(queue[key]) is int and queue[key]==expected for key,expected in dict(new_combination_count=34,new_task_count=102,new_completed_task_count=0,
        external_completed_task_count=96,full_plan_task_denominator=4713966,actual_fitter_invocation_count=0).items()),'Exact CPRT batch denominator')
    require(queue['forced_sid']==FORCED_SID and len(queue['selections'])==len(queue['new_materializations'])==34,'34 required-SID singleton slices')
    found=[];seen=set(old_ids);locations=set();combos=set()
    specs=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
    for i,(value,selection) in enumerate(zip(queue['new_materializations'],queue['selections'])):
        k=4+i//2;local=i%2
        require(all(type(selection[key]) is int for key in ('k','forced_local_rank','full_rank')) and selection['k']==k and selection['forced_local_rank']==local,'Exact prefix selection coordinates')
        rank=selection['full_rank']
        require(all(type(value[key]) is int for key in ('k','start','stop','combination_count','materialized_task_count','completed_task_count')) and
            (value['k'],value['start'],value['stop'])==(k,rank,rank+1) and value['combination_count']==1 and value['materialized_task_count']==3 and value['completed_task_count']==0,'One unattempted singleton per selected rank')
        require(value['plan_reference']==ref('plan') and value['panel_reference']==ref('panel') and value['fitter_source_hashes']==numerical and value['shard_id']==selection['shard_id'],'Saved slice lineage')
        require(value['status']=='MATERIALIZED_NOT_ATTEMPTED' and value['fit_performed'] is False and value['full_shard_completed'] is False and value['all_plan_tasks_completed'] is False,'Saved slice remains unattempted')
        require(len(value['combinations'])==1,'Single combination required');combination=value['combinations'][0]
        require(type(combination['k']) is int and type(combination['rank']) is int and combination['k']==k and combination['rank']==rank and
            combination['prefix_security_ids']==selection['prefix_security_ids'] and FORCED_SID in combination['prefix_security_ids'],'Required CPRT and complete-pool location')
        signature=tuple(combination['prefix_security_ids']);require(len(signature)==len(set(signature))==k and signature not in combos,'Distinct complete combinations');combos.add(signature)
        require([t['numerical_identity']['weight_spec'] for t in combination['tasks']]==specs,'Three exact specs, no alias')
        for spec_index,task in enumerate(combination['tasks']):
            tid=task['numerical_task_id'];location=task['location_identity'];identity=task['numerical_identity']
            require(task['status']=='MATERIALIZED_NOT_ATTEMPTED' and type(task['wrapper_call_attempt_count']) is int and task['wrapper_call_attempt_count']==0 and
                task['fit_performed'] is False and task['anchor_alias_equivalence_verified'] is False and task['expected_fitter_previous_target_weights']=={},'Saved task pending/zero-attempt contract')
            require(tid not in seen and digest(identity)==tid and digest(location)==task['location_id'] and task['location_id'] not in locations,'Unique numerical/location identities')
            require(all(type(location[key]) is int for key in ('k','rank','spec_index')) and (location['k'],location['rank'],location['spec_index'])==(k,rank,spec_index) and
                location['plan_reference']==ref('plan') and location['shard_id']==selection['shard_id'] and location['weight_spec']==specs[spec_index] and
                identity['requested_previous_target_weights'] is None and set(identity['selected'])==set(signature),'Full selected/None-prior location binding')
            seen.add(tid);locations.add(task['location_id'])
            if tid==task_id:found.append((value,combination,task,f'/new_materializations/{i}/combinations/0/tasks/{spec_index}'))
    require(len(seen)==198 and len(found)==1,'Exactly102 new tasks and one requested ID')
    require(set(audit['verified_numerical_task_ids'])==seen-set(old_ids) and len(audit['verified_numerical_task_ids'])==102 and
        set(audit['verified_location_ids'])==locations and len(audit['verified_location_ids'])==102,'Audited complete new identity coverage')
    value,combination,task,pointer=found[0];identity=task['numerical_identity']
    require(len(numerical)==25 and numerical==value['fitter_source_hashes']==plan['plan']['fitter_source_hashes'],'Exact 25 fitter sources required')
    require(digest(identity)==task_id and digest(task['location_identity'])==task['location_id'],'Task identity checksum')
    require(identity['fitter_source_fingerprint']==digest(numerical),'Numerical source fingerprint')
    panel=codec.decode_frames(paneldoc['panel']);frame=panel['returns']
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V3' and panel['panel_content_sha256']==value['panel_content_sha256'],'Panel checksum differs')
    require(all(panel[key] is False for key in codec.PANEL_FALSE),'Inner panel permissions remain false')
    require(type(panel['conditional_security_count']) is int and panel['conditional_security_count']==21 and type(panel['conditional_issuer_count']) is int and
        panel['conditional_issuer_count']==20 and frame.shape==(126,21),'Entire21 security panel required')
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
        queue_reference=ref('queue'),queue_audit_reference=ref('audit'),rebinding_reference=ref('rebinding'),rebinding_audit_reference=ref('rebinding_audit'),task_reference=dict(ref('queue'),json_pointer=pointer))


def preflight(numerical_task_id):
    require(type(numerical_task_id) is str and len(numerical_task_id)==64 and all(c in '0123456789abcdef' for c in numerical_task_id),'Explicit canonical numerical task SHA required')
    require(not (OUTPUT_ROOT/numerical_task_id).exists(),'Attempt evidence already exists; no retry or recovery here')
    require(not (OLD_OUTPUT_ROOT/numerical_task_id).exists() and not (MULTIK_OUTPUT_ROOT/numerical_task_id).exists(),'Either old namespace evidence blocks another attempt')
    require(all(type(h) is str and len(h)==64 for p,h in BOUND.values()),'Actual queue and independent audit anchors pending')
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
    started=dict(schema='NEW_CUTOFF_CPRT_SINGLE_TASK_STARTED_V1',**{k:v for k,v in state.items() if k!='returns'},planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    started_ref=save(destination/'started.json',started)
    identity=state['task']['numerical_identity'];fitted=None;error=None
    try:
        fitted=fitter.refit_dynamic_cutoff_weights(returns=state['returns'],cutoff=identity['cutoff'],selected=deepcopy(identity['selected']),
            weight_spec=identity['weight_spec'],previous_target_weights=deepcopy(identity['requested_previous_target_weights']),**identity['parameters'])
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
    raw=dict(schema='NEW_CUTOFF_CPRT_SINGLE_TASK_RAW_V1',started_reference=started_ref,numerical_task_id=numerical_task_id,
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
    return save(destination/'postcheck.json',dict(schema='NEW_CUTOFF_CPRT_SINGLE_TASK_POSTCHECK_V1',status=status,started_reference=started_ref,raw_reference=raw_ref,
        numerical_task_id=numerical_task_id,checks=checks,error=post_error,**dict.fromkeys(FALSE,False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--numerical-task-id',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.numerical_task_id,execute=args.execute)))
