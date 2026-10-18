"""Per-task diagnostic with an explicitly absent integer track, never a fake cash path."""
from copy import deepcopy
from fractions import Fraction
import hashlib,math
from pathlib import Path
import types

HELPER_SOURCE=Path(__file__).resolve().with_name('ndx_dated_economic_comparison_research.py')
HELPER_SHA='6216723e1d906ba689be58aa9eaee4f6b43dd2711ad2ed681566a1c7c3c5ef1b'
_blob=HELPER_SOURCE.read_bytes()
if hashlib.sha256(_blob).hexdigest()!=HELPER_SHA:raise ValueError('Frozen numeric helper source drift')
_helpers=types.ModuleType('_frozen_dated_metrics_only');exec(compile(_blob,str(HELPER_SOURCE),'exec'),_helpers.__dict__)
number=_helpers.number;metrics=_helpers.metrics;metric=_helpers.metric;require=_helpers.require;MODES=_helpers.MODES
FLAGS=dict(_helpers.FLAGS,complete_economic_comparison_verified=False,integer_missing_replaced_with_cash=False,shared_control_reexecuted=False)

def reference(value):
    require(type(value) is dict and set(value)=={'path','sha256','json_pointer'},'Each track has its own explicit byte reference and pointer')
    require(type(value['path']) is str and value['path'] and value['path']==value['path'].strip(),'Reference path')
    h=value['sha256'];require(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Reference SHA')
    p=value['json_pointer'];require(type(p) is str and p.startswith('/') and len(p)>1 and all('~' not in x.replace('~0','').replace('~1','') for x in p.split('/')[1:]),'Exact nonroot JSON pointer')

def continuous_metrics(track,calendar):
    require(track['schema']=='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1' and track['calendar']==calendar and type(track['interval_count']) is int and track['interval_count']==126,'Saved continuous schema/calendar')
    require(len(track['path'])==127 and [p['session'] for p in track['path']]==calendar,'No missing continuous points')
    for k in ('formal_cohort_verified','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','accounting_conservation_verified','dividends_included','weights_refitted','weights_normalized','daily_rebalancing_performed'):require(track[k] is False,'Continuous scope')
    values=[number(p['normalized_value']) for p in track['path']];require(values[0]==1,'Continuous initial1');result=metrics(values,calendar)
    for field,key in [('cumulative_return_exact','cumulative_return'),('annualized_return_exact','annualized_return'),('max_drawdown_exact','maximum_drawdown')]:require(number(track[field])==number(result[key]['exact']),'Saved continuous metrics')
    require(number(track['annualization_exponent_exact'])==2,'Square annualization')
    positions=track['positions_preserved'];require(type(positions) is list and positions and len({p['security_id'] for p in positions})==len(positions),'Complete unique positions')
    weights={p['security_id']:number(p['target_weight'],stored_float=True) for p in positions};require(all(w>=0 for w in weights.values()) and sum(weights.values())>0,'Original nonnegative weights including zeros')
    return result,values,positions

def integer_metrics(account,role,positions,calendar):
    require(account['schema']==('ndx_dynamic_frozen_execution_research_v2' if role=='candidate' else 'ndx_dynamic_frozen_incumbent_control_v1'),'Integer original schema')
    for k in ('point_in_time_verified','promotion_allowed','dividend_modelled'):require(account[k] is False,'Integer research flags')
    daily=account['daily'];require(len(daily)==127 and [r['session'] for r in daily]==calendar,'Complete integer dates')
    values=[number(r['total_value_usd'],stored_float=True) for r in daily];require(values[0]==25000 and number(daily[0]['cash_usd'],stored_float=True)==25000 and daily[0]['shares']=={},'Original initial25000')
    require(len(account['decisions'])==1 and account['decisions'][0]['decision_date']==calendar[0] and account['decisions'][0]['execution_date']==calendar[1],'One decision')
    decision=account['decisions'][0];require(decision['status'] in ('FROZEN','NO_PLAN'),'Saved decision terminal')
    require(type(account['executions']) is list and len(account['executions'])<=1,'At most one entry')
    for e in account['executions']:require(e['session']==calendar[1] and e['decision_date']==calendar[0] and e['status'] in ('FILLED','REJECTED','CANCELLED_SPLIT'),'Preserve real entry outcome')
    if decision['status']=='NO_PLAN':require(account['executions']==[],'NO_PLAN cannot invent execution')
    targets=decision['targets'];require(set(targets)=={p['security_id'] for p in positions},'Full identical integer/continuous support')
    weights={p['security_id']:float(p['target_weight']) for p in positions};require(all(math.isfinite(w) and w>0 for w in weights.values()),'Available integer requires actual positive-compatible coordinates')
    total=sum(weights[s] for s in targets)
    for p in positions:
        t=targets[p['security_id']];expected=weights[p['security_id']]/total if role=='candidate' else weights[p['security_id']]
        require(t['issuer_id']==p['issuer_id'] and type(t['target_weight']) is float and t['target_weight']==expected,'Original engine weight semantics')
    return metrics(values,calendar),values

def compare_per_task_paths(*,candidate_account,candidate_integer_status,incumbent_account,candidate_continuous,incumbent_continuous,nav_metrics,source_references):
    require(hashlib.sha256(HELPER_SOURCE.read_bytes()).hexdigest()==HELPER_SHA,'Frozen helper current bytes')
    roles={'candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous','nav_metrics'}
    require(type(source_references) is dict and set(source_references)==roles,'Five separate track source roles')
    for role,r in source_references.items():
        if role!='candidate_integer' or r is not None:reference(r)
    status=candidate_integer_status;require(type(status) is dict and set(status)=={'status','reason','evidence_reference'},'Explicit candidate integer availability contract');reference(status['evidence_reference'])
    require(status['status'] in ('AVAILABLE','NOT_EXECUTED_NONPOSITIVE_TARGET','TECHNICAL_MISSING'),'Known availability status')
    require((candidate_account is not None)==(status['status']=='AVAILABLE') and (source_references['candidate_integer'] is not None)==(candidate_account is not None),'No invented or hidden account')
    if candidate_account is None:require(type(status['reason']) is str and bool(status['reason'].strip()),'Preserve exact non-success reason')
    else:require(status['reason'] is None,'Available account has no synthetic absence reason')
    claims={}
    for r in [x for x in source_references.values() if x is not None]+[status['evidence_reference']]:
        require(r['path'] not in claims or claims[r['path']]==r['sha256'],'Source conflict');claims[r['path']]=r['sha256']
    require(nav_metrics['schema']=='SAME_WINDOW_NAV_REFERENCE_METRICS_V1' and nav_metrics['status']=='HISTORICAL_EXTERNAL_REFERENCE_ONLY','External NAV metrics role')
    require(nav_metrics['mode_order']==list(MODES) and set(nav_metrics['modes'])==set(MODES) and nav_metrics['modes_retained_separately'] is True,'Both FX modes, no picking')
    for k in ('point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout'):require(nav_metrics[k] is False,'NAV authority')
    calendar=nav_metrics['reference_calendar']['dates'];_helpers.calendar_check(calendar);tracks={};positions_by={}
    for role,track in [('candidate',candidate_continuous),('incumbent',incumbent_continuous)]:
        cm,values,positions=continuous_metrics(track,calendar);positions_by[role]=positions
        tracks[role+'_continuous']=dict(status='AVAILABLE',metrics=cm,source_reference=deepcopy(source_references[role+'_continuous']),stored_values_exact=[str(v) for v in values],original_track_preserved=deepcopy(track),value_encoding='SAVED_EXACT_FRACTIONAL_REFERENCE_NOT_CASH_ACCOUNT')
    if status['status']=='NOT_EXECUTED_NONPOSITIVE_TARGET':require(any(number(p['target_weight'],stored_float=True)==0 for p in positions_by['candidate']),'Nonpositive block requires actual preserved zero')
    for role,account in [('candidate',candidate_account),('incumbent',incumbent_account)]:
        if account is None:
            require(role=='candidate','Only candidate integer optional');tracks[role+'_integer']=dict(status=status['status'],metrics=None,source_reference=None,stored_values_exact=None,original_account_preserved=None,missing_evidence=deepcopy(status));continue
        im,values=integer_metrics(account,role,positions_by[role],calendar)
        tracks[role+'_integer']=dict(status='AVAILABLE',metrics=im,source_reference=deepcopy(source_references[role+'_integer']),stored_values_exact=[str(v) for v in values],original_account_preserved=deepcopy(account),value_encoding='FRACTION_OF_STR_SAVED_FLOAT_NOT_ORIGINAL_ECONOMIC_EXACTNESS')
    modes={};distances={}
    for mode in MODES:
        saved=nav_metrics['modes'][mode];require(saved['mode']==mode and saved['status']=='RETROSPECTIVE_REFERENCE_METRICS_COMPUTED' and saved['missing_sessions']==[],'Complete saved mode required')
        require(type(saved['observation_count']) is int and saved['observation_count']==127 and type(saved['interval_count']) is int and saved['interval_count']==126 and [r['session'] for r in saved['observations']]==calendar,'NAV full127')
        values=[number(r['saved_value_exact']) for r in saved['observations']];nm=metrics(values,calendar)
        require([r['normalized_value_exact'] for r in saved['observations']]==nm['normalized_values_exact'] and len(saved['interval_returns'])==126,'Complete NAV normalization/returns')
        for i,r in enumerate(saved['interval_returns']):require(r['previous_session']==calendar[i] and r['session']==calendar[i+1] and number(r['return_exact'])==values[i+1]/values[i]-1,'Saved NAV intervals')
        for key in ('cumulative_return','annualized_return','maximum_drawdown'):require(number(saved['metrics'][key]['exact'])==number(nm[key]['exact']),'Saved NAV metrics')
        modes[mode]=dict(metrics=nm,original_mode_preserved=deepcopy(saved),source_reference=deepcopy(source_references['nav_metrics']))
        distances[mode]={}
        for kind in ('integer','continuous'):
            per={};cm=tracks['candidate_'+kind]['metrics'];im=tracks['incumbent_'+kind]['metrics']
            for key in ('annualized_return','maximum_drawdown'):
                nv=number(nm[key]['exact']);old=abs(number(im[key]['exact'])-nv);new=None if cm is None else abs(number(cm[key]['exact'])-nv)
                per[key]=dict(candidate_absolute_distance=None if new is None else metric(new),incumbent_absolute_distance=metric(old),candidate_minus_incumbent_distance=None if new is None else metric(new-old),status='CANDIDATE_INTEGER_UNAVAILABLE' if new is None else 'BOTH_TRACKS_AVAILABLE_DIAGNOSTIC_ONLY',formula='ABS(CANDIDATE-NAV)-ABS(INCUMBENT-NAV);NO_PASS_THRESHOLD_APPLIED')
            distances[mode][kind]=per
    result=dict(schema='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1',status='ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY' if candidate_account is not None else 'PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE',candidate_integer_status_preserved=deepcopy(status),calendar=deepcopy(calendar),valuation_point_count=127,return_interval_count=126,tracks=tracks,nav_modes=modes,absolute_distance_comparisons=distances,mode_order=list(MODES),modes_retained_separately=True,source_references_preserved=deepcopy(source_references),source_hash_claims=claims,numeric_helper_reference=dict(path=str(HELPER_SOURCE),sha256=HELPER_SHA,functions=['number','metric','metrics','calendar_check']),evaluation_interval_previously_used_for_fitting=True,**FLAGS)
    require(hashlib.sha256(HELPER_SOURCE.read_bytes()).hexdigest()==HELPER_SHA,'Helper changed during comparison');return result
