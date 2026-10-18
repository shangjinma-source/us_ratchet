"""All-k mathematical planning of an explicit pool; never prove NDX membership.

Only universal necessary bounds can prune a cardinality. Every input issuer
cardinality remains reported, including excluded values and unsearched values.
"""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re

from backtest import ndx_cardinality_search as combinatorics
from backtest import ndx_membership_scope_research as scope

_SOURCE = Path(__file__).resolve()
_LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
           (_SOURCE, Path(combinatorics.__file__).resolve(), Path(scope.__file__).resolve(),
            _SOURCE.with_name('ndx_dynamic_cutoff_refit_research.py'))}
_RISK_KEYS = ('max_single_weight', 'min_single_weight', 'top_weight_cap',
              'minimum_effective_n_ratio', 'risk_chain_top1_cap')
_RISK_TOLERANCE = Fraction(1, 10**9)
_SIMPLEX_TOLERANCE = Fraction(1, 10**9)
_ROUNDING_MARGIN_PER_TERM = Fraction(1, 10**12)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _verify(sources):
    if type(sources) is not dict or not sources:
        raise ValueError('Explicit nonempty mathematical-input source bindings required')
    for path, digest in sources.items():
        if (type(path) is not str or not Path(path).is_absolute() or type(digest) is not str
                or re.fullmatch('[0-9a-f]{64}', digest) is None):
            raise ValueError('Absolute source and canonical SHA256 required')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Cardinality plan source drift: ' + path)


def _merge(*mappings):
    result = {}
    for mapping in mappings:
        for path, digest in mapping.items():
            canonical = str(Path(path).resolve())
            if canonical in result and result[canonical] != digest:
                raise ValueError('Conflicting cardinality source bindings')
            result[canonical] = digest
    return result


def _rational(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def _necessary_bounds(k, risk):
    """Exact rational bounds on a deliberately widened acceptance envelope."""
    padding = (k + 1) * _ROUNDING_MARGIN_PER_TERM
    minimum_mass = max(Fraction(0), 1 - _SIMPLEX_TOLERANCE - padding)
    maximum_mass = 1 + _SIMPLEX_TOLERANCE + padding
    maximum_capacity = k * (risk['max_single_weight'] + _RISK_TOLERANCE) + padding
    minimum_required = k * max(Fraction(0), risk['min_single_weight'] - _RISK_TOLERANCE) - padding
    true_top3_lower_bound = Fraction(min(3, k), k) * minimum_mass
    accepted_top3_upper_bound = risk['top_weight_cap'] + _RISK_TOLERANCE + padding
    comparisons = (
        ('MAX_SINGLE_CAPACITY_BELOW_MINIMUM_SIMPLEX_MASS', maximum_capacity, '<', minimum_mass),
        ('MIN_SINGLE_REQUIRED_MASS_ABOVE_MAXIMUM_SIMPLEX_MASS', minimum_required, '>', maximum_mass),
        ('TRUE_TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_ACCEPTED_CAP', true_top3_lower_bound, '>', accepted_top3_upper_bound))
    certificates = []
    for reason, left, operator, right in comparisons:
        excluded = left < right if operator == '<' else left > right
        if excluded:
            certificates.append(dict(reason=reason, left=_rational(left), comparison=operator,
                right=_rational(right), strict_gap=_rational(abs(left - right)),
                arithmetic='EXACT_RATIONAL_DECIMAL_INPUT_WITH_CONSERVATIVE_TOLERANCE_AND_ROUNDING_PADDING'))
    return certificates


def build_membership_cardinality_plan_research(*, securities, risk_parameters, scope_path, scope_sha256,
                                               source_hashes, membership_input_status, exact_limit):
    """Plan all issuer cardinalities of an explicitly unverified input pool.

    This version accepts proxy/unverified pools only as mathematical examples.
    It cannot confer member status or authorize a search or a candidate trade.
    Risk thresholds and the exact/bounded engineering boundary are mandatory.
    """
    securities, risk_parameters, source_hashes = deepcopy((securities, risk_parameters, source_hashes))
    _verify(_LOADED)
    _verify(source_hashes)
    loaded_scope = scope.load_membership_scope_contract(path=scope_path, expected_sha256=scope_sha256)
    sources = _merge(_LOADED, source_hashes, loaded_scope['source_hashes'])
    if membership_input_status not in ('PROXY_INPUT_NOT_VERIFIED_MEMBERSHIP', 'EXPLICIT_INPUT_NOT_VERIFIED_MEMBERSHIP'):
        raise ValueError('Explicit unverified mathematical-pool status required; member status is not established here')
    if type(exact_limit) is not int or exact_limit < 1:
        raise ValueError('Positive explicit exact-enumeration engineering limit required')
    if type(securities) is not list or not securities:
        raise ValueError('Explicit nonempty security identity pool required')
    if type(risk_parameters) is not dict or set(risk_parameters) != set(_RISK_KEYS):
        raise ValueError('All five original risk parameters required')
    risk = {}
    for key, value in risk_parameters.items():
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Finite nonboolean risk parameter in [0,1] required: ' + key)
        risk[key] = Fraction(str(value))
    if (risk['max_single_weight'] <= 0 or risk['risk_chain_top1_cap'] <= 0
            or risk['min_single_weight'] > risk['max_single_weight']):
        raise ValueError('Invalid explicit original risk envelope')
    identities = []
    seen_securities, seen_tickers = set(), set()
    for row in securities:
        if type(row) is not dict or set(row) != {'security_id', 'issuer_id', 'ticker'}:
            raise ValueError('Exact security/issuer/ticker identity schema required')
        if any(type(value) is not str or not value or value != value.strip() for value in row.values()):
            raise ValueError('Canonical nonempty identity required')
        if (not row['security_id'].startswith('security:') or len(row['security_id']) <= 9
                or not row['issuer_id'].startswith('issuer:') or len(row['issuer_id']) <= 7
                or re.fullmatch('[A-Z0-9][A-Z0-9.-]*', row['ticker']) is None):
            raise ValueError('Canonical SID/issuer/ticker namespace required')
        if row['security_id'] in seen_securities or row['ticker'] in seen_tickers:
            raise ValueError('Duplicate security or concurrent ticker identity')
        seen_securities.add(row['security_id'])
        seen_tickers.add(row['ticker'])
        identities.append(dict(row))
    identities.sort(key=lambda row: row['security_id'])
    multiplicities = Counter(row['issuer_id'] for row in identities)
    issuer_counts = combinatorics.issuer_dedup_combination_counts([multiplicities[key] for key in sorted(multiplicities)])
    security_count, issuer_count = len(identities), len(multiplicities)
    rows = []
    for k in range(1, issuer_count + 1):
        combinations = int(issuer_counts[k])
        certificates = _necessary_bounds(k, risk)
        rows.append(dict(holding_count=k, raw_security_combinations=str(math.comb(security_count, k)),
            issuer_unique_security_combinations=str(combinations),
            issuer_collision_pruned_combinations=str(math.comb(security_count, k) - combinations),
            structural_status='STRUCTURALLY_INFEASIBLE_NECESSARY_BOUND' if certificates else 'NOT_PROVEN_FEASIBLE',
            infeasibility_certificates=certificates,
            planned_search_mode='NO_SEARCH_NECESSARY_BOUND_PROOF' if certificates
                                else ('EXACT_ENUMERATION' if combinations <= exact_limit else 'BOUNDED_MULTIOBJECTIVE_SEARCH'),
            planned_action='NO_SEARCH_NECESSARY_BOUND_PROOF' if certificates
                           else 'SEARCH_NOT_AUTHORIZED_MEMBERSHIP_AND_DATA_VALIDATION_REQUIRED',
            search_executed=False, search_admission_allowed=False, feasible_portfolio_proven=False,
            evaluated_security_sets=0, unevaluated_issuer_unique_security_sets=str(combinations)))
    payload = dict(securities=identities, risk_parameters=risk_parameters, membership_input_status=membership_input_status,
                   scope_contract_sha256=scope_sha256, exact_limit=exact_limit)
    _verify(sources)
    return dict(schema='ndx_membership_cardinality_plan_research_v1', scope_contract_id=scope.CONTRACT_ID,
        scope_changed=True, industry_filter_applied=False, input_sha256=_digest(payload), source_hashes=sources,
        input_securities=identities, input_security_count=security_count, input_distinct_issuer_count=issuer_count,
        issuer_security_multiplicities=dict(sorted(multiplicities.items())), risk_parameters=dict(risk_parameters),
        membership_input_status=membership_input_status, universe_count_scope='SUPPLIED_IDENTITY_POOL_MATHEMATICS_ONLY',
        verified_ndx_security_count=None, verified_ndx_issuer_count=None, full_ndx_coverage_verified=False,
        membership_evidence_verified=False, candidate_admission_allowed=False, all_input_cardinalities_reported=True,
        minimum_reported_k=1, maximum_reported_k=issuer_count, cardinality_row_count=len(rows),
        structurally_excluded_cardinality_count=sum(bool(row['infeasibility_certificates']) for row in rows),
        not_proven_feasible_cardinality_count=sum(not row['infeasibility_certificates'] for row in rows),
        exact_enumeration_limit=exact_limit, rows=rows,
        certificate_policy=dict(risk_check_tolerance='0.000000001', simplex_tolerance='0.000000001',
            tolerance_source_path=str(_SOURCE.with_name('ndx_dynamic_cutoff_refit_research.py')),
            conservative_rounding_padding='(k+1)*0.000000000001',
            original_risk_thresholds_changed=False, true_top3_count='min(3,k)',
            excluded_only_if_widened_necessary_bound_strictly_violated=True,
            nonexcluded_cardinality_does_not_prove_feasibility=True),
        risk_chain_assignment_feasibility_verified=False, effective_n_feasibility_verified=False,
        liquidity_verified=False, whole_lot_execution_verified=False, identity_evidence_authenticated=False,
        training_or_refit_performed=False, search_performed=False, execution_performed=False, unique_selection_performed=False,
        global_optimum_proven=False, point_in_time_verified=False, promotion_allowed=False,
        portfolio_track='portfolio_optimization', migration_control_included=False)
