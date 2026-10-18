"""Fixed original weights comparator; reuse V4 execution, no market or account IO."""
from fractions import Fraction

from backtest.return_priority_monthly_quantity_provider_v4 import (
    amount, build_monthly_quantity_provider_v4,
)

VERSION = 'MONTHLY_ORIGINAL_FIXED_WEIGHTS_V1'


def build_monthly_fixed_weight_provider(*, weights, session_dates, monthly_inputs,
                                        close_prices, actions=()):
    """Preserve exact supplied weights; never optimize or silently normalize them.

    This is a fixed-weight control, not a replay of the original strategy.
    Historical decision closes are for research execution only, not live quotes.
    """
    frozen_weights = {sid: amount(value) for sid, value in weights.items()}
    if not frozen_weights or not all(frozen_weights.values()):
        raise ValueError('Positive nonempty fixed weights required')

    def decide(*, decision_date, account_state, valuation_quotes,
               search_arguments, source_hashes):
        if amount(search_arguments['fee_bps']) or amount(search_arguments['minimum_cash_buffer']):
            raise ValueError('Fixed control requires zero commission and zero buffer')
        prices = {}
        for quote in valuation_quotes:
            sid = quote['security_id']
            if sid in prices:
                raise ValueError('Duplicate valuation quote')
            prices[sid] = amount(quote['price'])
            if not prices[sid]:
                raise ValueError('Positive valuation price required')
        required = set(frozen_weights) | {sid for sid, q in account_state['shares'].items() if q}
        if not required <= prices.keys():
            raise ValueError('Missing fixed-weight or held-security quote')
        equity = amount(account_state['cash']) + sum(
            (q * prices[sid] for sid, q in account_state['shares'].items() if q), Fraction(0))
        target = {sid: int(equity * weight // prices[sid])
                  for sid, weight in frozen_weights.items()}
        notional = sum((q * prices[sid] for sid, q in target.items()), Fraction(0))
        if notional > equity:
            raise ValueError('FIXED_WEIGHT_INTEGER_TARGET_EXCEEDS_EQUITY')
        return dict(method=VERSION, target_quantities=target, investable_equity=str(equity),
                    target_notional=str(notional), residual_cash=str(equity-notional),
                    original_weights={sid: str(w) for sid, w in frozen_weights.items()},
                    original_weight_sum=str(sum(frozen_weights.values())),
                    weights_normalized=False, core_calls=0, research_only=True)

    provider = build_monthly_quantity_provider_v4(session_dates=session_dates,
        monthly_inputs=monthly_inputs, close_prices=close_prices, actions=actions, decide=decide)

    def callback(**arguments):
        result = provider(**arguments)
        result.update(method=VERSION, core_calls=0,
                      execution_provider='MONTHLY_QUANTITY_PROVIDER_V4_TARGET_DIFFERENCE',
                      full_original_strategy_replay=False)
        return result

    return callback
