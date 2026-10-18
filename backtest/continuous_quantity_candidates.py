"""Deterministic continuous-relaxation proposals, not a portfolio selector.

Cost-dollar weights occupy a simplex including the cash vertex (all zero).
Fixed Frank-Wolfe steps use exact rational gradients and 2/(iteration+2).
Issuer cleanup and flooring are heuristics; no integer/global guarantee follows.
No IO, search of historical strategies, optimizer library, or execution authority.
"""
from fractions import Fraction
import re


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    require(type(value) in (str, int, float, Fraction), 'FINITE_NONBOOLEAN_NUMBER_REQUIRED')
    require(not isinstance(value, str) or len(value) <= 2048, 'NUMBER_SIZE_LIMIT')
    try:
        text = str(value)
        exponent = re.search(r'[eE]([+-]?[0-9]+)$', text)
        require(exponent is None or abs(int(exponent.group(1))) <= 1024, 'NUMBER_SIZE_LIMIT')
        result = Fraction(text)
        require(max(result.numerator.bit_length(),result.denominator.bit_length()) <= 4096, 'NUMBER_SIZE_LIMIT')
        return result
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('FINITE_NUMBER_REQUIRED') from error


def generate_candidates(*, prices, metadata, entered_cash, fee_bps,
                        minimum_cash_buffer, training_scenarios, iterations):
    """iterations is an explicit computation budget, not a tuned risk parameter.

    Caller must establish scenario date availability and compatible price units.
    Returned candidates must still compete under the original exact objective and
    tie-break rules. This module cannot replace mandatory single/k coverage.
    """
    require(type(prices) is dict and prices and type(metadata) is dict
            and set(prices) == set(metadata), 'COMMON_SECURITY_DOMAIN_REQUIRED')
    require(all(type(sid) is str and sid for sid in prices), 'EXPLICIT_SID_REQUIRED')
    require(len(prices) <= 256, 'SECURITY_DOMAIN_LIMIT')
    require(type(iterations) is int and 1 <= iterations <= 256, 'ITERATION_BUDGET_1_TO_256_REQUIRED')
    order = sorted(prices)
    marks = {sid: number(prices[sid]) for sid in order}
    require(all(value > 0 for value in marks.values()), 'POSITIVE_PRICES_REQUIRED')
    require(all(type(metadata[sid]) is dict and all(type(metadata[sid].get(key)) is str
            and metadata[sid][key] for key in ('issuer_id','ticker')) for sid in order), 'EXPLICIT_IDENTITY_REQUIRED')
    require(len({metadata[sid]['ticker'] for sid in order}) == len(order), 'UNIQUE_TICKERS_REQUIRED')
    cash, fee, buffer = number(entered_cash), number(fee_bps)/10000, number(minimum_cash_buffer)
    require(cash > 0 and 0 <= fee < 1 and buffer >= 0, 'INVALID_CASH_FEE_BUFFER')
    require(type(training_scenarios) is list and training_scenarios, 'NONEMPTY_SCENARIOS_REQUIRED')
    require(len(training_scenarios) <= 64, 'SCENARIO_LIMIT')
    scenarios = []
    for row in training_scenarios:
        require(type(row) is dict and set(row) == set(marks), 'COMPLETE_SCENARIOS_REQUIRED')
        values = {sid: number(row[sid]) for sid in order}
        require(all(value > 0 for value in values.values()), 'POSITIVE_RELATIVES_REQUIRED')
        scenarios.append(values)
    spendable = max(Fraction(0), cash-buffer)
    costs = {sid: marks[sid]*(1+fee) for sid in order}
    coefficients = [{sid: row[sid]/(1+fee)-1 for sid in order} for row in scenarios]
    weights = {sid: Fraction(0) for sid in order}
    seen = {()}; candidates = [dict(quantities={},residual_cash=str(cash),fees='0',actual_k=0)]
    trace = []; groups = {}
    for sid in order:
        groups.setdefault(metadata[sid]['issuer_id'], []).append(sid)
    for iteration in range(iterations):
        wealth = [cash + spendable*sum((weights[sid]*row[sid] for sid in order), Fraction(0)) for row in coefficients]
        require(all(value > 0 for value in wealth), 'NONPOSITIVE_CONTINUOUS_WEALTH')
        gradients = {sid: sum((spendable*row[sid]/value for row,value in zip(coefficients,wealth)), Fraction(0)) for sid in order}
        winner = min(order, key=lambda sid: (-gradients[sid],sid))
        vertex = winner if gradients[winner] > 0 else None  # zero/tie chooses cash
        step = Fraction(2,iteration+2)
        weights = {sid: (1-step)*weights[sid]+(step if sid == vertex else 0) for sid in order}
        keep = {min(sids,key=lambda sid:(-weights[sid],sid)) for sids in groups.values()}
        quantities = {sid: int(spendable*weights[sid]//costs[sid]) for sid in order if sid in keep}
        quantities = {sid:q for sid,q in quantities.items() if q > 0}
        notional = sum((marks[sid]*q for sid,q in quantities.items()), Fraction(0))
        residual = cash-notional*(1+fee)
        require(residual >= 0 and (not quantities or residual >= buffer), 'INFEASIBLE_ROUNDED_CANDIDATE')
        signature = tuple(quantities.items()); added = signature not in seen
        if added:
            seen.add(signature)
            candidates.append(dict(quantities=quantities,residual_cash=str(residual),fees=str(notional*fee),actual_k=len(quantities)))
        trace.append(dict(iteration=iteration+1,vertex=vertex,step=str(step),candidate_added=added))
    return dict(method='EXACT_RATIONAL_FIXED_STEP_FRANK_WOLFE_CANDIDATES_V1',candidates=candidates,
                iterations_requested=iterations,iterations_completed=iterations,gradient_evaluations=iterations,
                scenario_wealth_evaluations=iterations*len(scenarios),trace=trace,
                candidate_count=len(candidates),issuer_cleanup='LARGEST_COST_WEIGHT_THEN_ASCENDING_SID_NO_REALLOCATION',
                research_only=True,global_optimum_established=False,all_cardinalities_covered=False,
                original_mandatory_coverage_must_be_preserved=True,source_authenticated=False,
                future_return_or_drawdown_guaranteed=False)
