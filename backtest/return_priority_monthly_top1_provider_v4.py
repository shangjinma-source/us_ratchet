"""TOP1 selection using the same distribution-aware execution as quantity."""
from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
from backtest.return_priority_monthly_top1_selector import decide_top1_for_account, VERSION


def build_monthly_top1_provider_v4(*, session_dates, monthly_inputs, close_prices, actions=()):
    attempts = 0

    def decide(**arguments):
        nonlocal attempts
        attempts += 1
        return decide_top1_for_account(**arguments)

    provider = build_monthly_quantity_provider_v4(session_dates=session_dates,
        monthly_inputs=monthly_inputs, close_prices=close_prices, actions=actions, decide=decide)

    def callback(*, decision_date, active_date, state):
        before = attempts
        result = provider(decision_date=decision_date, active_date=active_date, state=state)
        selection = result.get('selection')
        called = attempts - before
        result.update(execution_provider='MONTHLY_QUANTITY_PROVIDER_V4_TARGET_DIFFERENCE',
                      method=VERSION, core_calls=0,
                      capital_decision_attempts=called, total_capital_decision_attempts=attempts,
                      selector_calls=selection['selector_calls'] if selection is not None else None if called else 0)
        return result

    return callback
