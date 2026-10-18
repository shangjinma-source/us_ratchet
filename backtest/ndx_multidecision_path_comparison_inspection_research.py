"""Independent saved comparison arithmetic; stdlib only, no engine or producer.

Saved binary64 TWR is interpreted as its exact rational value.  Drawdown uses
all earlier/later pairs, including initial capital. Decimal80 powers reproduce
the declared historical display arithmetic, not exact economic annualization.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, Context, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import math

MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
KINDS=('CONTINUOUS','WHOLE_LOT')
DAYS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
FALSE=('source_bytes_authenticated','account_ledger_independently_reaudited','account_executed','fit_performed','formal_comparison_passed','formal_noninferiority_passed','cohort_statistics_computed','promotion_allowed','future_independent_oos','point_in_time_verified','winner_selected','fx_mode_selected_using_results')
AUDIT_FALSE=('account_engine_called','fit_called','source_bytes_authenticated','point_in_time_verified','formal_benchmark_passed','promotion_allowed','execution_authorized','integer_repair_search_independently_recomputed','binary64_bitwise_reproduction_claimed')
ABSENT=('BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT','NUMERICAL_EXCEPTION','VALIDATION_FAILURE','UNRESOLVED_DISPATCH','UNDISPATCHED')


def check(value,message):
    if not value:raise ValueError(message)


def same(a,b,message):
    check(json.dumps(a,sort_keys=True,allow_nan=False,separators=(',',':'))==json.dumps(b,sort_keys=True,allow_nan=False,separators=(',',':')),message)


def pointer(r):
    check(type(r)is dict and set(r)=={'path','sha256','json_pointer'},'Explicit source object locator')
    check(type(r['path'])is str and r['path'] and type(r['sha256'])is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Source syntax')
    check(type(r['json_pointer'])is str and (r['json_pointer']=='' or r['json_pointer'].startswith('/')),'Explicit JSON pointer')


def number(v):
    check(type(v)in(int,float) and math.isfinite(v),'Finite nonboolean saved TWR/number')
    return Fraction(v)


def ratio(f):return dict(numerator=str(f.numerator),denominator=str(f.denominator))


def rational(r):
    check(type(r)is dict and set(r)=={'numerator','denominator'} and all(type(v)is str for v in r.values()),'Saved rational shape')
    check(int(r['denominator'])>0,'Positive denominator');f=Fraction(int(r['numerator']),int(r['denominator']));same(r,ratio(f),'Canonical reduced ratio');return f


def independently_measure(calendar,wealth):
    check(len(wealth)==len(calendar)>=2 and wealth[0]==1 and all(v>0 for v in wealth),'Positive full wealth from initial one')
    # Every previous peak candidate is considered independently of the producer's rolling maximum.
    dd=max([Fraction(0)]+[1-wealth[j]/wealth[i] for j in range(len(wealth)) for i in range(j+1)])
    intervals=len(wealth)-1
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)) as ctx:
        annual=ctx.power(Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator),Decimal(252)/Decimal(intervals))-Decimal(1)
    return dict(observation_count=len(wealth),interval_count=intervals,cumulative_return=ratio(wealth[-1]-1),maximum_drawdown=ratio(dd),wealth=[dict(session=d,normalized_wealth=ratio(w)) for d,w in zip(calendar,wealth)],initial_one_in_drawdown=True,annualized_return_calculated=True,annualized_return_diagnostic_decimal=str(annual),annualization=dict(formula='terminal_normalized_wealth ** (252 / interval_count) - 1',sessions_per_year=252,interval_count=intervals,decimal_precision=80,rounding='ROUND_HALF_EVEN',arithmetic='DECIMAL80_POWER_FROM_EXACT_TERMINAL_FRACTION_NOT_EXACT_RATIONAL_ANNUALIZATION',annualization_is_historical_diagnostic=True,short_window_below_252_intervals=intervals<252,short_window_limitation='SHORT_WINDOW_COMPOUNDING_CAN_MAGNIFY_SMALL_MOVES_NOT_LONG_TERM_EVIDENCE',formal_admission_allowed=False))


def saved_role(slot,prepared,coordinate,calendar,role):
    same(slot['coordinate'],coordinate,'Original slot coordinate');pointer(slot['evidence_reference'])
    if slot['outcome'] in ABSENT:
        check(slot['result']is None and slot['result_reference']is None and slot['audit_evidence']is None,'Missing is not a cash path')
        check(type(slot['reason'])is str and slot['reason'],'Missing reason preserved')
        return dict(status=slot['outcome'],reason=slot['reason'],metrics=None,evidence=deepcopy(slot))
    check(slot['outcome']=='ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK' and slot['reason']is None,'Known successful saved path')
    check(prepared['status']==('ENGINE_INPUTS_PREPARED_NOT_EXECUTED' if role=='candidate' else 'CONTROL_INPUTS_PREPARED_NOT_EXECUTED'),'Successful path requires ready input')
    pointer(slot['result_reference']);a=slot['audit_evidence']
    for key in ('reference','reader_reference','result_reference'):pointer(a[key])
    same(a['result_reference'],slot['result_reference'],'Audit exact result pointer')
    ins=a['inspection'];check(ins['schema']==('MULTIDECISION_ACCOUNT_LEDGER_INSPECTION_V1' if role=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT_LEDGER_INSPECTION_V1'),'Ledger audit role')
    check(ins['status']=='PASS' and ins['track']==coordinate[2],'Ledger audit matching track')
    for key,n in (('daily_rows',len(calendar)),('return_intervals',len(calendar)-1)):check(type(ins[key])is int and ins[key]==n,'Ledger complete denominator')
    for flag in AUDIT_FALSE:check(ins[flag]is False,'Ledger audit cannot confer authority')
    r=slot['result'];daily=r['daily'];same([d['session'] for d in daily],calendar,'Full saved daily observations')
    kw=prepared['engine_binding']['keyword_arguments'];kind=coordinate[2]
    check(r['schema']==('DYNAMIC_FIXED_INCUMBENT_USD_FLOW_SPLIT_CONTROL_V1' if role=='control' else ('DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2' if kind=='CONTINUOUS' else 'DYNAMIC_WHOLE_LOT_USD_FLOW_SPLIT_ACCOUNT_V1')),'Saved account version/role')
    for flag in ('point_in_time_verified','formal_benchmark_passed','promotion_allowed'):check(r[flag]is False,'Saved account authority')
    check(number(daily[0]['close_equity_usd' if kind=='CONTINUOUS' else 'total_value_usd'])==number(kw['initial_cash_usd']),'Original initial capital')
    if kind=='CONTINUOUS':
        for trace in r['external_flows']:
            encoded=json.dumps(trace['event'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            check(trace['event_id']==hashlib.sha256(encoded).hexdigest() and trace['performance_boundary']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE','Original continuous flow identity/boundary')
    flows=[t['event'] for t in r['external_flows']] if kind=='CONTINUOUS' else r['external_flows']
    same(flows,sorted(kw['external_flows'],key=lambda f:f['session']) if kind=='CONTINUOUS' else kw['external_flows'],'Original credited flows')
    for d in daily:check(number(d['cash_injection_usd'])==number(sum(f['amount_usd'] for f in kw['external_flows'] if f['session']==d['session'])),'Session credited flow not wealth')
    wealth=[number(d['normalized_twr']) for d in daily]
    check(r['summary']['chained_twr']==daily[-1]['normalized_twr']-1 and type(r['summary']['chained_twr'])in(int,float),'Saved TWR summary link')
    if kind=='CONTINUOUS':
        check(r['quantity_policy']=='FROZEN_PRIOR_CLOSE_TARGET_WEIGHTS_OPEN_CONTINUOUS_TWO_SIDED_FEE_SOLVE' and r['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE_AND_FEES','Continuous mechanism')
        for key in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps'):same(r[key],float(kw[key]),'Saved continuous configuration')
    else:
        check(r['execution_policy']=='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET' and r['flow_policy']=='ONLY_ALREADY_CREDITED_CASH_AVAILABLE_AT_DECISION_CLOSE' and r['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES','Frozen integer mechanism')
    if role=='control':
        check(r['weights_normalized']is False and r['risk_is_order_gate']is False and r['track']==kind,'Original8 fixed financial control')
        same(r['original_targets'],kw['schedule'][0]['targets'],'Literal control target')
    return dict(status='SAVED_PATH_DIAGNOSTIC',reason=None,metrics=independently_measure(calendar,wealth),arithmetic='EXACT_FRACTIONS_OF_SAVED_BINARY64_TWR_NOT_EXACT_ECONOMIC_VALUES',evidence_reference=deepcopy(slot['evidence_reference']),result_reference=deepcopy(slot['result_reference']),audit_evidence=deepcopy(a),saved_execution_diagnostics={k:deepcopy(r[k]) for k in ('summary','trades','rebalances','executions','decisions') if k in r})


def independent_distances(candidate,control,nav):
    result={};annual={};drawdown={}
    for name,m in (('candidate',candidate),('control',control)):
        if nav is None or m is None:result[name]=None;continue
        with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
            annual[name]=abs(Decimal(m['annualized_return_diagnostic_decimal'])-Decimal(nav['annualized_return_diagnostic_decimal']))
        drawdown[name]=abs(rational(m['maximum_drawdown'])-rational(nav['maximum_drawdown']))
        result[name]=dict(annualized_return_absolute_distance=str(annual[name]),maximum_drawdown_absolute_distance=str(drawdown[name]))
    result['candidate_minus_control_absolute_distance']=None
    if len(annual)==2:
        with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
            difference=str(annual['candidate']-annual['control'])
        result['candidate_minus_control_absolute_distance']=dict(annualized_return=difference,maximum_drawdown=str(drawdown['candidate']-drawdown['control']))
    return result


def inspect_multidecision_comparison(*,saved_comparison,candidate_prepared,control_prepared,candidate_slots,control_slots,nav_metrics,source_references):
    check(set(source_references)=={'candidate_prepared','control_prepared','candidate_results','control_results','nav_metrics'},'Complete source role map')
    for r in source_references.values():pointer(r)
    check(len(candidate_slots)==len(control_slots)==16,'Full16 saved source slots')
    for p,schema in ((candidate_prepared,'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1'),(control_prepared,'MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1')):
        check(p['schema']==schema and len(p['rows'])==8,'Original prepared role')
        for key,n in (('coordinate_count',48),('lane_count',8),('track_count',16)):check(type(p[key])is int and p[key]==n,'Prepared complete domain')
    calendar=candidate_prepared['rows'][0]['tracks'][0]['engine_binding']['keyword_arguments']['closes']['index']
    check(calendar==sorted(set(calendar)) and calendar[0]==DAYS[0] and all(d in calendar for d in DAYS),'Full common registered calendar')
    for d in calendar:check(type(d)is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5,'Canonical session')
    check(nav_metrics['schema']=='MULTIDECISION_CONTIGUOUS_NAV_REFERENCE_METRICS_V1' and set(nav_metrics['modes'])==set(MODES),'Two original NAV modes')
    same(nav_metrics['reference_calendar']['dates'],calendar,'Same full NAV calendar')
    check(nav_metrics['original_fx_context']['rate_direction']=='CNY_PER_USD' and nav_metrics['interpretation']=='EX_POST_EXTERNAL_NAV_REFERENCE_NOT_SUBSCRIPTION_ACCOUNT_OR_COHORT','Original currency context')
    for flag in ('source_bytes_authenticated','formal_admission_allowed','mode_selected_using_results','cohort_statistics_computed'):check(nav_metrics[flag]is False,'NAV authority False')
    navs={}
    for mode in MODES:
        n=nav_metrics['modes'][mode];check(n['mode']==mode,'Separate FX mode');same([v['original_alignment_row']['session'] for v in n['observations']],calendar,'NAV full source slots')
        missing=[o['original_alignment_row']['session'] for o in n['observations'] if o['saved_value_exact']is None];same(n['missing_sessions'],missing,'Exact missing NAV slots')
        if n['status']=='BLOCKED_MISSING_REFERENCE_INPUT':
            check(n['metrics']is None and n['missing_sessions'],'Explicit missing NAV');navs[mode]=None
        else:
            check(n['status']=='HISTORICAL_METRICS_COMPUTED' and n['missing_sessions']==[],'Known complete NAV')
            check(all(type(o['saved_value_exact'])is str for o in n['observations']),'Saved exact NAV literals');values=[Fraction(o['saved_value_exact']) for o in n['observations']];check(all(v>0 for v in values),'Positive saved conditional USD NAV')
            expected=independently_measure(calendar,[v/values[0] for v in values]);same(n['metrics'],expected,'Saved NAV metrics consistent with saved aligned observations');navs[mode]=expected
    rows=[]
    for li in range(8):
        mode,lane=MODES[li//4],LANES[li%4];c=candidate_prepared['rows'][li];o=control_prepared['rows'][li]
        for p in (c,o):
            same([p['fx_mode'],p['lane']],[mode,lane],'Original lane order');same(p['coordinate_indexes'],[li+8*j for j in range(6)],'Six original coordinates');check(len(p['tracks'])==2,'Both execution mechanisms')
        for ti,kind in enumerate(KINDS):
            ci,oi=c['tracks'][ti],o['tracks'][ti];check(ci['track']==oi['track']==kind,'Mechanism mapping')
            ck,ok=[p['engine_binding']['keyword_arguments'] for p in (ci,oi)]
            for p,k in ((ci,ck),(oi,ok)):
                for frame in ('opens','closes'):same(k[frame]['index'],calendar,'Full path calendar')
                check(k['valuation_end_date']==calendar[-1] and number(k['initial_cash_usd'])>0,'Full end and positive initial')
                same(p['own_initial_state'],dict(cash_usd=k['initial_cash_usd'],shares={}),'Own initial state')
                for parameter in ('minimum_cash_buffer_usd','transaction_cost_bps'):check(number(k[parameter])>=0,'Nonnegative fees and buffer')
                seen=set()
                for f in k['external_flows']:
                    check(set(f)=={'session','amount_usd','currency','timing','source_reference'} and f['currency']=='USD' and f['timing']=='BEFORE_OPEN' and f['session'] in calendar[1:] and number(f['amount_usd'])>=0,'Supported explicit flow')
                    check(set(f['source_reference'])=={'path','sha256'},'Flow source identity');pointer(dict(f['source_reference'],json_pointer=''))
                    identity=(f['session'],f['source_reference']['path'],f['source_reference']['sha256']);check(identity not in seen,'Unique flow identity');seen.add(identity)
            for key in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','external_flows','valuation_end_date'):same(ck[key],ok[key],'Same comparable capital/flow/fees')
            clock=[(s['decision_date'],s['execution_date']) for s in ok['schedule']];check([d for d,e in clock]==list(DAYS),'Six original closes')
            for d,e in clock:check(calendar[calendar.index(d)+1]==e,'Next actual session')
            cclock=[(s['decision_date'],s['execution_date']) for s in ck['schedule']];check(all(pair in clock for pair in cclock),'Candidate original clocks')
            if ci['status']=='ENGINE_INPUTS_PREPARED_NOT_EXECUTED':same(cclock,clock,'Ready full schedule')
            ordinal=li*2+ti;coordinate=[mode,lane,kind]
            cm=saved_role(candidate_slots[ordinal],ci,coordinate,calendar,'candidate');om=saved_role(control_slots[ordinal],oi,coordinate,calendar,'control')
            rows.append(dict(track_index=ordinal,coordinate=coordinate,candidate=cm,control=om,nav_mode=mode,nav_status=nav_metrics['modes'][mode]['status'],distances=independent_distances(cm['metrics'],om['metrics'],navs[mode]),prepared_blocking_reasons=dict(candidate=deepcopy(ci['blocking_reasons']),control=deepcopy(oi['blocking_reasons'])),**dict.fromkeys(FALSE,False)))
    count=sum(r['candidate']['metrics']is not None for r in rows)
    expected=dict(schema='MULTIDECISION_SAME_WINDOW_PATH_DIAGNOSTIC_V1',scope='SINGLE_HISTORICAL_TWR_PATH_TWO_DISTANCE_DIAGNOSTICS_NOT_FOUR_DIMENSION_COHORT_GATE',coordinate_count=48,lane_count=8,track_count=16,calendar=deepcopy(calendar),rows=rows,nav_modes_preserved=deepcopy(nav_metrics),source_references=deepcopy(source_references),counts=dict(candidate_metrics=count,control_metrics=sum(r['control']['metrics']is not None for r in rows),missing_candidate=16-count),missing_formal_evidence=['INDEPENDENT_COHORT_P50_P10_P90','FORMAL_COMPONENTWISE_NONINFERIORITY','FRESH_FORWARD_OOS_AND_PIT'],audit_projection_scope='CALLER_SUPPLIED_SAVED_INSPECTIONS_NOT_BYTE_AUTHENTICATION',**dict.fromkeys(FALSE,False))
    same(saved_comparison,expected,'Complete saved comparison projection/arithmetic mismatch')
    return dict(schema='MULTIDECISION_PATH_COMPARISON_INSPECTION_V1',status='PASS',scope='SAVED16_TWR_ALL_PAIRS_DRAWDOWN_DECIMAL80_DISTANCES_NOT_LEDGER_OR_SOURCE_AUTHENTICATION',coordinate_count=48,lane_count=8,track_count=16,account_metric_count=count+expected['counts']['control_metrics'],nav_mode_count=2,calendar_rows=len(calendar),drawdown_method='ALL_EARLIER_LATER_PAIRS_INCLUDING_INITIAL_ONE',comparison_producer_called=False,metrics_helpers_called=False,account_engine_called=False,**dict.fromkeys(FALSE,False))
