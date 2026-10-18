"""Exact AM-GM upper bound over the continuous cash-budget relaxation.

For candidate scenario wealth w[j] and any feasible wealth W[j], AM-GM gives
product(W[j]/w[j]) <= (sum(W[j]/w[j])/m)**m. The sum is affine in purchases.
Its maximum over the relaxed nonnegative purchase simplex is cash baseline
plus spendable cash times the largest positive coefficient per purchase dollar.
Dropping integer and issuer restrictions enlarges the domain, so this remains
an upper bound for every cardinality. Equality certifies objective value only,
not the tie-break winner, source validity, or future performance.
"""
from fractions import Fraction
from math import prod


def training_product_upper_bound(*, cash, fee, buffer, prices, scenarios, quantities):
    cash, fee, buffer = map(Fraction, (cash, fee, buffer))
    prices = {sid: Fraction(value) for sid, value in prices.items()}
    if cash <= 0 or not 0 <= fee < 1 or buffer < 0 or not prices or not scenarios:
        raise ValueError('Invalid training bound inputs')
    if any(value <= 0 for value in prices.values()):
        raise ValueError('Positive prices required')
    if any(sid not in prices or type(q) is not int or q <= 0 for sid, q in quantities.items()):
        raise ValueError('Positive integer quantities required')
    relatives = [{sid: Fraction(value) for sid, value in row.items()} for row in scenarios]
    if any(row.keys() != prices.keys() or any(value <= 0 for value in row.values()) for row in relatives):
        raise ValueError('Complete positive scenario domain required')
    notional = sum((prices[sid]*q for sid, q in quantities.items()), Fraction(0))
    residual = cash-notional*(1+fee)
    if residual < 0 or (quantities and residual < buffer):
        raise ValueError('Infeasible candidate')
    wealth = [residual+sum((prices[sid]*q*row[sid] for sid, q in quantities.items()), Fraction(0))
              for row in relatives]
    baseline = sum((cash/value for value in wealth), Fraction(0))
    coefficients = {sid: sum(((row[sid]-1-fee)/value for row, value in zip(relatives, wealth)), Fraction(0))/(1+fee)
                    for sid in prices}
    maximum_sum = baseline+max(Fraction(0), cash-buffer)*max(Fraction(0), *coefficients.values())
    count = len(wealth)
    assert maximum_sum >= count  # The candidate itself belongs to the relaxation.
    ratio_bound = (maximum_sum/count)**count
    candidate_product = prod(value/cash for value in wealth)
    return dict(candidate_product=candidate_product, product_upper_bound=candidate_product*ratio_bound,
                product_ratio_upper_bound=ratio_bound, maximum_wealth_ratio_sum=maximum_sum,
                scenario_count=count, objective_value_optimal=(maximum_sum == count))


def public_bound(bound):
    def compact(value):
        return str(value) if max(value.numerator.bit_length(), value.denominator.bit_length()) <= 4096 else None
    return dict(method='EXACT_AM_GM_CONTINUOUS_BUDGET_RELAXATION',
                scope='SUPPLIED_TRAINING_SCENARIOS_PRICE_ONLY_OBJECTIVE_VALUE',
                product_ratio_upper_bound=compact(bound['product_ratio_upper_bound']),
                maximum_wealth_ratio_sum=compact(bound['maximum_wealth_ratio_sum']),
                scenario_count=bound['scenario_count'],
                objective_value_optimal=bound['objective_value_optimal'],
                tie_break_optimality_established=False,
                source_authentication_established=False,
                forecast_or_annualized_return=False,
                omitted_large_rationals=any(compact(bound[key]) is None for key in
                                           ['product_ratio_upper_bound', 'maximum_wealth_ratio_sum']))
