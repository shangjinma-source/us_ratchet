"""Exact bounded floor/ceil projection of one frozen fresh-cash target.

No IO, source certification, selection, return scoring or ledger calls. The
original capacity and target weights define the neighborhood and maximum stock
notional. Ceil rounding never borrows the frozen strategic cash allocation.
"""
from fractions import Fraction
from itertools import product
from math import prod

from backtest.return_priority_joint_candidate_generator_research import _number, _risk, RISK_KEYS


class ProjectionInputError(ValueError):
    """Input is invalid or is not eligible for a rounding-only repair."""


def require(condition, message):
    if not condition:
        raise ProjectionInputError(message)


def project_exact_floor_ceil(*, candidate, prices, metadata, risk_parameters,
                            entered_cash, fee_bps, minimum_cash_buffer,
                            max_evaluations):
    """Return FEASIBLE, NO_FEASIBLE_IN_NEIGHBORHOOD or SEARCH_BUDGET_EXHAUSTED.

Invalid/profile-risk/non-rounding failures raise ProjectionInputError without
search. A valid original floor is returned unchanged with zero neighborhood
evaluations. Otherwise the complete neighborhood must fit max_evaluations;
oversize searches return no partial allocation. No existing positions apply.
"""
    require(type(candidate) is dict, 'Explicit frozen candidate required')
    require(type(max_evaluations) is int and 1 <= max_evaluations <= 1048576,
            'Explicit evaluation budget from 1 through 1048576')
    require(candidate.get('status') in ('LEGAL_INDICATIVE_ONLY', 'BLOCKED'), 'Stock candidate required')
    allowed = {'ZERO_QUANTITY_REQUESTED_MEMBER', 'INDICATIVE_WHOLE_LOT_RISK_FAILED'}
    require(type(candidate.get('blocked_reasons')) is list
            and all(type(reason) is str for reason in candidate['blocked_reasons'])
            and set(candidate['blocked_reasons']) <= allowed,
            'Only whole-quantity or whole-lot risk failures may be repaired')
    securities = candidate.get('security_ids')
    require(type(securities) is list and securities and len(set(securities)) == len(securities)
            and all(type(security) is str and security for security in securities), 'Unique existing security IDs required')
    securities = sorted(securities)
    require(type(candidate.get('requested_k')) is int and candidate['requested_k'] == len(securities),
            'Original requested k must match the complete frozen support')
    require(type(prices) is dict and type(metadata) is dict and set(securities) <= set(prices)
            and set(securities) <= set(metadata), 'Complete known prices and metadata required')
    require(type(candidate.get('target_weights')) is dict and set(candidate['target_weights']) == set(securities),
            'Exact frozen target support required')
    require(type(risk_parameters) is dict and set(risk_parameters) == RISK_KEYS, 'Five original risk parameters required')
    try:
        policy = {key: _number(value) for key, value in risk_parameters.items()}
        weights = {security: _number(candidate['target_weights'][security]) for security in securities}
        marks = {security: _number(prices[security]) for security in securities}
        cash, buffer, fee = _number(entered_cash), _number(minimum_cash_buffer), _number(fee_bps) / 10000
        capacity = _number(candidate['sizing_capacity'])
    except (ValueError, KeyError) as error:
        raise ProjectionInputError('Explicit finite rational parameters required') from error
    exposure = sum(weights.values())
    require(all(0 <= value <= 1 for value in policy.values()), 'Risk thresholds must be in [0,1]')
    require(cash > 0 and buffer >= 0 and cash >= buffer and 0 <= fee < Fraction(1, 2), 'Fresh cash, buffer and fee invalid')
    require(capacity == max(Fraction(0), cash - buffer - 2 * fee * cash), 'Original two-sided-reserve sizing capacity differs')
    require(all(value > 0 for value in marks.values()) and all(value > 0 for value in weights.values()) and 0 < exposure <= 1,
            'Positive prices and target weights with sum<=1 required')
    for security in securities:
        row = metadata[security]
        require(type(row) is dict and all(type(row.get(field)) is str and row[field]
                                         for field in ('ticker', 'issuer_id', 'risk_chain')), 'Explicit identity and risk labels required')
    require(len({metadata[security]['ticker'] for security in securities}) == len(securities)
            and len({metadata[security]['issuer_id'] for security in securities}) == len(securities), 'Ticker/issuer uniqueness required')
    profile = {security: weight / exposure for security, weight in weights.items()}
    require(_risk(profile, metadata, policy)['all_passed'], 'Frozen stock-internal profile risk fails; rounding cannot repair it')
    if 'stock_internal_profile_weights' in candidate:
        declared = candidate['stock_internal_profile_weights']
        require(type(declared) is dict and set(declared) == set(profile)
                and all(_number(declared[security]) == profile[security] for security in securities), 'Original profile weights differ')
    options = {}
    for security in securities:
        raw = capacity * weights[security] / marks[security]
        lower, upper = raw.numerator // raw.denominator, -(-raw.numerator // raw.denominator)
        options[security] = (lower,) if lower == upper else (lower, upper)
    floor = {security: values[0] for security, values in options.items()}
    if candidate.get('indicative_quantities') is not None:
        require(candidate['indicative_quantities'] == floor, 'Supplied original floor does not match frozen inputs')
    size = prod(len(values) for values in options.values())

    def evaluate(quantities):
        notionals = {security: quantities[security] * marks[security] for security in securities if quantities[security] > 0}
        invested = sum(notionals.values(), Fraction(0))
        fees = fee * invested
        remaining = cash - invested - fees
        risk = _risk(notionals, metadata, policy)
        exposure_budget_passed = invested <= capacity * exposure
        feasible = (all(value > 0 for value in quantities.values()) and remaining >= buffer
                    and exposure_budget_passed and risk['all_passed'])
        actual = {security: notionals.get(security, Fraction(0)) / invested if invested else Fraction(0) for security in securities}
        differences = [abs(actual[security] - profile[security]) for security in securities]
        score = (sum(differences), max(differences), invested, tuple(quantities[security] for security in securities))
        projection = {
            'quantities': dict(quantities), 'actual_k': len(notionals), 'buy_notional': str(invested),
            'buy_fee': str(fees), 'residual_cash': str(remaining), 'total_cost': str(invested + fees),
            'budget_conservation_exact': invested + fees + remaining == cash,
            'frozen_stock_budget_passed': exposure_budget_passed,
            'actual_stock_exposure': str(invested / cash),
            'actual_stock_internal_weights': {security: str(value) for security, value in actual.items()},
            'target_buy_notional': str(capacity * exposure), 'signed_notional_drift': str(invested - capacity * exposure),
            'risk': risk, 'l1_target_weight_drift': str(score[0]), 'max_absolute_target_weight_drift': str(score[1]),
        }
        return feasible, score, projection

    floor_evaluation = evaluate(floor)
    floor_feasible, _, floor_projection = floor_evaluation
    result = {
        'schema': 'EXACT_FROZEN_TARGET_FLOOR_CEIL_PROJECTION_V1', 'status': None,
        'method_rule_id': candidate.get('method_rule_id'), 'research_only': True,
        'entered_cash': str(cash), 'sizing_capacity': str(capacity), 'requested_stock_exposure': str(exposure),
        'target_weights': {security: str(value) for security, value in weights.items()},
        'floor_quantities': floor, 'floor_feasible': floor_feasible,
        'search_space_size': size, 'max_evaluations': max_evaluations,
        'floor_checks': 1, 'candidate_evaluations': 1, 'neighborhood_evaluations': 0, 'search_complete': False,
        'feasible_candidates': 0, 'projection': None,
        'tie_break': 'MIN_STOCK_INTERNAL_L1_THEN_MAX_ABS_DRIFT_THEN_BUY_NOTIONAL_THEN_SORTED_SID_QUANTITIES',
        'full_integer_infeasibility_claimed': False, 'global_optimality_claimed': False,
        'current_adoption_allowed': False, 'orders_created': False,
    }
    if floor_feasible:
        result.update(status='FEASIBLE', feasible_candidates=1, projection=floor_projection,
                      selection_role='ORIGINAL_FLOOR_UNCHANGED_NO_REPAIR_NEEDED')
        return result
    if size > max_evaluations:
        result.update(status='SEARCH_BUDGET_EXHAUSTED', selection_role='NO_PARTIAL_ALLOCATION_RETURNED')
        return result
    best = None
    for vector in product(*(options[security] for security in securities)):
        quantities = dict(zip(securities, vector))
        if quantities == floor:
            feasible, score, projection = floor_evaluation
        else:
            feasible, score, projection = evaluate(quantities)
            result['candidate_evaluations'] += 1
        result['neighborhood_evaluations'] += 1
        if feasible:
            result['feasible_candidates'] += 1
            if best is None or score < best[0]:
                best = score, projection
    result['search_complete'] = True
    if best is None:
        result.update(status='NO_FEASIBLE_IN_NEIGHBORHOOD', selection_role='ONLY_THIS_FINITE_NEIGHBORHOOD_REJECTED')
    else:
        result.update(status='FEASIBLE', selection_role='COMPLETE_NEIGHBORHOOD_MINIMUM_TRACKING_DRIFT', projection=best[1])
    return result
