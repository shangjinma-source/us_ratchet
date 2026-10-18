"""Pure whole-share paper book; frozen plans are data, never selector callbacks.

Conditional supplied Open/Close basis is not broker execution or authenticated
corporate-action accounting. Same engine can consume rule/control/variable-k
plans, but it performs no candidate search or price-source IO.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import math


def require(ok,message):
    if not ok:raise ValueError(message)


def amount(value):
    require(type(value) in (str,int,float),'Typed rational money, bool denied')
    if type(value) is float:require(math.isfinite(value),'Finite money')
    try:parsed=Fraction(str(value))
    except (ValueError,ZeroDivisionError) as error:raise ValueError('Explicit rational money') from error
    require(parsed>=0,'Nonnegative money')
    return parsed



def cash_event_amount(value):
    require(type(value) in (str,int,float),'Typed signed cash event, bool denied')
    if type(value) is float:require(math.isfinite(value),'Finite external cash event')
    try:return Fraction(str(value))
    except (ValueError,ZeroDivisionError) as error:raise ValueError('Explicit signed rational cash event') from error


def price_at(prices,session,sid):
    row=prices.get(session,{})
    if sid not in row or row[sid] is None:return None
    value=amount(row[sid]);require(value>0,'Positive supplied price')
    return value


def diagnostics(holdings,marks,metadata,risk):
    notionals={sid:float(q*marks[sid]) for sid,q in sorted(holdings.items()) if q>0}
    if not notionals:return dict(status='NO_STOCK_HOLDINGS',weights={},all_passed=None)
    total=sum(notionals.values());require(math.isfinite(total) and total>0,'Finite stock value')
    weights={sid:value/total for sid,value in notionals.items()};ordered=sorted(weights.values(),reverse=True)
    chains={}
    for sid,weight in weights.items():
        chain=metadata[sid]['risk_chain'];chains[chain]=chains.get(chain,0.)+weight
    neff=1/sum(value*value for value in ordered)
    checks=dict(max_single_weight=ordered[0]<=risk['max_single_weight']+1e-9,
        min_single_weight=ordered[-1]>=risk['min_single_weight']-1e-9,
        top_three_cap=sum(ordered[:3])<=risk['top_three_cap']+1e-9,
        min_neff_ratio=neff>=risk['min_neff_ratio']*len(weights)-1e-9,
        chain_cap=max(chains.values())<=risk['chain_cap']+1e-9)
    unique=len({metadata[sid]['issuer_id'] for sid in weights})==len(weights)
    return dict(status='FIVE_ORIGINAL_FLOAT_NOTIONAL_CHECKS',weights=weights,checks=checks,
        issuer_unique=unique,all_passed=all(checks.values()) and unique,effective_n=neff,
        risk_is_diagnostic_not_daily_rebalance=True)


def simulate_paper_book(*,calendar,open_prices,close_prices,metadata,initial_shares,
                        initial_cash,fee_bps,minimum_cash_buffer,decisions,cash_events,
                        risk_parameters,enforce_initial_target_risk,declared_price_basis):
    """Weights size at next Open with fixed two-sided fee reserve; shares stay fixed.

    Target shares=floor(weight*(Open equity-buffer-2*fee*Open equity)/Open price).
    Actual fees are charged only on actual sells/buys. Unused reserve stays cash.
    Explicit shares are never silently resized. Insufficient cash blocks the
    entire rebalance atomically; no partial sell/buy commits or automatic retry.
    """
    require(type(calendar) is list and calendar and calendar==sorted(set(calendar))
            and all(type(day) is str and date.fromisoformat(day).isoformat()==day for day in calendar),'Explicit ordered common observation calendar')
    require(type(open_prices) is dict and type(close_prices) is dict and type(metadata) is dict and metadata,'Explicit price/identity maps')
    require(all(type(sid) is str and sid and type(row) is dict and set(row)=={'ticker','issuer_id','risk_chain'}
                and all(type(value) is str and value for value in row.values()) for sid,row in metadata.items()),'Explicit SID/issuer/risk metadata, never invented')
    require(len({row['ticker'] for row in metadata.values()})==len(metadata),'Distinct explicit ticker domain')
    require(type(initial_shares) is dict and set(initial_shares)<=set(metadata)
            and all(type(q) is int and q>=0 for q in initial_shares.values()),'Initial nonnegative whole shares')
    require(type(enforce_initial_target_risk) is bool,'Explicit candidate/control initial gate')
    require(type(declared_price_basis) is str and declared_price_basis.startswith('CONDITIONAL_'),'Explicit conditional price basis')
    keys={'max_single_weight','min_single_weight','top_three_cap','min_neff_ratio','chain_cap'}
    require(type(risk_parameters) is dict and set(risk_parameters)==keys
            and all(type(value) in (int,float) and math.isfinite(value) and 0<=value<=1 for value in risk_parameters.values()),'Five unchanged risk checks')
    cash=amount(initial_cash);buffer=amount(minimum_cash_buffer);fee=amount(fee_bps)/10000
    require(fee<Fraction(1,2) and cash>=0,'Explicit research fee rate0<=f<0.5/cash')
    shares={sid:q for sid,q in initial_shares.items() if q>0};plans={};events={};ids=set()
    require(type(decisions) is list and type(cash_events) is list,'Frozen plans/events as explicit data lists')
    for plan in decisions:
        require(type(plan) is dict and set(plan) in ({'id','decision_date','target_shares'},{'id','decision_date','target_weights'}),'Closed frozen target plan')
        require(type(plan['id']) is str and plan['id'] and plan['id'] not in ids,'Unique plan/event ID');ids.add(plan['id'])
        day=plan['decision_date'];require(day in calendar and day not in plans,'One frozen target per declared decision session')
        target=plan.get('target_shares',plan.get('target_weights'))
        require(type(target) is dict and set(target)<=set(metadata),'Full supplied target SID keys')
        if 'target_shares' in plan:require(all(type(q) is int and q>=0 for q in target.values()),'Whole target shares')
        else:require(target and all(amount(value)>0 for value in target.values()) and sum((amount(value) for value in target.values()),Fraction(0))<=1,'Positive target weights sum<=1, residual stays cash')
        plans[day]=deepcopy(plan)
    for event in cash_events:
        require(type(event) is dict and set(event)=={'id','session','amount'} and event['session'] in calendar,'Explicit once-only cash event')
        require(type(event['id']) is str and event['id'] and event['id'] not in ids,'Unique plan/event ID');ids.add(event['id'])
        events.setdefault(event['session'],[]).append(dict(id=event['id'],amount=cash_event_amount(event['amount'])))
    rows=[];executions=[];pending=None;previous_equity=None;growth=Fraction(1);consumed=[]
    def result(status,reason=None):
        return dict(schema='PURE_CONTINUOUS_PAPER_WHOLE_BOOK_V1',status=status,reason=reason,daily_rows=rows,
            executions=executions,final_shares=shares,final_cash=str(cash),pending_plan=pending,
            consumed_cash_event_ids=consumed,price_basis=declared_price_basis,
            conditional_paper_only=True,complete_split_dividend_accounting_verified=False,
            execution_price_basis_authenticated=False,current_adoption_allowed=False,orders_created=False,
            candidate_search_performed=False,cagr=None,annualization_performed=False,
            performance_measure='FLOW_ADJUSTED_DAILY_CHAIN_TWR_WITHOUT_ANNUALIZATION',
            cash_flow_return_warning='End/start equity with deposits or withdrawals is not strategy return',
            root_method_reference=dict(path='research_contracts/continuous_portfolio_book_method_20261013_v1.json',sha256='868e8a8df29827709e284e2c692043fc85900197c72d293babaf14194cfd6f93'),
            parameters_authority='ROOT_RESEARCH_MECHANICS_NOT_USER_PREFERENCE')
    for day in calendar:
        required=set(shares)
        if pending:
            target=pending.get('target_shares',pending.get('target_weights'))
            required|={sid for sid,value in target.items() if amount(value)>0}
        opened={sid:price_at(open_prices,day,sid) for sid in required}
        if any(value is None for value in opened.values()):return result('BLOCKED','NEXT_OBSERVED_OPEN_OR_HELD_POSITION_MARK_MISSING')
        opening_equity=cash+sum((q*opened[sid] for sid,q in shares.items()),Fraction(0))
        flow=sum((event['amount'] for event in events.get(day,[])),Fraction(0))
        if cash+flow<0:return result('BLOCKED','EXTERNAL_WITHDRAWAL_EXCEEDS_PRE_EXECUTION_CASH')
        if opening_equity+flow<=0:return result('BLOCKED','POST_FLOW_EQUITY_NONPOSITIVE_TWR_UNDEFINED')
        cash+=flow
        consumed.extend(event['id'] for event in events.get(day,[]))
        pretrade=opening_equity+flow
        if pending:
            if 'target_shares' in pending:target=dict(pending['target_shares']);capacity=None
            else:
                capacity=max(Fraction(0),pretrade-buffer-2*fee*pretrade)
                target={sid:int(capacity*amount(weight)//opened[sid]) for sid,weight in pending['target_weights'].items()}
            target={sid:q for sid,q in target.items() if q>0}
            notional_marks={sid:opened[sid] for sid in target}
            risk=diagnostics(target,notional_marks,metadata,risk_parameters)
            if enforce_initial_target_risk and risk['all_passed'] is not True:return result('BLOCKED','INITIAL_TARGET_CONCENTRATION_FAILED')
            sold={sid:shares.get(sid,0)-target.get(sid,0) for sid in set(shares)|set(target) if shares.get(sid,0)>target.get(sid,0)}
            bought={sid:target.get(sid,0)-shares.get(sid,0) for sid in set(shares)|set(target) if target.get(sid,0)>shares.get(sid,0)}
            sell_value=sum((q*opened[sid] for sid,q in sold.items()),Fraction(0));sell_fee=fee*sell_value
            buy_value=sum((q*opened[sid] for sid,q in bought.items()),Fraction(0));buy_fee=fee*buy_value
            after_sells=cash+sell_value-sell_fee;after=cash+sell_value-sell_fee-buy_value-buy_fee
            attempt=dict(plan_id=pending['id'],decision_date=pending['decision_date'],execution_date=day,
                target_shares=target,target_weights=pending.get('target_weights'),weight_sizing_capacity=str(capacity) if capacity is not None else None,
                sells=sold,buys=bought,sell_notional=str(sell_value),buy_notional=str(buy_value),sell_fee=str(sell_fee),buy_fee=str(buy_fee),
                cash_before=str(cash),cash_after_sells=str(after_sells),cash_after=str(after),initial_target_risk=risk)
            if after_sells<0 or after<buffer:
                executions.append(dict(attempt,status='BLOCKED_ATOMIC_NO_TRADES_COMMITTED'))
                return result('BLOCKED','TARGET_CASH_OR_BUFFER_INSUFFICIENT')
            shares=target;cash=after;executions.append(dict(attempt,status='COMMITTED_SELLS_THEN_BUYS'));pending=None
        closing={sid:price_at(close_prices,day,sid) for sid in shares}
        if any(value is None for value in closing.values()):return result('BLOCKED','HELD_POSITION_CLOSE_MISSING')
        equity=cash+sum((q*closing[sid] for sid,q in shares.items()),Fraction(0))
        require(pretrade>0 and equity>0,'Positive paper book equity')
        if previous_equity is None:growth*=equity/pretrade
        else:growth*=opening_equity/previous_equity*equity/pretrade
        rows.append(dict(session=day,cash=str(cash),shares=dict(shares),close_equity=str(equity),external_cash_flow=str(flow),
            cumulative_time_weighted_return=str(growth-1),daily_risk=diagnostics(shares,closing,metadata,risk_parameters)))
        previous_equity=equity
        if day in plans:pending=deepcopy(plans[day])
    return result('PENDING_NEXT_OBSERVATION_OPEN' if pending else 'COMPLETE_CONDITIONAL_PAPER_BOOK')
