"""Single historical path diagnostics from saved ledgers; never a cohort gate."""
from copy import deepcopy
from datetime import date
from decimal import Context,Decimal,ROUND_HALF_EVEN,localcontext
from fractions import Fraction
import math
import re

MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
FLAGS=dict.fromkeys(('account_executed','fit_performed','raw_prices_redecoded','formal_comparison_passed','formal_noninferiority_verified','benchmark_qualified','winner_selected','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','cohort_p90_computed','mode_selected_using_results','point_in_time_verified','promotion_allowed','execution_authorized','future_independent_oos','untouched_holdout','source_bytes_authenticated','original_economic_values_exact','subscription_redemption_execution_required_for_reference_metrics'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def number(value,*,stored_float=False):
    if stored_float:
        require(type(value) in (int,float) and (type(value) is int or math.isfinite(value)),'Finite saved numeric value; no bool')
        return Fraction(str(value))
    if type(value) is dict:
        require(set(value)=={'numerator','denominator'},'Exact rational object')
        n=value['numerator'];d=value['denominator']
        require(type(n) is str and type(d) is str and 0<len(n)<4096 and 0<len(d)<4096 and n.lstrip('-').isdigit() and d.isdigit() and int(d)>0,'Exact rational integer strings')
        return Fraction(int(n),int(d))
    require(type(value) is str and 0<len(value)<4096 and re.fullmatch(r'-?[0-9]+(?:/[0-9]+)?',value) is not None,'Bounded exact rational string')
    try:return Fraction(value)
    except (ValueError,ZeroDivisionError):raise ValueError('Invalid rational value') from None


def metric(value):
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
        display=str(Decimal(value.numerator)/Decimal(value.denominator))
    return dict(exact=str(value),decimal=display,unit='DIMENSIONLESS_RATIO_NOT_PERCENT')


def metrics(values,calendar):
    require(len(values)==127 and values[0]>0 and all(v>0 for v in values),'Complete positive127 values')
    normalized=[v/values[0] for v in values];peak=Fraction(1);peak_index=0;worst=Fraction(0);pair=(0,0)
    for i,v in enumerate(normalized):
        if v>peak:peak=v;peak_index=i
        loss=1-v/peak
        if loss>worst:worst=loss;pair=(peak_index,i)
    ratio=normalized[-1]
    return dict(cumulative_return=metric(ratio-1),annualized_return=metric(ratio**2-1),maximum_drawdown=metric(worst),annualization=dict(trading_days_per_year=252,return_interval_count=126,exponent_exact='2',formula='(LAST / FIRST) ** 2 - 1',historical_diagnostic_only=True),drawdown=dict(first_observation_included_as_peak=True,peak_index=pair[0],trough_index=pair[1],peak_session=calendar[pair[0]],trough_session=calendar[pair[1]],equal_peak_policy='EARLIEST_UNTIL_STRICTLY_HIGHER_PEAK',equal_maximum_policy='FIRST_STRICT_MAXIMUM'),normalized_values_exact=[str(v) for v in normalized])


def calendar_check(values):
    require(type(values) is list and len(values)==127 and values==sorted(set(values)),'Full ordered127 calendar; no compression')
    for d in values:require(type(d) is str and date.fromisoformat(d).isoformat()==d,'Canonical date')
    require(values[0]=='2026-03-20' and values[1]=='2026-03-23' and values[-1]=='2026-09-21','Fixed freeze/entry/end')


def compare_dated_paths(*,candidate_account,incumbent_account,continuous_document,nav_metrics,source_references):
    require(type(source_references) is dict and set(source_references)=={'candidate_account','incumbent_account','continuous','nav_metrics'},'Four explicit source roles')
    for r in source_references.values():
        require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Exact source reference')
    require(continuous_document['schema']=='SOURCE_BOUND_DATED_CONTINUOUS_WEIGHT_DIAGNOSTIC_V1' and set(continuous_document['tracks'])=={'candidate','incumbent'},'Both saved continuous tracks')
    require(nav_metrics['schema']=='SAME_WINDOW_NAV_REFERENCE_METRICS_V1' and nav_metrics['status']=='HISTORICAL_EXTERNAL_REFERENCE_ONLY','Saved NAV reference')
    require(nav_metrics['mode_order']==list(MODES) and set(nav_metrics['modes'])==set(MODES) and nav_metrics['modes_retained_separately'] is True,'Both FX modes remain distinct')
    calendar=nav_metrics['reference_calendar']['dates'];calendar_check(calendar)
    for obj in (continuous_document,nav_metrics):
        for k in ('point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout'):require(obj[k] is False,'Source authority cannot be upgraded')
    tracks={};preserved={}
    for role,account,schema in [('candidate',candidate_account,'ndx_dynamic_frozen_execution_research_v2'),('incumbent',incumbent_account,'ndx_dynamic_frozen_incumbent_control_v1')]:
        require(account['schema']==schema,'Original saved integer account schema')
        for k in ('point_in_time_verified','promotion_allowed','dividend_modelled'):require(account[k] is False,'Integer research scope')
        daily=account['daily'];require(type(daily) is list and len(daily)==127 and [r['session'] for r in daily]==calendar,'Every integer daily row retained')
        values=[number(r['total_value_usd'],stored_float=True) for r in daily]
        require(values[0]==25000 and number(daily[0]['cash_usd'],stored_float=True)==25000 and daily[0]['shares']=={},'Initial25000 empty holdings')
        require(len(account['decisions'])==1 and account['decisions'][0]['decision_date']==calendar[0] and account['decisions'][0]['execution_date']==calendar[1],'Single priorClose decision')
        require(type(account['executions']) is list and len(account['executions'])<=1,'No later rebalance execution')
        for execution in account['executions']:require(execution['session']==calendar[1] and execution['decision_date']==calendar[0] and execution['status'] in ('FILLED','REJECTED'),'Single original entry status retained')
        continuous=continuous_document['tracks'][role]
        require(continuous['schema']=='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1' and continuous['calendar']==calendar and len(continuous['path'])==127 and [r['session'] for r in continuous['path']]==calendar,'Full saved continuous calendar')
        require(type(continuous['interval_count']) is int and continuous['interval_count']==126,'Exact126 intervals')
        for k in ('formal_cohort_verified','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','accounting_conservation_verified','dividends_included','weights_refitted','weights_normalized','daily_rebalancing_performed'):require(continuous[k] is False,'Continuous diagnostic only')
        fractional=[number(r['normalized_value']) for r in continuous['path']];require(fractional[0]==1,'Continuous initial1')
        cm=metrics(fractional,calendar)
        for saved,key in [('cumulative_return_exact','cumulative_return'),('annualized_return_exact','annualized_return'),('max_drawdown_exact','maximum_drawdown')]:require(number(continuous[saved])==number(cm[key]['exact']),'Saved continuous metrics inconsistent')
        require(number(continuous['annualization_exponent_exact'])==2,'Saved exact square annualization')
        positions=continuous['positions_preserved'];require(type(positions) is list and len({p['security_id'] for p in positions})==len(positions),'Complete distinct continuous coordinates')
        targets=account['decisions'][0]['targets'];require(set(targets)=={p['security_id'] for p in positions},'Integer and continuous same saved support')
        original={p['security_id']:float(p['target_weight']) for p in positions};require(all(math.isfinite(w) and w>0 for w in original.values()),'Saved positive engine-compatible target weights')
        total=sum(original[s] for s in targets)
        for p in positions:
            s=p['security_id'];require(targets[s]['issuer_id']==p['issuer_id'],'Same issuer labels')
            expected=original[s]/total if role=='candidate' else original[s]
            require(type(targets[s]['target_weight']) is float and targets[s]['target_weight']==expected,'Saved candidate normalized versus control unchanged target')
        im=metrics(values,calendar)
        tracks[role+'_integer']=dict(metrics=im,value_encoding='EXACT_FRACTION_OF_STR_SAVED_FLOAT_NOT_ORIGINAL_ECONOMIC_EXACTNESS',original_summary=deepcopy(account['summary']),source_reference=deepcopy(source_references[role+'_account']),path_pointer='/account/daily',stored_values_exact=[str(v) for v in values],initial_capital_usd='25000',rejections_or_all_cash_retained=True)
        tracks[role+'_continuous']=dict(metrics=cm,value_encoding='SAVED_EXACT_RATIONAL_FRACTIONAL_WEIGHT_DIAGNOSTIC_NOT_CASH_CONSERVING_ACCOUNT',source_reference=deepcopy(source_references['continuous']),path_pointer='/tracks/'+role+'/path',stored_values_exact=[str(v) for v in fractional],initial_normalized_value='1',normalization_or_weights_changed_by_comparison=False)
        preserved[role]=dict(integer_account=deepcopy(account),continuous_track=deepcopy(continuous))
    references={};distances={}
    for mode in MODES:
        item=nav_metrics['modes'][mode]
        require(item['mode']==mode and item['status']=='RETROSPECTIVE_REFERENCE_METRICS_COMPUTED' and item['missing_sessions']==[] and type(item['observation_count']) is int and item['observation_count']==127 and type(item['interval_count']) is int and item['interval_count']==126,'Complete reference mode required; missing data never compressed')
        rows=item['observations'];require(len(rows)==127 and [r['session'] for r in rows]==calendar,'Every NAV observation')
        raw=[number(r['saved_value_exact']) for r in rows];nm=metrics(raw,calendar)
        require([r['normalized_value_exact'] for r in rows]==nm['normalized_values_exact'],'NAV normalization anchored at first observation')
        require(len(item['interval_returns'])==126,'NAV interval slots')
        for i,row in enumerate(item['interval_returns']):require(row['previous_session']==calendar[i] and row['session']==calendar[i+1] and number(row['return_exact'])==raw[i+1]/raw[i]-1,'Saved NAV interval arithmetic')
        for key in ('cumulative_return','annualized_return','maximum_drawdown'):require(number(item['metrics'][key]['exact'])==number(nm[key]['exact']),'Saved NAV metric inconsistent')
        references[mode]=dict(metrics=nm,original_mode=deepcopy(item),source_reference=deepcopy(source_references['nav_metrics']),path_pointer='/metrics/modes/'+mode)
        distances[mode]={}
        for execution in ('integer','continuous'):
            per={}
            for key in ('annualized_return','maximum_drawdown'):
                nav=number(nm[key]['exact']);cd=abs(number(tracks['candidate_'+execution]['metrics'][key]['exact'])-nav);od=abs(number(tracks['incumbent_'+execution]['metrics'][key]['exact'])-nav)
                per[key]=dict(candidate_absolute_distance=metric(cd),incumbent_absolute_distance=metric(od),candidate_minus_incumbent_distance=metric(cd-od),formula='ABS(CANDIDATE-NAV)-ABS(INCUMBENT-NAV);NO_PASS_THRESHOLD_APPLIED')
            distances[mode][execution]=per
    return dict(schema='DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1',status='SINGLE_PATH_DIAGNOSTIC_ONLY',calendar=deepcopy(calendar),valuation_point_count=127,return_interval_count=126,tracks=tracks,nav_modes=references,absolute_distance_comparisons=distances,mode_order=list(MODES),modes_retained_separately=True,source_references_preserved=deepcopy(source_references),saved_paths_preserved=preserved,nav_context_preserved=deepcopy({k:v for k,v in nav_metrics.items() if k!='modes'}),annualization_is_historical_diagnostic=True,evaluation_interval_previously_used_for_fitting=True,limitations=['LATE_POOL_AND_COMPOSITION_SELECTION','STORED_FLOAT_ARITHMETIC_IS_NOT_ORIGINAL_ECONOMIC_EXACTNESS','INTEGER_FEE_CASH_AND_REJECTION_DIFFER_FROM_FRACTIONAL_DIAGNOSTIC','NO_DIVIDENDS_OR_COMPLETE_ACTION_CERTIFICATION','NAV_CURRENT_VINTAGE_PUBLICATION_UNKNOWN_AND_CONDITIONAL_CURRENCY','REFERENCE_IS_NOT_A_FUND_SUBSCRIPTION_EXECUTION'],**FLAGS)
