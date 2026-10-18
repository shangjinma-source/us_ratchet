"""Pure independent materialized-task readback; no production index or fitter imports."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

ORDER='ISSUER_SID_PREFIX_LEX_V1'
SPECS=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
PARAMETERS={'fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'}
ROOT=Path(__file__).resolve().parents[1]
MATERIALIZER_SOURCES={str(ROOT/'backtest/ndx_issuer_combination_index_research.py'):'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',
 str(ROOT/'backtest/ndx_issuer_shard_prepare_research.py'):'722f48952a6d0c8c878df76eedeb0b8ca3b1e3feeb77560598414890ae00a4ec',
 str(ROOT/'backtest/ndx_issuer_task_materialization_research.py'):'11348bd4aa99b8ee61bacdd12438aaf3c600e1f808e430130464895c22a2df88'}


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)


def text(value):
    require(type(value) is str and value and value==value.strip(),'Canonical text required');return value


def hash_string(value):require(type(value) is str and len(value)==64 and set(value)<=set('0123456789abcdef'),'SHA256 required')


def reference(value):
    require(type(value) is dict and set(value)=={'path','sha256'} and Path(text(value['path'])).is_absolute(),'Exact absolute reference required')
    hash_string(value['sha256'])


def groups_contract(groups):
    require(type(groups) is list and groups,'Explicit groups required')
    normalized=[];seen=set();issuers=set()
    for row in groups:
        require(type(row) is dict and set(row)=={'issuer_id','security_ids'},'Group schema')
        issuer=text(row['issuer_id']);members=row['security_ids']
        require(issuer not in issuers and type(members) is list and members and members==sorted(set(members)),'Canonical unique issuer group')
        for sid in members:require(text(sid) not in seen,'Duplicate SID');seen.add(sid)
        issuers.add(issuer);normalized.append((issuer,members))
    require(normalized==sorted(normalized),'Issuer order')
    return normalized


def suffix_count(groups,start,degree):
    """Coefficient of x**degree in product(1+group_size*x); never enumerate selections."""
    if degree<0:return 0
    coefficients=[1]+[0]*degree
    for _,members in groups[start:]:
        for power in range(degree,0,-1):coefficients[power]+=len(members)*coefficients[power-1]
    return coefficients[degree]


def independent_position(groups,selection):
    require(type(selection) is list and selection,'Explicit prefix SID list required')
    lookup={sid:(i,j) for i,(_,members) in enumerate(groups) for j,sid in enumerate(members)}
    require(all(type(s) is str and s in lookup for s in selection),'Unknown selected SID')
    locations=[lookup[s] for s in selection]
    require(all(a[0]<b[0] for a,b in zip(locations,locations[1:])),'Prefix issuer order/one-class-per-issuer')
    position=0;lower=0
    for offset,(issuer,share_class) in enumerate(locations):
        remaining=len(selection)-offset-1
        for skipped in range(lower,issuer):position+=len(groups[skipped][1])*suffix_count(groups,skipped+1,remaining)
        position+=share_class*suffix_count(groups,issuer+1,remaining)
        lower=issuer+1
    return position


def validate_plan_panel(plan,panel,expected_fitter_source_hashes):
    require(plan['schema']=='ISSUER_COUNTS_ONLY_SHARD_PREPARE_V1' and plan['status']=='PLANNED_NOT_ENUMERATED','Pending counts-only plan')
    context=plan['context'];groups=groups_contract(plan['canonical_groups'])
    require(context['plan_version']==plan['schema'] and context['order_version']==ORDER and context['weight_specs']==SPECS,'Three specs/order contract')
    require(context['group_fingerprint']==digest({'order_version':ORDER,'groups':groups}) and plan['plan_id']==digest(context),'Plan/group identity')
    reference(context['panel_reference']);reference(context['panel_audit_reference'])
    require(context['panel_reference']['path']!=context['panel_audit_reference']['path'],'Separate panel/audit')
    source_map=expected_fitter_source_hashes
    require(type(source_map) is dict and len(source_map)==25,'External full 25-source fitter map required')
    for path,h in source_map.items():require(Path(text(path)).is_absolute(),'Absolute source');hash_string(h)
    require(exact(plan['fitter_source_hashes'],source_map) and context['fitter_source_fingerprint']==digest(source_map),'Full fitter source map')
    params=context['parameters'];require(type(params) is dict and set(params)==PARAMETERS,'All eight parameters')
    require(type(params['fit_days']) is int and params['fit_days']==126,'126 fit days')
    for k,v in params.items():require(type(v) in (int,float) and math.isfinite(v) and (k=='fit_days' or 0<=v<=1),'Parameter numeric type/range')
    require(params['max_single_weight']>0 and params['risk_chain_top1_cap']>0 and params['min_single_weight']<=params['max_single_weight'],'Risk envelope')
    prior=context['previous_target_weights']
    if prior is not None:
        require(type(prior) is dict and prior,'Complete prior or None')
        for sid,weight in prior.items():require(text(sid) and type(weight) in (int,float) and math.isfinite(weight) and 0<=weight<=1,'Prior element')
        require(abs(sum((Fraction(str(v)) for v in prior.values()),Fraction(0))-1)<=Fraction(1,10**9) and math.isclose(sum(float(v) for v in prior.values()),1.,abs_tol=1e-12,rel_tol=0),'Full prior mass; no intersection/renormalization')
    require(type(panel) is dict and set(panel)=={'panel_reference','panel_content_sha256','dates','columns','returns','universe'},'Pure panel schema')
    require(panel['panel_reference']==context['panel_reference'],'Panel external reference');hash_string(panel['panel_content_sha256'])
    days=panel['dates'];cols=panel['columns'];matrix=panel['returns']
    require(type(days) is list and len(days)==126 and days==sorted(set(days)) and all(type(d) is str and date.fromisoformat(d).isoformat()==d for d in days) and days[-1]==context['decision_cutoff'],'Full126 dates')
    require(type(cols) is list and cols and len(cols)==len(set(cols)) and all(type(t) is str and t==t.strip()==t.upper() and t for t in cols),'Full unique canonical columns')
    require(type(matrix) is list and len(matrix)==126 and all(type(r) is list and len(r)==len(cols) for r in matrix),'Full matrix rectangle')
    for row in matrix:
        for v in row:require(type(v) in (int,float) and math.isfinite(v) and v>-1,'Full panel finite returns, including unselected cells')
    lookup={};by_issuer={};tickers=set()
    for row in panel['universe']:
        require(type(row) is dict and set(row)=={'security_id','ticker','issuer_id','risk_chain'},'Universe row exact')
        for v in row.values():text(v)
        sid=row['security_id'];ticker=row['ticker'];require(sid not in lookup and ticker not in tickers and ticker in cols,'Unique full universe')
        lookup[sid]=row;tickers.add(ticker);by_issuer.setdefault(row['issuer_id'],[]).append(sid)
    require(tickers==set(cols) and [(i,sorted(s)) for i,s in sorted(by_issuer.items())]==groups,'Full panel/group coverage')
    require(all(type(plan[k]) is int and plan[k]>=0 for k in ('completed_canonical_task_count','remaining_canonical_task_count','planned_canonical_task_count')),'Exact integer plan counters')
    require(plan['completed_canonical_task_count']==0 and plan['remaining_canonical_task_count']==plan['planned_canonical_task_count'],'No plan completion')
    for flag in ('combination_enumeration_performed','risk_feasibility_proven','score_filtering_performed','task_identity_generated','runner_attached','external_source_bytes_verified','source_bytes_reverified_at_call','anchor_alias_equivalence_verified','identity_authenticated','fit_performed','promotion_allowed'):
        require(plan[flag] is False,'Plan authority/state differs')
    require(plan['all_three_specs_planned_without_alias_deduplication'] is True,'Three specs cannot alias')
    return groups,lookup


def verify_materialized(*,value,plan,plan_reference,shard_id,panel,start,stop,max_materialized_combinations,expected_fitter_source_hashes):
    """Caller must hard-bind plan/panel/value bytes; this pure reader authenticates no IO.

    Validates selected shard/task contract, not all plan risk certificates. A later
    wrapper must bind the separately audited counts-only plan and complete sources.
    """
    reference(plan_reference);hash_string(shard_id)
    require(all(type(v) is int for v in (start,stop,max_materialized_combinations)) and 1<=max_materialized_combinations<=10000,'Exact bounded request')
    groups,lookup=validate_plan_panel(plan,panel,expected_fitter_source_hashes);ctx=plan['context']
    shards=[s for s in plan['shards'] if s['shard_id']==shard_id];require(len(shards)==1,'One declared shard')
    shard=shards[0];k=shard['k'];require(type(k) is int and 1<=k<=len(groups),'Valid k')
    require(all(type(shard[key]) is int and shard[key]>=0 for key in ('start','stop','completed_canonical_task_count','remaining_canonical_task_count')),'Exact integer shard counters')
    require(type(ctx['shard_size']) is int and 1<=ctx['shard_size']<=10000,'Exact shard size')
    identity=dict(ctx,k=k,start=shard['start'],stop=shard['stop'])
    require(shard_id==digest(identity) and all(exact(shard[key],val) for key,val in identity.items()) and shard['plan_id']==plan['plan_id'],'Shard full context identity')
    require(shard['status']=='PLANNED_NOT_ENUMERATED' and shard['completed_canonical_task_count']==0 and shard['remaining_canonical_task_count']==3*(shard['stop']-shard['start']),'Shard pending state')
    total=suffix_count(groups,0,k)
    require(0<=shard['start']<=start<=stop<=shard['stop']<=total and stop-start<=max_materialized_combinations,'Exact requested half-open interval')
    require(type(value['combinations']) is list and len(value['combinations'])==stop-start,'Requested combination count')
    positions={t:i for i,t in enumerate(panel['columns'])};combinations=[]
    for offset,combo in enumerate(value['combinations']):
        rank=start+offset;prefix=combo['prefix_security_ids'];require(len(prefix)==k and independent_position(groups,prefix)==rank,'Independent combination position differs')
        ordered=sorted(prefix);selected={s:{key:lookup[s][key] for key in ('ticker','issuer_id','risk_chain')} for s in ordered}
        tickers=[selected[s]['ticker'] for s in ordered]
        matrix=dict(dates=deepcopy(panel['dates']),tickers=tickers,returns=[[float(row[positions[t]]) for t in tickers] for row in panel['returns']])
        matrix_sha=digest(matrix);tasks=[]
        for index,spec in enumerate(SPECS):
            numerical=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=k,selected=deepcopy(selected),weight_spec=spec,parameters=deepcopy(ctx['parameters']),requested_previous_target_weights=deepcopy(ctx['previous_target_weights']),fit_data_sha256=matrix_sha,fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
            location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=deepcopy(plan_reference),plan_id=plan['plan_id'],shard_id=shard_id,order_version=ORDER,group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=index,weight_spec=spec)
            tasks.append(dict(numerical_task_id=digest(numerical),numerical_identity=numerical,location_id=digest(location),location_identity=location,status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False,expected_fitter_previous_target_weights={} if ctx['previous_target_weights'] is None else deepcopy(ctx['previous_target_weights']),anchor_alias_equivalence_verified=False))
        expected=dict(k=k,rank=rank,prefix_security_ids=prefix,fitter_sorted_security_ids=ordered,fit_matrix=matrix,fit_data_sha256=matrix_sha,tasks=tasks)
        require(exact(combo,expected),'Complete selected/matrix/three tasks/dual IDs differs');combinations.append(expected)
    expected=dict(schema='ISSUER_BOUNDED_TASK_MATERIALIZATION_V1',status='MATERIALIZED_NOT_ATTEMPTED',plan_reference=deepcopy(plan_reference),plan_id=plan['plan_id'],shard_id=shard_id,order_version=ORDER,group_fingerprint=ctx['group_fingerprint'],k=k,start=start,stop=stop,panel_reference=deepcopy(ctx['panel_reference']),panel_audit_reference=deepcopy(ctx['panel_audit_reference']),panel_content_sha256=panel['panel_content_sha256'],fitter_source_hashes=deepcopy(expected_fitter_source_hashes),materializer_loaded_source_hashes=deepcopy(MATERIALIZER_SOURCES),combination_count=stop-start,materialized_task_count=(stop-start)*3,completed_task_count=0,remaining_unattempted_materialized_task_count=(stop-start)*3,max_materialized_combinations=max_materialized_combinations,combinations=combinations,source_bytes_authenticated=False,source_bytes_reverified_at_call=False,identity_authenticated=False,old_task_identity_reused=False,full_shard_completed=False,all_plan_tasks_completed=False,fit_performed=False,promotion_allowed=False)
    require(exact(value,expected),'Full materialization envelope differs')
    return dict(schema='ISSUER_MATERIALIZATION_PURE_INDEPENDENT_READBACK_V1',status='PASSED',combination_count=stop-start,task_count=3*(stop-start),verified_positions=list(range(start,stop)),k=k,
      complete_materialization_sha256=digest(value),plan_assertion_sha256=digest(plan),panel_assertion_sha256=digest(panel),
      independent_position_counting=True,all_selected_tasks_exact=True,full_fitter_source_count=25,full_prior_preserved=True,
      producer_called=False,production_index_called=False,production_prepare_called=False,full_combination_enumeration_performed=False,
      all_plan_risk_certificates_recomputed=False,source_bytes_authenticated=False,identity_authenticated=False,fit_performed=False,promotion_allowed=False)
