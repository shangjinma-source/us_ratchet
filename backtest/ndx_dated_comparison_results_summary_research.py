"""Pure projection of saved audited comparisons, without recomputing economics."""
from collections import Counter
from copy import deepcopy
from datetime import date
from fractions import Fraction
import json
import math

FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
FULL=6222659648236112670
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
TRACKS=('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')
METRICS=('cumulative_return','annualized_return','maximum_drawdown')
FLAGS=dict.fromkeys(('comparison_recomputed','account_executed','fit_performed','source_bytes_authenticated','audit_reexecuted','cohort_statistics_computed','formal_comparison_passed','formal_noninferiority_verified','point_in_time_verified','promotion_allowed','winner_selected','global_optimum_proved','future_independent_oos'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def exact(a,b,message):require(json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False),message)
def integer(v,n,message):require(type(v) is int and v==n,message)
def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and bool(r['path']),'External byte reference')
    require(type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Canonical SHA')
def metric(v):
    require(type(v) is dict and type(v['exact']) is str,'Saved exact metric')
    try:f=Fraction(v['exact'])
    except (ValueError,ZeroDivisionError) as e:raise ValueError('Invalid metric fraction') from e
    require(str(f)==v['exact'],'Canonical saved metric fraction')
    return deepcopy(v)
def metrics(v):
    require(type(v) is dict,'Available saved metric map')
    return {key:metric(v[key]) for key in METRICS}
def false(v):
    for key in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','winner_selected'):require(v[key] is False,'No authority '+key)

def project_task(task,envelope):
    require(type(envelope) is dict and set(envelope)=={'document','document_reference','audit','audit_reference','original_targets'},'Exact saved comparison envelope')
    doc=envelope['document'];c=doc['comparison'];audit=envelope['audit'];r=envelope['document_reference'];ar=envelope['audit_reference'];reference(r);reference(ar)
    require(audit['status']=='PASS','Accepted saved independent evidence');exact(audit['comparison_reference'],r,'Comparison/audit linkage')
    tid=task['numerical_task_id'];first=tid==FIRST
    if first:
        require(doc['schema']=='SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' and c['schema']=='DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1' and c['status']=='SINGLE_PATH_DIAGNOSTIC_ONLY','Explicit first comparison adapter')
        require(audit['schema']=='DATED_COMPARISON_INDEPENDENT_READBACK_V1','First independent schema')
        positions=c['saved_paths_preserved']['candidate']['continuous_track']['positions_preserved']
    else:
        require(doc['schema']=='SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1' and doc['numerical_task_id']==tid and c['schema']=='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1','Explicit per-task adapter')
        require(audit['schema']=='DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1' and audit['numerical_task_id']==tid,'Same audited task')
        require(doc['original_task_preserved']['numerical_task_id']==tid,'Original task preserved')
        positions=c['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved']
    false(doc);false(c)
    for key in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos'):require(audit[key] is False,'Independent scope remains conditional')
    integer(c['valuation_point_count'],127,'Full valuation count');integer(c['return_interval_count'],126,'Full interval count')
    calendar=c['calendar'];require(type(calendar) is list and len(calendar)==127 and calendar==sorted(set(calendar)),'Complete preserved calendar')
    for d in calendar:require(type(d) is str and date.fromisoformat(d).isoformat()==d,'Canonical session')
    require(calendar[0]=='2026-03-20' and calendar[1]=='2026-03-23' and calendar[-1]=='2026-09-21','Same dated evaluation window')
    require(c['mode_order']==list(MODES) and set(c['nav_modes'])==set(MODES) and set(c['absolute_distance_comparisons'])==set(MODES) and c['modes_retained_separately'] is True,'Both FX modes remain separate')
    exact(envelope['original_targets'],positions,'Original unnormalized target coordinates exact')
    require(type(positions) is list and len(positions)==task['k'],'Full target slots including zero')
    require(len({p['security_id'] for p in positions})==len(positions),'Unique original SID slots')
    for p in positions:
        for key in ('security_id','ticker','issuer_id'):require(type(p[key]) is str and bool(p[key]),'Explicit true coordinate')
        require(type(p['target_weight']) in (int,float) and math.isfinite(p['target_weight']) and p['target_weight']>=0,'Saved original finite nonnegative weight')
    require(any(p['target_weight']>0 for p in positions),'Positive target sum')
    require(set(c['tracks'])==set(TRACKS),'Four complete track slots')
    tracks={}
    for name in TRACKS:
        t=c['tracks'][name];available=first or t['status']=='AVAILABLE'
        if not available:
            require(name=='candidate_integer' and t['status'] in ('NOT_EXECUTED_NONPOSITIVE_TARGET','TECHNICAL_MISSING'),'Only explicit candidate integer absence')
            require(t['metrics'] is None and t['original_account_preserved'] is None and t['stored_values_exact'] is None and t['source_reference'] is None,'No artificial all-cash replacement')
            tracks[name]=dict(status=t['status'],metrics=None,decision_status=None,execution_statuses=None,source_reference=None,missing_evidence=deepcopy(t['missing_evidence']))
            continue
        status='AVAILABLE';decision=None;executions=None
        if name.endswith('_integer'):
            role=name.split('_')[0];account=c['saved_paths_preserved'][role]['integer_account'] if first else t['original_account_preserved']
            require(len(account['decisions'])==1,'One saved decision');decision=account['decisions'][0]['status'];executions=[e['status'] for e in account['executions']]
            require(decision in ('FROZEN','NO_PLAN') and len(executions)<=1 and all(x in ('FILLED','REJECTED','CANCELLED_SPLIT') for x in executions),'Saved execution states')
            if decision=='NO_PLAN':require(executions==[],'No invented execution')
        source=deepcopy(t['source_reference'])
        tracks[name]=dict(status=status,metrics=metrics(t['metrics']),decision_status=decision,execution_statuses=executions,source_reference=source,path_pointer=t.get('path_pointer'),value_encoding=t['value_encoding'])
    missing=tracks['candidate_integer']['status']!='AVAILABLE'
    if not first:
        require(c['status']==('PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE' if missing else 'ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY'),'Partial comparison status')
        require(c['candidate_integer_status_preserved']['status']==tracks['candidate_integer']['status'],'Absence status retained')
    modes={}
    for mode in MODES:
        saved=c['nav_modes'][mode];distances={}
        require(set(c['absolute_distance_comparisons'][mode])=={'integer','continuous'},'Both distance tracks')
        for kind in ('integer','continuous'):
            distances[kind]={};values=c['absolute_distance_comparisons'][mode][kind]
            require(set(values)=={'annualized_return','maximum_drawdown'},'Two component distances')
            for key in ('annualized_return','maximum_drawdown'):
                row=values[key];absent=missing and kind=='integer'
                require((row['candidate_absolute_distance'] is None)==absent and (row['candidate_minus_incumbent_distance'] is None)==absent,'No missing metric substitution')
                metric(row['incumbent_absolute_distance'])
                if not absent:metric(row['candidate_absolute_distance']);metric(row['candidate_minus_incumbent_distance'])
                distances[kind][key]=deepcopy(row)
        modes[mode]=dict(nav_metrics=metrics(saved['metrics']),nav_source_reference=deepcopy(saved['source_reference']),absolute_distance_comparisons=distances)
    return dict(numerical_task_id=tid,k=task['k'],weight_spec=task['weight_spec'],status='AUDITED_COMPARISON_PRESENT',original_targets=deepcopy(positions),target_weights_normalized_by_summary=False,comparison_reference=deepcopy(r),audit_reference=deepcopy(ar),calendar=deepcopy(calendar),tracks=tracks,nav_modes=modes,original_candidate_integer_status=None if first else deepcopy(c['candidate_integer_status_preserved']),source_references_preserved=deepcopy(c['source_references_preserved']))

def summarize_comparisons(*,task_summary,task_summary_reference,comparisons_by_task):
    reference(task_summary_reference);require(task_summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1','Full dated task summary')
    integer(task_summary['materialized_task_count'],1632,'Original bounded queue');integer(task_summary['full_new_cutoff_task_denominator'],FULL,'Complete domain unchanged')
    tasks=task_summary['rows'];require(type(tasks) is list and len(tasks)==1632,'No denominator compression');ids=[t['numerical_task_id'] for t in tasks];require(len(set(ids))==1632,'Unique task IDs')
    require(type(comparisons_by_task) is dict and set(comparisons_by_task).issubset(ids),'No foreign comparisons')
    coverage=Counter()
    for t in tasks:
        require(type(t['k']) is int and 4<=t['k']<=20 and t['weight_spec'] in SPECS,'Original k/spec coordinates');coverage[t['k'],t['weight_spec']]+=1
    require(coverage==Counter({(k,s):32 for k in range(4,21) for s in SPECS}),'Full 51 strata, 32 tasks each')
    rows=[];sources={task_summary_reference['path']:task_summary_reference['sha256']}
    for t in tasks:
        tid=t['numerical_task_id']
        if tid not in comparisons_by_task:rows.append(dict(numerical_task_id=tid,k=t['k'],weight_spec=t['weight_spec'],status='NOT_SUPPLIED',original_targets=None,tracks=None,nav_modes=None,reason='No externally audited comparison supplied; not inferred failed or all cash'));continue
        e=comparisons_by_task[tid]
        for key in ('document_reference','audit_reference'):
            r=e[key];reference(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Conflicting source reference');sources[r['path']]=r['sha256']
        rows.append(project_task(t,e))
    present=[r for r in rows if r['status']=='AUDITED_COMPARISON_PRESENT'];strata=[]
    for k,spec in sorted(coverage):
        group=[r for r in rows if (r['k'],r['weight_spec'])==(k,spec)];ok=[r for r in group if r['status']=='AUDITED_COMPARISON_PRESENT']
        strata.append(dict(k=k,weight_spec=spec,planned_task_count=32,supplied_comparison_count=len(ok),not_supplied_count=32-len(ok),candidate_integer_status_counts=dict(Counter(r['tracks']['candidate_integer']['status'] for r in ok)),candidate_integer_decision_counts=dict(Counter(r['tracks']['candidate_integer']['decision_status'] for r in ok if r['tracks']['candidate_integer']['decision_status'] is not None)),candidate_integer_execution_counts=dict(Counter(x for r in ok for x in (r['tracks']['candidate_integer']['execution_statuses'] or [])))))
    return dict(schema='DATED_COMPARISON_RESULTS_TABLES_V1',rows=rows,k_spec_coverage=strata,materialized_task_count=1632,supplied_comparison_count=len(present),not_supplied_count=1632-len(present),full_new_cutoff_task_denominator=FULL,unrepresented_full_domain_count=FULL-len(present),mode_order=list(MODES),modes_kept_separate=True,original_order_preserved=True,task_summary_reference=deepcopy(task_summary_reference),source_hash_claims=sources,aggregation_scope='SAVED_AUDITED_METRICS_PROJECTION_ONLY_NO_RETURN_DISTANCE_RECOMPUTATION',single_path_diagnostics_not_cohort_envelope=True,**FLAGS)
