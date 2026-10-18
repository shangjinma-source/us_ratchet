"""Single-book execution component. No CLI or execution on import.

Actual-data invocation requires a separately frozen, independently reviewed
registration. This component alone does not grant that admission.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

from backtest.return_priority_limit_book_v4 import run_limit_book_v4
from backtest.return_priority_limit_book_summary_v4 import summarize_limit_book_v4
from backtest.return_priority_monthly_fixed_weight_provider import build_monthly_fixed_weight_provider


def plain(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def execute_control(*, proposal, binding, directory):
    """Persist intent before the one kernel call; preserve failures without retry."""
    arguments = deepcopy(binding['provider_arguments'])
    days = arguments['session_dates']
    account = proposal['proposed_account']
    if (proposal['session_dates'] != days or proposal['target_weights'] != arguments['weights']
            or account['initial_shares'] or Fraction(account['commission_bps'])
            or Fraction(account['minimum_cash_buffer']) or arguments['actions']):
        raise ValueError('Control scope mismatch or unreviewed actions')
    if [p['decision_date'] for p in arguments['monthly_inputs']] != account['monthly_decision_dates']:
        raise ValueError('Monthly schedule mismatch')
    for sid, series in proposal['ohlc'].items():
        if {d: v['close'] for d,v in series.items()} != arguments['close_prices'].get(sid):
            raise ValueError('Execution and selection prices differ')
    if set(proposal['ohlc']) != set(arguments['close_prices']):
        raise ValueError('Execution and selection domains differ')
    output = Path(directory)
    output.mkdir()  # Existing partial/successful runs are never overwritten.

    def save(name, value):
        with (output / name).open('x', encoding='utf-8') as stream:
            json.dump(plain(value), stream, indent=2, allow_nan=False)

    save('book_intent.json', dict(maximum_book_calls=1, search_calls=0,
        automatic_retry=False, initial_cash=account['initial_cash'], initial_shares={}))
    audit = []
    try:
        provider = build_monthly_fixed_weight_provider(**arguments)

        def callback(**kwargs):
            day = kwargs['decision_date']
            save('callback_intent_' + day + '.json', kwargs)
            response = provider(**kwargs)
            record = dict(deepcopy(kwargs), response=deepcopy(response))
            save('callback_' + day + '.json', record)
            audit.append(record)
            return response

        outcome = run_limit_book_v4(session_dates=days, ohlc=proposal['ohlc'],
            initial_cash=account['initial_cash'], initial_shares={}, fee_bps='0',
            events=[], order_provider=callback)
        save('outcome.json', outcome)
        save('provider_audit.json', audit)
        result = dict(metrics=summarize_limit_book_v4(outcome, audit, account['initial_cash'], days),
            book_calls=1, search_calls=0, price_only=True, independent_oos=False,
            full_original_strategy_replay=False, adoption_allowed=False)
        save('result.json', result)
        return result
    except Exception as error:
        save('exception.json', dict(type=type(error).__name__, message=str(error),
                                   automatic_retry=False, completed_callbacks=len(audit)))
        raise
