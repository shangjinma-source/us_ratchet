"""Load the authorized NDX membership scope, without authenticating membership.

This module validates policy only. Membership evidence, full universe coverage,
identity, liquidity and the original risk gates require independent validation.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

import yaml

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
CONTRACT_ID = 'ndx_membership_scope_research_v1'
_EXPECTED = dict(
    schema_version=1, contract_id=CONTRACT_ID, status='USER_AUTHORIZED_SCOPE_CHANGE_RESEARCH_ONLY',
    research_track='portfolio_optimization', migration_control_included=False,
    scope_change=dict(scope_changed=True, authorized_scope='ALL_POINT_IN_TIME_NASDAQ_100_MEMBERS_MAY_COMPETE',
        industry_filter_applied=False, pure_technology_requirement_removed=True,
        existing_frozen_contracts_mutated=False, existing_frozen_results_relabelled=False),
    membership_contract=dict(scope_basis='POINT_IN_TIME_NASDAQ_100_MEMBERSHIP',
        permitted_status='VERIFIED_POINT_IN_TIME_MEMBER', nonmember_policy='EXCLUDE_AND_REPORT',
        unknown_membership_policy='EXCLUDE_AND_REPORT_NOT_ACCEPT', identity_bound_membership_evidence_required=True,
        evidence_available_by_decision_required=True, membership_effective_on_decision_required=True,
        evidence_information_cutoff='DECISION_DATA_CUTOFF_NOT_EXECUTION_DATE',
        membership_effective_asof='DECISION_SESSION',
        announced_future_membership_policy='NOT_CURRENT_MEMBER_UNTIL_EFFECTIVE_AND_REVALIDATED',
        current_snapshot_historical_backfill_allowed=False, observation_date_equals_effective_date_assumed=False,
        source_hash_alone_proves_membership=False, index_etf_is_stock_candidate=False),
    unchanged_guards=dict(original_identity_requirements_preserved=True, one_security_per_issuer_per_portfolio=True,
        original_liquidity_thresholds_preserved=True, original_five_risk_thresholds_preserved=True,
        original_risk_parameter_source='EXPLICIT_ORIGINAL_PER_RUN_CONTRACT', risk_threshold_override_allowed=False,
        risk_chain_role='CONCENTRATION_EVIDENCE_NOT_INDUSTRY_ELIGIBILITY',
        missing_risk_chain_policy='BLOCK_RISK_VALIDATION_NOT_DECLARE_NONMEMBER',
        original_execution_cost_and_cash_rules_preserved=True, original_dual_benchmark_and_forward_requirements_preserved=True),
    cardinality_contract=dict(minimum_k=1, maximum_k='VERIFIED_ELIGIBLE_POOL_DISTINCT_ISSUER_COUNT', fixed_k=None,
        securities_count_assumed_to_equal_100=False, shared_issuer_share_classes_increase_k_upper_bound=False,
        composition_and_weights_compete=True, user_preference_role='REFERENCE_NOT_FIXED_ANSWER'),
    legacy_evidence_contract=dict(strict_technology_role='LEGACY_SUBSET_NOT_FULL_NASDAQ_100',
        technology_plus_adjacent_role='LEGACY_SUBSET_NOT_FULL_NASDAQ_100',
        frozen_training_results_reusable_as_subset_evidence=True, legacy_subsets_prove_full_membership_coverage=False,
        legacy_risk_labels_prove_membership=False, complete_universe_claim_requires_independent_full_denominator=True,
        current_contract_reconstructs_missing_historical_rules=False),
    mutation_boundary=dict(research_only=True, membership_evidence_verified_by_contract=False,
        point_in_time_verified_by_contract=False, full_universe_coverage_verified_by_contract=False,
        promotion_allowed=False, live_config_mutation_allowed=False, state_mutation_allowed=False,
        broker_snapshot_mutation_allowed=False, today_advice_mutation_allowed=False,
        order_creation_allowed=False, scheduler_mutation_allowed=False))


def validate_membership_scope_contract(contract):
    """Reject any change to this version's scope or unchanged safety contracts."""
    def check(actual, expected, path):
        if type(actual) is not type(expected):
            raise ValueError('Membership scope contract type differs: ' + path)
        if type(expected) is dict:
            if set(actual) != set(expected):
                raise ValueError('Exact membership scope schema required: ' + path)
            for key, value in expected.items():
                check(actual[key], value, path + '.' + key)
        elif actual != expected:
            raise ValueError('Membership scope contract value differs: ' + path)
    check(contract, _EXPECTED, CONTRACT_ID)


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            raise ValueError('Duplicate or nonstring membership contract key')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_membership_scope_contract(*, path, expected_sha256):
    """Read an explicitly SHA-bound new research contract, with source checks."""
    if type(expected_sha256) is not str or re.fullmatch('[0-9a-f]{64}', expected_sha256) is None:
        raise ValueError('Explicit canonical membership scope SHA256 required')
    target = Path(path).resolve()
    if hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _LOADED_SHA:
        raise ValueError('Loaded membership scope source drift')
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Membership scope contract SHA differs')
    try:
        contract = yaml.load(raw.decode('utf-8-sig'), Loader=_UniqueLoader)
    except yaml.YAMLError as error:
        raise ValueError('Invalid membership scope YAML') from error
    validate_membership_scope_contract(contract)
    sources = {str(_SOURCE): _LOADED_SHA, str(target): expected_sha256}
    for source, digest in sources.items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest() != digest:
            raise ValueError('Membership scope source changed during load')
    return dict(schema='ndx_membership_scope_research_load_v1', contract=deepcopy(contract), source_hashes=sources,
        scope_changed=True, industry_filter_applied=False, contract_validated=True,
        membership_evidence_verified=False, point_in_time_verified=False,
        full_universe_coverage_verified=False, promotion_allowed=False)
