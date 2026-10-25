"""Research book: reselect using this book's wealth, then apply a risk cap.

The optional stateful risk adapter belongs exclusively to this run. Results are
next-open diagnostics, not live limit-order or independently validated returns.
"""
from copy import deepcopy
from fractions import Fraction

from backtest.continuous_guided_capped_account_decision import decide_capped_account
from backtest.continuous_guided_cost_monthly_provider import build_cost_monthly_quantity_provider
from backtest.continuous_guided_cost_full_next_open import drawdown_summary
from backtest.current_quantity_v2_next_open_book import run_next_open_book


def run_capped_next_open(*, assembled, ohlc, initial_cash, fee_bps,
                        slippage_bps, risk=None, progress=None):
    if (str(fee_bps), str(slippage_bps)) not in {('0', '5'), ('1', '10')}:
        raise ValueError('DECLARED_COST_SCENARIO_REQUIRED')
    if any(str(p['search_arguments']['fee_bps']) != str(fee_bps)
           for p in assembled['monthly_inputs']):
        raise ValueError('MONTHLY_EXECUTION_FEE_MISMATCH')
    accounts, audit = [], []

    def decide(**arguments):
        accounts.append(deepcopy(arguments))
        if progress:
            progress(dict(stage='MONTHLY_SEARCH_STARTED', decision_date=arguments['decision_date']))
        selected = decide_capped_account(**arguments)
        if progress:
            progress(dict(stage='MONTHLY_SEARCH_COMPLETED', decision_date=arguments['decision_date'],
                          target=selected['target_quantities']))
        return selected

    provider = build_cost_monthly_quantity_provider(
        session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
        close_prices=assembled['close_prices'], actions=assembled['provider_actions'], decide=decide)

    def callback(**arguments):
        result = provider(**arguments)
        try:
            if result['status'] == 'READY':
                if result.get('action') == 'WAIT_POST_ACTION_MARK':
                    # A peak rule cannot silently skip a session or compare
                    # pre-action prices with post-action quantities.
                    if risk is not None:
                        raise ValueError('RISK_POST_ACTION_COORDINATES_REQUIRE_REVIEW')
                else:
                    day = arguments['decision_date']
                    ceiling = deepcopy(result['target_shares'])
                    target, diagnostics = ceiling, None
                    if risk is not None:
                        target, diagnostics = risk.apply(
                            day=day, month=result['target_decision_date'], target=deepcopy(ceiling),
                            closes={s: assembled['close_prices'][s][day] for s in ceiling},
                            adjustments=result.get('target_adjustments', ()))
                        if set(target) != set(ceiling) or any(
                            type(q) is not int or not 0 <= q <= ceiling[s] for s, q in target.items()
                        ):
                            raise ValueError('INVALID_RISK_TARGET')
                    orders = []
                    shares = arguments['state']['shares']
                    for security in sorted(set(shares) | set(target)):
                        delta = target.get(security, 0) - shares.get(security, 0)
                        if not delta:
                            continue
                        mark = Fraction(assembled['close_prices'][security][day])
                        if mark <= 0:
                            raise ValueError('POSITIVE_DECISION_MARK_REQUIRED')
                        orders.append(dict(id='cap:' + day + ':' + security, security_id=security,
                            side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                            decision_date=day, active_date=arguments['active_date'], decision_mark=str(mark)))
                    result.update(orders=orders, monthly_ceiling=ceiling, target_shares=target,
                                  risk_overlay=diagnostics, reserved_cash='0',
                                  unreserved_cash=arguments['state']['cash'], wait_cash=[],
                                  action='NEXT_OPEN_RISK_DIFFERENCES' if orders else 'NO_ACTION',
                                  time_in_force='NEXT_OPEN_MODEL')
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
            result = dict(status='BLOCKED', orders=[], reason=str(error), underlying_provider=result)
        audit.append(deepcopy(result))
        return result

    result = run_next_open_book(
        session_dates=assembled['session_dates'], ohlc=ohlc, initial_cash=initial_cash,
        fee_bps=fee_bps, slippage_bps=slippage_bps, order_provider=callback,
        events=assembled['actions'], cash_stock_merger_events=assembled['cash_stock_merger_events'],
        fractional_settlements=assembled['fractional_settlements'],
        price_source_references=assembled['price_source_references'],
        distribution_events=assembled['distribution_events'],
        distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'],
        account_model=assembled.get('account_model'))
    equity = [dict(date=assembled['session_dates'][0], equity=str(initial_cash))] + result['daily_ledger']
    result.update(selection_account_states=accounts, provider_audit=audit,
                  drawdown=drawdown_summary(equity), research_only=True, performance_validated=False,
                  independent_oos=False, point_in_time_certified=False,
                  total_return=str(Fraction(equity[-1]['equity']) / Fraction(initial_cash) - 1)
                  if result['status'] == 'COMPLETE' else None)
    return result
