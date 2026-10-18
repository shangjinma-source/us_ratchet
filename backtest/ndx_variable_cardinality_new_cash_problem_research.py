"""Pure, source-UNBOUND all-issuer/all-k buy-only problem preparation.

This module does not read sources, qualify members, enumerate quantity tuples,
fit, rank, select a winner or create execution rows. Caller facts describe a
conditional mathematical problem only. A source adapter is deliberately absent.
Risk necessary bounds use the exact Fraction acceptance model with 1e-9
tolerance of ndx_conditional_new_cash_fork_research._risk, not float-engine
bitwise equivalence. All input/output monetary values are exact rational strings.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA = 'VARIABLE_CARDINALITY_NEW_CASH_PROBLEM_V1'
TOLERANCE = Fraction(1, 10**9)
RISK_KEYS = ('max_single_weight', 'min_single_weight', 'top_weight_cap',
             'minimum_effective_n_ratio', 'risk_chain_top1_cap')
SOURCE_REQUIREMENTS = (
    ('HOST_BINDING', 'MISSING_OR_UNRECOGNIZED_HOST_BINDING'),
    ('PIT_MEMBERSHIP', 'PIT_MEMBERSHIP_CLOSURE_UNPROVEN'),
    ('IDENTITY_AND_ACTIONS', 'IDENTITY_OR_ACTION_CLOSURE_UNPROVEN'),
    ('RISK_AND_LIQUIDITY', 'RISK_OR_LIQUIDITY_SOURCE_UNPROVEN'),
    ('CAUSAL_MATRIX', 'CAUSAL_FULL_POOL_MATRIX_INCOMPLETE'),
    ('PRIOR_BOOK', 'PRIOR_BOOK_OR_CAUSAL_PRIOR_MISSING'),
    ('CASH_EVENT', 'CASH_EVENT_OR_CURRENCY_UNBOUND'),
    ('PRICE_CONTEXT', 'PRICE_BASIS_OR_AVAILABLE_AT_UNPROVEN'),
    ('POLICY', 'ORIGINAL_POLICY_BINDING_MISSING'),
    ('DUAL_BENCHMARKS', 'DUAL_BENCHMARK_OR_COMMON_BASIS_MISSING'))
AUTHORITY_KEYS = ('source_bytes_authenticated', 'full_transitive_source_closure_reverified',
    'point_in_time_verified', 'full_ndx_membership_verified', 'qualified_by_caller',
    'price_available_at_verified', 'modern_dynamic_policy_binding_verified',
    'formal_admission_allowed', 'execution_authorized', 'promotion_allowed',
    'current_account_verified', 'current_new_money_supplied', 'fit_called',
    'enumeration_called', 'winner_selected', 'global_optimality_proven')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _mapping(value, name):
    _require(type(value) is dict, name + ' must be a dict')
    return value


def _text(value, name):
    _require(type(value) is str and bool(value) and value.strip() == value,
             name + ' requires canonical nonblank text')
    return value


def _integer(value, name, positive=False):
    _require(type(value) is int and value >= (1 if positive else 0),
             name + ' requires a nonboolean ' + ('positive' if positive else 'nonnegative') + ' integer')
    return value


def _number(value, name):
    """Decimal inputs only; no floats/bools, nonfinite values or ratio literals."""
    _require(type(value) in (int, str, Decimal), name + ' requires exact decimal input, not float/bool')
    if type(value) is str:
        _require(bool(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value)),
                 name + ' requires a canonical finite decimal literal')
        _require(len(value) <= 160, name + ' decimal resource limit')
    number = Decimal(value)
    _require(number.is_finite(), name + ' requires a finite decimal')
    _require(len(number.as_tuple().digits) <= 80 and abs(number.as_tuple().exponent) <= 80,
             name + ' decimal resource limit')
    result = Fraction(number)
    _require(result >= 0, name + ' cannot be negative')
    return result


def _day(value, name):
    _text(value, name)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(name + ' requires YYYY-MM-DD') from error
    _require(parsed.isoformat() == value, name + ' requires YYYY-MM-DD')
    return parsed


def _instant(value, name):
    _text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError(name + ' requires an ISO timestamp with timezone') from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             name + ' requires an ISO timestamp with timezone')
    return parsed


def _session_zone(value):
    _text(value, 'session_timezone')
    _require(len(value) <= 128 and re.fullmatch(r'[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*', value)
             is not None and all(part not in ('.', '..') for part in value.split('/')),
             'Canonical IANA session_timezone key required, never a file path')
    try:
        # Standard-library resolver may read its runtime TZif database. This
        # does not read caller source references or authenticate a session zone.
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError('Unknown IANA session_timezone') from error


def _sid_list(value, name):
    _require(type(value) is list, name + ' must be a list')
    result = [_text(sid, name) for sid in value]
    _require(len(set(result)) == len(result), name + ' duplicate SID')
    return result


def _securities(value, name):
    _require(type(value) is list, name + ' must be a list')
    result = {}
    for row in value:
        _mapping(row, name + ' row')
        _require(set(row) == {'security_id', 'issuer_id', 'ticker', 'risk_chain'},
                 name + ' exact SID/issuer/ticker/risk_chain row required')
        for key, item in row.items():
            _text(item, name + '.' + key)
        sid = row['security_id']
        _require(sid not in result, name + ' duplicate SID')
        result[sid] = dict(row)
    return dict(sorted(result.items()))


def _coefficients(identities):
    """Elementary symmetric coefficients; no composition enumeration."""
    multiplicities = {}
    for row in identities:
        issuer = row['issuer_id']
        multiplicities[issuer] = multiplicities.get(issuer, 0) + 1
    coefficients = [1]
    for issuer in sorted(multiplicities):
        size = multiplicities[issuer]
        coefficients.append(0)
        for k in range(len(coefficients) - 1, 0, -1):
            coefficients[k] += coefficients[k - 1] * size
    return coefficients


def _certificate(reason, left, comparison, right, **context):
    excluded = left < right if comparison == '<' else left > right
    if not excluded:
        return None
    return dict(reason=reason, left=str(left), comparison=comparison,
                right=str(right), strict_gap=str(abs(left - right)),
                arithmetic='EXACT_FRACTION_RISK_ACCEPTANCE_TOLERANCE_1E_MINUS9', **context)


def _universal_certificates(k, risk):
    comparisons = (
        ('MAX_SINGLE_CAPACITY_BELOW_ONE', k * (risk['max_single_weight'] + TOLERANCE), '<', Fraction(1)),
        ('MIN_SINGLE_REQUIRED_MASS_ABOVE_ONE', k * (risk['min_single_weight'] - TOLERANCE), '>', Fraction(1)),
        ('TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_CAP', Fraction(min(3, k), k), '>', risk['top_weight_cap'] + TOLERANCE))
    return [certificate for args in comparisons
            if (certificate := _certificate(*args)) is not None]


def _references(value):
    _mapping(value, 'input_references')
    result = {}
    for role, reference in sorted(value.items()):
        _text(role, 'reference role')
        _mapping(reference, 'reference')
        _require(set(reference) <= {'path', 'sha256', 'json_pointer'}
                 and {'path', 'sha256'} <= set(reference), 'reference shape')
        _text(reference['path'], 'reference.path')
        _require(type(reference['sha256']) is str
                 and re.fullmatch('[0-9a-f]{64}', reference['sha256']) is not None, 'reference.sha256')
        if 'json_pointer' in reference:
            _require(type(reference['json_pointer']) is str
                     and (reference['json_pointer'] == '' or reference['json_pointer'].startswith('/')),
                     'reference.json_pointer')
        result[role] = dict(reference)
    return result


def prepare_synthetic_new_cash_problem(*, synthetic_case):
    """Same formulas, explicit synthetic label; never relax a supplied policy."""
    _mapping(synthetic_case, 'synthetic_case')
    _require(set(synthetic_case) == {'evidence_facts', 'prior_book', 'cash_event',
             'price_context', 'policy', 'domain_kind'}, 'synthetic_case exact input fields')
    return _prepare(**synthetic_case, input_scope='SYNTHETIC_UNBOUND')


def prepare_new_cash_problem(*, evidence_facts, prior_book, cash_event,
                             price_context, policy, domain_kind):
    """Describe the caller's full conditional inventory, never qualify it.

    evidence_facts requires conditional_inventory (SID rows), optionally explicit
    conditional_exclusions (SID -> reason) and frozen_only_securities (old SIDs
    outside that inventory). Every excluded SID stays in the reported inventory.
    supplied_inventory_security_ids, if given, must exactly cover that inventory;
    a mismatch blocks the numerical context instead of accepting a target subset.
    Arbitrary qualified/authority/source-status claims are ignored, not trusted.
    All ten source requirements remain blocked even when references are supplied.
    """
    return _prepare(evidence_facts=evidence_facts, prior_book=prior_book,
                    cash_event=cash_event, price_context=price_context,
                    policy=policy, domain_kind=domain_kind, input_scope='CONDITIONAL_UNBOUND')


def _prepare(*, evidence_facts, prior_book, cash_event, price_context, policy,
             domain_kind, input_scope):
    for name, value in (('evidence_facts', evidence_facts), ('prior_book', prior_book),
                        ('cash_event', cash_event), ('price_context', price_context), ('policy', policy)):
        _mapping(value, name)
    _require(domain_kind in ('CONTINUOUS_INCREMENTAL_DOLLARS', 'WHOLE_LOT_QUANTITIES')
             and type(domain_kind) is str, 'Unknown domain_kind')
    inventory = _securities(evidence_facts.get('conditional_inventory'), 'conditional_inventory')
    old_only = _securities(evidence_facts.get('frozen_only_securities', []), 'frozen_only_securities')
    _require(not (set(inventory) & set(old_only)), 'frozen_only_securities overlap inventory')
    identities = dict(sorted({**inventory, **old_only}.items()))
    _require(len({row['ticker'] for row in identities.values()}) == len(identities),
             'Concurrent ticker ambiguity must be resolved before a mathematical problem')
    exclusions = _mapping(evidence_facts.get('conditional_exclusions', {}), 'conditional_exclusions')
    _require(set(exclusions) <= set(inventory), 'Exclusion outside full conditional inventory')
    for reason in exclusions.values():
        _text(reason, 'conditional exclusion reason')
    buys = sorted(set(inventory) - set(exclusions))
    references = _references(evidence_facts.get('input_references', {}))
    context_blockers = []
    if 'supplied_inventory_security_ids' in evidence_facts:
        declared = _sid_list(evidence_facts['supplied_inventory_security_ids'], 'supplied_inventory_security_ids')
        if set(declared) != set(inventory):
            context_blockers.append(dict(reason='FULL_POOL_OMISSION_OR_MISMATCH',
                missing_security_ids=sorted(set(declared) - set(inventory)),
                unexpected_security_ids=sorted(set(inventory) - set(declared))))
    _require(set(prior_book) == {'holdings', 'cash', 'currency', 'as_of', 'cash_includes_event'},
             'prior_book exact fields')
    holdings = _mapping(prior_book['holdings'], 'holdings')
    q = {_text(sid, 'holding SID'): _number(count, 'holding quantity') for sid, count in holdings.items()}
    _require(set(q) <= set(identities), 'Frozen old SID metadata missing')
    _require(set(old_only) <= {sid for sid, count in q.items() if count > 0},
             'frozen_only_securities must describe positive old holdings only')
    q = {sid: q.get(sid, 0) for sid in identities}
    positive_old = {sid: count for sid, count in q.items() if count > 0}
    old_cash = _number(prior_book['cash'], 'prior cash')
    prior_day = _day(prior_book['as_of'], 'prior as_of')
    _require(type(prior_book['cash_includes_event']) is bool, 'cash_includes_event requires bool')
    if prior_book['cash_includes_event']:
        context_blockers.append(dict(reason='CASH_EVENT_ALREADY_IN_PRIOR_CASH'))
    _require(set(cash_event) == {'amount', 'currency', 'decision_date', 'execution_date', 'available_at'},
             'cash_event exact fields')
    amount = _number(cash_event['amount'], 'new cash amount')
    decision = _day(cash_event['decision_date'], 'decision_date')
    execution = _day(cash_event['execution_date'], 'execution_date')
    cash_available = _instant(cash_event['available_at'], 'cash available_at')
    _require(set(price_context) == {'currency', 'stage', 'decision_at', 'basis', 'prices', 'session_timezone'},
             'price_context exact fields')
    decision_at = _instant(price_context['decision_at'], 'decision_at')
    session_zone = _session_zone(price_context['session_timezone'])
    stage = price_context['stage']
    _require(type(stage) is str and stage in ('DECISION_KNOWN_PRICES', 'REALIZED_EXECUTION_OPEN'),
             'Explicit price stage required')
    basis = _text(price_context['basis'], 'price basis')
    if decision_at.astimezone(session_zone).date() != decision:
        context_blockers.append(dict(reason='DECISION_TIMESTAMP_DATE_MISMATCH'))
    if execution <= decision:
        context_blockers.append(dict(reason='EXECUTION_MUST_FOLLOW_DECISION'))
    if prior_day > decision:
        context_blockers.append(dict(reason='FUTURE_PRIOR_BOOK'))
    if cash_available > decision_at:
        context_blockers.append(dict(reason='CASH_EVENT_NOT_AVAILABLE_AT_DECISION'))
    _require(set(policy) == {'risk_parameters', 'transaction_cost_bps', 'minimum_cash_buffer', 'currency'},
             'policy exact five-risk/fee/buffer/currency fields')
    risk_inputs = _mapping(policy['risk_parameters'], 'risk_parameters')
    _require(set(risk_inputs) == set(RISK_KEYS), 'All five risk parameters required')
    risk = {key: _number(risk_inputs[key], key) for key in RISK_KEYS}
    _require(all(value <= 1 for value in risk.values()), 'Risk parameters must be in [0,1]')
    _require(risk['max_single_weight'] > 0 and risk['risk_chain_top1_cap'] > 0
             and risk['min_single_weight'] <= risk['max_single_weight'], 'Invalid risk envelope')
    fee_bps = _number(policy['transaction_cost_bps'], 'fee_bps')
    _require(fee_bps <= 10000, 'fee_bps exceeds 10000')
    buffer = _number(policy['minimum_cash_buffer'], 'cash buffer')
    currencies = [_text(obj['currency'], name + ' currency') for name, obj in
                  (('prior', prior_book), ('event', cash_event), ('prices', price_context), ('policy', policy))]
    _require(all(re.fullmatch('[A-Z]{3}', currency) is not None for currency in currencies),
             'Canonical three-letter currency required')
    if len(set(currencies)) != 1:
        context_blockers.append(dict(reason='CURRENCY_MISMATCH_NO_BOUND_FX', currencies=currencies))
    marks = _mapping(price_context['prices'], 'prices')
    _require(set(marks) == set(identities), 'Exact full conditional plus frozen-only price inventory required')
    prices, lots, price_days = {}, {}, set()
    for sid, mark in sorted(marks.items()):
        _mapping(mark, 'price row')
        _require(set(mark) == {'price', 'lot_size', 'available_at', 'price_date', 'basis'}, 'price row exact fields')
        prices[sid] = _number(mark['price'], 'price ' + sid)
        _require(prices[sid] > 0, 'Positive price required ' + sid)
        lots[sid] = _integer(mark['lot_size'], 'lot_size ' + sid, positive=True)
        available = _instant(mark['available_at'], 'price available_at ' + sid)
        price_day = _day(mark['price_date'], 'price_date ' + sid)
        price_days.add(price_day)
        _text(mark['basis'], 'price basis ' + sid)
        if mark['basis'] != basis:
            context_blockers.append(dict(reason='PRICE_BASIS_MISMATCH', security_id=sid))
        if stage == 'DECISION_KNOWN_PRICES' and (available > decision_at or price_day > decision):
            context_blockers.append(dict(reason='PRICE_NOT_AVAILABLE_AT_DECISION', security_id=sid))
        # Both labels and IANA zone remain unbound. This checks only their
        # declared consistency, not an exchange opening time or PIT availability.
        if stage == 'REALIZED_EXECUTION_OPEN' and (price_day != execution
                or available.astimezone(session_zone).date() < execution):
            context_blockers.append(dict(reason='REALIZED_OPEN_SESSION_MISMATCH', security_id=sid))
    if len(price_days) > 1:
        context_blockers.append(dict(reason='COMMON_PRICE_SESSION_MISMATCH'))
    total_cash = old_cash + amount
    budget = total_cash - buffer
    fee_factor = 1 + fee_bps / 10000
    old_amounts = {sid: prices[sid] * count for sid, count in positive_old.items()}
    old_value = sum(old_amounts.values(), Fraction(0))
    old_issuers = {}
    for sid in positive_old:
        old_issuers.setdefault(identities[sid]['issuer_id'], []).append(sid)
    conflicts = {issuer: sorted(sids) for issuer, sids in sorted(old_issuers.items()) if len(sids) > 1}
    locked_zero = {sid: old_issuers[identities[sid]['issuer_id']][0] for sid in buys
                   if identities[sid]['issuer_id'] in old_issuers and sid not in positive_old}
    old_count = len(positive_old)
    full_coefficients = _coefficients(inventory.values())
    all_domain_identities = {sid: identities[sid] for sid in set(inventory) | set(positive_old)}
    full_domain_coefficients = _coefficients(all_domain_identities.values())
    maximum_k = len(full_domain_coefficients) - 1
    new_issuer_rows = [identities[sid] for sid in buys if identities[sid]['issuer_id'] not in old_issuers]
    frozen_coefficients = _coefficients(new_issuer_rows)
    conditional_support_upper = len(old_issuers) + len(frozen_coefficients) - 1
    numerical_ready = not context_blockers
    nonnegative_budget = budget >= 0
    available_gross = budget / fee_factor if nonnegative_budget and numerical_ready else None
    caps = ({sid: int(budget // (prices[sid] * lots[sid] * fee_factor)) for sid in buys}
            if nonnegative_budget and numerical_ready and domain_kind == 'WHOLE_LOT_QUANTITIES' else None)
    box_count = None
    whole_upper = None
    activation_costs = {}
    if caps is not None:
        box_count = 1
        for sid in buys:
            box_count *= caps[sid] + 1
            issuer = identities[sid]['issuer_id']
            if issuer not in old_issuers and caps[sid] > 0:
                cost = prices[sid] * lots[sid] * fee_factor
                activation_costs[issuer] = min(activation_costs.get(issuer, cost), cost)
        running, new_count = Fraction(0), 0
        for cost in sorted(activation_costs.values()):
            if running + cost > budget:
                break
            running += cost
            new_count += 1
        whole_upper = old_count + new_count
    frozen_bounds, global_certificates = [], []
    if available_gross is not None and old_value + available_gross > 0:
        greatest_value = old_value + available_gross
        for sid, value in sorted(old_amounts.items()):
            lower = value / greatest_value
            frozen_bounds.append(dict(kind='SECURITY', identity=sid, lower_bound=str(lower)))
            certificate = _certificate('FROZEN_SECURITY_CANNOT_DILUTE_BELOW_MAX', lower, '>',
                risk['max_single_weight'] + TOLERANCE, security_id=sid)
            if certificate is not None:
                global_certificates.append(certificate)
        chains = {}
        for sid, value in old_amounts.items():
            chain = identities[sid]['risk_chain']
            chains[chain] = chains.get(chain, Fraction(0)) + value
        for chain, value in sorted(chains.items()):
            lower = value / greatest_value
            frozen_bounds.append(dict(kind='RISK_CHAIN', identity=chain, lower_bound=str(lower)))
            certificate = _certificate('FROZEN_CHAIN_CANNOT_DILUTE_BELOW_CAP', lower, '>',
                risk['risk_chain_top1_cap'] + TOLERANCE, risk_chain=chain)
            if certificate is not None:
                global_certificates.append(certificate)
    k_rows = []
    for k in range(1, maximum_k + 1):
        necessary = _universal_certificates(k, risk) + deepcopy(global_certificates)
        discrete_reasons = []
        if k < old_count:
            discrete_reasons.append('BELOW_FROZEN_POSITIVE_HOLDING_COUNT')
        if k > conditional_support_upper:
            discrete_reasons.append('ABOVE_CONDITIONAL_ELIGIBLE_ISSUER_SUPPORT')
        if numerical_ready and budget < 0:
            discrete_reasons.append('CASH_BUFFER_NOT_MET_BEFORE_BUYS')
        if whole_upper is not None and k > whole_upper:
            discrete_reasons.append('WHOLE_LOT_ACTIVATION_BUDGET_UPPER_BOUND')
        if (domain_kind == 'CONTINUOUS_INCREMENTAL_DOLLARS' and available_gross == 0
                and k > old_count):
            discrete_reasons.append('ZERO_INCREMENTAL_CAPITAL_CANNOT_ADD_SUPPORT')
        if available_gross == 0 and old_value == 0:
            discrete_reasons.append('NO_POSITIVE_INVESTED_CAPITAL')
        coefficient_index = k - old_count
        frozen_count = (frozen_coefficients[coefficient_index]
                        if 0 <= coefficient_index < len(frozen_coefficients) else 0)
        status = ('STRUCTURALLY_INFEASIBLE' if conflicts else
                  'CONDITIONAL_CONTEXT_BLOCKED' if not numerical_ready else
                  'NECESSARY_INFEASIBLE' if necessary or discrete_reasons else
                  'NOT_PRUNED_NECESSARY_ONLY')
        k_rows.append(dict(holding_count=k, inventory_scope=input_scope,
            full_conditional_composition_count=str(full_domain_coefficients[k]),
            frozen_old_conditional_composition_count=None if conflicts else str(frozen_count),
            necessary_certificates=necessary, domain_necessary_reasons=discrete_reasons,
            status=status, source_status='SOURCE_BLOCKED', feasibility_proven=False))
    source_checks = [dict(requirement_id=key, status='SOURCE_BLOCKED', reason_code=reason,
        source_binding_status='UNBOUND', reference=deepcopy(references.get(key)),
        reference_state='CLAIMED_REFERENCE_UNVERIFIED' if key in references else 'MISSING',
        cutoff=decision.isoformat(),
        missing_fields=(['HOST_AUTHENTICATION', 'SOURCE_SPECIFIC_FACT_RECONSTRUCTION']
                        if key in references else ['SOURCE_BYTES', 'HOST_AUTHENTICATION', 'SOURCE_SPECIFIC_FACT_RECONSTRUCTION']),
        qualification_established=False) for key, reason in SOURCE_REQUIREMENTS]
    ignored_claims = sorted(set(evidence_facts) - {'conditional_inventory', 'frozen_only_securities',
        'conditional_exclusions', 'input_references', 'supplied_inventory_security_ids',
        'observed_inventory_reference', 'conditional_inventory_reference', 'decision_coordinate'})
    result = dict(schema=SCHEMA, input_scope=input_scope, source_binding_status='UNBOUND',
        status='SOURCE_BLOCKED', numerical_status='CONDITIONAL_CONTEXT_READY' if numerical_ready else 'CONDITIONAL_CONTEXT_BLOCKED',
        decision_coordinate=deepcopy(evidence_facts.get('decision_coordinate')),
        decision_date=decision.isoformat(), execution_date=execution.isoformat(),
        decision_timestamp=decision_at.astimezone(timezone.utc).isoformat(),
        session_date_convention='ALL_INSTANT_SESSION_DATES_USE_EXPLICIT_CALLER_IANA_ZONE_UNBOUND',
        session_timezone=price_context['session_timezone'],
        timezone_resolution='STDLIB_ZONEINFO_RUNTIME_DATABASE_NOT_SOURCE_AUTHENTICATION',
        exchange_session_timezone_verified=False, realized_open_available_at_verified=False,
        exchange_adjacency_verified=False, pricing_stage=stage,
        causal_decision_price_proven=False, context_blockers=context_blockers,
        source_checks=source_checks, source_blockers=[dict(requirement_id=row['requirement_id'],
            reason_code=row['reason_code']) for row in source_checks], input_references=references,
        observed_inventory_reference=deepcopy(evidence_facts.get('observed_inventory_reference')),
        observed_inventory_status='REFERENCE_ONLY_UNBOUND_NOT_QUALIFIED',
        conditional_inventory_reference=deepcopy(evidence_facts.get('conditional_inventory_reference')),
        conditional_inventory=dict(securities=list(inventory.values()), security_count=len(inventory),
            issuer_count=len(full_coefficients) - 1, all_k_denominators=[dict(holding_count=k,
                composition_count=str(value)) for k, value in enumerate(full_coefficients) if k]),
        conditional_buy_security_ids=buys, conditional_exclusions=deepcopy(exclusions),
        qualified_inventory_or_null=None, qualified_all_k_denominators_or_null=None,
        ignored_caller_claim_keys=ignored_claims,
        frozen_prior_book=dict(quantities={sid: str(count) for sid, count in sorted(positive_old.items())},
            cash=str(old_cash), currency=currencies[0], as_of=prior_day.isoformat(),
            security_metadata=[identities[sid] for sid in sorted(positive_old)],
            frozen_ineligible_security_ids=sorted(set(positive_old) - set(buys)),
            issuer_conflicts=conflicts, positive_holding_count=old_count),
        domain_kind=domain_kind,
        domain_formula=dict(currency=currencies[0], cash_event_amount=str(amount),
            total_cash_before_buys=str(total_cash), minimum_cash_buffer=str(buffer),
            cash_budget_after_buffer=str(budget), fee_factor=str(fee_factor),
            old_stock_value=str(old_value), maximum_incremental_gross_or_null=None if available_gross is None else str(available_gross),
            prices={sid: str(value) for sid, value in sorted(prices.items())}, lot_sizes=lots,
            coordinate_caps_or_null=caps, issuer_locked_zero_security_ids=locked_zero,
            constraints=['OLD_QUANTITIES_FROZEN', 'NONNEGATIVE_INCREMENT_ONLY',
                'COUPLED_GROSS_TIMES_FEE_FACTOR_LE_BUDGET', 'AT_MOST_ONE_POSITIVE_SID_PER_ISSUER',
                'ALL_FIVE_EXACT_TOLERANCE_RISK_CONSTRAINTS'],
            variable='NONNEGATIVE_DOLLARS' if domain_kind == 'CONTINUOUS_INCREMENTAL_DOLLARS' else 'NONNEGATIVE_INTEGER_LOTS',
            induced_weight_formula='(q_s*p_s+increment_s)/(sum(q*p)+sum(increment))',
            cash_excluded_from_stock_risk_denominator=True,
            full_conditional_issuer_upper=maximum_k,
            eligible_conditional_support_upper=conditional_support_upper,
            whole_lot_activation_upper_or_null=whole_upper,
            activation_costs_by_new_issuer={issuer: str(value) for issuer, value in sorted(activation_costs.items())},
            frozen_weight_lower_bounds=frozen_bounds),
        all_k_rows=k_rows, bounding_box_count_or_null=None if box_count is None else str(box_count),
        all_cash_control=dict(holding_count=0, feasible_conditionally=(numerical_ready and not positive_old and nonnegative_budget),
            positive_portfolio=False, winner_selected=False),
        coverage=dict(compositions_evaluated=0, quantity_tuples_evaluated=0, fits_evaluated=0,
            full_domain_exhausted=False, bounding_box_is_feasible_count=False,
            necessary_bounds_sufficient=False, source_qualified_domain_known=False),
        policy=dict(risk_parameters={key: str(value) for key, value in risk.items()},
            risk_tolerance=str(TOLERANCE), risk_model='EXACT_FRACTION_CONDITIONAL_FORK_ACCEPTANCE',
            policy_scope='SYNTHETIC_POLICY_UNBOUND' if input_scope == 'SYNTHETIC_UNBOUND' else 'CALLER_POLICY_UNBOUND',
            acceptance_constraints=['max(w)<=max_single+tol', 'min(w)>=min_single-tol',
                'sum(largest_three(w))<=top_weight_cap+tol',
                '1/sum(w*w)>=minimum_effective_n_ratio*k-tol',
                'max(sum(w by risk_chain))<=risk_chain_top1_cap+tol'],
            original_float_engine_bitwise_equivalence=False, transaction_cost_bps=str(fee_bps),
            minimum_cash_buffer=str(buffer), policy_binding_status='UNBOUND'),
        benchmark_context=dict(status='SOURCE_BLOCKED', incumbent_reference=deepcopy(references.get('INCUMBENT')),
            target_012922_reference=deepcopy(references.get('TARGET_012922')),
            comparable_economic_readiness=False),
        authority=dict.fromkeys(AUTHORITY_KEYS, False), current_account=None, current_new_money=None, plan_rows=[])
    # Only normalized, detached output participates; no arbitrary caller claim is serialized.
    normalized = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
    result['problem_id'] = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    return deepcopy(result)
