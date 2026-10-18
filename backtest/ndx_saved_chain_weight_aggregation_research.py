"""Aggregate saved SID weights, without renormalizing or evaluating a gate."""
from datetime import date
from fractions import Fraction
import math


def aggregate_saved_weights(*, session, weights, chains, observation_dates):
    def require(value, message):
        if not value:
            raise ValueError(message)

    def day(value):
        require(type(value) is str and date.fromisoformat(value).isoformat() == value, 'ISO session')
        return value

    def ratio(value):
        return dict(numerator=str(value.numerator), denominator=str(value.denominator))

    day(session)
    require(all(type(item) is dict for item in (weights, chains, observation_dates)), 'Explicit saved mappings')
    require(set(weights) == set(chains) == set(observation_dates), 'Exact saved SID sets')
    totals = {}
    for sid, weight in weights.items():
        require(type(sid) is str and bool(sid), 'Nonempty SID')
        require(type(weight) in (int, float) and (type(weight) is int or math.isfinite(weight)), 'Finite original JSON weight')
        weight = Fraction(str(weight))
        require(0 <= weight <= 1, 'Original weight in unit interval')
        chain = chains[sid]
        require(type(chain) is str and bool(chain), 'Original chain label')
        require(day(observation_dates[sid]) <= session, 'No future label')
        totals[chain] = totals.get(chain, Fraction(0)) + weight
    total = sum(totals.values(), Fraction(0))
    require(not weights or total > 0, 'Nonempty saved weights cannot all be zero')
    return dict(schema='SAVED_WEIGHT_CHAIN_AGGREGATION_V1', session=session,
                status='DERIVED_SUM_OF_ORIGINAL_SAVED_WEIGHTS' if weights else 'EMPTY_WEIGHT_SET_UNDEFINED',
                chain_weights={key: ratio(value) for key, value in sorted(totals.items())},
                total_saved_weight=ratio(total),
                maximum_chain_weight=ratio(max(totals.values())) if totals else None,
                numeric_basis='EXACT_RATIONAL_SUM_OF_SAVED_JSON_DECIMAL_WEIGHTS',
                normalization_performed=False, original_saved_chain_aggregate=False,
                source_bytes_authenticated=False, order_gate_evaluated=False,
                account_executed=False, point_in_time_verified=False, promotion_allowed=False)
