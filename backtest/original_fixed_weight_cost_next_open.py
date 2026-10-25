"""Original fixed-weight conditional control, explicit full-next-open adapter fork.
Derived from continuous_guided_cost_full_next_open; same provider and book.
No optimizer, network, or automatic historical execution. Not original ratchet replay.
"""
from copy import deepcopy
from fractions import Fraction
VERSION = "ORIGINAL_FIXED_WEIGHT_COST_NEXT_OPEN_V1"
from backtest.continuous_guided_cost_monthly_provider import build_cost_monthly_quantity_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book


def number(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_NUMBER')
    value = Fraction(str(value))
    if value < 0:
        raise ValueError('NEGATIVE_NUMBER')
    return value


def drawdown_summary(equities):
    peak = number(equities[0]['equity'])
    peak_day = equities[0]['date']
    worst = Fraction(0)
    trough = peak_day
    underwater_start = None
    longest = 0
    completed = []
    for index, row in enumerate(equities):
        value = number(row['equity'])
        if value >= peak:
            if underwater_start is not None:
                completed.append(index - underwater_start)
            underwater_start = None
            peak, peak_day = value, row['date']
        else:
            if underwater_start is None:
                underwater_start = index
            longest = max(longest, index - underwater_start + 1)
            loss = 1 - value / peak if peak else Fraction(0)
            if loss > worst:
                worst, trough = loss, row['date']
    return dict(maximum_close_drawdown=str(worst), trough_date=trough,
                longest_underwater_observations=longest,
                recovered_at_end=underwater_start is None,
                current_underwater_observations=0 if underwater_start is None else len(equities)-underwater_start,
                completed_recovery_observations=completed)


def run_original_fixed_weight_next_open(*, weights, assembled, ohlc, initial_cash, fee_bps, slippage_bps, progress=None):
    """Monthly targets use own current equity, exact original weights and floor.
    No weight normalization, residual redistribution, or risk overlay. Next-open
    sells, immediate proceeds, slippage/fees and cash rationing match the book.
    """
    frozen_weights = {sid: number(value) for sid, value in weights.items()}
    if not frozen_weights or any(not value for value in frozen_weights.values()):
        raise ValueError('POSITIVE_ORIGINAL_WEIGHTS_REQUIRED')
    if abs(sum(frozen_weights.values())-1) > Fraction(1, 10**12):
        raise ValueError('ORIGINAL_WEIGHT_SUM_REQUIRED')
    if (str(fee_bps), str(slippage_bps)) not in {('0', '5'), ('1', '10')}:
        raise ValueError('DECLARED_COST_SCENARIO_REQUIRED')
    if any(str(plan['search_arguments']['fee_bps']) != str(fee_bps) for plan in assembled['monthly_inputs']):
        raise ValueError('MONTHLY_EXECUTION_FEE_MISMATCH')
    selection_account_states=[]
    def decide(**arguments):
        selection_account_states.append(deepcopy(arguments))
        if progress is not None:progress(dict(stage='MONTHLY_SEARCH_STARTED',decision_date=arguments['search_arguments']['decision_date'],account_state=deepcopy(arguments['account_state'])))
        prices = {}
        for quote in arguments['valuation_quotes']:
            sid = quote['security_id']
            if sid in prices or quote['as_of'] != arguments['decision_date']:
                raise ValueError('DUPLICATE_OR_WRONG_DATE_QUOTE')
            prices[sid] = number(quote['price'])
            if not prices[sid]: raise ValueError('POSITIVE_MARK_REQUIRED')
        state = arguments['account_state']
        if not set(frozen_weights) <= prices.keys():
            raise ValueError('ORIGINAL_WEIGHT_QUOTE_MISSING')
        equity = number(state['cash']) + sum((q * prices[sid] for sid,q in state['shares'].items() if q), Fraction(0))
        target = {sid: int(equity * weight // prices[sid]) for sid,weight in frozen_weights.items()}
        notional = sum((target[sid]*prices[sid] for sid in target), Fraction(0))
        if notional > equity: raise ValueError('FIXED_WEIGHT_TARGET_EXCEEDS_EQUITY')
        result = dict(target_quantities=target, investable_equity=str(equity),
            original_weights={sid:str(value) for sid,value in frozen_weights.items()},
            weights_normalized=False, search_calls=0, method=VERSION)
        if progress is not None:progress(dict(stage='MONTHLY_SEARCH_COMPLETED',decision_date=arguments['search_arguments']['decision_date'],target=result.get('target_quantities')))
        return result
    provider = build_cost_monthly_quantity_provider(
        session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
        close_prices=assembled['close_prices'], actions=assembled['provider_actions'],
        decide=decide)
    audit = []

    def full_difference(**kwargs):
        result = provider(**kwargs)
        if progress is not None:
            progress(dict(decision_date=kwargs['decision_date'],active_date=kwargs['active_date'],
                          status=result['status'],selection_completed=result.get('selection') is not None))
        if result['status'] != 'READY' or result.get('action') == 'WAIT_POST_ACTION_MARK':
            audit.append(deepcopy(result))
            return result
        # Preserve target evolution/rights guards, discard legacy prior-close
        # cash clipping. This adapter sees no next-session price.
        shares = kwargs['state']['shares']
        target = result['target_shares']
        orders = []
        for sid in sorted(set(shares) | set(target)):
            delta = target.get(sid,0)-shares.get(sid,0)
            if not delta: continue
            mark = number(assembled['close_prices'][sid][kwargs['decision_date']])
            orders.append(dict(id='nextopen:'+kwargs['decision_date']+':'+sid,
                security_id=sid, side='BUY' if delta>0 else 'SELL',quantity=abs(delta),
                decision_date=kwargs['decision_date'],active_date=kwargs['active_date'],decision_mark=str(mark)))
        result = dict(result, orders=orders, reserved_cash='0',
                      unreserved_cash=kwargs['state']['cash'], wait_cash=[],
                      action='NEXT_OPEN_TARGET_DIFFERENCES' if orders else 'NO_ACTION',
                      time_in_force='NEXT_OPEN_MODEL',
                      sizing_note='Open cash rationing occurs only in execution; no proceeds reserved at Close.')
        audit.append(deepcopy(result))
        return result

    result = run_next_open_book(session_dates=assembled['session_dates'],ohlc=ohlc,
        initial_cash=initial_cash,fee_bps=fee_bps,slippage_bps=slippage_bps,
        order_provider=full_difference,events=assembled['actions'],
        cash_stock_merger_events=assembled['cash_stock_merger_events'],
        fractional_settlements=assembled['fractional_settlements'],
        price_source_references=assembled['price_source_references'],
        distribution_events=assembled['distribution_events'],
        distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],
        account_model=assembled.get('account_model'))
    equity=[dict(date=assembled['session_dates'][0],equity=str(number(initial_cash)))]+result['daily_ledger']
    result.update(selection_account_states=selection_account_states,provider_audit=audit,drawdown=drawdown_summary(equity),
        selection_method=VERSION, search_calls=0, full_original_strategy_replay=False,
        pullback_performance=False, independent_oos=False, point_in_time_certified=False,
        total_return=str(number(equity[-1]['equity'])/number(initial_cash)-1) if result['status']=='COMPLETE' else None)
    return result


