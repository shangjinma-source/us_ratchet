"""Exact least integer minimum-weight top-up closure on one fixed stock support.

This is a necessary-condition subproblem, not a portfolio optimizer. Issuer,
other risk checks, eligibility, prices and source authority are caller concerns.
"""
from decimal import Decimal
from fractions import Fraction

SCHEMA = 'FIXED_SUPPORT_MIN_WEIGHT_INTEGER_CLOSURE_V1'
TOLERANCE = Fraction(1, 10**9)
MAX_SECURITIES = 256
MAX_SHARES = 10**12
MAX_ITERATIONS = 10000
MAX_COORDINATE_UPDATES = 100000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value):
    require(type(value) in (str, int, Decimal), 'Decimal literal/Decimal/int required, not float/bool')
    if type(value) is str:
        require(0 < len(value) <= 80 and value.strip() == value, 'Bounded canonical decimal literal required')
    if type(value) is int:
        require(0 <= value <= 10**40, 'Numeric engineering bound exceeded')
    parsed = Decimal(value)
    require(parsed.is_finite() and len(parsed.as_tuple().digits) <= 40
            and abs(parsed.as_tuple().exponent) <= 40, 'Bounded finite decimal required')
    result = Fraction(parsed)
    require(0 <= result <= 10**40, 'Nonnegative bounded number required')
    return result


def ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def integer(value, maximum):
    require(type(value) is int and 0 <= value <= maximum, 'Bounded integer required, not bool/float')
    return value


def close_min_weight_topups(*, holdings, execution_prices, support_security_ids,
        seed_buy_shares, buy_limits, min_single_weight, starting_cash_usd,
        cash_injection_usd, transaction_cost_bps, minimum_cash_buffer_usd, max_iterations):
    """Synchronous x'=max(x,ceil((m*equity(x)-old_notional)/price),0).

    m=max(0,min_single_weight-1e-9), exactly equivalent for positive stocks.
    Every iterate is <= every feasible y >= seed on this fixed support. Thus
    cap or fee-inclusive budget failure excludes ONLY this upward domain.
    Budget exhaustion is UNKNOWN. A fixed point proves minimum weight plus
    caps/cash here, never the remaining four risks or same-issuer uniqueness.
    """
    require(all(type(value) is dict for value in (holdings,execution_prices,seed_buy_shares,buy_limits)), 'Explicit SID dictionaries required')
    require(all(type(sid) is str and sid and sid.strip() == sid for sid in execution_prices), 'Canonical nonblank SID required')
    sids = sorted(execution_prices)
    require(len(sids) <= MAX_SECURITIES and set(holdings) == set(seed_buy_shares) == set(buy_limits) == set(sids), 'Exact full SID domain required, use zero holdings explicitly')
    require(all(type(sid) is str and sid and sid.strip() == sid for sid in sids), 'Canonical nonblank SID required')
    require(type(support_security_ids) is list and all(type(sid) is str for sid in support_security_ids)
            and support_security_ids == sorted(set(support_security_ids))
            and set(support_security_ids) <= set(sids), 'Canonical ordered unique support required')
    support = set(support_security_ids)
    old = {sid:integer(holdings[sid],MAX_SHARES) for sid in sids}
    seed = {sid:integer(seed_buy_shares[sid],MAX_SHARES) for sid in sids}
    caps = {sid:integer(buy_limits[sid],MAX_SHARES) for sid in sids}
    require(all(sid in support for sid in sids if old[sid] > 0), 'Support must contain every positive old holding')
    require(all(seed[sid] == 0 for sid in sids if sid not in support), 'Inactive SID additional buys must stay zero')
    require(all(old[sid] > 0 or seed[sid] >= 1 for sid in support), 'Newly supported SID requires positive seed buy')
    prices = {sid:number(execution_prices[sid]) for sid in sids}
    require(all(value > 0 for value in prices.values()), 'Complete positive prices required')
    minimum = number(min_single_weight)
    require(0 < minimum <= 1, 'Minimum weight must be in (0,1]')
    threshold = max(Fraction(0),minimum-TOLERANCE)
    cash, injection, fee_bps, buffer = map(number,(starting_cash_usd,cash_injection_usd,transaction_cost_bps,minimum_cash_buffer_usd))
    require(fee_bps <= 10000, 'Fee rate exceeds engineering contract')
    iterations_limit = integer(max_iterations,MAX_ITERATIONS)
    require(iterations_limit*len(sids) <= MAX_COORDINATE_UPDATES, 'Coordinate-update engineering budget exceeded')
    effective_caps = {sid:caps[sid] if sid in support else 0 for sid in sids}
    old_values = {sid:old[sid]*prices[sid] for sid in sids}
    old_equity = sum(old_values.values(),Fraction(0))
    available = cash+injection-buffer
    rate = fee_bps/10000
    trace = []
    current = dict(seed)

    def financial(x):
        gross = sum((prices[sid]*x[sid] for sid in sids),Fraction(0))
        fees = gross*rate
        return gross,fees,gross+fees,cash+injection-gross-fees

    def failure(x, stage):
        violations = [{'security_id':sid,'required_buy_shares':x[sid],'cap':effective_caps[sid],
                       'strict_excess_shares':x[sid]-effective_caps[sid]}
                      for sid in sids if x[sid] > effective_caps[sid]]
        base = {'scope':'FIXED_SUPPORT_SEED_UPWARD_DOMAIN_ONLY','stage':stage,
                'lower_bound_buy_shares':dict(x),'all_feasible_upward_plans_dominate_this_lower_bound':True}
        if violations:
            return dict(base,kind='CAP_EXCEEDED',violations=violations)
        gross,fees,cost,left = financial(x)
        if cost > available:
            return dict(base,kind='CASH_BUFFER_EXCEEDED',gross_buy_usd=ratio(gross),fees_usd=ratio(fees),
                        lower_bound_total_buy_cost_usd=ratio(cost),available_after_buffer_usd=ratio(available),
                        strict_cost_excess_usd=ratio(cost-available),cash_after_usd=ratio(left),
                        required_cash_buffer_usd=ratio(buffer))
        return None

    def finish(status, certificate=None):
        gross,fees,cost,left = financial(current)
        equity = old_equity+gross
        checks = {sid:old_values[sid]+prices[sid]*current[sid] >= threshold*equity for sid in support_security_ids}
        fixed = status == 'FIXED_POINT'
        return {'schema':SCHEMA,'status':status,'buy_shares':dict(current) if fixed else None,
            'last_iterate_buy_shares':dict(current),'seed_buy_shares':dict(seed),'buy_limits':dict(caps),
            'effective_buy_limits':effective_caps,'holdings':old,'execution_prices':{sid:str(execution_prices[sid]) for sid in sids},
            'support_security_ids':list(support_security_ids),'original_min_single_weight':str(min_single_weight),
            'original_tolerance':ratio(TOLERANCE),'effective_minimum_weight':ratio(threshold),
            'starting_cash_usd':str(starting_cash_usd),'cash_injection_usd':str(cash_injection_usd),
            'transaction_cost_bps':str(transaction_cost_bps),'minimum_cash_buffer_usd':str(minimum_cash_buffer_usd),
            'trace':trace,'iterations':len(trace),'max_iterations':iterations_limit,'failure_certificate':certificate,
            'last_iterate_financials':{'gross_buy_usd':ratio(gross),'fees_usd':ratio(fees),
                'total_buy_cost_usd':ratio(cost),'cash_after_usd':ratio(left),'stock_equity_usd':ratio(equity)},
            'last_iterate_min_weight_checks':checks,'minimum_weight_fixed_point_verified':fixed,
            'least_feasible_buy_vector_in_seed_upward_domain_verified':fixed,
            'seed_upward_domain_necessarily_infeasible':certificate is not None,
            'all_risks_evaluated':False,'issuer_uniqueness_evaluated':False,'eligibility_inferred':False,
            'global_optimality_claimed':False,'full_integer_space_infeasibility_claimed':False,
            'orders_executed':False,'point_in_time_verified':False,'promotion_allowed':False,
            'parameter_authority':'SYNTHETIC_CALLER_SUPPLIED_NOT_SOURCE_BOUND',
            'engineering_limits_not_k_or_pool_policy':{'security_ids':MAX_SECURITIES,'iterations':MAX_ITERATIONS,
                'coordinate_updates':MAX_COORDINATE_UPDATES}}

    certificate = failure(current,'SEED')
    if certificate is not None:
        return finish('PROVEN_INFEASIBLE_UPWARD_DOMAIN',certificate)
    if not support:
        return finish('UNSUPPORTED_EMPTY_SUPPORT')
    for iteration in range(iterations_limit):
        equity = old_equity+financial(current)[0]
        requirements, next_vector = {},dict(current)
        for sid in support_security_ids:
            raw = (threshold*equity-old_values[sid])/prices[sid]
            ceiling = -(-raw.numerator//raw.denominator)
            next_vector[sid] = max(current[sid],ceiling,0)
            requirements[sid] = {'minimum_additional_shares_rational':ratio(raw),'ceil_additional_shares':ceiling}
        gross,fees,cost,left = financial(next_vector)
        trace.append({'iteration':iteration+1,'before_buy_shares':dict(current),'equity_before':ratio(equity),
            'requirements':requirements,'next_buy_shares':dict(next_vector),'gross_buy_usd':ratio(gross),
            'fees_usd':ratio(fees),'total_buy_cost_usd':ratio(cost),'cash_after_usd':ratio(left)})
        previous = current
        current = next_vector
        certificate = failure(current,'SYNCHRONOUS_UPDATE')
        if certificate is not None:
            return finish('PROVEN_INFEASIBLE_UPWARD_DOMAIN',certificate)
        if current == previous:
            return finish('FIXED_POINT')
    return finish('UNKNOWN_ITERATION_BUDGET')
