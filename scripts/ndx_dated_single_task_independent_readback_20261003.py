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
RUNNER=ROOT/'scripts/ndx_dated_single_task_20261003.py';RUNNER_SHA='2561779479a7a2373204540d85f86095d6096a53ff899058929035d9a1703fcf';PURE_SHA='f4ac1f2ced3d73601bdf43850951063fc347401cb301c928e48c589ba5f8a72a'
OUTPUT_ROOT=BASE/'dated_single_task_20261003_v1'
BOUND={'preparation': ('data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json', 'ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e'), 'publication': ('data/cache/research/dated_fixed_task_preparation_20261003_v1/publication.json', '805fa9852e599448aa01461098f094f2d21344cc7d26053b208de342361383fe'), 'audit': ('DYNAMIC_DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_20261003.json', 'c5820043e0d5456faf45a8c3243f62ef481945ba16523504376b1da51c0532c7'), 'audit_reader': ('scripts/ndx_dated_fixed_task_independent_review_20261003.py', '70dfac61bc90d5d9f02efacbe8aa25c73b0271e7aeefb4229ad20e63a9481e59'), 'panel': ('data/cache/research/dated_training_panel_20261003_v1/panel.json', '895f31e30647e1422bcd2feab3025f8e9103c745f9d176549d59a069a30b9d96'), 'plan': ('data/cache/research/bulk_all_k_plan_20261003_v1/plan.json', '77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'), 'prior_preparation': ('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json', '03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1')}
FALSE=('promotion_allowed', 'execution_authorized', 'legal_training_input_admitted', 'point_in_time_verified', 'independent_readback_performed', 'full_shard_completed', 'all_plan_tasks_completed', 'retry_allowed', 'runtime_binary_closure_verified', 'full_transitive_source_closure_reverified', 'historical_pool_eligibility_verified', 'historical_selection_timeliness_verified', 'liquidity_qualification_at_training_cutoff_verified', 'future_independent_oos', 'untouched_holdout', 'old_task_completion_applies_to_new_cutoff')
LIBRARIES=(np,pd,scipy)
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(pure.__file__).resolve(),Path(codec.__file__).resolve(),*[Path(m.__file__).resolve() for m in LIBRARIES])}


def require(ok,message):
    if not ok:raise ValueError(message)


def ref(role):return dict(path=str(ROOT/BOUND[role][0]),sha256=BOUND[role][1])
def merge(left,right):
    for p,h in right.items():require(p not in left or left[p]==h,'Source conflict');left[p]=h


def runtime():return dict(python=sys.version,implementation=platform.python_implementation(),executable=str(Path(sys.executable).resolve()),platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)


def counts(task):
    equal=task['numerical_identity']['weight_spec']=='equal_weight'
    return dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)


def inspect_envelopes(*,started,raw,state,started_reference,numerical_sources):
    expected=dict(schema='DATED_SINGLE_TASK_STARTED_V1',**state,planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    require(pure.exact(started,expected),'Started must equal hard-authorized task/full matrix/runtime/source contract')
    require(set(raw)=={'schema','started_reference','numerical_task_id','status','operation_counts','fitted','error','returned_fit_count','internal_optimizer_call_count','source_hashes','runtime'}|set(FALSE),'Raw schema')
    require(raw['schema']=='DATED_SINGLE_TASK_RAW_V1' and raw['started_reference']==started_reference and raw['numerical_task_id']==state['task']['numerical_task_id'],'Raw task/started binding')
    require(pure.exact(raw['operation_counts'],counts(state['task'])) and raw['internal_optimizer_call_count'] is None,'Exact single wrapper request, internal calls unknown')
    require(raw['source_hashes']==state['source_hashes'] and raw['runtime']==state['runtime'] and all(raw[k] is False for k in FALSE),'Raw source/runtime/authority')
    require(type(raw['returned_fit_count']) is int,'Returned fit exact count')
    if raw['status']=='FIT_EXCEPTION':
        require(raw['fitted'] is None and raw['returned_fit_count']==0 and type(raw['error']) is dict and set(raw['error'])=={'type','message'} and type(raw['error']['type']) is str and raw['error']['type'] and type(raw['error']['message']) is str,'Exception preserves no returned fit')
        return dict(status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',error=deepcopy(raw['error']),checks=None,numerical_failure_is_economic_infeasibility=False,optimizer_call_count_unknown=True,fitter_called=False,promotion_allowed=False)
    require(raw['status']=='FIT_RETURNED' and raw['error'] is None and raw['returned_fit_count']==1,'Returned result status')
    return pure.inspect_fitted(task=state['task'],combination=state['combination_identity'],fitted=raw['fitted'],numerical_sources=numerical_sources)



from datetime import date
from types import MappingProxyType
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
SPECS=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
FITTER=ROOT/'backtest/ndx_dynamic_cutoff_refit_v2_research.py'
FITTER_SHA='4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75'
_COMMON={}
def exact(a,b,message):require(pure.exact(a,b),message)
def count(v,n,message):require(type(v) is int and v==n,message)
def canonical(v):require(type(v) is str and len(v)==64 and set(v)<=set('0123456789abcdef'),'Explicit SHA required')
def digest(v):return pure.digest(v)
def guard(sources):
    require(RUNNER_SHA is not None,'Runner pin pending')
    require(LOADED[str(Path(pure.__file__).resolve())]==PURE_SHA,'Pure loaded version')
    require(LOADED[str(Path(codec.__file__).resolve())]=='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9','Frozen codec loaded version')
    expected=dict(sources);merge(expected,LOADED);merge(expected,codec.LOADED);merge(expected,{str(RUNNER):RUNNER_SHA,str(FITTER):FITTER_SHA})
    for path,h in expected.items():require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,'Source drift: '+path)

def validate_documents(docs):
    q=docs['preparation'];m=q['materialized'];p=docs['panel']['panel'];plan=docs['plan']['plan'];prior=docs['prior_preparation'];pub=docs['publication'];audit=docs['audit']
    require(q['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_DOCUMENT_V1' and m['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_V1' and m['status']=='PREPARED_NOT_ATTEMPTED','New dated preparation')
    require(pub['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_NEW_DATED_TASK_INPUTS_NOT_FITTED','New dated publication')
    exact(pub['preparation_reference'],ref('preparation'),'Publication payload');exact(pub['source_hashes'],q['source_hashes'],'Publication sources')
    require(audit['schema']=='DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['preparation_sha256']==ref('preparation')['sha256'] and audit['publication_sha256']==ref('publication')['sha256'] and audit['reader_sha256']==ref('audit_reader')['sha256'],'External independent audit')
    for key,n in dict(combination_count=544,materialized_task_count=1632,new_numerical_ids=1632,new_location_ids=1632,old_id_intersection=0,original_provenance_count=101,preserved_sidecar_count=7,new_cutoff_completed_task_count=0).items():count(audit[key],n,'Audit full scope')
    for obj in (q,m,docs['panel'],p):
        for key in ('fit_performed','point_in_time_verified','legal_training_input_admitted','execution_authorized','promotion_allowed'):require(obj[key] is False,'No authority')
    require(docs['panel']['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1' and p['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_V1','New typed schema')
    require(p['content_sha256']==digest({k:v for k,v in p.items() if k!='content_sha256'}) and m['content_sha256']==digest({k:v for k,v in m.items() if k!='content_sha256'}),'Saved content checksums')
    for key in ('evaluation_values_in_fit_payload','old_task_weights_reused','liquidity_qualification_at_training_cutoff_verified','future_independent_oos','untouched_holdout'):require(p[key] is False,'Late evidence is not training qualification')
    payload=p['fit_payload'];exact(q['training_fit_payload'],payload,'Full executable payload');require(set(payload)=={'cutoff','returns','selected_by_security'} and payload['cutoff']=='2026-03-20','Dated input only')
    frame=payload['returns'];mapping=payload['selected_by_security'];require(frame['type']=='DataFrame' and frame['index_type']=='DatetimeIndex' and frame['dtypes']==['float64']*77,'Typed float frame')
    count(len(frame['data']),126,'126 rows');count(len(frame['columns']),77,'77columns');require(frame['columns']==sorted(set(frame['columns'])),'Unique ticker columns')
    dates=[v[:10] for v in frame['index']];require(len(dates)==126 and dates==sorted(set(dates)) and dates[-1]=='2026-03-20','126 cutoff dates')
    for stamp in frame['index']:require(type(stamp) is str and stamp==stamp[:10]+'T00:00:00' and date.fromisoformat(stamp[:10]).isoformat()==stamp[:10],'Exact timestamp')
    require(all(type(row) is list and len(row)==77 and all(type(v) is float and math.isfinite(v) and v>-1 for v in row) for row in frame['data']),'All cells finite float >-1')
    require(type(mapping) is dict and len(mapping)==77 and list(mapping)==sorted(mapping),'Canonical SID mapping')
    for v in mapping.values():require(set(v)=={'ticker','issuer_id','risk_chain'} and all(type(x) is str and x for x in v.values()),'Three selected fields')
    require(sorted(x['ticker'] for x in mapping.values())==frame['columns'] and len({x['issuer_id'] for x in mapping.values()})==76,'77SID76issuer')
    require(p['training_frame_sha256']==digest(frame) and p['fit_payload_sha256']==digest(payload),'Training hashes')
    for outer,inner in [('complete_observed_provenance_and_missing','original_provenance_and_missing'),('preserved_evidence_sidecars','preserved_evidence_sidecars'),('original_coordinate_evidence','original_coordinate_evidence'),('evaluation_references','evaluation_references')]:exact(q[outer],p[inner],'Full evidence preservation')
    require(len(q['complete_observed_provenance_and_missing'])==101 and set(q['preserved_evidence_sidecars'])==set(SIDECARS),'101 and all7 layers')
    ctx=m['context'];require(m['context_id']==digest(ctx),'Context hash');exact(ctx['parameters'],PARAMETERS,'Original8 parameters');exact(ctx['weight_specs'],SPECS,'Three specs');require(ctx['cutoff']=='2026-03-20' and ctx['requested_previous_target_weights'] is None,'Dated None prior')
    for key,role in [('training_reference','panel'),('prior_preparation_reference','prior_preparation'),('original_plan_reference','plan')]:exact(ctx[key],ref(role),'Context source binding')
    numerical=plan['fitter_source_hashes'];require(len(numerical)==25 and digest(numerical)==ctx['fitter_source_fingerprint'],'25source fingerprint');exact(m['fitter_source_hashes'],numerical,'25source map')
    for key,n in dict(combination_count=544,materialized_task_count=1632,new_unattempted_task_count=1632,new_wrapper_call_attempt_count=0,new_fit_count=0,new_cutoff_completed_task_count=0,full_plan_task_denominator=6222659648236112670,remaining_new_cutoff_uncompleted_task_count=6222659648236112670).items():count(m[key],n,'Full dated task denominator')
    for key in ('old_fit_results_reused','old_weights_reused','old_task_completion_applies_to_new_cutoff','evaluation_values_used_for_fit','historical_pool_eligibility_verified','historical_selection_timeliness_verified','all_plan_tasks_completed','future_independent_oos','untouched_holdout'):require(m[key] is False,'No past completion/qualification')
    require(m['late_pool_and_composition_selection'] is True and q['late_pool_and_composition_selection'] is True,'Late composition disclosure')
    exact(m['original_all_k_cardinalities_preserved'],plan['cardinalities'],'Full all-k domain');exact(m['original_selection_schedule_preserved'],prior['schedule'],'Late fixed selection')
    old=prior['materialized']['combinations'];require(len(old)==len(m['combinations'])==544,'All544')
    oldids=[t['numerical_task_id'] for c in old for t in c['tasks']];require(len(set(oldids))==1632,'Old unique task IDs');exact(m['prior_different_cutoff_numerical_task_ids'],oldids,'Old task list')
    index={};combos=[];seen=set(oldids);locations=set();positions=set();columns={t:i for i,t in enumerate(frame['columns'])}
    for ci,(combo,previous) in enumerate(zip(m['combinations'],old)):
        k=combo['k'];rank=combo['rank'];require(type(k) is int and k==4+ci//32 and type(rank) is int and rank>=0 and (k,rank) not in positions,'Cardinality/rank');positions.add((k,rank))
        for key in ('k','rank','prefix_security_ids','fitter_sorted_security_ids','selection_position'):exact(combo[key],previous[key],'Fixed composition')
        prefix=combo['prefix_security_ids'];require(type(prefix) is list and len(prefix)==len(set(prefix))==k and set(prefix)<=set(mapping),'Complete selected SIDs')
        require(prefix==sorted(prefix,key=lambda s:(mapping[s]['issuer_id'],s)) and len({mapping[s]['issuer_id'] for s in prefix})==k,'Issuer-aware prefix')
        order=sorted(prefix);exact(combo['fitter_sorted_security_ids'],order,'Fitter SID order');chosen={s:deepcopy(mapping[s]) for s in order};tickers=[chosen[s]['ticker'] for s in order]
        matrix=dict(dates=dates,tickers=tickers,returns=[[row[columns[t]] for t in tickers] for row in frame['data']]);exact(combo['fit_matrix'],matrix,'Actual training matrix');mh=digest(matrix);require(combo['fit_data_sha256']==mh and mh!=previous['fit_data_sha256'],'New training hash')
        require(len(combo['tasks'])==len(previous['tasks'])==3,'Three tasks');combos.append(pure.encoded({k:v for k,v in combo.items() if k!='tasks'}))
        for si,(task,oldtask) in enumerate(zip(combo['tasks'],previous['tasks'])):
            identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-03-20',holding_count=k,selected=chosen,weight_spec=SPECS[si],parameters=PARAMETERS,requested_previous_target_weights=None,fit_data_sha256=mh,fitter_source_fingerprint=digest(numerical))
            exact(task['numerical_identity'],identity,'Full numeric contract');tid=task['numerical_task_id'];canonical(tid);require(tid==digest(identity) and tid not in seen,'No repeated or old numeric IDs');seen.add(tid)
            ptr=dict(ref('prior_preparation'),json_pointer=f'/materialized/combinations/{ci}/tasks/{si}');exact(task['complete_prior_different_cutoff_task'],oldtask,'Full old task preserved');exact(task['prior_different_cutoff_task_reference'],ptr,'Old task reference')
            loc=dict(schema='DATED_FIXED_CONSTITUENT_TASK_LOCATION_V1',dated_context_id=m['context_id'],training_reference=ref('panel'),prior_task_reference=ptr,prior_location_id=oldtask['location_id'],original_plan_reference=ref('plan'),combination_index=ci,k=k,rank=rank,spec_index=si,weight_spec=SPECS[si])
            exact(task['location_identity'],loc,'Full new location');require(task['location_id']==digest(loc) and task['location_id'] not in locations,'Unique location');locations.add(task['location_id'])
            require(task['status']=='MATERIALIZED_NOT_ATTEMPTED' and task['fit_performed'] is False and task['completed_reference'] is None,'No inherited completion');count(task['wrapper_call_attempt_count'],0,'No prior attempt');exact(task['expected_fitter_previous_target_weights'],{},'RequestedNone fitter{}')
            index[tid]=(ci,si,pure.encoded(task))
    count(len(index),1632,'Full task count');exact(list(index),m['new_unattempted_numerical_task_ids'],'Ordered task queue')
    return index,tuple(combos),dict(numerical)

def load_common():
    guard({});docs={};sources={}
    require({p.name for p in Path(ref('preparation')['path']).parent.iterdir()}=={'started.json','preparation.json','publication.json'},'Sealed preparation namespace')
    for role in BOUND:
        r=ref(role);blob=Path(r['path']).read_bytes();require(codec.sha(blob)==r['sha256'],'Hard parent SHA');merge(sources,{r['path']:r['sha256']})
        if role not in ('audit_report','audit_reader'):docs[role]=codec.loads(blob);merge(sources,docs[role].get('source_hashes',{}))
    tasks,combos,numerical=validate_documents(docs)
    runner_sources={str(RUNNER):RUNNER_SHA,str(FITTER):FITTER_SHA,str(Path(codec.__file__).resolve()):LOADED[str(Path(codec.__file__).resolve())]}
    for module in LIBRARIES:runner_sources[str(Path(module.__file__).resolve())]=LOADED[str(Path(module.__file__).resolve())]
    merge(runner_sources,sources);merge(runner_sources,numerical);merge(runner_sources,codec.LOADED);guard(runner_sources)
    handle=dict(ordered_task_ids=list(tasks))
    _COMMON[id(handle)]=(handle,MappingProxyType(dict(tasks=MappingProxyType(tasks),combos=combos,numerical=MappingProxyType(numerical),sources=MappingProxyType(runner_sources),runtime=pure.encoded(runtime()),denominator=docs['plan']['plan']['planned_canonical_task_count'])))
    return handle

def expected_state(task_id,common):
    canonical(task_id);entry=_COMMON.get(id(common));require(entry is not None and entry[0] is common,'Only load_common issued handle accepted');cache=entry[1]
    exact(common,dict(ordered_task_ids=list(cache['tasks'])),'Common public metadata modified');require(task_id in cache['tasks'],'Unknown or old completed task')
    sources=dict(cache['sources']);guard(sources);rt=codec.loads(cache['runtime']);require(runtime()==rt,'Runtime drift')
    i,s,t=cache['tasks'][task_id];task=codec.loads(t);combo=codec.loads(cache['combos'][i]);require(digest(task['numerical_identity'])==task_id and digest(combo['fit_matrix'])==task['numerical_identity']['fit_data_sha256'],'Cached identity/matrix')
    state=dict(task=task,combination_identity=combo,input_references={key:ref(key) for key in BOUND},preparation_reference=ref('preparation'),preparation_audit_reference=ref('audit'),task_reference=dict(ref('preparation'),json_pointer=f'/materialized/combinations/{i}/tasks/{s}'),source_hashes=sources,runtime=rt)
    return state,cache

def inspect_postcheck(post,started_ref,raw_ref,task_id,detail):
    require(set(post)=={'schema','status','started_reference','raw_reference','numerical_task_id','checks','error'}|set(FALSE),'Postcheck exact fields')
    require(post['schema']=='DATED_SINGLE_TASK_POSTCHECK_V1' and post['started_reference']==started_ref and post['raw_reference']==raw_ref and post['numerical_task_id']==task_id and all(post[k] is False for k in FALSE),'Postcheck binding/permission')
    if post['status']=='VALIDATION_FAILURE_RECORDED':
        require(type(post['error']) is dict and set(post['error'])=={'type','message'} and all(type(v) is str for v in post['error'].values()),'Saved validation failure')
        if post['checks'] is not None:exact(post['checks'],detail.get('checks'),'Saved risk checks')
        return 'VALIDATION_FAILURE'
    if detail['status']=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT':
        require(post['status']==detail['status'] and post['checks'] is None,'Exception classification');exact(post['error'],detail['error'],'Original numerical exception preserved');return 'NUMERICAL_EXCEPTION'
    passed=detail['status']=='FITTED_FIVE_RISKS_PASSED';require(detail['status'] in ('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED'),'Known numerical state')
    require(post['status']==('ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' if passed else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK') and post['error'] is None,'Risk outcome distinct from exception');exact(post['checks'],detail['checks'],'Original risk checks')
    return 'RISK_PASSED' if passed else 'RISK_FAILED'

def readback(task_id,postcheck_reference,common=None):
    canonical(task_id);folder=OUTPUT_ROOT/task_id;output=folder/'independent_readback.json'
    require({p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json'},'Only complete unfinalized attempt; no retry')
    require(type(postcheck_reference) is dict and set(postcheck_reference)=={'path','sha256'} and postcheck_reference['path']==str(folder/'postcheck.json'),'External postcheck path');canonical(postcheck_reference['sha256'])
    if common is None:common=load_common()
    state,cache=expected_state(task_id,common);sources=dict(state['source_hashes']);merge(sources,LOADED)
    def consume(r,name):
        require(set(r)=={'path','sha256'} and r['path']==str(folder/(name+'.json')),'Exact attempt evidence path');canonical(r['sha256']);blob=Path(r['path']).read_bytes();require(codec.sha(blob)==r['sha256'],'External evidence bytes');merge(sources,{r['path']:r['sha256']});return codec.loads(blob)
    post=consume(postcheck_reference,'postcheck');started_ref=post['started_reference'];raw_ref=post['raw_reference'];started=consume(started_ref,'started');raw=consume(raw_ref,'raw')
    detail=inspect_envelopes(started=started,raw=raw,state=state,started_reference=started_ref,numerical_sources=dict(cache['numerical']))
    outcome=inspect_postcheck(post,started_ref,raw_ref,task_id,detail)
    value=dict(schema='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1',status='PASSED',attempt_outcome=outcome,numerical_task_id=task_id,started_reference=deepcopy(started_ref),raw_reference=deepcopy(raw_ref),postcheck_reference=deepcopy(postcheck_reference),detail=detail,saved_postcheck=post,source_hashes=sources,runtime=state['runtime'],input_references=state['input_references'],task_reference=state['task_reference'],materialized_task_denominator=1632,other_new_tasks_not_inferred=1631,externally_completed_task_count=0,prior_different_cutoff_task_count=1632,late_pool_and_composition_selection=True,full_plan_task_denominator=cache['denominator'],independent_readback_performed=True,runner_called=False,fitter_called=False,optimization_repeated=False,risk_projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,**{k:False for k in FALSE if k!='independent_readback_performed'})
    guard(sources);require(runtime()==state['runtime'],'Runtime drift before publication');blob=codec.pretty(value)
    with output.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(sources);require(output.read_bytes()==blob and runtime()==state['runtime'],'Final output/runtime drift')
    require({p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json','independent_readback.json'},'Final namespace')
    return dict(path=str(output),sha256=codec.sha(blob))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--numerical-task-id',required=True);parser.add_argument('--postcheck-sha256',required=True);a=parser.parse_args()
    print(json.dumps(readback(a.numerical_task_id,dict(path=str(OUTPUT_ROOT/a.numerical_task_id/'postcheck.json'),sha256=a.postcheck_sha256))))
