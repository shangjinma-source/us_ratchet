"""Pure, bounded joint candidate generation; no IO, return fitting or execution.

All money/weights in output are exact rational strings. The supplied ranking and
Close must be known on decision_date. Metadata and its provenance are caller
declarations, not certified by this component. Next Open is deliberately absent.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256


RISK_KEYS = {'min_single_weight', 'max_single_weight', 'top_three_cap',
             'min_neff_ratio', 'chain_cap'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(type(value) in (str, int, float), 'Explicit finite rational number; bool denied')
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('Explicit finite rational number') from error


def _risk(weights, metadata, parameters):
    if not weights:
        return {'all_passed': False, 'checks': {}, 'effective_n': None,
                'stock_internal_weights': {}}
    total = sum(weights.values())
    normalized = {security: value / total for security, value in weights.items()}
    ordered = sorted(normalized.values(), reverse=True)
    chains = {}
    for security, weight in normalized.items():
        chain = metadata[security]['risk_chain']
        chains[chain] = chains.get(chain, Fraction(0)) + weight
    effective_n = 1 / sum(weight * weight for weight in ordered)
    checks = {
        'min_single_weight': ordered[-1] >= parameters['min_single_weight'],
        'max_single_weight': ordered[0] <= parameters['max_single_weight'],
        'top_three_cap': sum(ordered[:3]) <= parameters['top_three_cap'],
        'min_neff_ratio': effective_n >= parameters['min_neff_ratio'] * len(ordered),
        'chain_cap': max(chains.values()) <= parameters['chain_cap'],
        'issuer_unique': len({metadata[security]['issuer_id'] for security in weights}) == len(weights),
    }
    return {'all_passed': all(checks.values()), 'checks': checks,
            'effective_n': str(effective_n),
            'stock_internal_weights': {security: str(value) for security, value in normalized.items()}}


def generate_joint_candidates(*, decision_date, ordered_security_ids, metadata,
                              close_prices, entered_cash, fee_bps,
                              minimum_cash_buffer, risk_parameters,
                              source_context, fixed_seed):
    """Generate at most 12*N+1 records for N distinct supplied issuers.

metadata[sid] requires ticker, issuer_id, risk_chain and nonempty source_refs.
source_context requires ranking_as_of, close_as_of, qualification_start,
qualification_end, and nonempty source_refs. All dates are ISO dates.
ordered_security_ids is an explicit best-first total order of metadata keys.
Structural failures produce one record per k, without fabricated targets.
Legal means indicative at known decision Close, never certified executable.
The complete entered cash remains equity; exposure is a strategy allocation.
"""
    _require(type(source_context) is dict, 'Explicit source context')
    for field in ('ranking_as_of', 'close_as_of', 'qualification_start', 'qualification_end'):
        value = source_context.get(field)
        _require(type(value) is str and date.fromisoformat(value).isoformat() == value,
                 'Explicit ISO source date: ' + field)
    _require(type(decision_date) is str and date.fromisoformat(decision_date).isoformat() == decision_date,
             'Explicit ISO decision date')
    _require(source_context['ranking_as_of'] <= decision_date and source_context['close_as_of'] == decision_date,
             'Ranking known no later than decision and exact decision Close')
    _require(source_context['qualification_start'] <= decision_date <= source_context['qualification_end'],
             'Decision must stay inside explicitly supplied qualification interval')
    _require(type(source_context.get('source_refs')) is list and source_context['source_refs'],
             'Explicit source references')
    _require(type(fixed_seed) is str and bool(fixed_seed), 'Explicit fixed research seed')
    _require(type(metadata) is dict and type(close_prices) is dict, 'Explicit metadata and Close maps')
    _require(type(ordered_security_ids) is list and len(ordered_security_ids) == len(set(ordered_security_ids))
             and set(ordered_security_ids) == set(metadata), 'One supplied rank for every existing security ID')
    for security, row in metadata.items():
        _require(type(security) is str and security and type(row) is dict, 'Explicit security identity')
        _require(all(type(row.get(field)) is str and row[field] for field in ('ticker', 'issuer_id', 'risk_chain')),
                 'Explicit ticker, issuer and risk chain')
        _require(type(row.get('source_refs')) is list and row['source_refs'], 'Metadata source references required')
    _require(len({row['ticker'] for row in metadata.values()}) == len(metadata), 'Distinct ticker domain')
    _require(type(risk_parameters) is dict and set(risk_parameters) == RISK_KEYS, 'Five explicit existing risk checks')
    risk = {key: _number(value) for key, value in risk_parameters.items()}
    _require(all(0 <= value <= 1 for value in risk.values()), 'Risk bounds inside [0,1]')
    cash, buffer, fee = _number(entered_cash), _number(minimum_cash_buffer), _number(fee_bps) / 10000
    _require(cash >= 0 and buffer >= 0 and 0 <= fee < Fraction(1, 2), 'Nonnegative cash/buffer and finite research fee')
    prices = {}
    for security in metadata:
        value = close_prices.get(security)
        if value is not None:
            prices[security] = _number(value)
            _require(prices[security] > 0, 'Positive supplied Close')
    rank = {security: index for index, security in enumerate(ordered_security_ids)}
    issuer_members = {}
    for security in ordered_security_ids:
        issuer_members.setdefault(metadata[security]['issuer_id'], []).append(security)

    def hashed(domain, value):
        # Length prefixes avoid delimiter collisions in caller-supplied identifiers.
        parts = (fixed_seed, domain, value)
        payload = ''.join(str(len(part)) + ':' + part for part in parts)
        return sha256(payload.encode('utf-8')).hexdigest()

    ranked_issuers = list(issuer_members)
    shuffled_issuers = sorted(issuer_members, key=lambda issuer: (hashed('issuer', issuer), issuer))
    capacity = max(Fraction(0), cash - buffer - 2 * fee * cash)
    records = [{
        'method_rule_id': 'ALL_CASH_REFERENCE', 'status': 'REFERENCE_ALL_CASH',
        'requested_k': 0, 'actual_k': 0, 'blocked_reasons': [], 'security_ids': [],
        'stock_internal_profile_weights': {}, 'target_weights': {}, 'target_shares': {},
        'stock_exposure': '0', 'strategic_cash_fraction': '1', 'entered_cash_pool': str(cash),
        'indicative_quantities': {}, 'indicative_buy_notional': '0', 'indicative_buy_fee': '0',
        'indicative_total_cost': '0', 'indicative_residual_cash': str(cash),
        'metadata': {}, 'risk': {'applicable': False},
    }]
    for count in range(1, len(issuer_members) + 1):
        impossible = []
        if count * risk['min_single_weight'] > 1:
            impossible.append('K_TIMES_MIN_WEIGHT_EXCEEDS_ONE')
        if count * risk['max_single_weight'] < 1:
            impossible.append('K_TIMES_MAX_WEIGHT_BELOW_ONE')
        if count <= 3 and risk['top_three_cap'] < 1:
            impossible.append('K_AT_MOST_THREE_WITH_TOP_THREE_CAP_BELOW_ONE')
        if count > 3 and risk['top_three_cap'] < Fraction(3, count):
            impossible.append('TOP_THREE_CAP_BELOW_EQUAL_WEIGHT_LOWER_BOUND')
        if impossible:
            records.append({'method_rule_id': 'STRUCTURAL_K_' + str(count),
                            'requested_k': count, 'status': 'BLOCKED_STRUCTURAL',
                            'blocked_reasons': impossible, 'no_targets_generated': True})
            continue
        for composition, issuers in (('RANK_TOP', ranked_issuers), ('FIXED_SEED_SUBSET', shuffled_issuers)):
            selected = []
            for issuer in issuers[:count]:
                members = issuer_members[issuer]
                # The second rule must actually compete with rank-top's class.
                # For two-class issuers this guarantees both supplied classes;
                # >2 classes remain an explicitly bounded, non-exhaustive family.
                alternatives = members[1:] if len(members) > 1 else members
                selected.append(members[0] if composition == 'RANK_TOP' else
                                min(alternatives, key=lambda security: (hashed('class', security), security)))
            selected.sort(key=rank.__getitem__)
            for profile in ('EQUAL', 'ORDINAL_TILT'):
                floor = risk['min_single_weight']
                if count > 3:
                    floor = max(floor, (1 - risk['top_three_cap']) / (count - 3))
                if profile == 'EQUAL':
                    weights = {security: Fraction(1, count) for security in selected}
                else:
                    remainder = 1 - count * floor
                    weights = {security: floor + remainder * Fraction(count - index, count * (count + 1) // 2)
                               for index, security in enumerate(selected)}
                profile_valid = all(value > 0 for value in weights.values()) and sum(weights.values()) == 1
                profile_risk = _risk(weights, metadata, risk) if profile_valid else {'all_passed': False}
                for exposure in (Fraction(1, 2), Fraction(3, 4), Fraction(1)):
                    reasons = []
                    if not profile_valid or (profile == 'ORDINAL_TILT' and count * floor > 1):
                        reasons.append('PROFILE_FLOOR_INFEASIBLE')
                    if not profile_risk['all_passed']:
                        reasons.append('PROFILE_RISK_FAILED')
                    missing = [security for security in selected if security not in prices]
                    quantities, notional, cost_fee, residual = None, None, None, None
                    actual_risk = None
                    if missing:
                        reasons.append('DECISION_CLOSE_MISSING')
                    elif profile_valid:
                        quantities = {security: int(capacity * exposure * weights[security] // prices[security])
                                      for security in selected}
                        if any(quantity <= 0 for quantity in quantities.values()):
                            reasons.append('ZERO_QUANTITY_REQUESTED_MEMBER')
                        notionals = {security: quantity * prices[security] for security, quantity in quantities.items() if quantity > 0}
                        notional = sum(notionals.values(), Fraction(0))
                        cost_fee = notional * fee
                        residual = cash - notional - cost_fee
                        actual_risk = _risk(notionals, metadata, risk)
                        if not actual_risk['all_passed']:
                            reasons.append('INDICATIVE_WHOLE_LOT_RISK_FAILED')
                        if residual < buffer:
                            reasons.append('INDICATIVE_CASH_BUFFER_FAILED')
                    records.append({
                        'method_rule_id': f'K{count}:{composition}:{profile}:EXPOSURE{exposure}',
                        'requested_k': count, 'actual_k': sum(quantity > 0 for quantity in quantities.values()) if quantities is not None else None,
                        'status': 'BLOCKED' if reasons else 'LEGAL_INDICATIVE_ONLY',
                        'blocked_reasons': reasons, 'composition_rule': composition, 'weight_rule': profile,
                        'security_ids': list(selected), 'stock_internal_profile_weights': {security: str(value) for security, value in weights.items()},
                        'target_weights': {security: str(exposure * value) for security, value in weights.items()},
                        'stock_exposure': str(exposure), 'strategic_cash_fraction': str(1 - exposure),
                        'entered_cash_pool': str(cash), 'sizing_capacity': str(capacity),
                        'indicative_quantities': quantities, 'missing_close_security_ids': missing,
                        'indicative_buy_notional': str(notional) if notional is not None else None,
                        'indicative_buy_fee': str(cost_fee) if cost_fee is not None else None,
                        'indicative_total_cost': str(notional + cost_fee) if notional is not None else None,
                        'indicative_residual_cash': str(residual) if residual is not None else None,
                        'profile_risk': profile_risk, 'risk': actual_risk,
                        'metadata': {security: deepcopy(metadata[security]) for security in selected},
                    })
    return {
        'schema': 'PURE_BOUNDED_JOINT_CANDIDATES_V1', 'decision_date': decision_date,
        'records': records, 'issuer_count': len(issuer_members), 'security_count': len(metadata),
        'record_limit': 12 * len(issuer_members) + 1,
        'all_k_considered': list(range(1, len(issuer_members) + 1)),
        'source_context': deepcopy(source_context), 'risk_parameters': {key: str(value) for key, value in risk.items()},
        'fee_bps': str(_number(fee_bps)), 'minimum_cash_buffer': str(buffer), 'fixed_seed': fixed_seed,
        'parameters_authority': 'ROOT_RESEARCH_CHOICES_NOT_USER_PREFERENCES',
        'risk_normalization': 'STOCK_INTERNAL_EXCLUDING_CASH',
        'sizing_rule': 'FLOOR((ENTERED_CASH-BUFFER-2*FEE*ENTERED_CASH)*EXPOSURE*STOCK_WEIGHT/DECISION_CLOSE)',
        'execution_rule': 'NEXT_OPEN_RESIZE_SAME_FROZEN_TARGET_WEIGHTS_AND_BLOCK_IF_INFEASIBLE_NO_MEMBER_SUBSTITUTION',
        'cash_pool_rule': 'ALL_ENTERED_CASH_REMAINS_EQUITY_EXPOSURE_IS_STRATEGIC_ALLOCATION_NOT_BUDGET_HAIRCUT',
        'bounded_family_not_global_optimum': True, 'qualification_certified': False,
        'ranking_performed': False, 'returns_read': False, 'book_calls': 0,
        'future_prices_read': False, 'current_adoption_allowed': False, 'orders_created': False,
        'benchmark_win_required': False, 'drawdown_new_numerical_cap': False,
        'later_ranking_contract': 'FOUR_BLOCK_MEAN_NET_LOG_RETURN_ANNUAL_OBJECTIVE;SEM_REPORT_ONLY_NOT_PENALTY',
    }
