"""Six-decision saved-path diagnostics. No ledger execution or cohort admission."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, Context, localcontext
from fractions import Fraction
import hashlib
import json
import math
from backtest.ndx_multidecision_reference_metrics_research import account_twr_metrics

MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
TRACKS=('CONTINUOUS','WHOLE_LOT')
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
INSPECTION_FLAGS=('account_engine_called','fit_called','source_bytes_authenticated','point_in_time_verified','formal_benchmark_passed','promotion_allowed','execution_authorized','integer_repair_search_independently_recomputed','binary64_bitwise_reproduction_claimed')
SUCCESS='ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK'
MISSING=('BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT','NUMERICAL_EXCEPTION','VALIDATION_FAILURE','UNRESOLVED_DISPATCH','UNDISPATCHED')
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_ledger_independently_reaudited','account_executed','fit_performed','formal_comparison_passed','formal_noninferiority_passed','cohort_statistics_computed','promotion_allowed','future_independent_oos','point_in_time_verified','winner_selected','fx_mode_selected_using_results'),False)


def require(ok,message):
    if not ok: raise ValueError(message)


def exact(a,b,message):
    require(json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False),message)


def reference(r):
    require(type(r)is dict and set(r)=={'path','sha256','json_pointer'},'Exact file and object pointer')
    require(type(r['path'])is str and r['path'] and type(r['sha256'])is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Reference syntax')
    require(type(r['json_pointer'])is str and (r['json_pointer']=='' or r['json_pointer'].startswith('/')),'Explicit pointer')


def finite(x):
    require(type(x)in(int,float) and math.isfinite(x),'Finite nonbool stored number')
    return x


def calendar_check(calendar):
    require(type(calendar)is list and len(calendar)>=2 and calendar==sorted(set(calendar)),'Full sorted calendar')
    for d in calendar:
        require(type(d)is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5,'Canonical observed session')
    require(calendar[0]==CUTOFFS[0] and all(d in calendar for d in CUTOFFS),'All six decision closes retained')


def setup(track):
    kw=track['engine_binding']['keyword_arguments'];calendar=kw['closes']['index'];calendar_check(calendar)
    exact(kw['opens']['index'],calendar,'Same open/close calendar')
    require(kw['valuation_end_date']==calendar[-1],'Explicit full end date')
    for key in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps'):
        require(finite(kw[key])>=0,'Nonnegative configured capital/fees')
    require(kw['initial_cash_usd']>0,'Positive initial capital')
    exact(track['own_initial_state'],dict(cash_usd=kw['initial_cash_usd'],shares={}),'Own initial cash-only state')
    flows=kw['external_flows'];require(type(flows)is list,'Explicit flow list');seen=set()
    for f in flows:
        require(f['currency']=='USD' and f['timing']=='BEFORE_OPEN' and f['session'] in calendar[1:] and finite(f['amount_usd'])>=0,'Known USD positive/zero session flow')
        require(set(f)=={'session','amount_usd','currency','timing','source_reference'},'Explicit USD flow fields');require(set(f['source_reference'])=={'path','sha256'},'Flow source role');reference(dict(f['source_reference'],json_pointer=''))
        identity=(f['session'],f['source_reference']['path'],f['source_reference']['sha256']);require(identity not in seen,'Duplicate flow');seen.add(identity)
    return kw,calendar


def metric_shape(m,calendar):
    require(type(m['observation_count'])is int and m['observation_count']==len(calendar) and type(m['interval_count'])is int and m['interval_count']==len(calendar)-1,'Metric full denominator')
    require(m['initial_one_in_drawdown'] is True and m['annualized_return_calculated'] is True,'Initial capital peak retained')
    require([r['session'] for r in m['wealth']]==calendar,'Full metric wealth calendar')
    def rat(r):
        require(type(r)is dict and set(r)=={'numerator','denominator'} and all(type(v)is str for v in r.values()),'Saved exact ratio')
        require(int(r['denominator'])>0,'Positive denominator');return Fraction(int(r['numerator']),int(r['denominator']))
    wealth=[rat(r['normalized_wealth']) for r in m['wealth']]
    require(wealth[0]==1 and all(v>0 for v in wealth),'Saved normalized positive wealth')
    require(rat(m['cumulative_return'])==wealth[-1]-1 and 0<=rat(m['maximum_drawdown'])<1,'Saved metric bounds/terminal')
    a=Decimal(m['annualized_return_diagnostic_decimal']);require(a.is_finite() and a>-1,'Finite annualized diagnostic')
    ann=m['annualization'];require(all(type(ann[k])is int for k in ('sessions_per_year','interval_count','decimal_precision')),'Typed annualization denominator');require(ann['sessions_per_year']==252 and ann['interval_count']==len(calendar)-1 and ann['decimal_precision']==80 and ann['formal_admission_allowed']is False,'Existing annualization semantics')
    return a,rat(m['maximum_drawdown'])


def account(slot,prepared,coordinate,calendar,role):
    exact(slot['coordinate'],coordinate,'Exact source slot coordinate')
    require(slot['outcome'] in (SUCCESS,)+MISSING,'Known saved terminal/missing status')
    reference(slot['evidence_reference'])
    if slot['outcome']!=SUCCESS:
        require(slot['result']is None and slot['result_reference']is None and slot['audit_evidence']is None,'Missing account has no fabricated cash path')
        require(type(slot['reason'])is str and slot['reason'],'Explicit missing reason')
        return dict(status=slot['outcome'],reason=slot['reason'],metrics=None,evidence=deepcopy(slot))
    require(prepared['status']==('ENGINE_INPUTS_PREPARED_NOT_EXECUTED' if role=='candidate' else 'CONTROL_INPUTS_PREPARED_NOT_EXECUTED'),'Blocked input cannot acquire successful account')
    require(slot['reason']is None,'Success has no missing reason');reference(slot['result_reference'])
    audit=slot['audit_evidence'];reference(audit['reference']);reference(audit['reader_reference']);exact(audit['result_reference'],slot['result_reference'],'Audited exact raw result object')
    ins=audit['inspection'];require(ins['schema']==('MULTIDECISION_ACCOUNT_LEDGER_INSPECTION_V1' if role=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT_LEDGER_INSPECTION_V1'),'Role-specific ledger inspection');require(ins['status']=='PASS' and ins['track']==coordinate[2] and type(ins['daily_rows'])is int and ins['daily_rows']==len(calendar),'Saved slot ledger inspection projection')
    for flag in INSPECTION_FLAGS:require(ins[flag]is False,'Saved ledger inspection authority remains False')
    require(type(ins['return_intervals'])is int and ins['return_intervals']==len(calendar)-1,'Ledger full return interval count')
    r=slot['result'];kind=coordinate[2]
    expected='DYNAMIC_FIXED_INCUMBENT_USD_FLOW_SPLIT_CONTROL_V1' if role=='control' else ('DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2' if kind=='CONTINUOUS' else 'DYNAMIC_WHOLE_LOT_USD_FLOW_SPLIT_ACCOUNT_V1')
    require(r['schema']==expected,'Versioned actual account role')
    for flag in ('point_in_time_verified','formal_benchmark_passed','promotion_allowed'):require(r[flag]is False,'No inherited authority')
    kw=prepared['engine_binding']['keyword_arguments']
    if kind=='CONTINUOUS':
        traces=r['external_flows'];exact([f['event'] for f in traces],sorted(kw['external_flows'],key=lambda f:f['session']),'Saved continuous credited events')
        for f in traces:
            require(f['event_id']==hashlib.sha256(json.dumps(f['event'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest() and f['performance_boundary']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE','Saved continuous flow trace identity')
    else:exact(r['external_flows'],kw['external_flows'],'Saved whole account actual flows')
    if kind=='CONTINUOUS':
        require(r['quantity_policy']=='FROZEN_PRIOR_CLOSE_TARGET_WEIGHTS_OPEN_CONTINUOUS_TWO_SIDED_FEE_SOLVE' and r['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE_AND_FEES','Continuous execution mechanism')
        for key in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps'):exact(r[key],float(kw[key]),'Saved continuous configuration')
    else:
        require(r['execution_policy']=='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET' and r['flow_policy']=='ONLY_ALREADY_CREDITED_CASH_AVAILABLE_AT_DECISION_CLOSE' and r['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES','Whole prior-close basket mechanism')
    if role=='control':
        require(r['track']==kind and r['weights_normalized']is False and r['risk_is_order_gate']is False,'Original8 financial-only fixed control')
        exact(r['original_targets'],kw['schedule'][0]['targets'],'Original literal control targets')
    daily=r['daily'];require([d['session'] for d in daily]==calendar,'No missing/extra account session')
    require(finite(daily[0]['normalized_twr'])==1 and finite(daily[0]['close_equity_usd' if kind=='CONTINUOUS' else 'total_value_usd'])==kw['initial_cash_usd'],'Actual initial capital/TWR')
    for d in daily:
        expected_flow=sum(f['amount_usd'] for f in kw['external_flows'] if f['session']==d['session'])
        require(finite(d['cash_injection_usd'])==expected_flow,'Same actual credited session flow')
    require(finite(r['summary']['chained_twr'])==daily[-1]['normalized_twr']-1,'Saved cumulative TWR linkage')
    metric=account_twr_metrics(daily=daily,calendar=calendar);metric_shape(metric['metrics'],calendar)
    return dict(status='SAVED_PATH_DIAGNOSTIC',reason=None,metrics=metric['metrics'],arithmetic=metric['arithmetic'],evidence_reference=deepcopy(slot['evidence_reference']),result_reference=deepcopy(slot['result_reference']),audit_evidence=deepcopy(audit),saved_execution_diagnostics={k:deepcopy(r[k]) for k in ('summary','trades','rebalances','executions','decisions') if k in r})


def distances(candidate,control,nav,calendar):
    result={}
    for role,m in (('candidate',candidate),('control',control)):
        if m is None or nav is None:result[role]=None;continue
        a,d=metric_shape(m,calendar);na,nd=metric_shape(nav,calendar)
        with localcontext(Context(prec=80)):
            result[role]=dict(annualized_return_absolute_distance=str(abs(a-na)),maximum_drawdown_absolute_distance=str(abs(d-nd)))
    result['candidate_minus_control_absolute_distance']=None
    if all(result[r] is not None for r in ('candidate','control')):
        with localcontext(Context(prec=80)):
            result['candidate_minus_control_absolute_distance']=dict(annualized_return=str(Decimal(result['candidate']['annualized_return_absolute_distance'])-Decimal(result['control']['annualized_return_absolute_distance'])),maximum_drawdown=str(Fraction(result['candidate']['maximum_drawdown_absolute_distance'])-Fraction(result['control']['maximum_drawdown_absolute_distance'])))
    return result


def compare_multidecision_paths(*,candidate_prepared,control_prepared,candidate_slots,control_slots,nav_metrics,source_references):
    require(set(source_references)=={'candidate_prepared','control_prepared','candidate_results','control_results','nav_metrics'},'All five explicit source roles')
    for r in source_references.values():reference(r)
    for p,schema in ((candidate_prepared,'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1'),(control_prepared,'MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1')):
        require(p['schema']==schema and len(p['rows'])==8,'Actual prepared source role')
        for key,n in (('lane_count',8),('track_count',16),('coordinate_count',48)):require(type(p[key])is int and p[key]==n,'Complete original domain')
    require(len(candidate_slots)==len(control_slots)==16,'Full16 result projection required')
    require(nav_metrics['original_fx_context']['rate_direction']=='CNY_PER_USD' and nav_metrics['interpretation']=='EX_POST_EXTERNAL_NAV_REFERENCE_NOT_SUBSCRIPTION_ACCOUNT_OR_COHORT','Conditional session-aligned USD NAV reference, not CNY wealth')
    require(nav_metrics['schema']=='MULTIDECISION_CONTIGUOUS_NAV_REFERENCE_METRICS_V1' and set(nav_metrics['modes'])==set(MODES),'Both saved NAV FX modes')
    for key in ('source_bytes_authenticated','formal_admission_allowed','mode_selected_using_results','cohort_statistics_computed'):require(nav_metrics[key]is False,'NAV remains conditional context')
    rows=[];common=None
    for li,(mode,lane) in enumerate((m,l) for m in MODES for l in LANES):
        cp,ip=candidate_prepared['rows'][li],control_prepared['rows'][li]
        for p in (cp,ip):
            require(p['fx_mode']==mode and p['lane']==lane and len(p['tracks'])==2,'Full original lane order')
            exact(p['coordinate_indexes'],list(range(li,48,8)),'All six registered coordinates')
        for ti,track in enumerate(TRACKS):
            c,i=cp['tracks'][ti],ip['tracks'][ti];require(c['track']==i['track']==track,'Separate mechanism slots')
            ck,cal=setup(c);ik,ical=setup(i);exact(cal,ical,'Same candidate/control calendar')
            if common is None:common=cal
            exact(cal,common,'All16 same reference calendar')
            for key in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','external_flows','valuation_end_date'):exact(ck[key],ik[key],'Same explicit capital/flow/fee contract')
            clocks=lambda k:[[s['decision_date'],s['execution_date']] for s in k['schedule']]
            iclock=clocks(ik);require([s[0] for s in iclock]==CUTOFFS,'Full six control decisions')
            for d,e in iclock:require(cal.index(d)+1<len(cal) and cal[cal.index(d)+1]==e,'Prior close to next observed open')
            # A blocked candidate can have missing targets; never invent its missing schedule.
            for pair in clocks(ck):require(pair in iclock,'Candidate decision must use registered control clock')
            if c['status']=='ENGINE_INPUTS_PREPARED_NOT_EXECUTED':exact(clocks(ck),iclock,'Ready candidate full six schedule')
            coordinate=[mode,lane,track];ci=account(candidate_slots[li*2+ti],c,coordinate,cal,'candidate');co=account(control_slots[li*2+ti],i,coordinate,cal,'control')
            exact(nav_metrics['reference_calendar']['dates'],cal,'NAV exact full calendar')
            nm=nav_metrics['modes'][mode];require(nm['mode']==mode,'No FX substitution')
            require([o['original_alignment_row']['session'] for o in nm['observations']]==cal,'All NAV source observations')
            if nm['status']=='BLOCKED_MISSING_REFERENCE_INPUT':require(nm['metrics']is None and nm['missing_sessions'],'Missing NAV preserved');nav=None
            else:
                require(nm['status']=='HISTORICAL_METRICS_COMPUTED' and nm['missing_sessions']==[],'Known NAV status');nav=nm['metrics'];metric_shape(nav,cal)
            rows.append(dict(track_index=li*2+ti,coordinate=coordinate,candidate=ci,control=co,nav_mode=mode,nav_status=nm['status'],distances=distances(ci['metrics'],co['metrics'],nav,cal),prepared_blocking_reasons=dict(candidate=deepcopy(c['blocking_reasons']),control=deepcopy(i['blocking_reasons'])),**FLAGS))
    return dict(schema='MULTIDECISION_SAME_WINDOW_PATH_DIAGNOSTIC_V1',scope='SINGLE_HISTORICAL_TWR_PATH_TWO_DISTANCE_DIAGNOSTICS_NOT_FOUR_DIMENSION_COHORT_GATE',coordinate_count=48,lane_count=8,track_count=16,calendar=deepcopy(common),rows=rows,nav_modes_preserved=deepcopy(nav_metrics),source_references=deepcopy(source_references),counts=dict(candidate_metrics=sum(r['candidate']['metrics']is not None for r in rows),control_metrics=sum(r['control']['metrics']is not None for r in rows),missing_candidate=sum(r['candidate']['metrics']is None for r in rows)),missing_formal_evidence=['INDEPENDENT_COHORT_P50_P10_P90','FORMAL_COMPONENTWISE_NONINFERIORITY','FRESH_FORWARD_OOS_AND_PIT'],audit_projection_scope='CALLER_SUPPLIED_SAVED_INSPECTIONS_NOT_BYTE_AUTHENTICATION',**FLAGS)
