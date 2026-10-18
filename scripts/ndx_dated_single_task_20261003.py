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

from datetime import date
from types import MappingProxyType
OUTPUT_ROOT=BASE/'dated_single_task_20261003_v1'
OLD_ROOTS=tuple(BASE/name for name in ('new_cutoff_single_task_20260924_v1','new_cutoff_multik_single_task_20260924_v1',
 'new_cutoff_cprt_single_task_20260925_v1','new_cutoff_bkng_single_task_20260925_v1',
 'new_cutoff_orly_single_task_20260925_v1','new_cutoff_ctas_single_task_20260925_v1','bulk_budgeted_single_task_20261003_v1'))
BOUND={
 'preparation':('data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json','ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e'),
 'publication':('data/cache/research/dated_fixed_task_preparation_20261003_v1/publication.json','805fa9852e599448aa01461098f094f2d21344cc7d26053b208de342361383fe'),
 'audit':('DYNAMIC_DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_20261003.json','c5820043e0d5456faf45a8c3243f62ef481945ba16523504376b1da51c0532c7'),
 'audit_reader':('scripts/ndx_dated_fixed_task_independent_review_20261003.py','70dfac61bc90d5d9f02efacbe8aa25c73b0271e7aeefb4229ad20e63a9481e59'),
 'panel':('data/cache/research/dated_training_panel_20261003_v1/panel.json','895f31e30647e1422bcd2feab3025f8e9103c745f9d176549d59a069a30b9d96'),
 'plan':('data/cache/research/bulk_all_k_plan_20261003_v1/plan.json','77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'),
 'prior_preparation':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json','03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1')}
PINS={str(Path(fitter.__file__).resolve()):'4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75',
 str(Path(codec.__file__).resolve()):'0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
 (SOURCE,Path(fitter.__file__).resolve(),Path(codec.__file__).resolve(),Path(np.__file__).resolve(),Path(pd.__file__).resolve(),Path(scipy.__file__).resolve())}
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
 min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
SPECS=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
SIDECARS={'original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection',
 'v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection'}
_COMMON_REGISTRY={}
FALSE=('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified',
 'independent_readback_performed','full_shard_completed','all_plan_tasks_completed','retry_allowed',
 'runtime_binary_closure_verified','full_transitive_source_closure_reverified',
 'historical_pool_eligibility_verified','historical_selection_timeliness_verified','liquidity_qualification_at_training_cutoff_verified','future_independent_oos','untouched_holdout','old_task_completion_applies_to_new_cutoff')


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def ref(role):return dict(path=str(ROOT/BOUND[role][0]),sha256=BOUND[role][1])
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



def exact(left,right,message):require(digest(left)==digest(right),message)


def canonical_id(value):
    require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Explicit numerical SHA required')


def check_roots(task_id):
    canonical_id(task_id)
    require(all(not (root/task_id).exists() for root in (*OLD_ROOTS,OUTPUT_ROOT)),'Attempt evidence exists in an old or new root; no retry')


def validate_common(documents,numerical):
    """Independently reconstruct all dated matrices and identities, no fitter call."""
    q=documents['preparation'];pub=documents['publication'];audit=documents['audit'];paneldoc=documents['panel'];p=paneldoc['panel'];plan=documents['plan']['plan'];prior=documents['prior_preparation']
    require(q['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_DOCUMENT_V1','New preparation schema')
    require(pub['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_NEW_DATED_TASK_INPUTS_NOT_FITTED','New publication status')
    exact(pub['preparation_reference'],ref('preparation'),'Publication reference');exact(pub['source_hashes'],q['source_hashes'],'Publication source map')
    require(audit['status']=='PASS' and audit['preparation_sha256']==ref('preparation')['sha256'] and audit['publication_sha256']==ref('publication')['sha256'] and audit['reader_sha256']==ref('audit_reader')['sha256'],'New independent readback binding')
    require(audit['schema']=='DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_V1','New dated audit schema')
    for key,value in dict(combination_count=544,materialized_task_count=1632,new_numerical_ids=1632,new_location_ids=1632,old_id_intersection=0,original_provenance_count=101,preserved_sidecar_count=7,new_cutoff_completed_task_count=0).items():exact(audit[key],value,'Dated readback count '+key)
    for obj in (q,paneldoc,p):
        for key in ('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted'):require(obj[key] is False,'Source authority')
    require(paneldoc['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1' and p['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_V1','New typed schema')
    require(p['content_sha256']==digest({k:v for k,v in p.items() if k!='content_sha256'}),'Typed content digest')
    payload=p['fit_payload'];require(set(payload)=={'cutoff','returns','selected_by_security'} and payload['cutoff']=='2026-03-20','Strict dated fitter payload')
    exact(q['training_fit_payload'],payload,'Prepared executable payload');frame=payload['returns'];by=payload['selected_by_security']
    require(frame['type']=='DataFrame' and frame['index_type']=='DatetimeIndex' and len(frame['index'])==len(frame['data'])==126 and len(frame['columns'])==77 and frame['columns']==sorted(set(frame['columns'])) and frame['dtypes']==['float64']*77,'Typed126x77')
    dates=[]
    for value in frame['index']:
        require(type(value) is str and value==value[:10]+'T00:00:00' and date.fromisoformat(value[:10]).isoformat()==value[:10],'Exact training timestamp');dates.append(value[:10])
    require(dates==sorted(set(dates)) and dates[-1]=='2026-03-20','No evaluation row in fitting frame')
    require(all(type(row) is list and len(row)==77 and all(type(v) is float and math.isfinite(v) and v>-1 for v in row) for row in frame['data']),'Full finite matrix')
    require(type(by) is dict and len(by)==77 and list(by)==sorted(by) and len({v['issuer_id'] for v in by.values()})==76,'77SID76issuer')
    require(all(set(v)=={'ticker','issuer_id','risk_chain'} and all(type(x) is str and x for x in v.values()) for v in by.values()),'Only three selected fields')
    require(sorted(v['ticker'] for v in by.values())==frame['columns'],'SID/ticker matrix columns');require(p['training_frame_sha256']==digest(frame) and p['fit_payload_sha256']==digest(payload),'Typed frame hashes')
    for field in ('liquidity_qualification_at_training_cutoff_verified','evaluation_values_in_fit_payload','old_task_weights_reused','future_independent_oos','untouched_holdout'):require(p[field] is False,'Dated historical limits')
    exact(q['complete_observed_provenance_and_missing'],p['original_provenance_and_missing'],'All101 gaps');require(len(q['complete_observed_provenance_and_missing'])==101,'Full101 count')
    exact(q['preserved_evidence_sidecars'],p['preserved_evidence_sidecars'],'Seven original layers');require(set(q['preserved_evidence_sidecars'])==SIDECARS,'Seven layer count')
    exact(q['original_coordinate_evidence'],p['original_coordinate_evidence'],'Original MDV remains evidence only');exact(q['evaluation_references'],p['evaluation_references'],'Evaluation only referenced')
    m=q['materialized'];ctx=m['context'];require(m['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_V1' and m['status']=='PREPARED_NOT_ATTEMPTED','New dated materialization')
    require(m['content_sha256']==digest({k:v for k,v in m.items() if k!='content_sha256'}) and m['context_id']==digest(ctx),'New materialized content/context')
    for key,value in dict(combination_count=544,materialized_task_count=1632,new_unattempted_task_count=1632,new_wrapper_call_attempt_count=0,new_fit_count=0,new_cutoff_completed_task_count=0,full_plan_task_denominator=6222659648236112670,remaining_new_cutoff_uncompleted_task_count=6222659648236112670).items():exact(m[key],value,'Dated count '+key)
    for key in ('fit_performed','old_weights_reused','old_fit_results_reused','old_task_completion_applies_to_new_cutoff','evaluation_values_used_for_fit','point_in_time_verified','all_plan_tasks_completed'):require(m[key] is False,'No old completion or authority')
    exact(ctx['parameters'],PARAMETERS,'Original8 parameters');exact(ctx['weight_specs'],SPECS,'All3 specs');require(ctx['requested_previous_target_weights'] is None and ctx['cutoff']=='2026-03-20','None prior/new cutoff')
    require(len(numerical)==25 and numerical==plan['fitter_source_hashes'] and digest(numerical)==ctx['fitter_source_fingerprint'],'Frozen25 sources');exact(m['fitter_source_hashes'],numerical,'Materialized25 sources')
    for key,role in [('training_reference','panel'),('prior_preparation_reference','prior_preparation'),('original_plan_reference','plan')]:exact(ctx[key],ref(role),'New context reference')
    exact(m['original_all_k_cardinalities_preserved'],plan['cardinalities'],'All k necessary-bound domain');exact(m['original_selection_schedule_preserved'],prior['schedule'],'Late selection unchanged')
    require(m['late_pool_and_composition_selection'] is True and q['late_pool_and_composition_selection'] is True,'Late pool disclosed')
    oldcombos=prior['materialized']['combinations'];require(len(oldcombos)==len(m['combinations'])==544,'All544 fixed compositions')
    oldids={t['numerical_task_id'] for c in oldcombos for t in c['tasks']};require(len(oldids)==1632,'All1632 old dated identities')
    exact(m['prior_different_cutoff_numerical_task_ids'],[t['numerical_task_id'] for c in oldcombos for t in c['tasks']],'All old task comparison references')
    tasks={};combobytes=[];seen=set(oldids);locations=set();ranks=set();tickloc={t:i for i,t in enumerate(frame['columns'])}
    for i,(combo,old) in enumerate(zip(m['combinations'],oldcombos)):
        k=combo['k'];rank=combo['rank'];require(type(k) is int and type(rank) is int and k==4+i//32 and rank>=0 and (k,rank) not in ranks,'Exact k order/rank');ranks.add((k,rank))
        for key in ('k','rank','prefix_security_ids','fitter_sorted_security_ids','selection_position'):exact(combo[key],old[key],'Original constituent selection')
        prefix=combo['prefix_security_ids'];require(len(prefix)==len(set(prefix))==k and all(s in by for s in prefix) and prefix==sorted(prefix,key=lambda s:(by[s]['issuer_id'],s)) and len({by[s]['issuer_id'] for s in prefix})==k,'Original issuer-aware prefix')
        order=sorted(prefix);exact(combo['fitter_sorted_security_ids'],order,'Sorted SID fitter order');selected={s:deepcopy(by[s]) for s in order};tickers=[selected[s]['ticker'] for s in order]
        matrix=dict(dates=dates,tickers=tickers,returns=[[row[tickloc[t]] for t in tickers] for row in frame['data']]);exact(combo['fit_matrix'],matrix,'New train matrix');require(combo['fit_data_sha256']==digest(matrix) and combo['fit_data_sha256']!=old['fit_data_sha256'],'Different dated matrix hash')
        require(len(combo['tasks'])==len(old['tasks'])==3,'All3 original specs');combobytes.append(json.dumps({key:value for key,value in combo.items() if key!='tasks'},sort_keys=True,allow_nan=False).encode())
        for s,task in enumerate(combo['tasks']):
            identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-03-20',holding_count=k,selected=selected,weight_spec=SPECS[s],parameters=PARAMETERS,requested_previous_target_weights=None,fit_data_sha256=digest(matrix),fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
            exact(task['numerical_identity'],identity,'Full new numeric contract');tid=task['numerical_task_id'];canonical_id(tid)
            oldtask=old['tasks'][s];priorref=dict(ref('prior_preparation'),json_pointer=f'/materialized/combinations/{i}/tasks/{s}')
            exact(task['complete_prior_different_cutoff_task'],oldtask,'Complete different-cutoff task');exact(task['prior_different_cutoff_task_reference'],priorref,'Prior task pointer')
            location=dict(schema='DATED_FIXED_CONSTITUENT_TASK_LOCATION_V1',dated_context_id=m['context_id'],training_reference=ref('panel'),prior_task_reference=priorref,prior_location_id=oldtask['location_id'],original_plan_reference=ref('plan'),combination_index=i,k=k,rank=rank,spec_index=s,weight_spec=SPECS[s])
            exact(task['location_identity'],location,'New location contract');require(tid==digest(identity) and tid not in seen and task['location_id']==digest(location) and task['location_id'] not in locations,'Unique new IDs');seen.add(tid);locations.add(task['location_id'])
            require(task['status']=='MATERIALIZED_NOT_ATTEMPTED' and task['fit_performed'] is False and task['completed_reference'] is None,'Unattempted new task');exact(task['wrapper_call_attempt_count'],0,'Exact attempt0');exact(task['expected_fitter_previous_target_weights'],{},'None requested, returned{}')
            tasks[tid]=(i,s,json.dumps(task,sort_keys=True,allow_nan=False).encode())
    require(len(tasks)==1632,'Full1632 new tasks');exact(list(tasks),m['new_unattempted_numerical_task_ids'],'New saved queue order')
    return dict(tasks=MappingProxyType(tasks),combinations=tuple(combobytes),frame=json.dumps(dict(dates=dates,columns=frame['columns'],data=frame['data']),allow_nan=False).encode())


def load_common():
    require(all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Independent new preparation audit pins pending')
    sources=dict(LOADED);guard(sources);documents={}
    require(set(p.name for p in Path(ref('preparation')['path']).parent.iterdir())=={'started.json','preparation.json','publication.json'},'Preparation namespace failure or orphan')
    for role in BOUND:
        r=ref(role);raw=Path(r['path']).read_bytes();require(hashlib.sha256(raw).hexdigest()==r['sha256'],'Hard input changed: '+role);merge(sources,{r['path']:r['sha256']})
        if role not in ('audit_report','audit_reader'):
            documents[role]=codec.loads(raw);merge(sources,documents[role].get('source_hashes',{}))
    numerical=fitter._sources();merge(sources,numerical);merge(sources,codec.LOADED)
    frozen=validate_common(documents,numerical);frozen.update(sources=MappingProxyType(dict(sources)),runtime=json.dumps(runtime(),sort_keys=True).encode())
    common=dict(ordered_task_ids=list(frozen['tasks']))
    _COMMON_REGISTRY[id(common)]=(common,MappingProxyType(frozen))
    guard(sources);return common


def preflight(numerical_task_id,*,common=None):
    check_roots(numerical_task_id)
    if common is None:common=load_common()
    stored=_COMMON_REGISTRY.get(id(common));require(stored is not None and stored[0] is common,'Only load_common issued handles accepted')
    frozen=stored[1];require(common==dict(ordered_task_ids=list(frozen['tasks'])),'Common public task order changed')
    require(numerical_task_id in frozen['tasks'],'Task outside complete new queue or old completed task')
    sources=dict(frozen['sources']);guard(sources);expected_runtime=codec.loads(frozen['runtime']);require(runtime()==expected_runtime,'Runtime differs from common load')
    i,s,raw=frozen['tasks'][numerical_task_id];task=codec.loads(raw);combo=codec.loads(frozen['combinations'][i]);frame=codec.loads(frozen['frame'])
    require(digest(task['numerical_identity'])==numerical_task_id and digest(combo['fit_matrix'])==task['numerical_identity']['fit_data_sha256'],'Cached task or matrix changed')
    return dict(task=task,combination_identity=combo,returns=pd.DataFrame(frame['data'],index=pd.to_datetime(frame['dates']),columns=frame['columns']),
        preparation_reference=ref('preparation'),preparation_audit_reference=ref('audit'),task_reference=dict(ref('preparation'),json_pointer=f'/materialized/combinations/{i}/tasks/{s}'),
        input_references={key:ref(key) for key in BOUND},source_hashes=sources,runtime=expected_runtime)
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


def run(numerical_task_id,*,execute=False,common=None):
    require(type(execute) is bool,'Exact execute boolean required');state=preflight(numerical_task_id,common=common)
    if not execute:return dict(status='PREFLIGHT_ONLY',numerical_task_id=numerical_task_id,wrapper_call_attempt_count=0)
    destination=OUTPUT_ROOT/numerical_task_id
    guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed before attempt')
    check_roots(numerical_task_id)
    destination.mkdir(parents=True,exist_ok=False)
    started=dict(schema='DATED_SINGLE_TASK_STARTED_V1',**{k:v for k,v in state.items() if k!='returns'},planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    started_ref=save(destination/'started.json',started)
    identity=state['task']['numerical_identity'];fitted=None;error=None
    try:
        fitted=fitter.refit_dynamic_cutoff_weights(returns=state['returns'],cutoff=identity['cutoff'],selected=deepcopy(identity['selected']),
            weight_spec=identity['weight_spec'],previous_target_weights=deepcopy(identity['requested_previous_target_weights']),**identity['parameters'])
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
    raw=dict(schema='DATED_SINGLE_TASK_RAW_V1',started_reference=started_ref,numerical_task_id=numerical_task_id,
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
    status=('NUMERICAL_EXCEPTION_NO_RETURNED_FIT' if error and post_error==error else 'VALIDATION_FAILURE_RECORDED') if post_error else ('ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' if all(checks.values()) else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK')
    return save(destination/'postcheck.json',dict(schema='DATED_SINGLE_TASK_POSTCHECK_V1',status=status,started_reference=started_ref,raw_reference=raw_ref,
        numerical_task_id=numerical_task_id,checks=checks,error=post_error,**dict.fromkeys(FALSE,False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--numerical-task-id',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.numerical_task_id,execute=args.execute)))
