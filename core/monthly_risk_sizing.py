"""Frozen monthly 50% target cap; apply once to fresh selector weights.

No redistribution, daily resizing, current-price chasing or SMA overlay.
Equity includes recorded holdings plus available/reserved account cash exactly
once; its valuation and the selector output must be validated by the caller.
"""
from fractions import Fraction


def capped_monthly_quantities(*, equity, weights, decision_prices):
    capital = Fraction(str(equity))
    if capital < 0 or set(weights) != set(decision_prices):
        raise ValueError('INVALID_MONTHLY_CAP_INPUT')
    fractions = {sid: Fraction(str(weight)) for sid, weight in weights.items()}
    prices = {sid: Fraction(str(price)) for sid, price in decision_prices.items()}
    if any(weight < 0 for weight in fractions.values()) or sum(fractions.values()) > 1:
        raise ValueError('INVALID_SELECTOR_WEIGHTS')
    if any(price <= 0 for price in prices.values()):
        raise ValueError('INVALID_DECISION_PRICE')
    targets = {sid: int(capital * min(weight, Fraction(1, 2)) // prices[sid])
               for sid, weight in fractions.items()}
    reserved = sum((targets[sid] * prices[sid] for sid in targets), Fraction(0))
    return dict(target_quantities=targets, unallocated_cash=str(capital - reserved),
                target_notional=str(reserved), policy='MONTHLY_CAP50_EXIT20',
                cap_applies_at='MONTHLY_CONFIGURATION_ONLY')
