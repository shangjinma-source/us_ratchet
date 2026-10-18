"""Generate bounded floor/ceil buy plans near a frozen target; never certify feasibility."""
from decimal import Context, localcontext
from fractions import Fraction
from itertools import product, islice
from math import prod
from backtest import ndx_conditional_new_cash_fork_research as kernel


def require(value, message):
    if not value:
        raise ValueError(message)


def ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def generate_target_neighbors(*, holdings, starting_cash_usd, injection_usd, execution_prices,
                              target_weights, buy_limits, transaction_cost_bps,
                              minimum_cash_buffer_usd, max_generated_plans):
    with localcontext(Context(prec=160)):
        return _generate(holdings, starting_cash_usd, injection_usd, execution_prices,
                         target_weights, buy_limits, transaction_cost_bps,
                         minimum_cash_buffer_usd, max_generated_plans)


def _generate(holdings, cash, injection, prices, targets, limits, fee, buffer, budget):
    require(all(type(x) is dict for x in (holdings, prices, targets, limits)), 'Explicit dictionaries required')
    require(type(budget) is int and 1 <= budget <= 10000, 'Engineering plan budget must be 1..10000')
    union = set(holdings) | set(limits)
    require(len(union) <= kernel.MAX_SECURITIES and set(prices) == union, 'Exact old/buy price union required')
    for sid in union:
        kernel._identifier(sid)
    require(targets and set(targets) <= union, 'Nonempty targets must belong to old/buy union')
    for sid, value in holdings.items():
        kernel._integer(value, kernel.MAX_SHARES)
    for sid, value in limits.items():
        kernel._integer(value, kernel.MAX_SHARES)
        require(value + holdings.get(sid, 0) <= kernel.MAX_SHARES, 'Final share resource bound')
    values = [Fraction(kernel._number(x)) for x in (cash, injection, fee, buffer)]
    cash, injection, fee, buffer = values
    require(min(values) >= 0 and fee <= 10000, 'Nonnegative cash/flow/buffer and bounded fee required')
    marks = {sid: Fraction(kernel._number(value)) for sid, value in prices.items()}
    require(all(value > 0 for value in marks.values()), 'Positive prices required')
    weights = {sid: Fraction(kernel._number(value)) for sid, value in targets.items()}
    require(all(value >= 0 for value in weights.values()), 'Nonnegative targets required')
    total = sum(weights.values(), Fraction(0))
    require(total > 0, 'Positive target sum required')
    normalized = {sid: weights.get(sid, Fraction(0)) / total for sid in sorted(union)}
    gross_budget = max(Fraction(0), cash + injection - buffer) / (1 + fee / 10000)
    stock_value = sum((holdings.get(sid, 0) * marks[sid] for sid in union), Fraction(0))
    deficits = {sid: max(Fraction(0), normalized[sid] * (stock_value + gross_budget)
                         - holdings.get(sid, 0) * marks[sid]) for sid in sorted(limits)}
    deficit_sum = sum(deficits.values(), Fraction(0))
    scale = min(Fraction(1), gross_budget / deficit_sum) if deficit_sum else Fraction(0)
    choices, details = {}, {}
    for sid, deficit in deficits.items():
        ideal = deficit * scale / marks[sid]
        floor = ideal.numerator // ideal.denominator
        ceiling = -(-ideal.numerator // ideal.denominator)
        choices[sid] = sorted({min(limits[sid], floor), min(limits[sid], ceiling)})
        details[sid] = {'positive_target_deficit_usd': ratio(deficit), 'ideal_buy_shares': ratio(ideal),
                        'unclipped_floor': floor, 'unclipped_ceil': ceiling,
                        'buy_limit': limits[sid], 'clipped_choices': choices[sid]}
    sids = list(choices)
    zero = dict.fromkeys(sids, 0)
    zero_in_domain = all(0 in choices[sid] for sid in sids)
    rounded_count = prod(len(value) for value in choices.values())
    distinct_count = rounded_count + (0 if zero_in_domain else 1)
    plans = [zero]
    for quantities in islice(product(*(choices[sid] for sid in sids)), budget):
        plan = dict(zip(sids, quantities))
        if plan == zero:
            continue
        if len(plans) >= budget:
            break
        plans.append(plan)
    require(len({tuple(plan.items()) for plan in plans}) == len(plans), 'Internal duplicate plan')
    return {'schema': 'TARGET_CASH_FLOOR_CEIL_NEIGHBORS_V1',
            'original_target_literals': {sid: str(value) for sid, value in targets.items()},
            'original_target_sum': ratio(total), 'normalized_target_weights': {sid: ratio(value) for sid, value in normalized.items()},
            'initial_stock_value_usd': ratio(stock_value), 'gross_buy_budget_usd': ratio(gross_budget),
            'deficit_scaling_factor': ratio(scale), 'rounding_details': details,
            'plans': plans, 'rounded_domain_count': rounded_count, 'distinct_supplied_domain_count': distinct_count,
            'zero_plan_already_in_rounded_domain': zero_in_domain,
            'generated_count': len(plans), 'ungenerated_count': distinct_count - len(plans),
            'domain_status': 'EXHAUSTED_ROUNDED_DOMAIN' if len(plans) == distinct_count else 'GENERATION_BUDGET_LIMITED',
            'order': 'ZERO_FIRST_THEN_SORTED_SID_FLOOR_CEIL_LEX_DEDUP',
            'all_integer_domain_exhausted': False, 'portfolio_feasibility_asserted': False,
            'target_provenance_verified': False, 'old_holdings_sold': False,
            'future_returns_used': False, 'orders_executed': False, 'promotion_allowed': False}
