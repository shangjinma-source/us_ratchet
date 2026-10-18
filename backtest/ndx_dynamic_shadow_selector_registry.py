from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from backtest.ndx_dynamic_candidate_policy import POLICY_ROLES
from backtest.ndx_portfolio_objective import (
    canonical_sha256,
    file_sha256,
    load_objective_contract,
)


class NdxDynamicShadowSelectorRegistryError(ValueError):
    """Raised when the inactive dynamic-shadow selector registry is unsafe."""


UNIVERSE_TRACKS = ("strict_technology", "technology_plus_adjacent")
SELECTOR_ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
PRIMARY_RULES = {
    "RETURN": ("maximize_return_p50", "tie_breaker_only"),
    "BAD_TAIL": ("maximize_return_p10", "tie_breaker_only"),
    "DRAWDOWN": ("minimize_max_drawdown_p90", "tie_breaker_only"),
    "TARGET_ENVELOPE": (
        "minimize_training_target_012922_scalar_distance",
        "primary_training_rank_only",
    ),
    "USER_PREFERENCE": (
        "exact_equal_weight_user_preference_reference_if_point_in_time_eligible",
        "none",
    ),
}


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowSelectorRegistryError(f"{name} must be a mapping")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise NdxDynamicShadowSelectorRegistryError(f"{name} must be a list")
    return value


def _require_true(mapping: Mapping[str, Any], key: str, name: str) -> None:
    if mapping.get(key) is not True:
        raise NdxDynamicShadowSelectorRegistryError(f"{name}.{key} must be true")


def _require_false(mapping: Mapping[str, Any], key: str, name: str) -> None:
    if mapping.get(key) is not False:
        raise NdxDynamicShadowSelectorRegistryError(f"{name}.{key} must be false")


def _exact_keys(mapping: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(mapping)
    if actual != expected:
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise NdxDynamicShadowSelectorRegistryError(
            f"{name} keys mismatch; unknown={unknown}, missing={missing}"
        )


def _selector_id(universe_track: str, role: str) -> str:
    return f"{universe_track}__{role.lower()}__v1"


def validate_dynamic_shadow_selector_registry(registry: Mapping[str, Any]) -> None:
    _exact_keys(
        registry,
        {
            "schema_version",
            "registry_id",
            "status",
            "research_track",
            "migration_control_included",
            "source_contracts",
            "selector_matrix",
            "per_selector_contract",
            "parallel_path_boundary",
            "activation",
            "evidence_and_promotion",
            "mutation_boundary",
        },
        "selector registry",
    )
    if registry.get("schema_version") != 1:
        raise NdxDynamicShadowSelectorRegistryError("schema_version must be 1")
    if registry.get("registry_id") != "ndx_dynamic_shadow_selector_registry_v1":
        raise NdxDynamicShadowSelectorRegistryError("unexpected registry_id")
    if registry.get("status") != "INACTIVE_PRE_REGISTERED_RESEARCH_ONLY":
        raise NdxDynamicShadowSelectorRegistryError("selector registry must remain inactive")
    if registry.get("research_track") != "portfolio_optimization":
        raise NdxDynamicShadowSelectorRegistryError("selector registry must stay on portfolio_optimization")
    _require_false(registry, "migration_control_included", "selector registry")

    sources = _mapping(registry.get("source_contracts"), "source_contracts")
    _exact_keys(
        sources,
        {
            "objective",
            "dynamic_walkforward",
            "selector_policy_module",
            "hash_binding_state",
            "objective_sha256",
            "dynamic_walkforward_sha256",
            "selector_policy_module_sha256",
        },
        "source_contracts",
    )
    objective = _mapping(sources.get("objective"), "source_contracts.objective")
    walkforward = _mapping(sources.get("dynamic_walkforward"), "source_contracts.dynamic_walkforward")
    policy_module = _mapping(sources.get("selector_policy_module"), "source_contracts.selector_policy_module")
    _exact_keys(objective, {"path", "required_contract_id"}, "source_contracts.objective")
    _exact_keys(walkforward, {"path", "required_contract_id"}, "source_contracts.dynamic_walkforward")
    _exact_keys(
        policy_module,
        {"path", "required_policy_roles"},
        "source_contracts.selector_policy_module",
    )
    if objective.get("path") != "config/ndx_portfolio_objective_v1.yaml":
        raise NdxDynamicShadowSelectorRegistryError("objective source path mismatch")
    if objective.get("required_contract_id") != "ndx_portfolio_objective_v1":
        raise NdxDynamicShadowSelectorRegistryError("objective contract binding mismatch")
    if walkforward.get("path") != "config/ndx_dynamic_walkforward_v1.yaml":
        raise NdxDynamicShadowSelectorRegistryError("walkforward source path mismatch")
    if walkforward.get("required_contract_id") != "ndx_dynamic_walkforward_v1":
        raise NdxDynamicShadowSelectorRegistryError("walkforward contract binding mismatch")
    if policy_module.get("path") != "backtest/ndx_dynamic_candidate_policy.py":
        raise NdxDynamicShadowSelectorRegistryError("selector policy module path mismatch")
    if tuple(_list(policy_module.get("required_policy_roles"), "required_policy_roles")) != SELECTOR_ROLES:
        raise NdxDynamicShadowSelectorRegistryError("selector policy role binding mismatch")
    if sources.get("hash_binding_state") != "PENDING_ACTIVATION":
        raise NdxDynamicShadowSelectorRegistryError("inactive sources must remain pending activation")
    for key in ("objective_sha256", "dynamic_walkforward_sha256", "selector_policy_module_sha256"):
        if sources.get(key) is not None:
            raise NdxDynamicShadowSelectorRegistryError(f"inactive source hash must remain null: {key}")

    matrix = _mapping(registry.get("selector_matrix"), "selector_matrix")
    _exact_keys(
        matrix,
        {"universe_tracks", "policy_roles", "expected_selector_count", "selectors"},
        "selector_matrix",
    )
    if tuple(_list(matrix.get("universe_tracks"), "selector_matrix.universe_tracks")) != UNIVERSE_TRACKS:
        raise NdxDynamicShadowSelectorRegistryError("selector universe tracks must be strict and adjacent")
    if tuple(_list(matrix.get("policy_roles"), "selector_matrix.policy_roles")) != SELECTOR_ROLES:
        raise NdxDynamicShadowSelectorRegistryError("selector role matrix has drifted")
    if matrix.get("expected_selector_count") != len(UNIVERSE_TRACKS) * len(SELECTOR_ROLES):
        raise NdxDynamicShadowSelectorRegistryError("expected selector count must be 10")
    selectors = _list(matrix.get("selectors"), "selector_matrix.selectors")
    if len(selectors) != 10:
        raise NdxDynamicShadowSelectorRegistryError("selector registry must contain 10 independent lanes")
    seen_ids: set[str] = set()
    seen_coordinates: set[tuple[str, str]] = set()
    for index, raw_selector in enumerate(selectors):
        selector = _mapping(raw_selector, f"selector_matrix.selectors[{index}]")
        _exact_keys(
            selector,
            {
                "selector_id",
                "universe_track",
                "policy_role",
                "primary_selection_rule",
                "target_scalar_training_usage",
            },
            f"selector_matrix.selectors[{index}]",
        )
        universe_track = str(selector.get("universe_track", ""))
        role = str(selector.get("policy_role", ""))
        coordinate = (universe_track, role)
        selector_id = str(selector.get("selector_id", ""))
        if universe_track not in UNIVERSE_TRACKS or role not in SELECTOR_ROLES:
            raise NdxDynamicShadowSelectorRegistryError("selector coordinate is not registered")
        if selector_id != _selector_id(universe_track, role):
            raise NdxDynamicShadowSelectorRegistryError("selector_id is not deterministic")
        if selector_id in seen_ids or coordinate in seen_coordinates:
            raise NdxDynamicShadowSelectorRegistryError("selector coordinate is duplicated")
        expected_rule, expected_scalar_usage = PRIMARY_RULES[role]
        if selector.get("primary_selection_rule") != expected_rule:
            raise NdxDynamicShadowSelectorRegistryError(f"primary selector rule mismatch: {selector_id}")
        if selector.get("target_scalar_training_usage") != expected_scalar_usage:
            raise NdxDynamicShadowSelectorRegistryError(f"target scalar usage mismatch: {selector_id}")
        seen_ids.add(selector_id)
        seen_coordinates.add(coordinate)
    expected_coordinates = {(track, role) for track in UNIVERSE_TRACKS for role in SELECTOR_ROLES}
    if seen_coordinates != expected_coordinates:
        raise NdxDynamicShadowSelectorRegistryError("selector matrix is not the complete 2 x 5 product")

    per_selector = _mapping(registry.get("per_selector_contract"), "per_selector_contract")
    _exact_keys(
        per_selector,
        {
            "status",
            "dynamic_k",
            "fixed_holding_count",
            "monthly_decisions_immutable",
            "independent_path_required",
            "target_scalar_admission_allowed",
            "componentwise_012922_forward_gate_required_for_formal_admission",
            "original_8_no_inferiority_gate_required_for_formal_admission",
            "user_preference_tickers",
            "user_preference_role",
        },
        "per_selector_contract",
    )
    if per_selector.get("status") != "INACTIVE":
        raise NdxDynamicShadowSelectorRegistryError("every selector must remain inactive")
    if per_selector.get("dynamic_k") != "1..point_in_time_eligible_pool_distinct_issuer_count":
        raise NdxDynamicShadowSelectorRegistryError("selectors must preserve dynamic k")
    if per_selector.get("fixed_holding_count") is not None:
        raise NdxDynamicShadowSelectorRegistryError("selectors cannot fix the holding count")
    for key in (
        "monthly_decisions_immutable",
        "independent_path_required",
        "componentwise_012922_forward_gate_required_for_formal_admission",
        "original_8_no_inferiority_gate_required_for_formal_admission",
    ):
        _require_true(per_selector, key, "per_selector_contract")
    _require_false(per_selector, "target_scalar_admission_allowed", "per_selector_contract")
    if set(_list(per_selector.get("user_preference_tickers"), "user preference tickers")) != {
        "AMAT",
        "AVGO",
        "CDNS",
        "GOOG",
    }:
        raise NdxDynamicShadowSelectorRegistryError("user preference reference has drifted")
    if per_selector.get("user_preference_role") != "reference_not_fixed_answer":
        raise NdxDynamicShadowSelectorRegistryError("user preference cannot become a fixed answer")

    parallel = _mapping(registry.get("parallel_path_boundary"), "parallel_path_boundary")
    _exact_keys(
        parallel,
        {
            "selectors_run_in_parallel",
            "shared_point_in_time_input_snapshot_allowed",
            "shared_realized_path_allowed",
            "cross_selector_path_splicing_allowed",
            "winner_take_all_ex_post_selection_allowed",
            "policy_change_requires_new_selector_version",
            "missing_selector_may_be_silently_replaced",
        },
        "parallel_path_boundary",
    )
    for key in ("selectors_run_in_parallel", "shared_point_in_time_input_snapshot_allowed", "policy_change_requires_new_selector_version"):
        _require_true(parallel, key, "parallel_path_boundary")
    for key in (
        "shared_realized_path_allowed",
        "cross_selector_path_splicing_allowed",
        "winner_take_all_ex_post_selection_allowed",
        "missing_selector_may_be_silently_replaced",
    ):
        _require_false(parallel, key, "parallel_path_boundary")

    activation = _mapping(registry.get("activation"), "activation")
    _exact_keys(
        activation,
        {
            "active",
            "runner_registered",
            "automation_enabled",
            "decision_generation_allowed",
            "activation_manifest_required",
            "all_source_hashes_required",
            "separate_open_execution_and_close_valuation_required",
            "security_id_to_issuer_id_continuity_required",
            "issuer_trace_required",
            "next_common_session_calendar_proof_required",
            "immutable_append_only_path_artifacts_required",
        },
        "activation",
    )
    for key in ("active", "runner_registered", "automation_enabled", "decision_generation_allowed"):
        _require_false(activation, key, "activation")
    for key in (
        "activation_manifest_required",
        "all_source_hashes_required",
        "separate_open_execution_and_close_valuation_required",
        "security_id_to_issuer_id_continuity_required",
        "issuer_trace_required",
        "next_common_session_calendar_proof_required",
        "immutable_append_only_path_artifacts_required",
    ):
        _require_true(activation, key, "activation")

    promotion = _mapping(registry.get("evidence_and_promotion"), "evidence_and_promotion")
    _exact_keys(
        promotion,
        {
            "evidence_role",
            "selectors_count_as_v4_cohorts",
            "selectors_count_as_v4_regimes",
            "shadow_can_replace_v4_formal_gate",
            "target_scalar_can_admit",
            "configuration_candidate_promotion_allowed",
            "live_promotion_allowed",
        },
        "evidence_and_promotion",
    )
    if promotion.get("evidence_role") != "PARALLEL_DYNAMIC_SHADOW_RESEARCH_ONLY":
        raise NdxDynamicShadowSelectorRegistryError("selector evidence role must remain research-only")
    for key in (
        "selectors_count_as_v4_cohorts",
        "selectors_count_as_v4_regimes",
        "shadow_can_replace_v4_formal_gate",
        "target_scalar_can_admit",
        "configuration_candidate_promotion_allowed",
        "live_promotion_allowed",
    ):
        _require_false(promotion, key, "evidence_and_promotion")

    mutation = _mapping(registry.get("mutation_boundary"), "mutation_boundary")
    _exact_keys(
        mutation,
        {
            "research_output_only",
            "live_configuration_mutation_allowed",
            "state_mutation_allowed",
            "broker_snapshot_mutation_allowed",
            "today_advice_mutation_allowed",
            "order_creation_allowed",
        },
        "mutation_boundary",
    )
    _require_true(mutation, "research_output_only", "mutation_boundary")
    for key in (
        "live_configuration_mutation_allowed",
        "state_mutation_allowed",
        "broker_snapshot_mutation_allowed",
        "today_advice_mutation_allowed",
        "order_creation_allowed",
    ):
        _require_false(mutation, key, "mutation_boundary")


def load_dynamic_shadow_selector_registry(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path)
    try:
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowSelectorRegistryError(f"cannot read selector registry: {registry_path}") from exc
    registry = dict(_mapping(loaded, "selector registry"))
    validate_dynamic_shadow_selector_registry(registry)
    return registry


def _load_yaml(path: str | Path, name: str) -> dict[str, Any]:
    source_path = Path(path)
    try:
        loaded = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowSelectorRegistryError(f"cannot read {name}: {source_path}") from exc
    return dict(_mapping(loaded, name))


def build_dynamic_shadow_selector_registry_audit(
    *,
    registry_path: str | Path,
    objective_path: str | Path,
    dynamic_walkforward_path: str | Path,
    selector_policy_module_path: str | Path,
) -> dict[str, Any]:
    resolved_registry_path = Path(registry_path).resolve()
    registry = load_dynamic_shadow_selector_registry(resolved_registry_path)
    repository_root = resolved_registry_path.parent.parent

    def bound_source_path(section_name: str, supplied_path: str | Path) -> Path:
        declared = str(registry["source_contracts"][section_name]["path"])
        expected_path = (repository_root / declared).resolve()
        try:
            expected_path.relative_to(repository_root)
        except ValueError as exc:
            raise NdxDynamicShadowSelectorRegistryError(
                f"registered source escapes repository root: {section_name}"
            ) from exc
        actual_path = Path(supplied_path).resolve()
        if actual_path != expected_path:
            raise NdxDynamicShadowSelectorRegistryError(
                f"supplied source path does not match registry: {section_name}"
            )
        return expected_path

    bound_objective_path = bound_source_path("objective", objective_path)
    bound_walkforward_path = bound_source_path("dynamic_walkforward", dynamic_walkforward_path)
    bound_policy_module_path = bound_source_path("selector_policy_module", selector_policy_module_path)
    canonical_policy_module_path = Path(__file__).resolve().with_name("ndx_dynamic_candidate_policy.py")
    if bound_policy_module_path != canonical_policy_module_path:
        raise NdxDynamicShadowSelectorRegistryError(
            "registered selector policy module is not the imported canonical module"
        )

    objective = load_objective_contract(bound_objective_path)
    walkforward = _load_yaml(bound_walkforward_path, "dynamic walkforward contract")
    if walkforward.get("contract_id") != "ndx_dynamic_walkforward_v1":
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward contract_id mismatch")
    if walkforward.get("research_track") != "portfolio_optimization":
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward research track mismatch")
    if tuple(_list(walkforward.get("dynamic_policy_lanes"), "dynamic_policy_lanes")) != SELECTOR_ROLES:
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward policy lanes mismatch")
    capital = _mapping(walkforward.get("capital_contract"), "capital_contract")
    if (
        float(capital.get("initial_comparison_capital_usd", 0.0)) != 25000.0
        or float(capital.get("minimum_cash_buffer_usd", 0.0)) != 100.0
        or float(capital.get("transaction_cost_bps", -1.0)) != 10.0
    ):
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward capital contract mismatch")
    _require_true(capital, "fractional_and_whole_lot_tracks_required", "capital_contract")
    future_shadow = _mapping(walkforward.get("future_one_year_shadow"), "future_one_year_shadow")
    if (
        future_shadow.get("earliest_first_observation_month") != "2026-10"
        or future_shadow.get("decision_frequency") != "first_complete_us_session_each_month"
        or future_shadow.get("execution_timing")
        != "first_common_us_session_strictly_after_decision_at_nominal_open"
        or future_shadow.get("primary_path_horizon_trading_days") != 252
    ):
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward shadow timing mismatch")
    _require_true(future_shadow, "carries_cash_and_security_id_shares", "future_one_year_shadow")
    _require_false(future_shadow, "can_replace_v4_formal_gate", "future_one_year_shadow")
    _require_false(future_shadow, "can_promote_by_itself", "future_one_year_shadow")
    formal = _mapping(walkforward.get("formal_forward_gate"), "formal_forward_gate")
    if (
        formal.get("minimum_mature_fresh_cohorts") != 12
        or formal.get("cohort_horizon_trading_days") != 126
        or formal.get("minimum_distinct_regimes") != 2
        or formal.get("remains_required") is not True
    ):
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward weakens the v4 formal gate")
    comparisons = _mapping(walkforward.get("comparison_benchmarks"), "comparison_benchmarks")
    if tuple(_list(comparisons.get("original_8"), "comparison_benchmarks.original_8")) != (
        "NVDA",
        "TXN",
        "ASML",
        "CDNS",
        "TSM",
        "MU",
        "MSFT",
        "GOOG",
    ):
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward original-eight control mismatch")
    if str(comparisons.get("target")) != "012922":
        raise NdxDynamicShadowSelectorRegistryError("dynamic walkforward target benchmark mismatch")
    _require_false(comparisons, "single_path_scalar_target_distance_can_admit", "comparison_benchmarks")
    _require_false(walkforward, "promotion_allowed", "dynamic walkforward contract")
    live = _mapping(walkforward.get("live_mutation"), "live_mutation")
    for key in ("config", "state", "broker_snapshot", "today_advice", "orders"):
        _require_false(live, key, "live_mutation")
    if tuple(POLICY_ROLES) != SELECTOR_ROLES:
        raise NdxDynamicShadowSelectorRegistryError("selector policy module roles mismatch")
    if objective["dynamic_shadow_path"]["implementation_readiness"]["runner_registered"] is not False:
        raise NdxDynamicShadowSelectorRegistryError("objective shadow runner must remain unregistered")

    selectors = registry["selector_matrix"]["selectors"]
    return {
        "schema_version": 1,
        "audit_id": "ndx_dynamic_shadow_selector_registry_audit_v1",
        "audit_role": "inactive_registry_consistency_only",
        "registry": {
            "registry_id": registry["registry_id"],
            "status": registry["status"],
            "file_sha256": file_sha256(registry_path),
            "canonical_sha256": canonical_sha256(registry),
            "selector_count": len(selectors),
            "universe_tracks": list(UNIVERSE_TRACKS),
            "policy_roles": list(SELECTOR_ROLES),
        },
        "current_unbound_source_hashes": {
            "objective_sha256": file_sha256(bound_objective_path),
            "dynamic_walkforward_sha256": file_sha256(bound_walkforward_path),
            "selector_policy_module_sha256": file_sha256(bound_policy_module_path),
        },
        "activation": {
            "hash_binding_state": registry["source_contracts"]["hash_binding_state"],
            "active": False,
            "runner_registered": False,
            "automation_enabled": False,
            "decision_generation_allowed": False,
            "activation_ready": False,
        },
        "anti_splicing": {
            "complete_cross_product": True,
            "independent_selector_paths_required": True,
            "cross_selector_path_splicing_allowed": False,
            "winner_take_all_ex_post_selection_allowed": False,
        },
        "admission_boundary": {
            "target_scalar_can_admit": False,
            "componentwise_012922_forward_gate_required": True,
            "selectors_count_as_v4_cohorts": False,
            "shadow_can_replace_v4_formal_gate": False,
            "configuration_candidate_promotion_allowed": False,
            "live_promotion_allowed": False,
        },
        "mutation_assertions": {
            "research_output_only": True,
            "live_configuration_mutated": False,
            "state_mutated": False,
            "broker_snapshot_mutated": False,
            "today_advice_mutated": False,
            "orders_created": False,
        },
    }


def audit_json(payload: Mapping[str, Any]) -> str:
    """Stable rendering helper for tests and research-only script output."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = [
    "NdxDynamicShadowSelectorRegistryError",
    "SELECTOR_ROLES",
    "UNIVERSE_TRACKS",
    "audit_json",
    "build_dynamic_shadow_selector_registry_audit",
    "load_dynamic_shadow_selector_registry",
    "validate_dynamic_shadow_selector_registry",
]
