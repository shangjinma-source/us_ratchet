from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


class NdxPortfolioObjectiveError(ValueError):
    """Raised when the research objective contract or its evidence is invalid."""


TARGET_COMPONENTS = (
    "return_p50",
    "return_p10",
    "max_drawdown_p50",
    "max_drawdown_p90",
)
EXECUTION_TRACKS = ("continuous", "whole_lot")
ORIGINAL_8 = ("NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG")
HISTORICAL_RESEARCH_THRESHOLDS = {
    "min_rolling_windows": 12,
    "min_target_win_rate": 0.50,
    "min_target_excess_p50": 0.0,
    "max_target_dd_cost_p50": 0.03,
    "max_target_dd_cost_bad_tail": 0.05,
    "min_incumbent_xirr_margin_p50": -0.001,
    "min_incumbent_xirr_margin_p10": -0.02,
    "max_incumbent_dd_cost_p50": 0.005,
    "max_incumbent_dd_cost_p90": 0.02,
}
SHADOW_INTEGRITY_GUARDS = (
    "point_in_time_guard_passed",
    "next_session_execution_passed",
    "selection_policy_version_continuity_passed",
    "monthly_schedule_completeness_passed",
    "security_id_continuity_passed",
    "issuer_uniqueness_passed",
    "whole_share_invariant_passed",
    "cash_conservation_passed",
    "accounting_invariant_passed",
    "cash_buffer_preserved",
    "external_cash_flow_absence_passed",
    "completed_session_path_continuity_passed",
    "benchmark_calendar_alignment_passed",
    "immutable_trace_passed",
)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, Path)):
        return value.isoformat() if not isinstance(value, Path) else str(value)
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NdxPortfolioObjectiveError(f"{name} must be a mapping")
    return value


def _sequence(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise NdxPortfolioObjectiveError(f"{name} must be a list")
    return value


def _require_false(mapping: Mapping[str, Any], key: str, name: str) -> None:
    if mapping.get(key) is not False:
        raise NdxPortfolioObjectiveError(f"{name}.{key} must be false")


def _require_true(mapping: Mapping[str, Any], key: str, name: str) -> None:
    if mapping.get(key) is not True:
        raise NdxPortfolioObjectiveError(f"{name}.{key} must be true")


def validate_objective_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != 1:
        raise NdxPortfolioObjectiveError("schema_version must be 1")
    if contract.get("contract_id") != "ndx_portfolio_objective_v1":
        raise NdxPortfolioObjectiveError("unexpected contract_id")

    objective = _mapping(contract.get("user_objective"), "user_objective")
    if objective.get("objective_mode") != "relative_dynamic_benchmark":
        raise NdxPortfolioObjectiveError("the primary objective must remain benchmark-relative")
    if str(objective.get("primary_target_id")) != "012922":
        raise NdxPortfolioObjectiveError("primary target must be 012922")
    absolute = _mapping(objective.get("absolute_targets"), "user_objective.absolute_targets")
    if absolute.get("annualized_return_floor") is not None:
        raise NdxPortfolioObjectiveError("annualized_return_floor must remain null until the user states one")
    if absolute.get("max_drawdown_ceiling") is not None:
        raise NdxPortfolioObjectiveError("max_drawdown_ceiling must remain null until the user states one")
    _require_false(absolute, "explicitly_stated_by_user", "user_objective.absolute_targets")
    _require_false(objective, "safe_leg_included", "user_objective")

    data_sources = _mapping(contract.get("data_sources"), "data_sources")
    target_source = _mapping(data_sources.get("target_012922"), "data_sources.target_012922")
    if str(target_source.get("expected_dataset_key")) != "012922":
        raise NdxPortfolioObjectiveError("target data source must be 012922")
    if target_source.get("expected_dataset_type") != "fund_nav":
        raise NdxPortfolioObjectiveError("target data source must be fund NAV")
    if target_source.get("refresh_semantics") != "dynamic_latest_verified_manifest":
        raise NdxPortfolioObjectiveError("012922 must be refreshed from a verified dynamic manifest")
    broker_source = _mapping(data_sources.get("broker_account_overlay"), "data_sources.broker_account_overlay")
    if broker_source.get("refresh_semantics") != "user_confirmed_snapshot_only":
        raise NdxPortfolioObjectiveError("broker overlay membership requires user-confirmed snapshots")

    registry = _mapping(contract.get("benchmark_registry"), "benchmark_registry")
    target = _mapping(registry.get("target_012922"), "benchmark_registry.target_012922")
    if target.get("benchmark_role") != "dynamic_external_target":
        raise NdxPortfolioObjectiveError("012922 must be a dynamic external target")
    _require_false(target, "fixed_metric_values", "benchmark_registry.target_012922")
    incumbent = _mapping(registry.get("original_8_incumbent"), "benchmark_registry.original_8_incumbent")
    if tuple(_sequence(incumbent.get("tickers"), "original_8_incumbent.tickers")) != ORIGINAL_8:
        raise NdxPortfolioObjectiveError("the original-eight research control has drifted")
    broker = _mapping(registry.get("broker_account_overlay"), "benchmark_registry.broker_account_overlay")
    if broker.get("benchmark_role") != "execution_truth_overlay_not_optimization_benchmark":
        raise NdxPortfolioObjectiveError("broker holdings must remain an execution overlay")
    _require_false(broker, "may_be_used_as_original_8_control", "benchmark_registry.broker_account_overlay")

    cardinality = _mapping(contract.get("portfolio_cardinality"), "portfolio_cardinality")
    if cardinality.get("mode") != "dynamic" or cardinality.get("minimum_k") != 1:
        raise NdxPortfolioObjectiveError("portfolio cardinality must be dynamic from k=1")
    if cardinality.get("maximum_k") != "eligible_pool_distinct_issuer_count":
        raise NdxPortfolioObjectiveError("maximum k must follow the eligible issuer pool")
    if cardinality.get("fixed_k") is not None:
        raise NdxPortfolioObjectiveError("fixed_k must be null")
    _require_false(cardinality, "eight_is_target_holding_count", "portfolio_cardinality")
    preference = _mapping(cardinality.get("user_preference_reference"), "portfolio_cardinality.user_preference_reference")
    if set(_sequence(preference.get("tickers"), "user_preference_reference.tickers")) != {"AMAT", "AVGO", "CDNS", "GOOG"}:
        raise NdxPortfolioObjectiveError("the four-ticker user preference reference has drifted")
    if preference.get("role") != "direction_reference_not_fixed_answer":
        raise NdxPortfolioObjectiveError("the user preference set cannot be a fixed answer")

    tracks = _mapping(contract.get("optimization_tracks"), "optimization_tracks")
    portfolio_track = _mapping(tracks.get("portfolio_optimization"), "optimization_tracks.portfolio_optimization")
    migration_track = _mapping(tracks.get("migration_control"), "optimization_tracks.migration_control")
    if portfolio_track.get("candidate_k") != "1..eligible_pool_distinct_issuer_count":
        raise NdxPortfolioObjectiveError("portfolio optimization must search dynamic k")
    _require_false(portfolio_track, "frozen_incumbent_action_scope", "optimization_tracks.portfolio_optimization")
    _require_false(migration_track, "eight_or_nine_positions_are_target_cardinality", "optimization_tracks.migration_control")
    _require_false(migration_track, "may_determine_portfolio_optimization_k", "optimization_tracks.migration_control")

    metrics = _mapping(contract.get("metric_contract"), "metric_contract")
    target_gate = _mapping(metrics.get("target_012922_componentwise_gate"), "metric_contract.target_012922_componentwise_gate")
    if tuple(_sequence(target_gate.get("dimensions"), "target gate dimensions")) != TARGET_COMPONENTS:
        raise NdxPortfolioObjectiveError("012922 gate must cover all four registered dimensions")
    if tuple(_sequence(target_gate.get("tracks"), "target gate tracks")) != EXECUTION_TRACKS:
        raise NdxPortfolioObjectiveError("012922 gate must apply to both execution tracks")
    if target_gate.get("rule") != "candidate_absolute_distance_to_target_lte_control_absolute_distance_for_every_dimension":
        raise NdxPortfolioObjectiveError("012922 admission must be componentwise")
    if target_gate.get("require_at_least_one_strict_improvement") is not True:
        raise NdxPortfolioObjectiveError("the target gate requires at least one strict improvement")
    scalar = _mapping(target_gate.get("scalar_l1_distance"), "target gate scalar_l1_distance")
    _require_false(scalar, "admission_decision_allowed", "target gate scalar_l1_distance")
    incumbent_gate = _mapping(metrics.get("incumbent_no_inferiority_gate"), "metric_contract.incumbent_no_inferiority_gate")
    if tuple(_sequence(incumbent_gate.get("tracks"), "incumbent gate tracks")) != EXECUTION_TRACKS:
        raise NdxPortfolioObjectiveError("incumbent no-inferiority must apply to both execution tracks")
    for key in (
        "paired_return_p50_minimum",
        "paired_return_p10_minimum",
        "paired_drawdown_cost_p50_maximum",
        "paired_drawdown_cost_p90_maximum",
    ):
        if not math.isclose(_finite_number(incumbent_gate.get(key), f"incumbent gate {key}"), 0.0, abs_tol=1e-12):
            raise NdxPortfolioObjectiveError(f"incumbent no-inferiority threshold must be zero: {key}")

    execution = _mapping(contract.get("execution_contract"), "execution_contract")
    if float(execution.get("standardized_comparison_capital_usd", 0.0)) != 25000.0:
        raise NdxPortfolioObjectiveError("standardized comparison capital must be $25,000")
    if execution.get("standardized_comparison_capital_role") != "full_sleeve_comparison_capital_not_deployable_cash":
        raise NdxPortfolioObjectiveError("$25,000 must not be interpreted as deployable cash")
    if _finite_number(execution.get("minimum_cash_buffer_usd"), "minimum_cash_buffer_usd") != 100.0:
        raise NdxPortfolioObjectiveError("minimum execution buffer must be $100")
    if _finite_number(execution.get("transaction_cost_bps"), "transaction_cost_bps") != 10.0:
        raise NdxPortfolioObjectiveError("forward comparison cost must be 10 bps")
    execution_tracks = _mapping(execution.get("tracks"), "execution_contract.tracks")
    if set(execution_tracks) != set(EXECUTION_TRACKS):
        raise NdxPortfolioObjectiveError("continuous and whole-lot tracks are both required")
    whole_lot = _mapping(execution_tracks["whole_lot"], "execution_contract.tracks.whole_lot")
    if whole_lot.get("fractional_shares_allowed") is not False:
        raise NdxPortfolioObjectiveError("whole-lot execution cannot allow fractional shares")
    if whole_lot.get("role") != "dynamic_security_id_continuous_whole_lot_rebalance":
        raise NdxPortfolioObjectiveError("whole-lot track must support dynamic security-id rebalancing")
    if whole_lot.get("ticker_rename_is_trade") is not False:
        raise NdxPortfolioObjectiveError("ticker rename must not create an economic trade")
    if whole_lot.get("genuine_membership_change_is_two_sided_trade") is not True:
        raise NdxPortfolioObjectiveError("genuine member replacement must charge both trade sides")
    if whole_lot.get("cash_and_shares_carried_between_rebalances") is not True:
        raise NdxPortfolioObjectiveError("whole-lot cash and shares must remain continuous")

    shadow = _mapping(contract.get("dynamic_shadow_path"), "dynamic_shadow_path")
    if shadow.get("path_contract_id") != "ndx_dynamic_portfolio_shadow_path_v1":
        raise NdxPortfolioObjectiveError("unexpected dynamic shadow path contract")
    if shadow.get("status") != "PRE_REGISTERED_RESEARCH_SHADOW_NOT_ADMISSION":
        raise NdxPortfolioObjectiveError("dynamic shadow path must remain research-only")
    if shadow.get("portfolio_track") != "portfolio_optimization":
        raise NdxPortfolioObjectiveError("dynamic shadow path belongs to portfolio optimization")
    _require_false(shadow, "migration_control_included", "dynamic_shadow_path")

    availability = _mapping(shadow.get("availability"), "dynamic_shadow_path.availability")
    if str(availability.get("planned_first_decision_on_or_after")) != "2026-10-01":
        raise NdxPortfolioObjectiveError("dynamic shadow path start must not be backfilled")
    if availability.get("one_year_review_target_quarter") != "2027Q4":
        raise NdxPortfolioObjectiveError("dynamic shadow path must target a review by approximately 2027Q4")
    _require_true(
        availability,
        "target_is_operational_timeline_not_performance_guarantee",
        "dynamic_shadow_path.availability",
    )
    if availability.get("minimum_completed_trading_days") != 252:
        raise NdxPortfolioObjectiveError("one-year shadow review requires 252 completed trading days")
    if availability.get("minimum_executed_monthly_rebalances") != 12:
        raise NdxPortfolioObjectiveError("one-year shadow review requires 12 executed monthly rebalances")
    _require_true(availability, "both_requirements_must_pass", "dynamic_shadow_path.availability")

    selection = _mapping(shadow.get("selection"), "dynamic_shadow_path.selection")
    if selection.get("frequency") != "monthly_first_completed_us_trading_session":
        raise NdxPortfolioObjectiveError("dynamic shadow selection must run monthly")
    if selection.get("decision_time") != "completed_session_close":
        raise NdxPortfolioObjectiveError("dynamic shadow decisions require a completed session")
    if selection.get("information_cutoff") != "all_inputs_available_no_later_than_decision_time":
        raise NdxPortfolioObjectiveError("dynamic shadow selection must be point-in-time")
    selected_fields = set(_sequence(selection.get("selected_fields"), "dynamic shadow selected_fields"))
    if selected_fields != {"k", "security_ids", "issuer_ids", "ticker_labels", "target_weights"}:
        raise NdxPortfolioObjectiveError("dynamic shadow selection must choose k, members, and weights")
    if selection.get("target_k_minimum") != 1:
        raise NdxPortfolioObjectiveError("dynamic shadow target k must start at 1")
    if selection.get("target_k_maximum") != "eligible_pool_distinct_issuer_count_at_decision_time":
        raise NdxPortfolioObjectiveError("dynamic shadow maximum k must follow the point-in-time issuer pool")
    _require_true(selection, "one_security_per_issuer_required", "dynamic_shadow_path.selection")
    _require_true(selection, "point_in_time_eligibility_required", "dynamic_shadow_path.selection")

    shadow_execution = _mapping(shadow.get("execution"), "dynamic_shadow_path.execution")
    if shadow_execution.get("execution_session") != "first_common_us_trading_session_strictly_after_decision":
        raise NdxPortfolioObjectiveError("dynamic shadow execution must occur on the next common session")
    if shadow_execution.get("execution_price") != "nominal_unadjusted_session_open":
        raise NdxPortfolioObjectiveError("dynamic shadow execution must use the next-session nominal open")
    if shadow_execution.get("valuation_price") != "nominal_unadjusted_session_close":
        raise NdxPortfolioObjectiveError("dynamic shadow valuation must use nominal closes")
    _require_false(shadow_execution, "same_session_execution_allowed", "dynamic_shadow_path.execution")
    if _finite_number(shadow_execution.get("standardized_initial_cash_usd"), "shadow initial cash") != 25000.0:
        raise NdxPortfolioObjectiveError("dynamic shadow initial comparison cash must be $25,000")
    if _finite_number(shadow_execution.get("minimum_cash_buffer_usd"), "shadow cash buffer") != 100.0:
        raise NdxPortfolioObjectiveError("dynamic shadow cash buffer must be $100")
    if _finite_number(shadow_execution.get("transaction_cost_bps"), "shadow transaction cost") != 10.0:
        raise NdxPortfolioObjectiveError("dynamic shadow transaction cost must be 10 bps")
    _require_false(shadow_execution, "fractional_shares_allowed", "dynamic_shadow_path.execution")
    if shadow_execution.get("security_identity_key") != "security_id":
        raise NdxPortfolioObjectiveError("dynamic shadow continuity must use security_id")
    _require_true(shadow_execution, "cash_and_shares_carried_between_rebalances", "dynamic_shadow_path.execution")
    _require_false(shadow_execution, "external_cash_flows_allowed", "dynamic_shadow_path.execution")
    _require_false(shadow_execution, "ticker_rename_is_trade", "dynamic_shadow_path.execution")
    _require_true(shadow_execution, "genuine_membership_change_is_two_sided_trade", "dynamic_shadow_path.execution")

    versioning = _mapping(shadow.get("versioning"), "dynamic_shadow_path.versioning")
    for key in (
        "selector_policy_must_be_preregistered",
        "monthly_decisions_are_immutable",
        "policy_change_requires_new_parallel_path_id",
    ):
        _require_true(versioning, key, "dynamic_shadow_path.versioning")
    for key in ("backfill_allowed", "winning_path_splicing_allowed"):
        _require_false(versioning, key, "dynamic_shadow_path.versioning")

    implementation = _mapping(shadow.get("implementation_readiness"), "dynamic_shadow_path.implementation_readiness")
    _require_true(implementation, "contract_defined", "dynamic_shadow_path.implementation_readiness")
    _require_false(implementation, "runner_registered", "dynamic_shadow_path.implementation_readiness")
    _require_false(implementation, "automation_enabled", "dynamic_shadow_path.implementation_readiness")
    if implementation.get("operational_status") != "CONTRACT_ONLY_PENDING_POINT_IN_TIME_RUNNER":
        raise NdxPortfolioObjectiveError("dynamic shadow path must not be reported operational before runner registration")
    required_before_activation = set(
        _sequence(implementation.get("required_before_activation"), "dynamic shadow activation requirements")
    )
    if required_before_activation != {
        "separate_next_open_execution_and_close_valuation_price_channels",
        "immutable_selector_policy_artifact_and_hash",
        "point_in_time_security_id_and_issuer_id_selection_trace",
        "complete_monthly_schedule_with_no_retrospective_backfill",
        "same_calendar_012922_and_original_8_controls",
        "append_only_rebalance_trade_cash_and_path_manifests",
    }:
        raise NdxPortfolioObjectiveError("dynamic shadow activation requirements are incomplete")

    evidence_verification = _mapping(
        shadow.get("evidence_verification"),
        "dynamic_shadow_path.evidence_verification",
    )
    if evidence_verification.get("status") != "DISABLED_UNTIL_IMMUTABLE_RUNNER_ARTIFACT_VERIFIER":
        raise NdxPortfolioObjectiveError("dynamic shadow evidence verifier must remain disabled before runner registration")
    _require_false(
        evidence_verification,
        "self_reported_counts_allowed",
        "dynamic_shadow_path.evidence_verification",
    )
    _require_false(
        evidence_verification,
        "self_reported_guard_booleans_allowed",
        "dynamic_shadow_path.evidence_verification",
    )
    if set(_sequence(evidence_verification.get("required_artifact_hashes"), "shadow evidence artifact hashes")) != {
        "runner_contract_sha256",
        "selector_registry_sha256",
        "selection_input_manifest_sha256",
        "execution_price_manifest_sha256",
        "rebalance_trace_sha256",
        "trade_trace_sha256",
        "daily_path_trace_sha256",
        "original_8_control_trace_sha256",
        "target_012922_trace_sha256",
        "us_session_calendar_manifest_sha256",
    }:
        raise NdxPortfolioObjectiveError("dynamic shadow evidence artifact hash requirements are incomplete")

    shadow_benchmarks = _mapping(shadow.get("benchmarks"), "dynamic_shadow_path.benchmarks")
    if set(_sequence(shadow_benchmarks.get("required"), "dynamic shadow benchmarks")) != {
        "target_012922",
        "original_8_incumbent",
    }:
        raise NdxPortfolioObjectiveError("dynamic shadow path requires both registered benchmarks")
    _require_true(shadow_benchmarks, "same_calendar_required", "dynamic_shadow_path.benchmarks")
    _require_true(
        shadow_benchmarks,
        "same_starting_capital_for_executable_control_required",
        "dynamic_shadow_path.benchmarks",
    )
    _require_false(shadow_benchmarks, "broker_account_overlay_included", "dynamic_shadow_path.benchmarks")

    evidence_boundary = _mapping(shadow.get("evidence_boundary"), "dynamic_shadow_path.evidence_boundary")
    if evidence_boundary.get("before_one_year_role") != "EARLY_FALSIFICATION_AND_PROGRESS_ONLY":
        raise NdxPortfolioObjectiveError("pre-one-year shadow evidence must remain diagnostic")
    if evidence_boundary.get("one_year_role") != "SUPPORTING_NON_SUFFICIENT_RESEARCH_EVIDENCE":
        raise NdxPortfolioObjectiveError("one-year shadow evidence cannot be sufficient for admission")
    _require_true(evidence_boundary, "may_open_internal_shadow_review", "dynamic_shadow_path.evidence_boundary")
    for key in (
        "formal_v4_gate_substitution_allowed",
        "counts_as_v4_fresh_mature_cohort",
        "counts_as_v4_distinct_regime",
        "single_adaptive_path_is_independent_cohort_sample",
        "path_level_metrics_can_satisfy_componentwise_formal_gate",
        "direct_configuration_candidate_promotion_allowed",
        "direct_live_promotion_allowed",
        "automatic_performance_veto_allowed_without_preregistered_rule",
    ):
        _require_false(evidence_boundary, key, "dynamic_shadow_path.evidence_boundary")
    if evidence_boundary.get("registered_performance_falsification_rule_id") is not None:
        raise NdxPortfolioObjectiveError("no dynamic-shadow performance veto is currently preregistered")
    _require_true(evidence_boundary, "integrity_failure_blocks_evidence", "dynamic_shadow_path.evidence_boundary")
    if tuple(_sequence(shadow.get("required_integrity_guards"), "dynamic shadow integrity guards")) != SHADOW_INTEGRITY_GUARDS:
        raise NdxPortfolioObjectiveError("dynamic shadow integrity guard registry is incomplete")

    formal_relationship = _mapping(shadow.get("formal_gate_relationship"), "dynamic_shadow_path.formal_gate_relationship")
    if formal_relationship.get("formal_gate_policy_id") != "ndx_challenger_forward_v4_componentwise_target_amendment_v1":
        raise NdxPortfolioObjectiveError("dynamic shadow path must point to the v4 formal gate")
    _require_true(formal_relationship, "formal_gate_remains_required", "dynamic_shadow_path.formal_gate_relationship")
    for key, expected in (
        ("formal_gate_primary_horizon_trading_days", 126),
        ("formal_gate_minimum_fresh_mature_cohorts", 12),
        ("formal_gate_minimum_distinct_regimes", 2),
    ):
        if formal_relationship.get(key) != expected:
            raise NdxPortfolioObjectiveError(f"dynamic shadow path cannot weaken the formal gate: {key}")

    stage_policy = _mapping(contract.get("stage_policy"), "stage_policy")
    if not str(stage_policy.get("policy_version", "")).strip():
        raise NdxPortfolioObjectiveError("stage policy must have a version")
    stages = _mapping(stage_policy.get("stages"), "stage_policy.stages")
    required_stages = {
        "discovery",
        "historical_research_gate",
        "fresh_oos_forward",
        "dynamic_shadow_research_review",
        "configuration_candidate",
        "live",
    }
    if set(stages) != required_stages:
        raise NdxPortfolioObjectiveError("stage policy must register all five stages")
    for stage_name in sorted(required_stages):
        stage = _mapping(stages[stage_name], f"stage_policy.stages.{stage_name}")
        if not str(stage.get("policy_id", "")).strip():
            raise NdxPortfolioObjectiveError(f"stage {stage_name} must have a policy_id")
    historical = _mapping(stages["historical_research_gate"], "stage_policy.stages.historical_research_gate")
    historical_thresholds = _mapping(historical.get("thresholds"), "historical research thresholds")
    if set(historical_thresholds) != set(HISTORICAL_RESEARCH_THRESHOLDS):
        raise NdxPortfolioObjectiveError("historical research threshold registry is incomplete")
    for key, expected in HISTORICAL_RESEARCH_THRESHOLDS.items():
        actual = _finite_number(historical_thresholds.get(key), f"historical research threshold {key}")
        if not math.isclose(actual, float(expected), rel_tol=0.0, abs_tol=1e-12):
            raise NdxPortfolioObjectiveError(f"historical research threshold has drifted: {key}")
    fresh = _mapping(stages["fresh_oos_forward"], "stage_policy.stages.fresh_oos_forward")
    for key, expected in (
        ("primary_horizon_trading_days", 126),
        ("minimum_fresh_mature_cohorts", 12),
        ("minimum_distinct_regimes", 2),
    ):
        if fresh.get(key) != expected:
            raise NdxPortfolioObjectiveError(f"fresh OOS requirement has drifted: {key}")
    if fresh.get("require_both_execution_tracks") is not True:
        raise NdxPortfolioObjectiveError("fresh OOS must require both execution tracks")
    if fresh.get("require_componentwise_target_gate") is not True:
        raise NdxPortfolioObjectiveError("fresh OOS must require the componentwise target gate")
    _require_true(fresh, "remains_only_formal_positive_admission_gate", "stage_policy.stages.fresh_oos_forward")
    _require_false(fresh, "dynamic_shadow_path_substitution_allowed", "stage_policy.stages.fresh_oos_forward")
    _require_false(fresh, "dynamic_shadow_events_count_as_cohorts", "stage_policy.stages.fresh_oos_forward")
    shadow_review = _mapping(stages["dynamic_shadow_research_review"], "stage_policy.stages.dynamic_shadow_research_review")
    if shadow_review.get("one_year_review_status") != "SUPPORTING_NON_SUFFICIENT_RESEARCH_EVIDENCE":
        raise NdxPortfolioObjectiveError("shadow review status must remain non-sufficient")
    _require_true(
        shadow_review,
        "formal_fresh_oos_gate_required_for_next_stage",
        "stage_policy.stages.dynamic_shadow_research_review",
    )
    _require_false(
        shadow_review,
        "configuration_candidate_promotion_allowed",
        "stage_policy.stages.dynamic_shadow_research_review",
    )
    _require_false(shadow_review, "live_promotion_allowed", "stage_policy.stages.dynamic_shadow_research_review")
    configuration_candidate = _mapping(stages["configuration_candidate"], "stage_policy.stages.configuration_candidate")
    _require_true(
        configuration_candidate,
        "formal_fresh_oos_gate_required",
        "stage_policy.stages.configuration_candidate",
    )
    _require_false(
        configuration_candidate,
        "dynamic_shadow_positive_evidence_sufficient",
        "stage_policy.stages.configuration_candidate",
    )
    _require_true(
        configuration_candidate,
        "unresolved_dynamic_shadow_veto_blocks_review",
        "stage_policy.stages.configuration_candidate",
    )
    for key in ("today_diff_required", "rollback_plan_required", "user_confirmation_required"):
        if configuration_candidate.get(key) is not True:
            raise NdxPortfolioObjectiveError(f"configuration candidate stage requires {key}")
    live = _mapping(stages["live"], "stage_policy.stages.live")
    _require_false(live, "automatic_promotion_allowed", "stage_policy.stages.live")
    _require_false(live, "automatic_mutation_allowed", "stage_policy.stages.live")

    boundary = _mapping(contract.get("mutation_boundary"), "mutation_boundary")
    if boundary.get("research_output_only") is not True:
        raise NdxPortfolioObjectiveError("the objective audit must remain research-only")
    for key in (
        "today_advice_mutation_allowed",
        "order_creation_allowed",
        "live_configuration_mutation_allowed",
        "state_mutation_allowed",
        "broker_snapshot_mutation_allowed",
    ):
        _require_false(boundary, key, "mutation_boundary")
    protected = set(_sequence(boundary.get("protected_files"), "mutation_boundary.protected_files"))
    required_protected = {"config/config.yaml", "data/state.json", "data/broker_positions.json"}
    if not required_protected.issubset(protected):
        raise NdxPortfolioObjectiveError("all live configuration, state, and broker files must be protected")


def load_objective_contract(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path)
    try:
        loaded = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxPortfolioObjectiveError(f"cannot read objective contract: {contract_path}") from exc
    contract = dict(_mapping(loaded, "objective contract"))
    validate_objective_contract(contract)
    return contract


def _finite_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxPortfolioObjectiveError(f"{name} is not numeric") from exc
    if not math.isfinite(number):
        raise NdxPortfolioObjectiveError(f"{name} must be finite")
    return number


def calculate_fund_nav_snapshot(csv_path: str | Path) -> dict[str, Any]:
    path = Path(csv_path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not {"Date", "Close"}.issubset(reader.fieldnames):
                raise NdxPortfolioObjectiveError("fund CSV requires Date and Close columns")
            rows = list(reader)
    except OSError as exc:
        raise NdxPortfolioObjectiveError(f"cannot read fund CSV: {path}") from exc
    if len(rows) < 2:
        raise NdxPortfolioObjectiveError("fund CSV requires at least two rows")

    dates: list[date] = []
    closes: list[float] = []
    for index, row in enumerate(rows, start=2):
        try:
            session_date = date.fromisoformat(str(row.get("Date", "")).strip())
        except ValueError as exc:
            raise NdxPortfolioObjectiveError(f"invalid Date at CSV row {index}") from exc
        close = _finite_number(row.get("Close"), f"Close at CSV row {index}")
        if close <= 0:
            raise NdxPortfolioObjectiveError(f"Close must be positive at CSV row {index}")
        if dates and session_date <= dates[-1]:
            raise NdxPortfolioObjectiveError("fund CSV dates must be unique and strictly increasing")
        dates.append(session_date)
        closes.append(close)

    elapsed_days = (dates[-1] - dates[0]).days
    if elapsed_days <= 0:
        raise NdxPortfolioObjectiveError("fund CSV has no positive elapsed period")
    cumulative_return = closes[-1] / closes[0] - 1.0
    annualized_return = (closes[-1] / closes[0]) ** (365.2425 / elapsed_days) - 1.0
    returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
    annualized_volatility = statistics.stdev(returns) * math.sqrt(252.0) if len(returns) >= 2 else 0.0

    peak_value = closes[0]
    peak_date = dates[0]
    max_drawdown = 0.0
    max_drawdown_peak_date = dates[0]
    max_drawdown_trough_date = dates[0]
    for session_date, close in zip(dates, closes):
        if close > peak_value:
            peak_value = close
            peak_date = session_date
        drawdown = 1.0 - close / peak_value
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_peak_date = peak_date
            max_drawdown_trough_date = session_date

    return {
        "metric_role": "descriptive_latest_available_not_absolute_user_target",
        "row_count": len(rows),
        "data_start": dates[0].isoformat(),
        "data_end": dates[-1].isoformat(),
        "elapsed_calendar_days": elapsed_days,
        "start_close": closes[0],
        "end_close": closes[-1],
        "cumulative_return": cumulative_return,
        "annualized_return": annualized_return,
        "annualized_volatility_252": annualized_volatility,
        "max_drawdown": max_drawdown,
        "max_drawdown_peak_date": max_drawdown_peak_date.isoformat(),
        "max_drawdown_trough_date": max_drawdown_trough_date.isoformat(),
    }


def evaluate_componentwise_target_gate(
    candidate: Mapping[str, Any],
    control: Mapping[str, Any],
    target: Mapping[str, Any],
    metric_names: Iterable[str] = TARGET_COMPONENTS,
    *,
    tolerance: float = 1e-12,
    require_strict_improvement: bool = True,
) -> dict[str, Any]:
    if tolerance < 0:
        raise NdxPortfolioObjectiveError("tolerance must be non-negative")
    checks: dict[str, dict[str, Any]] = {}
    candidate_l1 = 0.0
    control_l1 = 0.0
    strict_count = 0
    for name in metric_names:
        candidate_value = _finite_number(candidate.get(name), f"candidate.{name}")
        control_value = _finite_number(control.get(name), f"control.{name}")
        target_value = _finite_number(target.get(name), f"target.{name}")
        candidate_distance = abs(candidate_value - target_value)
        control_distance = abs(control_value - target_value)
        component_passed = candidate_distance <= control_distance + tolerance
        strict_improvement = candidate_distance < control_distance - tolerance
        strict_count += int(strict_improvement)
        candidate_l1 += candidate_distance
        control_l1 += control_distance
        checks[name] = {
            "candidate_value": candidate_value,
            "control_value": control_value,
            "target_value": target_value,
            "candidate_absolute_distance": candidate_distance,
            "control_absolute_distance": control_distance,
            "passed": component_passed,
            "strict_improvement": strict_improvement,
        }
    componentwise_passed = bool(checks) and all(item["passed"] for item in checks.values())
    strict_requirement_passed = strict_count > 0 or not require_strict_improvement
    return {
        "decision_rule": "componentwise_not_scalarized",
        "passed": componentwise_passed and strict_requirement_passed,
        "componentwise_passed": componentwise_passed,
        "strict_requirement_passed": strict_requirement_passed,
        "strict_improvement_count": strict_count,
        "checks": checks,
        "scalar_l1_reporting_only": {
            "candidate": candidate_l1,
            "control": control_l1,
            "candidate_not_worse": candidate_l1 <= control_l1 + tolerance,
            "used_for_admission": False,
        },
    }


def evaluate_dynamic_shadow_path_evidence(
    evidence: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify dynamic shadow evidence without granting formal admission.

    The v1 contract intentionally has no artifact verifier or registered
    runner.  Therefore raw counters and caller-supplied guard booleans are not
    evidence and can never open the internal one-year review.  A later version
    must read and hash-bind the runner artifacts before enabling classification.
    """
    validate_objective_contract(contract)
    _mapping(evidence, "dynamic shadow evidence")
    return {
        "status": "UNVERIFIED_EVIDENCE_RUNNER_NOT_REGISTERED",
        "evidence_role": "NO_ADMISSIBLE_EVIDENCE_UNTIL_ARTIFACT_VERIFIER",
        "evidence_verification_status": contract["dynamic_shadow_path"]["evidence_verification"]["status"],
        "self_reported_counts_accepted": False,
        "self_reported_guard_booleans_accepted": False,
        "one_year_requirements_passed": False,
        "research_veto": False,
        "internal_shadow_review_allowed": False,
        "counts_as_v4_fresh_mature_cohort": False,
        "counts_as_v4_distinct_regime": False,
        "single_adaptive_path_is_independent_cohort_sample": False,
        "path_level_metrics_can_satisfy_componentwise_formal_gate": False,
        "formal_v4_gate_substitution_allowed": False,
        "configuration_candidate_promotion_allowed": False,
        "live_promotion_allowed": False,
    }


def _load_json(path: str | Path, name: str) -> dict[str, Any]:
    json_path = Path(path)
    try:
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxPortfolioObjectiveError(f"cannot read {name}: {json_path}") from exc
    return dict(_mapping(loaded, name))


def build_objective_audit(
    *,
    contract_path: str | Path,
    fund_manifest_path: str | Path,
    fund_csv_path: str | Path,
    broker_snapshot_path: str | Path,
) -> dict[str, Any]:
    contract = load_objective_contract(contract_path)
    manifest = _load_json(fund_manifest_path, "012922 manifest")
    broker_snapshot = _load_json(broker_snapshot_path, "broker snapshot")

    expected_source = _mapping(_mapping(contract["data_sources"], "data_sources")["target_012922"], "data_sources.target_012922")
    if str(manifest.get("dataset_key")) != str(expected_source.get("expected_dataset_key")):
        raise NdxPortfolioObjectiveError("012922 manifest dataset_key mismatch")
    if manifest.get("dataset_type") != expected_source.get("expected_dataset_type"):
        raise NdxPortfolioObjectiveError("012922 manifest dataset_type mismatch")
    if manifest.get("completeness") != "verified_against_source_record_count":
        raise NdxPortfolioObjectiveError("012922 manifest is not source-count verified")
    expected_csv_hash = str(manifest.get("content_sha256", "")).lower()
    actual_csv_hash = file_sha256(fund_csv_path)
    if len(expected_csv_hash) != 64 or expected_csv_hash != actual_csv_hash:
        raise NdxPortfolioObjectiveError("012922 CSV hash does not match its manifest")

    target_snapshot = calculate_fund_nav_snapshot(fund_csv_path)
    for manifest_key, snapshot_key in (("row_count", "row_count"), ("data_start", "data_start"), ("data_end", "data_end")):
        if manifest.get(manifest_key) != target_snapshot[snapshot_key]:
            raise NdxPortfolioObjectiveError(f"012922 manifest {manifest_key} mismatch")

    positions = _sequence(broker_snapshot.get("positions"), "broker_snapshot.positions")
    actual_broker_tickers: list[str] = []
    for index, position in enumerate(positions):
        item = _mapping(position, f"broker_snapshot.positions[{index}]")
        ticker = str(item.get("ticker", "")).strip().upper()
        if not ticker:
            raise NdxPortfolioObjectiveError("broker position ticker is empty")
        actual_broker_tickers.append(ticker)
    if len(actual_broker_tickers) != len(set(actual_broker_tickers)):
        raise NdxPortfolioObjectiveError("broker snapshot contains duplicate tickers")
    registered = _sequence(
        _mapping(contract["benchmark_registry"], "benchmark_registry")["broker_account_overlay"].get("registered_snapshot_tickers"),
        "registered_snapshot_tickers",
    )
    registered_tickers = [str(ticker).strip().upper() for ticker in registered]
    if set(actual_broker_tickers) != set(registered_tickers):
        raise NdxPortfolioObjectiveError("broker overlay membership differs from the registered user-confirmed snapshot")

    return {
        "schema_version": 1,
        "audit_id": "ndx_portfolio_objective_audit_v1",
        "audit_role": "research_only_descriptive_snapshot",
        "contract": {
            "contract_id": contract["contract_id"],
            "policy_version": contract["stage_policy"]["policy_version"],
            "file_sha256": file_sha256(contract_path),
            "canonical_sha256": canonical_sha256(contract),
            "absolute_targets": contract["user_objective"]["absolute_targets"],
        },
        "target_012922": {
            "manifest_file_sha256": file_sha256(fund_manifest_path),
            "csv_file_sha256": actual_csv_hash,
            "manifest": {
                key: manifest.get(key)
                for key in (
                    "schema_version",
                    "dataset_key",
                    "dataset_type",
                    "version_id",
                    "source",
                    "completeness",
                    "row_count",
                    "data_start",
                    "data_end",
                    "generated_at",
                )
            },
            "descriptive_snapshot": target_snapshot,
            "fixed_acceptance_target": False,
        },
        "benchmark_separation": {
            "original_8": list(ORIGINAL_8),
            "original_8_role": "frozen_research_competition_control",
            "broker_overlay_tickers": actual_broker_tickers,
            "broker_overlay_role": "execution_truth_overlay_not_optimization_benchmark",
            "broker_snapshot_file_sha256": file_sha256(broker_snapshot_path),
        },
        "optimization_scope": {
            "cardinality_mode": contract["portfolio_cardinality"]["mode"],
            "minimum_k": contract["portfolio_cardinality"]["minimum_k"],
            "maximum_k": contract["portfolio_cardinality"]["maximum_k"],
            "portfolio_optimization_separate_from_migration_control": True,
        },
        "dynamic_shadow_path": {
            "path_contract_id": contract["dynamic_shadow_path"]["path_contract_id"],
            "status": contract["dynamic_shadow_path"]["status"],
            "planned_first_decision_on_or_after": str(
                contract["dynamic_shadow_path"]["availability"]["planned_first_decision_on_or_after"]
            ),
            "one_year_review_target_quarter": contract["dynamic_shadow_path"]["availability"][
                "one_year_review_target_quarter"
            ],
            "minimum_completed_trading_days": contract["dynamic_shadow_path"]["availability"][
                "minimum_completed_trading_days"
            ],
            "minimum_executed_monthly_rebalances": contract["dynamic_shadow_path"]["availability"][
                "minimum_executed_monthly_rebalances"
            ],
            "execution_session": contract["dynamic_shadow_path"]["execution"]["execution_session"],
            "execution_price": contract["dynamic_shadow_path"]["execution"]["execution_price"],
            "security_identity_key": contract["dynamic_shadow_path"]["execution"]["security_identity_key"],
            "operational_status": contract["dynamic_shadow_path"]["implementation_readiness"][
                "operational_status"
            ],
            "runner_registered": contract["dynamic_shadow_path"]["implementation_readiness"][
                "runner_registered"
            ],
            "automation_enabled": contract["dynamic_shadow_path"]["implementation_readiness"][
                "automation_enabled"
            ],
            "evidence_verification_status": contract["dynamic_shadow_path"]["evidence_verification"][
                "status"
            ],
            "self_reported_counts_allowed": False,
            "self_reported_guard_booleans_allowed": False,
            "before_one_year_role": contract["dynamic_shadow_path"]["evidence_boundary"][
                "before_one_year_role"
            ],
            "one_year_role": contract["dynamic_shadow_path"]["evidence_boundary"]["one_year_role"],
            "single_adaptive_path_is_independent_cohort_sample": False,
            "path_level_metrics_can_satisfy_componentwise_formal_gate": False,
            "formal_v4_gate_substitution_allowed": False,
            "configuration_candidate_promotion_allowed": False,
            "live_promotion_allowed": False,
        },
        "admission_semantics": {
            "target_gate": "componentwise_not_scalarized",
            "target_dimensions": list(TARGET_COMPONENTS),
            "execution_tracks": list(EXECUTION_TRACKS),
            "scalar_l1_admission_allowed": False,
            "fresh_oos_policy_id": contract["stage_policy"]["stages"]["fresh_oos_forward"]["policy_id"],
        },
        "stage_policy": {
            "policy_version": contract["stage_policy"]["policy_version"],
            "policy_ids": {
                stage_name: stage["policy_id"]
                for stage_name, stage in contract["stage_policy"]["stages"].items()
            },
            "historical_research_thresholds": contract["stage_policy"]["stages"]["historical_research_gate"]["thresholds"],
            "fresh_oos_requirements": {
                key: contract["stage_policy"]["stages"]["fresh_oos_forward"][key]
                for key in (
                    "primary_horizon_trading_days",
                    "minimum_fresh_mature_cohorts",
                    "minimum_distinct_regimes",
                    "require_both_execution_tracks",
                    "require_componentwise_target_gate",
                )
            },
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
