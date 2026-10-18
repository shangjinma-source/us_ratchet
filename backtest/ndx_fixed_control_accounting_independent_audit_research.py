"""Decimal cash/whole-slot audit of a saved fixed control; never gates on risk."""
import json
from datetime import date
from decimal import Decimal,localcontext,ROUND_FLOOR
from backtest import ndx_frozen_accounting_independent_audit_research as risk


def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def counts(value):
    if type(value) is not dict or any(type(q) is not int or q<0 for q in value.values()):raise ValueError('Nonnegative whole target slots required')
    return value
def same_amount(actual,expected):risk.equal_amount(actual,expected)


def observed_risk(saved,shares,marks,chains,contract):
    counts(shares);positive={s:q for s,q in shares.items() if q>0}
    extra={'target_slot_count','positive_holding_count','zero_share_security_ids','financial_allocation_checks','risk_is_order_gate'}
    if not extra<=set(saved) or type(saved['target_slot_count']) is not int or saved['target_slot_count']!=len(shares) or type(saved['positive_holding_count']) is not int or saved['positive_holding_count']!=len(positive) or saved['zero_share_security_ids']!=sorted(s for s,q in shares.items() if q==0) or not exact(saved['financial_allocation_checks'],{'NONNEGATIVE_WHOLE_SHARES':True}) or saved['risk_is_order_gate'] is not False:
        raise ValueError('Actual control zero-slot/risk-gate disclosure differs')
    risk.verify_risk({k:v for k,v in saved.items() if k not in extra},positive,{s:marks[s] for s in positive},chains,contract)


def audit(*,execution,calendar,schedule,prices,risk_chains_by_decision,contract):
    with localcontext() as context:
        context.prec=50
        return _audit(execution,calendar,schedule,prices,risk_chains_by_decision,contract)


def _audit(execution,calendar,schedule,prices,risk_chains_by_decision,contract):
    if len(calendar)!=127 or calendar!=sorted(set(calendar)) or any(type(d) is not str or date.fromisoformat(d).isoformat()!=d for d in calendar) or calendar[0]!='2026-03-18' or calendar[1]!='2026-03-19' or calendar[-1]!='2026-09-17' or set(prices)!=set(calendar):raise ValueError('Complete 127-session historical execution clock required')
    if len(schedule)!=1 or schedule[0]['decision_date']!=calendar[0] or schedule[0]['execution_date']!=calendar[1]:raise ValueError('Single next-Open historical decision required')
    if execution['schema']!='ndx_dynamic_frozen_incumbent_control_v1' or execution['risk_is_order_gate'] is not False or execution['original_target_weights_modified'] is not False or execution['zero_share_target_slots_allowed'] is not True or execution['candidate_eligibility_claimed'] is not False:raise ValueError('Original control semantics required')
    if execution['corporate_actions']!=[] or execution['identity_events']!=[] or execution['dividend_modelled'] is not False or execution['execution_policy']!='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET':raise ValueError('Action-free frozen Open control required')
    if len(execution['decisions'])!=1 or len(execution['executions'])!=1 or [r['session'] for r in execution['daily']]!=calendar:raise ValueError('Complete saved account denominators required')
    decision=execution['decisions'][0];fill=execution['executions'][0];source=schedule[0];targets=source['targets'];ids=sorted(targets)
    if len(ids)!=8 or any(not exact(decision[k],source[k]) for k in ('decision_date','execution_date','targets')) or type(decision['target_k']) is not int or decision['target_k']!=8 or decision['status']!='FROZEN':raise ValueError('Unmodified original eight target weights required')
    weights={s:risk.number(targets[s]['target_weight']) for s in ids}
    if any(w<=0 for w in weights.values()) or abs(sum(weights.values())-1)>Decimal('1e-12'):raise ValueError('Original positive weights must already sum to one')
    chains=risk_chains_by_decision[calendar[0]]
    if set(chains)!=set(ids):raise ValueError('Original risk coordinate denominator required')
    cash=risk.number(contract['initial_cash_usd']);initial=cash;buffer=risk.number(contract['minimum_cash_buffer_usd']);rate=risk.number(contract['transaction_cost_bps'])/10000
    if cash!=25000 or buffer!=100 or rate!=Decimal('.001'):raise ValueError('Original 25000/100/10bps control contract required')
    for key,value in dict(max_single_weight='.45',min_single_weight='.05',top_weight_cap='.8',minimum_effective_n_ratio='.7',risk_chain_top1_cap='.55').items():
        if risk.number(contract[key])!=Decimal(value):raise ValueError('Original five-risk observations cannot be relabelled')
    def marks(day,field):
        if set(prices[day])!=set(ids):raise ValueError('Complete independent eight price slots required')
        out={s:risk.number(prices[day][s][field]) for s in ids}
        if any(v<=0 for v in out.values()) or any(prices[day][s]['ticker']!=targets[s]['ticker'] for s in ids):raise ValueError('Positive original ticker marks required')
        return out
    def compare_marks(saved,expected):
        if set(saved)!=set(expected):raise ValueError('Complete saved mark slots required')
        for s,v in expected.items():same_amount(saved[s],v)
    def projection(wanted,mark):
        fee=sum((q*mark[s]*rate for s,q in wanted.items()),Decimal(0))
        return cash-sum((q*mark[s] for s,q in wanted.items()),Decimal(0))-fee,fee
    close=marks(calendar[0],'close');wanted={s:int(((cash-buffer)*weights[s]/close[s]).to_integral_value(rounding=ROUND_FLOOR)) for s in ids};floor=dict(wanted)
    while all(q>=1 for q in wanted.values()) and projection(wanted,close)[0]<buffer-Decimal('1e-8'):
        choices=[s for s,q in wanted.items() if q>1]
        if not choices:break
        wanted[max(choices,key=lambda s:(close[s],s))]-=1
    if projection(wanted,close)[0]<buffer-Decimal('1e-8'):
        wanted=dict(floor)
        while projection(wanted,close)[0]<buffer-Decimal('1e-8'):
            choices=[s for s,q in wanted.items() if q>0]
            if not choices:raise ValueError('No fee-feasible floor exists')
            wanted[max(choices,key=lambda s:(close[s],s))]-=1
    if not exact(counts(decision['shares_before']),{}) or not exact(counts(decision['desired_shares']),wanted) or not exact(risk.signed_lots(decision['delta']),wanted):raise ValueError('Independent Close floor/frozen deltas differ')
    if decision['risk_chains']!=chains or decision['risk_chain_observation_dates']!={s:calendar[0] for s in ids}:raise ValueError('Decision risk observation clock differs')
    projected,fee=projection(wanted,close);same_amount(decision['cash_before_usd'],cash);same_amount(decision['projected_cash_usd'],projected);same_amount(decision['projected_fees_usd'],fee);compare_marks(decision['prices'],close)
    observed_risk(decision['decision_risk'],wanted,close,chains,contract)
    opened=marks(calendar[1],'open');projected,fee=projection(wanted,opened);accepted=projected>=buffer-Decimal('1e-8')
    if fill['session']!=calendar[1] or fill['decision_date']!=calendar[0] or not exact(counts(fill['shares_before']),{}) or not exact(counts(fill['desired_shares']),wanted) or not exact(risk.signed_lots(fill['frozen_delta']),wanted):raise ValueError('Frozen next-Open basket changed')
    if fill['status']!=('FILLED' if accepted else 'REJECTED') or fill['failure_reasons']!=([] if accepted else ['CASH_BUFFER']):raise ValueError('Control gate must be financial only, not risk')
    same_amount(fill['cash_before_usd'],cash);same_amount(fill['projected_cash_usd'],projected);same_amount(fill['projected_fees_usd'],fee);compare_marks(fill['prices'],opened);observed_risk(fill['risk'],wanted,opened,chains,contract)
    held=dict(wanted) if accepted else {};after=projected if accepted else cash;fees=fee if accepted else Decimal(0)
    if not exact(counts(fill['shares_after']),held):raise ValueError('Atomic basket/zero slots changed')
    same_amount(fill['cash_after_usd'],after)
    if accepted:same_amount(fill['accounting_error_usd'],Decimal(0))
    trades=[dict(session=calendar[1],security_id=s,ticker=targets[s]['ticker'],share_delta=q,price_usd=opened[s],transaction_cost_usd=q*opened[s]*rate) for s,q in wanted.items() if accepted and q]
    if len(trades)!=len(execution['trades']):raise ValueError('Zero deltas cannot produce trades')
    for a,b in zip(execution['trades'],trades):
        if type(a['share_delta']) is not int:raise ValueError('Exact signed integer trade quantity required')
        for k,v in b.items():
            if k in ('price_usd','transaction_cost_usd'):same_amount(a[k],v)
            elif a[k]!=v:raise ValueError('Trade identity/clock/delta differs')
    values=[];peak=initial;drawdown=Decimal(0);cash_days=0
    for i,row in enumerate(execution['daily']):
        shares=held if i else {};balance=after if i else initial;day=calendar[i];mark=marks(day,'close');actual_marks={s:mark[s] for s in shares}
        if not exact(counts(row['shares']),shares) or row['tickers']!={s:targets[s]['ticker'] for s in shares} or row['risk_chains']!={s:chains[s] for s in shares} or row['risk_chain_observation_dates']!={s:calendar[0] for s in shares}:raise ValueError('Daily slots/identity/observation changed')
        compare_marks(row['prices'],actual_marks);observed_risk(row['risk'],shares,actual_marks,chains,contract)
        total=balance+sum((q*mark[s] for s,q in shares.items()),Decimal(0));same_amount(row['cash_usd'],balance);same_amount(row['total_value_usd'],total)
        peak=max(peak,total);drawdown=max(drawdown,1-total/peak);values.append(total);cash_days+=not any(shares.values())
    summary=execution['summary']
    if type(summary['session_count']) is not int or summary['session_count']!=127 or type(summary['all_cash_session_count']) is not int or summary['all_cash_session_count']!=cash_days or not exact(summary['k_path'],[8]):raise ValueError('Summary slots/calendar differ')
    same_amount(summary['terminal_value_usd'],values[-1]);same_amount(summary['path_return_net'],values[-1]/initial-1);same_amount(summary['path_max_drawdown'],drawdown)
    return dict(schema='FIXED_CONTROL_127_SESSION_INDEPENDENT_DECIMAL_AUDIT_V1',session_count=127,target_slot_count=8,positive_final_holdings=sum(q>0 for q in held.values()),zero_share_security_ids=sorted(s for s,q in held.items() if q==0),filled=accepted,rejected=not accepted,trade_count=len(trades),fees_usd=str(fees),terminal_value_usd=str(values[-1]),risk_is_order_gate=False,engine_called=False,source_authenticity_verified=False,point_in_time_verified=False,promotion_allowed=False)
