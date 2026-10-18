"""Decimal audit of a saved, action-free frozen-order account; no engine imports.

Inputs must be independently source-bound by the caller. This checks accounting
and risk decisions, not the optimizer's integer search or security authenticity.
"""
from decimal import Decimal, localcontext


def number(value):
    if type(value) not in (int, float, Decimal):
        raise ValueError('Nonboolean finite numeric value required')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Finite number required')
    return result


def equal_amount(actual, expected):
    if abs(number(actual) - expected) > Decimal('1e-7'):
        raise ValueError('Independent accounting amount differs')


def lots(value):
    if type(value) is not dict or any(type(q) is not int or q < 1 for q in value.values()):
        raise ValueError('Positive integer security lots required')
    return dict(value)


def risk_checks(shares, marks, chains, contract):
    if not shares:
        return {'ALL_CASH': False}
    weights = {sid: number(q) * marks[sid] for sid, q in lots(shares).items()}
    total = sum(weights.values())
    weights = {sid: v / total for sid, v in weights.items()}
    ordered = sorted(weights.values(), reverse=True)
    groups = {}
    for sid, weight in weights.items():
        groups[chains[sid]] = groups.get(chains[sid], Decimal(0)) + weight
    tolerance = Decimal('1e-9')
    return dict(MAX_SINGLE_WEIGHT=ordered[0] <= number(contract['max_single_weight']) + tolerance,
        MIN_SINGLE_WEIGHT=ordered[-1] >= number(contract['min_single_weight']) - tolerance,
        SECURITY_TOP3_WEIGHT=sum(ordered[:3]) <= number(contract['top_weight_cap']) + tolerance,
        MINIMUM_EFFECTIVE_N=1 / sum(w*w for w in ordered) >= number(contract['minimum_effective_n_ratio']) * len(ordered) - tolerance,
        RISK_CHAIN_TOP1_WEIGHT=max(groups.values()) <= number(contract['risk_chain_top1_cap']) + tolerance)


def verify_risk(saved, shares, marks, chains, contract):
    checks = risk_checks(shares, marks, chains, contract)
    if set(saved['checks']) != set(checks) or any(saved['checks'][k] is not v for k,v in checks.items()) or saved['all_passed'] is not all(checks.values()):
        raise ValueError('Saved risk checks differ from independent risks')
    if not shares:
        if set(saved) != {'checks','all_passed'}: raise ValueError('All cash risk payload differs')
        return
    total=sum(number(q)*marks[sid] for sid,q in shares.items())
    weights={sid:number(q)*marks[sid]/total for sid,q in shares.items()}
    if set(saved['actual_weights']) != set(weights): raise ValueError('Risk weight identities differ')
    for sid,value in weights.items(): equal_amount(saved['actual_weights'][sid],value)
    ordered=sorted(weights.values(),reverse=True); groups={}
    for sid,value in weights.items(): groups[chains[sid]]=groups.get(chains[sid],Decimal(0))+value
    for key,value in dict(top1_weight=ordered[0],minimum_single_weight=ordered[-1],top3_weight=sum(ordered[:3]),
        effective_n=1/sum(w*w for w in ordered),risk_chain_top1_weight=max(groups.values())).items():
        equal_amount(saved[key],value)


def signed_lots(value):
    if type(value) is not dict or any(type(q) is not int for q in value.values()):
        raise ValueError('Exact signed integer deltas required')
    return value


def audit(*, execution, calendar, schedule, prices, risk_chains_by_decision, contract):
    """prices[session][security_id] has positive open/close and observed ticker."""
    with localcontext() as context:
        context.prec = 50
        return _audit(execution, calendar, schedule, prices, risk_chains_by_decision, contract)


def _audit(execution, calendar, schedule, prices, risk_chains_by_decision, contract):
    if not calendar or calendar != sorted(set(calendar)) or set(prices) != set(calendar):
        raise ValueError('Complete ordered independent calendar required')
    if execution['corporate_actions'] or execution['identity_events'] or execution['dividend_modelled'] is not False:
        raise ValueError('This audit requires explicitly action-free interval')
    if execution['execution_policy'] != 'DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET':
        raise ValueError('Frozen next Open policy required')
    if [r['session'] for r in execution['daily']] != calendar or len(execution['decisions']) != len(schedule):
        raise ValueError('Exact daily and decision denominators required')
    decisions = {}
    for source, saved in zip(schedule, execution['decisions']):
        day = source['decision_date']
        if day in decisions or day not in calendar or calendar.index(day)+1 >= len(calendar):
            raise ValueError('Unique executable decision required')
        if source['execution_date'] != calendar[calendar.index(day)+1]:
            raise ValueError('Decision must precede next observed Open')
        if any(saved[k] != source[k] for k in ('decision_date','execution_date','targets')):
            raise ValueError('Saved target schedule differs')
        decisions[day] = saved
    if list(decisions) != sorted(decisions) or next(iter(decisions)) != calendar[0]:
        raise ValueError('Ordered schedule begins at initial cash date')
    executions = {r['session']: r for r in execution['executions']}
    wanted_dates = [r['execution_date'] for r in decisions.values() if r['status'] == 'FROZEN']
    if len(executions) != len(execution['executions']) or list(executions) != wanted_dates:
        raise ValueError('Exactly one execution for each frozen plan required')
    cash = number(contract['initial_cash_usd']); initial = cash
    fee_rate = number(contract['transaction_cost_bps']) / 10000
    buffer = number(contract['minimum_cash_buffer_usd'])
    if cash <= buffer or buffer < 0 or fee_rate < 0:
        raise ValueError('Positive initial investable cash and nonnegative fees required')
    shares = {}; chains = {}; chain_dates = {}; expected_trades = []; values = []; fees = Decimal(0); cash_days=0
    peak = cash; drawdown = Decimal(0); rejected = 0

    def marks(day, names, field):
        result = {sid: number(prices[day][sid][field]) for sid in names}
        if any(v <= 0 for v in result.values()):
            raise ValueError('Strictly positive independently supplied marks required')
        return result

    def assert_marks(saved, actual):
        if set(saved) != set(actual):
            raise ValueError('Full mark identity union differs')
        for sid, value in actual.items(): equal_amount(saved[sid], value)

    def projection(desired, actual_marks):
        delta = {sid: desired.get(sid,0)-shares.get(sid,0) for sid in sorted(set(desired)|set(shares))}
        cost = sum((abs(q)*actual_marks[sid]*fee_rate for sid,q in delta.items()), Decimal(0))
        return delta, cost, cash-sum((q*actual_marks[sid] for sid,q in delta.items()),Decimal(0))-cost

    for row in execution['daily']:
        day = row['session']
        if day in executions:
            fill = executions[day]; decision = decisions[fill['decision_date']]
            if decision['execution_date'] != day or decision['status'] != 'FROZEN': raise ValueError('Fill refers to another frozen decision clock')
            desired = lots(decision['desired_shares'])
            actual_marks = marks(day, set(shares)|set(desired), 'open')
            delta, cost, projected = projection(desired, actual_marks)
            if lots(fill['shares_before']) != shares or lots(decision['shares_before']) != shares or lots(fill['desired_shares']) != desired or signed_lots(fill['frozen_delta']) != delta or signed_lots(decision['delta']) != delta:
                raise ValueError('Frozen shares or delta changed before Open')
            equal_amount(fill['cash_before_usd'],cash); assert_marks(fill['prices'],actual_marks)
            equal_amount(fill['projected_cash_usd'],projected); equal_amount(fill['projected_fees_usd'],cost)
            checks = risk_checks(desired,actual_marks,chains,contract)
            verify_risk(fill['risk'],desired,actual_marks,chains,contract)
            failures = [k for k,v in checks.items() if not v]
            if projected < buffer-Decimal('1e-8'): failures.append('CASH_BUFFER')
            if fill['failure_reasons'] != failures or fill['status'] != ('REJECTED' if failures else 'FILLED'):
                raise ValueError('Independent atomic fill or rejection reason differs')
            if failures: rejected += 1
            else:
                equal_amount(fill['accounting_error_usd'],Decimal(0))
                cash = projected; shares = desired; fees += cost
                for sid, quantity in delta.items():
                    if quantity:
                        expected_trades.append(dict(session=day,security_id=sid,ticker=prices[day][sid]['ticker'],share_delta=quantity,
                            price_usd=actual_marks[sid],transaction_cost_usd=abs(quantity)*actual_marks[sid]*fee_rate))
            if lots(fill['shares_after']) != shares: raise ValueError('Partial fill or rejected share mutation')
            equal_amount(fill['cash_after_usd'],cash)
        if day in decisions:
            decision = decisions[day]
            for sid,target in decision['targets'].items():
                if target['ticker'] != prices[day][sid]['ticker']: raise ValueError('Decision ticker differs')
                chains[sid] = risk_chains_by_decision[day][sid]
                chain_dates[sid] = day
            actual_marks = marks(day,set(shares)|set(decision['targets']),'close')
            if lots(decision['shares_before']) != shares: raise ValueError('Decision preceding holdings differ')
            if type(decision['target_k']) is not int or decision['target_k'] != len(decision['targets']): raise ValueError('Decision cardinality differs')
            if decision['risk_chains'] != {sid:chains[sid] for sid in actual_marks} or decision['risk_chain_observation_dates'] != {sid:chain_dates[sid] for sid in actual_marks}:
                raise ValueError('Decision risk observation coordinates differ')
            equal_amount(decision['cash_before_usd'],cash); assert_marks(decision['prices'],actual_marks)
            if decision['status'] == 'FROZEN':
                desired = lots(decision['desired_shares'])
                if set(desired) != set(decision['targets']): raise ValueError('Frozen composition differs')
                delta,cost,projected = projection(desired,actual_marks)
                if signed_lots(decision['delta']) != delta or projected < buffer-Decimal('1e-8') or not all(risk_checks(desired,actual_marks,chains,contract).values()):
                    raise ValueError('Decision frozen basket fails independent checks')
                verify_risk(decision['decision_risk'],desired,actual_marks,chains,contract)
                equal_amount(decision['projected_cash_usd'],projected); equal_amount(decision['projected_fees_usd'],cost)
            elif decision['status'] != 'NO_PLAN': raise ValueError('Unknown decision status')
            elif {'desired_shares','delta','decision_risk','projected_cash_usd','projected_fees_usd'} & set(decision):
                raise ValueError('NO_PLAN cannot contain a frozen basket')
        actual_marks = marks(day,shares,'close')
        if lots(row['shares']) != shares or row['tickers'] != {sid:prices[day][sid]['ticker'] for sid in shares}:
            raise ValueError('Daily holdings or ticker differs')
        verify_risk(row['risk'],shares,actual_marks,chains,contract)
        if row['risk_chains'] != {sid:chains[sid] for sid in shares} or row['risk_chain_observation_dates'] != {sid:chain_dates[sid] for sid in shares}:
            raise ValueError('Daily risk observations differ')
        cash_days += not shares
        assert_marks(row['prices'],actual_marks); equal_amount(row['cash_usd'],cash)
        value = cash + sum((shares[sid]*p for sid,p in actual_marks.items()),Decimal(0))
        equal_amount(row['total_value_usd'],value)
        peak=max(peak,value); drawdown=max(drawdown,1-value/peak); values.append(value)
    if len(expected_trades) != len(execution['trades']): raise ValueError('Complete trade denominator differs')
    for expected,actual in zip(expected_trades,execution['trades']):
        if type(actual['share_delta']) is not int: raise ValueError('Trade quantity must be exact signed integer')
        for key,value in expected.items():
            if key in ('price_usd','transaction_cost_usd'): equal_amount(actual[key],value)
            elif actual[key] != value: raise ValueError('Trade coordinate or quantity differs')
    summary=execution['summary']
    if type(summary['session_count']) is not int or summary['session_count'] != len(calendar) or type(summary['all_cash_session_count']) is not int or summary['all_cash_session_count'] != cash_days:
        raise ValueError('Summary calendar or cash denominator differs')
    if summary['k_path'] != [len(r['targets']) for r in schedule] or any(type(k) is not int for k in summary['k_path']): raise ValueError('Summary cardinality path differs')
    equal_amount(summary['terminal_value_usd'],values[-1]); equal_amount(summary['path_return_net'],values[-1]/initial-1)
    equal_amount(summary['path_max_drawdown'],drawdown)
    return dict(schema='ACTION_FREE_FROZEN_ACCOUNT_DECIMAL_AUDIT_V1',session_count=len(calendar),decision_count=len(decisions),
        execution_count=len(executions),rejected_count=rejected,trade_count=len(expected_trades),fees_usd=str(fees),terminal_cash_usd=str(cash),
        terminal_value_usd=str(values[-1]),terminal_shares=shares,engine_called=False,integer_optimizer_independently_recomputed=False,
        corporate_actions_supported=False,source_authenticity_verified=False,point_in_time_verified=False,promotion_allowed=False)
