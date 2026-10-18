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
RUNNER=ROOT/'scripts/ndx_bulk_budgeted_single_task_20261003.py';RUNNER_SHA='8f3fdfc587a9ee7e168c22f6eddf33e66fdfb249f342fcb69cb9fbaba4485c46';PURE_SHA='f4ac1f2ced3d73601bdf43850951063fc347401cb301c928e48c589ba5f8a72a'
OUTPUT_ROOT=BASE/'bulk_budgeted_single_task_20261003_v1'
BOUND={
 'preparation':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json','03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1'),
 'publication':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/publication.json','2471685a55d652a9e732b2a6cdf218232a192f07c3ed6e9e9824f95f5cb76212'),
 'audit':('DYNAMIC_BULK_BUDGETED_SEARCH_PREPARE_INDEPENDENT_READBACK_20261003.json','ea0f3793f4a47f3cb58eb7125e5685344891eb9bc955cdcd1295866d1c801c1f'),
 'audit_report':('DYNAMIC_BULK_BUDGETED_SEARCH_PREPARE_INDEPENDENT_READBACK_20261003.md','d7e1eaeb28f14e8e711933c94ac25a1f4e5fcfaf9a76f91b59a100ed4929689d'),
 'audit_reader':('scripts/ndx_bulk_budgeted_search_prepare_independent_review_20261003.py','3d0eab3078d0ca9d2ffb30fedf1fab7dea95707d339c04f718f0583690a714d3'),
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'plan':('data/cache/research/bulk_all_k_plan_20261003_v1/plan.json','77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'),
 'rebinding':('data/cache/research/bulk_completed_task_rebinding_20261003_v1/rebinding.json','e2a3cb619a2cd46a2f7d557be91f362342676089756de6baf9ac4c9692daf29d')}
FALSE=('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified','independent_readback_performed','full_shard_completed','all_plan_tasks_completed','retry_allowed','runtime_binary_closure_verified','full_transitive_source_closure_reverified')
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
    expected=dict(schema='BULK_BUDGETED_SINGLE_TASK_STARTED_V1',**state,planned_operation_counts=counts(state['task']),**dict.fromkeys(FALSE,False))
    require(pure.exact(started,expected),'Started must equal hard-authorized task/full matrix/runtime/source contract')
    require(set(raw)=={'schema','started_reference','numerical_task_id','status','operation_counts','fitted','error','returned_fit_count','internal_optimizer_call_count','source_hashes','runtime'}|set(FALSE),'Raw schema')
    require(raw['schema']=='BULK_BUDGETED_SINGLE_TASK_RAW_V1' and raw['started_reference']==started_reference and raw['numerical_task_id']==state['task']['numerical_task_id'],'Raw task/started binding')
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
    """Check saved metadata and numerical inputs, never regenerate ranks or fits."""
    q=docs['preparation'];m=q['materialized'];outer=docs['plan'];plan=outer['plan'];ctx=plan['context'];pdoc=docs['panel'];panel=pdoc['panel'];audit=docs['audit'];pub=docs['publication']
    require(q['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_V1' and q['status']=='PREPARED_NOT_ATTEMPTED','Preparation status')
    require(pub['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1' and pub['status']=='PREPARED_NOT_ATTEMPTED' and pub['preparation_reference']==ref('preparation'),'Publication binding')
    exact(pub['source_hashes'],q['source_hashes'],'Publication source binding')
    require(audit['status']=='PASS' and audit['preparation_sha256']==ref('preparation')['sha256'] and audit['publication_sha256']==ref('publication')['sha256'] and audit['reader_sha256']==ref('audit_reader')['sha256'],'Saved independent audit reference')
    for key,n in [('combinations',544),('tasks',1632),('old_completed_reference_count',504),('selected_completed_intersection_count',0),('new_unattempted_tasks',1632),('new_fit_count',0)]:count(audit[key],n,'Audited scope')
    exact(audit['cardinalities'],list(range(4,21)),'Audited complete cardinalities')
    require(all(audit[k] is False for k in ('point_in_time_verified','full_search_completed','old_raw_readback_repeated')),'Audit authority')
    for obj in (q,m,pdoc,panel,outer):
        for key in ('promotion_allowed','point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed'):require(obj[key] is False,'Conditional permission boundary')
    for key,n in [('combination_count',544),('materialized_task_count',1632),('complete_saved_completed_task_count',504),('selected_completed_intersection_count',0),('new_unattempted_task_count',1632),('new_fit_count',0),('new_wrapper_call_attempt_count',0)]:count(m[key],n,'Materialization count')
    exact(ctx['parameters'],PARAMETERS,'Original eight parameters');exact(ctx['weight_specs'],SPECS,'Original specification order');require(ctx['previous_target_weights'] is None,'First cutoff prior is None')
    numerical=plan['fitter_source_hashes'];require(len(numerical)==25 and digest(numerical)==ctx['fitter_source_fingerprint'],'25-source fingerprint')
    exact(m['fitter_source_hashes'],numerical,'Materialized fitter sources')
    exact(q['complete_observed_provenance_and_missing'],outer['complete_observed_provenance_and_missing'],'Full missing provenance')
    exact(q['complete_observed_provenance_and_missing'],panel['observed_provenance_and_missing'],'Panel missing provenance')
    require(pdoc['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and panel['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1' and m['schema']=='BULK_LAZY_TASK_MATERIALIZATION_V1' and m['status']=='BOUNDED_INPUTS_MATERIALIZED_NO_EXECUTION','Saved schemas')
    for role in ('panel','plan','rebinding'):exact(q['input_references'][role],ref(role),'Preparation parent reference')
    exact(ctx['panel_reference'],ref('panel'),'Plan panel reference')
    exact(m['panel_reference'],ref('panel'),'Materialized panel reference');exact(m['plan_reference'],ref('plan'),'Materialized plan reference')
    require(m['panel_content_sha256']==panel['panel_content_sha256'],'Inner panel checksum binding')
    exact(q['preserved_evidence_sidecar_references'],outer['preserved_evidence_sidecar_references'],'Full sidecar references')
    require(len(panel['observed_provenance_and_missing'])==101,'101 denominator')
    require(set(outer['preserved_evidence_sidecar_references'])==set(SIDECARS),'Seven named sidecars')
    for name,reference in outer['preserved_evidence_sidecar_references'].items():
        require(reference['path']==ref('panel')['path'] and reference['sha256']==ref('panel')['sha256'] and reference['json_pointer']=='/'+name,'Sidecar pointer')
        require(name in pdoc,'All seven evidence layers')
    require(len(outer['preserved_evidence_sidecar_references'])==7,'Seven sidecars')
    frame=panel['returns'];universe=panel['universe']
    require(frame['type']=='dataframe' and frame['index_kind']=='DatetimeIndex' and universe['type']=='dataframe' and universe['index_kind']=='RangeIndex' and universe['index']==list(range(77)),'Typed frame axes')
    require(len(universe['columns'])==len(set(universe['columns']))==len(universe['dtypes']) and all(len(r)==len(universe['columns']) for r in universe['data']),'Complete universe dimensions')
    require(frame['dtypes']==['float64']*77 and len(frame['columns'])==len(set(frame['columns']))==77,'77 columns')
    dates=[]
    for value in frame['index']:
        require(type(value) is str and value==value[:10]+'T00:00:00' and date.fromisoformat(value[:10]).isoformat()==value[:10],'Canonical complete date');dates.append(value[:10])
    require(len(dates)==126 and dates==sorted(set(dates)) and dates[-1]==ctx['decision_cutoff'],'126 cutoff dates')
    require(len(frame['data'])==126 and all(len(row)==77 and all(type(v) is float and math.isfinite(v) and v>-1 for v in row) for row in frame['data']),'Complete finite matrix')
    rows=[dict(zip(universe['columns'],r)) for r in universe['data']];by={r['security_id']:r for r in rows}
    require(len(rows)==len(by)==77 and len({r['issuer_id'] for r in rows})==76 and sorted(r['ticker'] for r in rows)==frame['columns'],'Full SID/ticker/issuer universe')
    groups={}
    for row in rows:require(type(row['risk_chain']) is str and bool(row['risk_chain']),'Risk labels');groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    exact(plan['canonical_groups'],[dict(issuer_id=k,security_ids=sorted(v)) for k,v in sorted(groups.items())],'Canonical groups from full universe')
    prefix_order={sid:(i,j) for i,g in enumerate(plan['canonical_groups']) for j,sid in enumerate(g['security_ids'])}
    require(q['schedule']['status']=='PLANNED_NOT_ATTEMPTED' and q['schedule']['materialization_allowed'] is True and len(q['schedule']['positions'])==544,'Complete saved schedule')
    old=docs['rebinding'];oldids=[r['numerical_task_id'] for r in old['rows']];require(len(oldids)==len(set(oldids))==504,'Old504 unique')
    require(m['full_plan_task_denominator']==q['full_plan_task_denominator']==plan['planned_canonical_task_count'] and m['remaining_full_plan_uncompleted_count']==plan['planned_canonical_task_count']-504,'Full denominator remains')
    index={};combos=[];locations=set();seen=set();columns={v:i for i,v in enumerate(frame['columns'])}
    require(len(m['combinations'])==544,'Complete bounded combinations')
    for ci,combo in enumerate(m['combinations']):
        k=combo['k'];rank=combo['rank']
        require(type(k) is int and k==4+ci//32,'Thirty-two combinations in every retained k')
        exact(combo['selection_position'],q['schedule']['positions'][ci],'Saved selection position')
        for key in ('k','rank','prefix_security_ids'):exact(combo['selection_position'][key],combo[key],'Position fields match combination')
        require(combo['prefix_security_ids']==sorted(combo['prefix_security_ids'],key=prefix_order.__getitem__),'Canonical issuer-prefix order')
        require(type(k) is int and 4<=k<=20 and type(rank) is int and rank>=0 and (k,rank) not in seen,'Exact unique position');seen.add((k,rank))
        order=sorted(combo['prefix_security_ids']);require(len(order)==len(set(order))==k and all(s in by for s in order) and len({by[s]['issuer_id'] for s in order})==k,'Unique known issuer selection')
        exact(order,combo['fitter_sorted_security_ids'],'Sorted fitter IDs')
        selected={s:{key:by[s][key] for key in ('ticker','issuer_id','risk_chain')} for s in order};tickers=[selected[s]['ticker'] for s in order]
        matrix=dict(dates=dates,tickers=tickers,returns=[[r[columns[t]] for t in tickers] for r in frame['data']]);exact(combo['fit_matrix'],matrix,'Full126 selected matrix');require(combo['fit_data_sha256']==digest(matrix),'Matrix SHA')
        card=plan['cardinalities'][k-1];require(rank<card['planned_combination_count'],'Rank within retained k');start=rank//ctx['shard_size']*ctx['shard_size'];stop=min(start+ctx['shard_size'],card['planned_combination_count']);shard=digest(dict(ctx,k=k,start=start,stop=stop))
        require(len(combo['tasks'])==3,'All three specs')
        combos.append(pure.encoded({key:v for key,v in combo.items() if key!='tasks'}))
        for si,task in enumerate(combo['tasks']):
            identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=k,selected=selected,weight_spec=SPECS[si],parameters=PARAMETERS,requested_previous_target_weights=None,fit_data_sha256=digest(matrix),fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
            exact(task['numerical_identity'],identity,'Full authorized numerical identity')
            location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=ref('plan'),plan_id=plan['plan_id'],shard_id=shard,order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=si,weight_spec=SPECS[si])
            exact(task['location_identity'],location,'Full location identity');tid=task['numerical_task_id'];canonical(tid)
            require(tid==digest(identity) and tid not in index and tid not in oldids and task['location_id']==digest(location) and task['location_id'] not in locations,'Unique new identity/location');locations.add(task['location_id'])
            require(task['status']=='MATERIALIZED_NOT_ATTEMPTED' and task['fit_performed'] is False and task['anchor_alias_equivalence_verified'] is False and task['completed_reference'] is None and task['complete_saved_rebinding_row'] is None,'No old task dispatch')
            count(task['wrapper_call_attempt_count'],0,'Unattempted task');exact(task['expected_fitter_previous_target_weights'],{},'None request and empty returned prior distinct')
            index[tid]=(ci,si,pure.encoded(task))
    exact(list(index),m['new_unattempted_numerical_task_ids'],'All1632 ordered');exact(m['selected_completed_numerical_task_ids'],[],'No old intersection')
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
    require(post['schema']=='BULK_BUDGETED_SINGLE_TASK_POSTCHECK_V1' and post['started_reference']==started_ref and post['raw_reference']==raw_ref and post['numerical_task_id']==task_id and all(post[k] is False for k in FALSE),'Postcheck binding/permission')
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
    value=dict(schema='BULK_BUDGETED_SINGLE_TASK_INDEPENDENT_READBACK_V1',status='PASSED',attempt_outcome=outcome,numerical_task_id=task_id,started_reference=deepcopy(started_ref),raw_reference=deepcopy(raw_ref),postcheck_reference=deepcopy(postcheck_reference),detail=detail,saved_postcheck=post,source_hashes=sources,runtime=state['runtime'],input_references=state['input_references'],task_reference=state['task_reference'],materialized_task_denominator=1632,other_new_tasks_not_inferred=1631,externally_completed_task_count=504,full_plan_task_denominator=cache['denominator'],independent_readback_performed=True,runner_called=False,fitter_called=False,optimization_repeated=False,risk_projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,**{k:False for k in FALSE if k!='independent_readback_performed'})
    guard(sources);require(runtime()==state['runtime'],'Runtime drift before publication');blob=codec.pretty(value)
    with output.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(sources);require(output.read_bytes()==blob and runtime()==state['runtime'],'Final output/runtime drift')
    require({p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json','independent_readback.json'},'Final namespace')
    return dict(path=str(output),sha256=codec.sha(blob))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--numerical-task-id',required=True);parser.add_argument('--postcheck-sha256',required=True);a=parser.parse_args()
    print(json.dumps(readback(a.numerical_task_id,dict(path=str(OUTPUT_ROOT/a.numerical_task_id/'postcheck.json'),sha256=a.postcheck_sha256))))
