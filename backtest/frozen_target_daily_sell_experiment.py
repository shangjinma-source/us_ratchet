"""Independent cash paths under frozen baseline monthly absolute targets.

This does not rerun or represent capital-adaptive portfolio selection.
"""
from copy import deepcopy
from fractions import Fraction

from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4


def run_frozen_targets(*, assembled, ohlc, baseline, initial_cash, mode):
    from backtest.current_quantity_v2_daily_sell_book import run_daily_sell_book

    frozen = {}
    for row in baseline['provider_audit']:
        selection = row.get('selection')
        if selection is not None:
            day = selection['decision_date']
            if day in frozen:
                raise ValueError('DUPLICATE_FROZEN_MONTH')
            frozen[day] = deepcopy(selection['target_quantities'])
    if set(frozen) != {row['decision_date'] for row in assembled['monthly_inputs']}:
        raise ValueError('FROZEN_MONTH_COVERAGE_MISMATCH')

    def frozen_decision(*, decision_date, account_state, **unused):
        equity = Fraction(account_state['cash']) + sum(
            (quantity * Fraction(assembled['close_prices'][sid][decision_date])
             for sid, quantity in account_state['shares'].items() if quantity), Fraction(0))
        return dict(decision_date=decision_date, target_quantities=deepcopy(frozen[decision_date]),
                    investable_equity=str(equity), method='FROZEN_BASELINE_ABSOLUTE_TARGET_NO_SEARCH')

    provider = build_monthly_quantity_provider_v4(
        session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
        close_prices=assembled['close_prices'], actions=assembled['provider_actions'], decide=frozen_decision)
    audit = []

    def differences(**arguments):
        result = provider(**arguments)
        if result['status'] != 'READY' or result.get('action') == 'WAIT_POST_ACTION_MARK':
            audit.append(deepcopy(result))
            return result
        held, target = arguments['state']['shares'], result['target_shares']
        day, active = arguments['decision_date'], arguments['active_date']
        orders = []
        for sid in sorted(set(held) | set(target)):
            delta = target.get(sid, 0) - held.get(sid, 0)
            if delta:
                orders.append(dict(id='nextopen:'+day+':'+sid, security_id=sid,
                                   side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                                   decision_date=day, active_date=active,
                                   decision_mark=assembled['close_prices'][sid][day]))
        result = dict(result, orders=orders, reserved_cash='0',
                      unreserved_cash=arguments['state']['cash'], wait_cash=[],
                      action='FROZEN_TARGET_DIFFERENCES', time_in_force='DAY_MODEL')
        audit.append(deepcopy(result))
        return result

    result = run_daily_sell_book(
        session_dates=assembled['session_dates'], ohlc=ohlc, initial_cash=initial_cash,
        fee_bps='0', slippage_bps='0', mode=mode, order_provider=differences,
        events=assembled['actions'], cash_stock_merger_events=assembled['cash_stock_merger_events'],
        fractional_settlements=assembled['fractional_settlements'],
        price_source_references=assembled['price_source_references'],
        distribution_events=assembled['distribution_events'],
        distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],
        account_model=assembled.get('account_model'))
    result.update(provider_audit=audit, strategy_search_calls=0,
                  experiment_scope='FROZEN_B0_ABSOLUTE_TARGET_PATH_EXECUTION_COUNTERFACTUAL',
                  adaptive_strategy_performance=False, independent_oos=False,
                  point_in_time_certified=False, current_minute_policy_performance=False)
    return result
