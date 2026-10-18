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
OUTPUT_ROOT=BASE/'bulk_budgeted_single_task_20261003_v1'
OLD_ROOTS=tuple(BASE/name for name in ('new_cutoff_single_task_20260924_v1','new_cutoff_multik_single_task_20260924_v1',
 'new_cutoff_cprt_single_task_20260925_v1','new_cutoff_bkng_single_task_20260925_v1',
 'new_cutoff_orly_single_task_20260925_v1','new_cutoff_ctas_single_task_20260925_v1'))
BOUND={
 'preparation':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json','03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1'),
 'publication':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/publication.json','2471685a55d652a9e732b2a6cdf218232a192f07c3ed6e9e9824f95f5cb76212'),
 'audit':('DYNAMIC_BULK_BUDGETED_SEARCH_PREPARE_INDEPENDENT_READBACK_20261003.json','ea0f3793f4a47f3cb58eb7125e5685344891eb9bc955cdcd1295866d1c801c1f'),
 'audit_report':('DYNAMIC_BULK_BUDGETED_SEARCH_PREPARE_INDEPENDENT_READBACK_20261003.md','d7e1eaeb28f14e8e711933c94ac25a1f4e5fcfaf9a76f91b59a100ed4929689d'),
 'audit_reader':('scripts/ndx_bulk_budgeted_search_prepare_independent_review_20261003.py','3d0eab3078d0ca9d2ffb30fedf1fab7dea95707d339c04f718f0583690a714d3'),
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'plan':('data/cache/research/bulk_all_k_plan_20261003_v1/plan.json','77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'),
 'rebinding':('data/cache/research/bulk_completed_task_rebinding_20261003_v1/rebinding.json','e2a3cb619a2cd46a2f7d557be91f362342676089756de6baf9ac4c9692daf29d')}
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
 'runtime_binary_closure_verified','full_transitive_source_closure_reverified')


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
    """Metadata/matrix checks only; no prepare, selection, audit or fit calls."""
    q=documents['preparation'];pub=documents['publication'];audit=documents['audit'];outer=documents['plan'];plan=outer['plan'];ctx=plan['context']
    require(q['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_V1' and q['status']=='PREPARED_NOT_ATTEMPTED','Prepared schema/status')
    require(pub['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1' and pub['status']=='PREPARED_NOT_ATTEMPTED' and pub['preparation_reference']==ref('preparation'),'Publication binding')
    exact(pub['source_hashes'],q['source_hashes'],'Publication source map')
    require(audit['status']=='PASS' and audit['preparation_sha256']==ref('preparation')['sha256'] and audit['publication_sha256']==ref('publication')['sha256'] and audit['reader_sha256']==ref('audit_reader')['sha256'],'Independent readback binding')
    for key,expected in dict(combinations=544,tasks=1632,old_completed_reference_count=504,selected_completed_intersection_count=0,new_unattempted_tasks=1632,new_fit_count=0).items():exact(audit[key],expected,'Audit count '+key)
    exact(audit['cardinalities'],list(range(4,21)),'Complete audited k')
    for key in ('point_in_time_verified','full_search_completed','old_raw_readback_repeated'):require(audit[key] is False,'Audit permissions')
    for key in ('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','all_plan_tasks_completed','economic_comparison_performed','winner_selected','old_raw_reaudited'):require(q[key] is False,'Preparation permissions')
    for role in ('panel','plan','rebinding'):exact(q['input_references'][role],ref(role),'Input ref '+role)
    exact(ctx['parameters'],PARAMETERS,'Original parameters');exact(ctx['weight_specs'],SPECS,'Three specs')
    require(ctx['previous_target_weights'] is None and len(numerical)==25 and numerical==plan['fitter_source_hashes'] and digest(numerical)==ctx['fitter_source_fingerprint'],'25 sources and None prior')
    p=documents['panel']['panel'];frame=p['returns'];universe=p['universe']
    require(documents['panel']['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and p['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','Bulk panel schema')
    for obj in (documents['panel'],p):
        for key in ('point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed'):require(obj[key] is False,'Panel permissions')
    require(frame['type']=='dataframe' and frame['index_kind']=='DatetimeIndex' and len(frame['data'])==len(frame['index'])==126 and len(frame['columns'])==77 and frame['dtypes']==['float64']*77,'Complete typed126x77')
    dates=[]
    for value in frame['index']:
        require(type(value) is str and value==value[:10]+'T00:00:00' and date.fromisoformat(value[:10]).isoformat()==value[:10],'Canonical date');dates.append(value[:10])
    require(dates==sorted(set(dates)) and dates[-1]==ctx['decision_cutoff']==p['cutoff'],'Cutoff observations')
    require(all(type(row) is list and len(row)==77 and all(type(v) is float and math.isfinite(v) and v>-1 for v in row) for row in frame['data']),'Full finite float returns')
    require(universe['type']=='dataframe' and universe['index_kind']=='RangeIndex' and universe['index']==list(range(77)) and len(universe['data'])==77 and len(set(universe['columns']))==len(universe['columns']) and len(universe['dtypes'])==len(universe['columns']) and all(len(r)==len(universe['columns']) for r in universe['data']),'Typed universe')
    rows=[dict(zip(universe['columns'],r)) for r in universe['data']];by={r['security_id']:r for r in rows}
    require(list(by)==sorted(by) and len(by)==77 and len({r['issuer_id'] for r in rows})==76 and frame['columns']==sorted({r['ticker'] for r in rows}) and all(type(r['risk_chain']) is str and r['risk_chain'] for r in rows),'Full SID ticker issuer risk coordinates')
    groups={}
    for r in rows:groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
    exact(plan['canonical_groups'],[dict(issuer_id=k,security_ids=sorted(v)) for k,v in sorted(groups.items())],'Groups')
    exact(q['complete_observed_provenance_and_missing'],p['observed_provenance_and_missing'],'Full provenance')
    require(len(q['complete_observed_provenance_and_missing'])==101,'Full101 gaps');exact(q['complete_observed_provenance_and_missing'],outer['complete_observed_provenance_and_missing'],'Plan gaps')
    require(set(q['preserved_evidence_sidecar_references'])==SIDECARS,'Seven evidence layers')
    exact(q['preserved_evidence_sidecar_references'],outer['preserved_evidence_sidecar_references'],'Plan evidence layers')
    for key,value in q['preserved_evidence_sidecar_references'].items():require(key in documents['panel'] and value==dict(ref('panel'),json_pointer='/'+key),'Sidecar pointer')
    old=documents['rebinding'];require(old['schema']=='BULK_COMPLETED_TASK_REBINDING_V1' and old['numerical_contracts_unchanged'] is True,'Old rebinding state')
    old_ids=[r['numerical_task_id'] for r in old['rows']];require(len(old_ids)==len(set(old_ids))==504,'504 permanent old IDs')
    exact(old['input_references']['plan'],ref('plan'),'Old plan binding')
    m=q['materialized'];require(m['schema']=='BULK_LAZY_TASK_MATERIALIZATION_V1' and m['status']=='BOUNDED_INPUTS_MATERIALIZED_NO_EXECUTION','Materialized schema')
    for key,value in dict(combination_count=544,materialized_task_count=1632,new_unattempted_task_count=1632,complete_saved_completed_task_count=504,selected_completed_intersection_count=0,new_wrapper_call_attempt_count=0,new_fit_count=0).items():exact(m[key],value,'Materialized count '+key)
    require(m['fit_performed'] is False and m['full_shard_completed'] is False and m['all_plan_tasks_completed'] is False,'Materialized permissions')
    exact(m['fitter_source_hashes'],numerical,'Materialized sources');exact(m['plan_reference'],ref('plan'),'Materialized plan');exact(m['panel_reference'],ref('panel'),'Materialized panel')
    require(m['panel_content_sha256']==p['panel_content_sha256'],'Panel checksum linkage')
    schedule=q['schedule'];require(schedule['status']=='PLANNED_NOT_ATTEMPTED' and schedule['materialization_allowed'] is True,'Complete saved positions')
    require(len(m['combinations'])==len(schedule['positions'])==544,'Full544 positions')
    tasks={};combobytes=[];seen=set(old_ids);locations=set();seen_ranks=set();tickloc={t:i for i,t in enumerate(frame['columns'])}
    for i,(combo,pos) in enumerate(zip(m['combinations'],schedule['positions'])):
        k=combo['k'];rank=combo['rank'];require(type(k) is int and type(rank) is int and k==4+i//32 and rank>=0 and (k,rank) not in seen_ranks,'Complete k order and unique exact rank');seen_ranks.add((k,rank))
        exact(combo['selection_position'],pos,'Saved position');require(pos['k']==k and pos['rank']==rank and pos['prefix_security_ids']==combo['prefix_security_ids'],'Position binding')
        prefix=combo['prefix_security_ids'];require(len(prefix)==len(set(prefix))==k and all(s in by for s in prefix) and prefix==sorted(prefix,key=lambda s:(by[s]['issuer_id'],s)) and len({by[s]['issuer_id'] for s in prefix})==k,'Issuer prefix')
        order=sorted(prefix);exact(combo['fitter_sorted_security_ids'],order,'Fitter sorted SID')
        selected={s:{key:by[s][key] for key in ('ticker','issuer_id','risk_chain')} for s in order};tickers=[selected[s]['ticker'] for s in order]
        matrix=dict(dates=dates,tickers=tickers,returns=[[row[tickloc[t]] for t in tickers] for row in frame['data']]);exact(combo['fit_matrix'],matrix,'Saved matrix exact');require(combo['fit_data_sha256']==digest(matrix),'Matrix hash')
        card=plan['cardinalities'][k-1];require(rank<card['planned_combination_count'],'Retained rank');start=rank//ctx['shard_size']*ctx['shard_size'];stop=min(start+ctx['shard_size'],card['planned_combination_count']);shard=digest(dict(ctx,k=k,start=start,stop=stop))
        require(len(combo['tasks'])==3,'Three tasks');combobytes.append(json.dumps({key:value for key,value in combo.items() if key!='tasks'},sort_keys=True,allow_nan=False).encode())
        for s,task in enumerate(combo['tasks']):
            identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=k,selected=selected,weight_spec=SPECS[s],parameters=PARAMETERS,requested_previous_target_weights=None,fit_data_sha256=digest(matrix),fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
            exact(task['numerical_identity'],identity,'Full numerical identity')
            location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=ref('plan'),plan_id=plan['plan_id'],shard_id=shard,order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=s,weight_spec=SPECS[s])
            exact(task['location_identity'],location,'Full location identity');tid=task['numerical_task_id'];canonical_id(tid)
            require(tid==digest(identity) and tid not in seen and task['location_id']==digest(location) and task['location_id'] not in locations,'Unique numerical/location IDs');seen.add(tid);locations.add(task['location_id'])
            require(task['status']=='MATERIALIZED_NOT_ATTEMPTED' and task['fit_performed'] is False and task['anchor_alias_equivalence_verified'] is False and task['completed_reference'] is None and task['complete_saved_rebinding_row'] is None,'Unattempted new task')
            exact(task['wrapper_call_attempt_count'],0,'Exact attempt0');exact(task['expected_fitter_previous_target_weights'],{},'None returns{}')
            tasks[tid]=(i,s,json.dumps(task,sort_keys=True,allow_nan=False).encode())
    require(len(tasks)==1632,'Full1632');exact(list(tasks),m['new_unattempted_numerical_task_ids'],'Saved ordered IDs');exact(m['selected_completed_numerical_task_ids'],[],'No old dispatch')
    for obj in (q,m):require(obj['full_plan_task_denominator']==plan['planned_canonical_task_count'],'Global denominator')
    return dict(tasks=MappingProxyType(tasks),combinations=tuple(combobytes),frame=json.dumps(dict(dates=dates,columns=frame['columns'],data=frame['data']),allow_nan=False).encode())


def load_common():
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
    started=dict(schema='BULK_BUDGETED_SINGLE_TASK_STARTED_V1',**{k:v for k,v in state.items() if k!='returns'},planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    started_ref=save(destination/'started.json',started)
    identity=state['task']['numerical_identity'];fitted=None;error=None
    try:
        fitted=fitter.refit_dynamic_cutoff_weights(returns=state['returns'],cutoff=identity['cutoff'],selected=deepcopy(identity['selected']),
            weight_spec=identity['weight_spec'],previous_target_weights=deepcopy(identity['requested_previous_target_weights']),**identity['parameters'])
    except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
    raw=dict(schema='BULK_BUDGETED_SINGLE_TASK_RAW_V1',started_reference=started_ref,numerical_task_id=numerical_task_id,
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
    return save(destination/'postcheck.json',dict(schema='BULK_BUDGETED_SINGLE_TASK_POSTCHECK_V1',status=status,started_reference=started_ref,raw_reference=raw_ref,
        numerical_task_id=numerical_task_id,checks=checks,error=post_error,**dict.fromkeys(FALSE,False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--numerical-task-id',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.numerical_task_id,execute=args.execute)))
