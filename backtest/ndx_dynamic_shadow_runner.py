"""Fail-closed contracts for the future dynamic-cardinality shadow runner."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import yaml

from backtest.ndx_dynamic_candidate_policy import (
    NdxDynamicCandidatePolicyError,
    POLICY_ROLES,
    build_dynamic_policy_schedule,
    select_dynamic_candidate_policy,
    select_user_preference_reference_policy,
)
from backtest.ndx_dynamic_shadow_activation_readiness import (
    verify_observed_session_calendar_manifest,
    verify_original8_control_manifest,
)
from backtest.ndx_dynamic_shadow_selector_registry import (
    UNIVERSE_TRACKS,
    build_dynamic_shadow_selector_registry_audit,
    load_dynamic_shadow_selector_registry,
)
from backtest.ndx_dynamic_whole_lot_path import (
    simulate_dynamic_security_id_whole_lot_path,
)
from backtest.ndx_portfolio_objective import load_objective_contract
from core.helpers import atomic_write_text
from data.versioning import file_sha256


class NdxDynamicShadowRunnerError(ValueError):
    """Raised when future-shadow provenance or timing cannot be proven."""


_HEX = set("0123456789abcdef")
_EXPECTED_TOP_LEVEL = {
    "schema_version", "runner_id", "status", "research_track",
    "migration_control_included", "source_contracts", "lane_contract",
    "schedule_contract", "candidate_snapshot_contract",
    "required_runtime_inputs", "execution_contract", "operation_gate",
    "evidence_boundary", "mutation_boundary",
}


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowRunnerError(f"{name} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise NdxDynamicShadowRunnerError(
            f"{name} keys mismatch; unknown={sorted(actual - expected)}, "
            f"missing={sorted(expected - actual)}"
        )


def _require_bool(mapping: Mapping[str, Any], key: str, expected: bool, name: str) -> None:
    if mapping.get(key) is not expected:
        raise NdxDynamicShadowRunnerError(f"{name}.{key} must be {expected}")


def _sha256(value: Any, name: str) -> str:
    text = str(value or "").lower()
    if len(text) != 64 or any(character not in _HEX for character in text):
        raise NdxDynamicShadowRunnerError(f"{name} must be a SHA256 hex digest")
    return text


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_dynamic_shadow_runner_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowRunnerError(f"cannot read runner contract: {source}") from exc
    contract = dict(_mapping(loaded, "runner contract"))
    validate_dynamic_shadow_runner_contract(contract)
    return contract


def validate_dynamic_shadow_runner_contract(contract: Mapping[str, Any]) -> None:
    _exact_keys(contract, _EXPECTED_TOP_LEVEL, "runner contract")
    if (
        contract.get("schema_version") != 1
        or contract.get("runner_id") != "ndx_dynamic_shadow_runner_v1"
        or contract.get("status")
        != "IMPLEMENTED_FAIL_CLOSED_PENDING_ACTIVATION_AND_FUTURE_INPUTS"
    ):
        raise NdxDynamicShadowRunnerError("unexpected runner identity or status")
    if contract.get("research_track") != "portfolio_optimization":
        raise NdxDynamicShadowRunnerError("runner must stay on portfolio_optimization")
    _require_bool(contract, "migration_control_included", False, "runner contract")

    sources = _mapping(contract.get("source_contracts"), "source_contracts")
    expected_sources = {
        "objective": "config/ndx_portfolio_objective_v1.yaml",
        "selector_registry": "config/ndx_dynamic_shadow_selector_registry_v1.yaml",
        "dynamic_walkforward": "config/ndx_dynamic_walkforward_v1.yaml",
        "selector_policy_module": "backtest/ndx_dynamic_candidate_policy.py",
        "path_engine_module": "backtest/ndx_dynamic_whole_lot_path.py",
        "runner_module": "backtest/ndx_dynamic_shadow_runner.py",
        "runner_script": "scripts/ndx_dynamic_shadow_runner.py",
    }
    _exact_keys(sources, set(expected_sources), "source_contracts")
    if dict(sources) != expected_sources:
        raise NdxDynamicShadowRunnerError("runner source path registry has drifted")

    lanes = _mapping(contract.get("lane_contract"), "lane_contract")
    _exact_keys(lanes, {
        "universe_tracks", "policy_roles", "expected_independent_lane_count",
        "cross_lane_path_splicing_allowed", "winner_take_all_ex_post_selection_allowed",
        "missing_lane_replacement_allowed", "user_preference_role",
    }, "lane_contract")
    if tuple(lanes.get("universe_tracks") or ()) != tuple(UNIVERSE_TRACKS):
        raise NdxDynamicShadowRunnerError("universe lane registry mismatch")
    if tuple(lanes.get("policy_roles") or ()) != tuple(POLICY_ROLES):
        raise NdxDynamicShadowRunnerError("policy lane registry mismatch")
    if lanes.get("expected_independent_lane_count") != 10:
        raise NdxDynamicShadowRunnerError("future shadow requires 10 independent lanes")
    for key in (
        "cross_lane_path_splicing_allowed", "winner_take_all_ex_post_selection_allowed",
        "missing_lane_replacement_allowed",
    ):
        _require_bool(lanes, key, False, "lane_contract")
    if lanes.get("user_preference_role") != "REFERENCE_NOT_FIXED_ANSWER":
        raise NdxDynamicShadowRunnerError("USER_PREFERENCE cannot become a fixed answer")

    schedule = _mapping(contract.get("schedule_contract"), "schedule_contract")
    _exact_keys(schedule, {
        "first_decision_not_before", "decision_frequency", "decision_time",
        "registration_window", "execution_coordinate_rule",
        "execution_date_known_at_selection_seal", "execution_realization_time",
        "seal_must_precede_realized_execution_open",
        "missed_registration_window_action", "valuation_time",
        "retrospective_backfill_allowed", "monthly_decisions_immutable",
    }, "schedule_contract")
    if (
        str(schedule.get("first_decision_not_before")) != "2026-10-01"
        or schedule.get("decision_frequency") != "first_completed_us_session_each_month"
        or schedule.get("decision_time") != "completed_session_close"
        or schedule.get("registration_window")
        != "after_decision_close_and_before_next_common_session_open"
        or schedule.get("execution_coordinate_rule")
        != "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
        or schedule.get("execution_realization_time")
        != "after_execution_session_is_observed_complete"
        or schedule.get("missed_registration_window_action")
        != "NO_DECISION_NO_BACKFILL"
        or schedule.get("valuation_time") != "completed_session_nominal_close"
    ):
        raise NdxDynamicShadowRunnerError("future shadow schedule contract mismatch")
    _require_bool(
        schedule, "execution_date_known_at_selection_seal", False,
        "schedule_contract",
    )
    _require_bool(
        schedule, "seal_must_precede_realized_execution_open", True,
        "schedule_contract",
    )
    _require_bool(schedule, "retrospective_backfill_allowed", False, "schedule_contract")
    _require_bool(schedule, "monthly_decisions_immutable", True, "schedule_contract")

    candidate = _mapping(
        contract.get("candidate_snapshot_contract"), "candidate_snapshot_contract"
    )
    _exact_keys(candidate, {
        "manifest_type", "required_status", "registered_generator_status",
        "registered_generator_path", "registered_generator_sha256",
        "historical_consumed_candidate_reuse_allowed",
        "decision_date_or_later_returns_read_allowed", "required_candidate_columns",
        "inspected_legacy_generator_path",
        "inspected_historical_readiness_manifest_path",
    }, "candidate_snapshot_contract")
    if (
        candidate.get("manifest_type")
        != "ndx_dynamic_shadow_point_in_time_candidate_snapshot"
        or candidate.get("required_status")
        != "FRESH_MONTHLY_CANDIDATES_COMPLETE_NOT_ADMISSION"
        or candidate.get("registered_generator_status")
        != "MISSING_REGISTERED_FUTURE_POINT_IN_TIME_GENERATOR"
        or candidate.get("registered_generator_path") is not None
        or candidate.get("registered_generator_sha256") is not None
    ):
        raise NdxDynamicShadowRunnerError("future candidate generator must remain unregistered")
    _require_bool(
        candidate, "historical_consumed_candidate_reuse_allowed", False,
        "candidate_snapshot_contract",
    )
    _require_bool(
        candidate, "decision_date_or_later_returns_read_allowed", False,
        "candidate_snapshot_contract",
    )
    required_candidate_columns = {
        "universe_track", "selection_date", "decision_data_end", "holding_count",
        "portfolio_id", "weight_spec", "tickers", "weights", "security_ids",
        "issuer_ids", "declared_constraints_passed", "return_p50", "return_p10",
        "max_drawdown_p50", "max_drawdown_p90", "target_012922_distance",
    }
    if set(candidate.get("required_candidate_columns") or ()) != required_candidate_columns:
        raise NdxDynamicShadowRunnerError("fresh candidate snapshot columns have drifted")

    runtime = _mapping(contract.get("required_runtime_inputs"), "required_runtime_inputs")
    _exact_keys(runtime, {
        "activation_manifest_path", "us_session_calendar_manifest_path",
        "monthly_candidate_snapshot_root", "future_nominal_open_close_price_manifest_path",
        "frozen_original_8_definition_manifest_path", "target_012922_csv_path",
        "target_012922_manifest_path",
    }, "required_runtime_inputs")
    for key in (
        "activation_manifest_path", "monthly_candidate_snapshot_root",
        "future_nominal_open_close_price_manifest_path",
    ):
        if runtime.get(key) is not None:
            raise NdxDynamicShadowRunnerError(f"inactive runtime input must remain null: {key}")
    if (
        runtime.get("us_session_calendar_manifest_path")
        != "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
    ):
        raise NdxDynamicShadowRunnerError("observed-session calendar path binding mismatch")
    if (
        runtime.get("frozen_original_8_definition_manifest_path")
        != "data/cache/research/ndx_original_8_control_v1/manifest.json"
    ):
        raise NdxDynamicShadowRunnerError("original-eight control path binding mismatch")

    execution = _mapping(contract.get("execution_contract"), "execution_contract")
    _exact_keys(execution, {
        "initial_cash_usd", "minimum_cash_buffer_usd", "transaction_cost_bps",
        "fractional_shares_allowed", "separate_open_execution_and_close_valuation_required",
        "security_identity_key", "issuer_identity_continuity_required",
        "one_security_per_issuer_required", "cash_and_shares_carried_between_rebalances",
        "external_cash_flows_allowed",
    }, "execution_contract")
    if (
        float(execution.get("initial_cash_usd", 0)) != 25000.0
        or float(execution.get("minimum_cash_buffer_usd", 0)) != 100.0
        or float(execution.get("transaction_cost_bps", -1)) != 10.0
        or execution.get("security_identity_key") != "security_id"
    ):
        raise NdxDynamicShadowRunnerError("$25k/$100/10bp execution contract mismatch")
    for key in (
        "separate_open_execution_and_close_valuation_required",
        "issuer_identity_continuity_required", "one_security_per_issuer_required",
        "cash_and_shares_carried_between_rebalances",
    ):
        _require_bool(execution, key, True, "execution_contract")
    for key in ("fractional_shares_allowed", "external_cash_flows_allowed"):
        _require_bool(execution, key, False, "execution_contract")

    operations = _mapping(contract.get("operation_gate"), "operation_gate")
    _exact_keys(operations, {
        "readiness_audit_allowed", "decision_registration_allowed",
        "path_evaluation_allowed", "automation_enabled", "activation_manifest_required",
    }, "operation_gate")
    _require_bool(operations, "readiness_audit_allowed", True, "operation_gate")
    _require_bool(operations, "activation_manifest_required", True, "operation_gate")
    for key in ("decision_registration_allowed", "path_evaluation_allowed", "automation_enabled"):
        _require_bool(operations, key, False, "operation_gate")

    evidence = _mapping(contract.get("evidence_boundary"), "evidence_boundary")
    _exact_keys(evidence, {
        "historical_consumed_and_fresh_shadow_must_be_separate", "fresh_oos_only",
        "counts_as_v4_cohort", "counts_as_v4_regime", "can_replace_formal_forward_gate",
        "target_scalar_can_admit", "promotion_allowed",
    }, "evidence_boundary")
    for key in ("historical_consumed_and_fresh_shadow_must_be_separate", "fresh_oos_only"):
        _require_bool(evidence, key, True, "evidence_boundary")
    for key in (
        "counts_as_v4_cohort", "counts_as_v4_regime", "can_replace_formal_forward_gate",
        "target_scalar_can_admit", "promotion_allowed",
    ):
        _require_bool(evidence, key, False, "evidence_boundary")

    mutation = _mapping(contract.get("mutation_boundary"), "mutation_boundary")
    _exact_keys(mutation, {
        "research_output_only", "live_config_mutation_allowed", "state_mutation_allowed",
        "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
        "order_creation_allowed",
    }, "mutation_boundary")
    _require_bool(mutation, "research_output_only", True, "mutation_boundary")
    for key in (
        "live_config_mutation_allowed", "state_mutation_allowed",
        "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
        "order_creation_allowed",
    ):
        _require_bool(mutation, key, False, "mutation_boundary")


def _resolved(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise NdxDynamicShadowRunnerError("registered source escapes repository root") from exc
    return path


def _historical_coordinate_end(root: Path, contract: Mapping[str, Any]) -> str | None:
    candidate = contract["candidate_snapshot_contract"]
    manifest_path = _resolved(root, candidate["inspected_historical_readiness_manifest_path"])
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = (manifest.get("artifacts") or {}).get("job_readiness") or {}
        path = Path(str(artifact.get("path") or ""))
        if (
            not path.is_absolute() or not path.is_file()
            or file_sha256(path) != artifact.get("sha256")
        ):
            return None
        frame = pd.read_csv(path, usecols=["selection_date"])
        values = pd.to_datetime(frame["selection_date"], errors="raise")
        return values.max().date().isoformat() if len(values) else None
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def build_dynamic_shadow_readiness(
    contract_path: str | Path, *, as_of_date: str | pd.Timestamp
) -> dict[str, Any]:
    resolved_contract = Path(contract_path).resolve()
    root = resolved_contract.parent.parent
    contract = load_dynamic_shadow_runner_contract(resolved_contract)
    sources = contract["source_contracts"]
    source_paths = {name: _resolved(root, value) for name, value in sources.items()}
    missing_sources = [name for name, path in source_paths.items() if not path.is_file()]
    if missing_sources:
        raise NdxDynamicShadowRunnerError(f"runner source files are missing: {missing_sources}")

    objective = load_objective_contract(source_paths["objective"])
    registry = load_dynamic_shadow_selector_registry(source_paths["selector_registry"])
    registry_audit = build_dynamic_shadow_selector_registry_audit(
        registry_path=source_paths["selector_registry"],
        objective_path=source_paths["objective"],
        dynamic_walkforward_path=source_paths["dynamic_walkforward"],
        selector_policy_module_path=source_paths["selector_policy_module"],
    )
    blockers = [
        {
            "blocker_id": "SELECTOR_REGISTRY_INACTIVE",
            "required_local_input_or_change": "versioned activation registry with bound source hashes",
        },
        {
            "blocker_id": "OBJECTIVE_RUNNER_UNREGISTERED",
            "required_local_input_or_change": "versioned objective amendment registering this runner",
        },
        {
            "blocker_id": "OBJECTIVE_EVIDENCE_VERIFIER_DISABLED",
            "required_local_input_or_change": "immutable runner artifact verifier before evidence review",
        },
        {
            "blocker_id": "ACTIVATION_MANIFEST_MISSING",
            "required_local_input_or_change": "hash-bound research-only activation manifest",
        },
        {
            "blocker_id": "POINT_IN_TIME_FUTURE_CANDIDATE_GENERATOR_UNREGISTERED",
            "required_local_input_or_change": (
                "local generator emitting the registered fresh monthly candidate snapshot "
                "contract for both universe tracks"
            ),
        },
        {
            "blocker_id": "MONTHLY_CANDIDATE_SNAPSHOT_ROOT_MISSING",
            "required_local_input_or_change": "append-only fresh candidate snapshot root",
        },
        {
            "blocker_id": "FUTURE_NOMINAL_OPEN_CLOSE_PRICE_MANIFEST_MISSING",
            "required_local_input_or_change": "hash-bound unadjusted Open/Close bundle through valuation date",
        },
    ]
    as_of = pd.Timestamp(as_of_date).normalize()
    first = pd.Timestamp(contract["schedule_contract"]["first_decision_not_before"])
    historical_end = _historical_coordinate_end(root, contract)
    runtime = contract["required_runtime_inputs"]
    calendar_path = _resolved(root, runtime["us_session_calendar_manifest_path"])
    observed_calendar = verify_observed_session_calendar_manifest(calendar_path, root)
    if not observed_calendar["verified"]:
        blockers.append({
            "blocker_id": "VERIFIED_US_SESSION_CALENDAR_MANIFEST_MISSING_OR_INVALID",
            "required_local_input_or_change": (
                "canonical hash-bound append-only observed QQQ/SPY common-session calendar"
            ),
        })
    target_csv = _resolved(root, runtime["target_012922_csv_path"])
    target_manifest = _resolved(root, runtime["target_012922_manifest_path"])
    original8_path = _resolved(
        root, runtime["frozen_original_8_definition_manifest_path"]
    )
    original8_control = verify_original8_control_manifest(original8_path, root)
    if not original8_control["verified"]:
        blockers.append({
            "blocker_id": "FROZEN_ORIGINAL_8_CONTROL_MISSING_OR_INVALID",
            "required_local_input_or_change": (
                "reproducible immutable original-eight identities and consensus weights manifest"
            ),
        })
    target_ready = bool(target_csv.is_file() and target_manifest.is_file())
    if target_ready:
        try:
            target_meta = json.loads(target_manifest.read_text(encoding="utf-8"))
            target_ready = bool(target_meta.get("content_sha256") == file_sha256(target_csv))
        except (OSError, json.JSONDecodeError):
            target_ready = False
    if not target_ready:
        blockers.append({
            "blocker_id": "TARGET_012922_VERIFIED_MANIFEST_MISSING_OR_STALE",
            "required_local_input_or_change": "current verified 012922 CSV and matching sidecar",
        })

    legacy_path = _resolved(
        root, contract["candidate_snapshot_contract"]["inspected_legacy_generator_path"]
    )
    return {
        "schema_version": 1,
        "readiness_id": "ndx_dynamic_shadow_runner_readiness_v1",
        "as_of_date": as_of.date().isoformat(),
        "status": "BLOCKED_FAIL_CLOSED",
        "ready_for_decision_registration": False,
        "ready_for_path_evaluation": False,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "schedule_status": (
            "NOT_DUE_BEFORE_REGISTERED_START" if as_of < first else "DUE_BUT_BLOCKED"
        ),
        "first_decision_not_before": first.date().isoformat(),
        "blockers": blockers,
        "local_generator_audit": {
            "inspected_path": legacy_path.as_posix(),
            "exists": legacy_path.is_file(),
            "sha256": file_sha256(legacy_path) if legacy_path.is_file() else None,
            "accepted_for_fresh_shadow": False,
            "emitted_role": "HISTORICAL_TRAINING_DISCOVERY_ONLY",
            "latest_registered_historical_coordinate": historical_end,
            "rejection_reasons": [
                "not registered by immutable generator path and hash",
                "does not emit ndx_dynamic_shadow_point_in_time_candidate_snapshot",
                "depends on pre-registered historical readiness coordinates",
            ],
        },
        "source_hashes": {
            name: file_sha256(path) for name, path in source_paths.items()
        },
        "selector_registry_audit": {
            "selector_count": registry_audit["registry"]["selector_count"],
            "active": registry_audit["activation"]["active"],
            "runner_registered": registry_audit["activation"]["runner_registered"],
            "decision_generation_allowed": registry_audit["activation"]["decision_generation_allowed"],
            "registry_canonical_sha256": registry_audit["registry"]["canonical_sha256"],
        },
        "objective_state": {
            "runner_registered": objective["dynamic_shadow_path"]["implementation_readiness"]["runner_registered"],
            "evidence_verification_status": objective["dynamic_shadow_path"]["evidence_verification"]["status"],
        },
        "target_012922_verified": target_ready,
        "original_8_control": original8_control,
        "observed_session_calendar": observed_calendar,
        "historical_consumed_used": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


def _timestamp(value: Any, name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowRunnerError(f"invalid {name}") from exc
    if pd.isna(result) or result.tzinfo is None:
        raise NdxDynamicShadowRunnerError(f"{name} must be timezone-aware")
    return result.tz_convert(timezone.utc)


def validate_monthly_session_timing(
    sessions: pd.DataFrame, *, decision_date: Any, execution_date: Any,
    registration_timestamp_utc: Any,
) -> dict[str, str]:
    required = {"session_date", "open_timestamp_utc", "close_timestamp_utc", "completed"}
    if sessions.empty or not required.issubset(sessions.columns):
        raise NdxDynamicShadowRunnerError("verified session calendar is incomplete")
    frame = sessions.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"], errors="raise").dt.normalize()
    if frame["session_date"].duplicated().any() or not frame["session_date"].is_monotonic_increasing:
        raise NdxDynamicShadowRunnerError("session calendar dates must be unique and sorted")
    decision = pd.Timestamp(decision_date).normalize()
    execution = pd.Timestamp(execution_date).normalize()
    if decision < pd.Timestamp("2026-10-01"):
        raise NdxDynamicShadowRunnerError("retrospective shadow backfill is forbidden")
    month = frame.loc[frame["session_date"].dt.to_period("M") == decision.to_period("M")]
    completed = month.loc[month["completed"].map(lambda value: value is True or str(value).lower() == "true")]
    if completed.empty or completed.iloc[0]["session_date"] != decision:
        raise NdxDynamicShadowRunnerError("decision is not the first completed session of month")
    later = frame.loc[frame["session_date"] > decision]
    if later.empty or later.iloc[0]["session_date"] != execution:
        raise NdxDynamicShadowRunnerError("execution is not the first session after decision")
    decision_row = frame.loc[frame["session_date"] == decision]
    execution_row = frame.loc[frame["session_date"] == execution]
    if len(decision_row) != 1 or len(execution_row) != 1:
        raise NdxDynamicShadowRunnerError("decision or execution session is absent")
    close_time = _timestamp(decision_row.iloc[0]["close_timestamp_utc"], "decision close")
    open_time = _timestamp(execution_row.iloc[0]["open_timestamp_utc"], "execution open")
    registration = _timestamp(registration_timestamp_utc, "registration timestamp")
    if not (close_time <= registration < open_time):
        raise NdxDynamicShadowRunnerError(
            "decision must be registered after close and before next-session open"
        )
    return {
        "decision_date": decision.date().isoformat(),
        "execution_date": execution.date().isoformat(),
        "decision_close_timestamp_utc": close_time.isoformat(),
        "execution_open_timestamp_utc": open_time.isoformat(),
        "registration_timestamp_utc": registration.isoformat(),
    }


def build_monthly_decision_payloads(
    candidates: pd.DataFrame, *, sessions: pd.DataFrame, decision_date: Any,
    execution_date: Any, registration_timestamp_utc: Any,
    candidate_snapshot_sha256: str, calendar_manifest_sha256: str,
    generator_script_sha256: str, selector_registry_sha256: str,
    selector_policy_sha256: str,
    previous_lane_heads: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    timing = validate_monthly_session_timing(
        sessions, decision_date=decision_date, execution_date=execution_date,
        registration_timestamp_utc=registration_timestamp_utc,
    )
    provenance = {
        "candidate_snapshot_sha256": _sha256(candidate_snapshot_sha256, "candidate snapshot"),
        "calendar_manifest_sha256": _sha256(calendar_manifest_sha256, "calendar manifest"),
        "generator_script_sha256": _sha256(generator_script_sha256, "generator script"),
        "selector_registry_sha256": _sha256(selector_registry_sha256, "selector registry"),
        "selector_policy_sha256": _sha256(selector_policy_sha256, "selector policy"),
    }
    frame = candidates.copy()
    if "universe_track" not in frame:
        raise NdxDynamicShadowRunnerError("candidate snapshot lacks universe_track")
    previous = dict(previous_lane_heads or {})
    expected_selector_ids = {
        f"{track}__{role.lower()}__v1"
        for track in UNIVERSE_TRACKS for role in POLICY_ROLES
    }
    if previous and set(previous) != expected_selector_ids:
        raise NdxDynamicShadowRunnerError(
            "previous decision heads must cover all 10 independent lanes"
        )
    payloads: list[dict[str, Any]] = []
    for track in UNIVERSE_TRACKS:
        track_candidates = frame.loc[frame["universe_track"].astype(str).eq(track)].copy()
        if track_candidates.empty:
            raise NdxDynamicShadowRunnerError(f"candidate snapshot missing universe: {track}")
        selection_dates = pd.to_datetime(track_candidates["selection_date"], errors="raise").dt.normalize()
        data_ends = pd.to_datetime(track_candidates["decision_data_end"], errors="raise").dt.normalize()
        if not selection_dates.eq(pd.Timestamp(timing["execution_date"])).all():
            raise NdxDynamicShadowRunnerError("candidate execution date does not match calendar proof")
        if not data_ends.eq(pd.Timestamp(timing["decision_date"])).all():
            raise NdxDynamicShadowRunnerError("candidate information cutoff is not decision close")
        for role in POLICY_ROLES:
            selector_id = f"{track}__{role.lower()}__v1"
            previous_head = previous.get(selector_id)
            if previous_head is None:
                decision_sequence = 1
                previous_hash = None
            else:
                previous_head = _mapping(previous_head, f"previous head {selector_id}")
                if previous_head.get("selector_id") != selector_id:
                    raise NdxDynamicShadowRunnerError("previous decision head lane mismatch")
                previous_hash = _sha256(
                    previous_head.get("payload_sha256"), "previous decision head"
                )
                unsigned_previous = dict(previous_head)
                unsigned_previous.pop("payload_sha256", None)
                if canonical_sha256(unsigned_previous) != previous_hash:
                    raise NdxDynamicShadowRunnerError("previous decision head hash mismatch")
                previous_month = pd.Timestamp(
                    _mapping(previous_head.get("timing"), "previous head timing").get(
                        "decision_date"
                    )
                ).to_period("M")
                current_month = pd.Timestamp(timing["decision_date"]).to_period("M")
                if current_month.ordinal != previous_month.ordinal + 1:
                    raise NdxDynamicShadowRunnerError(
                        "previous decision head is not the immediately preceding month"
                    )
                try:
                    decision_sequence = int(previous_head.get("decision_sequence")) + 1
                except (TypeError, ValueError) as exc:
                    raise NdxDynamicShadowRunnerError(
                        "previous decision sequence is invalid"
                    ) from exc
            status = "SELECTED_FRESH_SHADOW_DECISION"
            selected_payload: dict[str, Any] | None = None
            try:
                selected = (
                    select_user_preference_reference_policy(track_candidates)
                    if role == "USER_PREFERENCE"
                    else select_dynamic_candidate_policy(track_candidates, policy_role=role)
                )
                if len(selected) != 1:
                    raise NdxDynamicShadowRunnerError("monthly selector did not return one row")
                schedule = build_dynamic_policy_schedule(selected)
                if len(schedule) != 1:
                    raise NdxDynamicShadowRunnerError("monthly schedule did not return one decision")
                row = selected.iloc[0]
                selected_payload = {
                    "portfolio_id": str(row["portfolio_id"]),
                    "k": int(row["holding_count"]),
                    "targets": schedule[0]["targets"],
                    "declared_constraints_passed": bool(row["declared_constraints_passed"]),
                }
                if role == "USER_PREFERENCE":
                    status = "SELECTED_REFERENCE_NOT_FIXED_ANSWER"
            except NdxDynamicCandidatePolicyError as exc:
                if role != "USER_PREFERENCE":
                    raise NdxDynamicShadowRunnerError(
                        f"competitive selector unavailable: {selector_id}: {exc}"
                    ) from exc
                status = "REFERENCE_UNAVAILABLE_NOT_REPLACED"
                selected_payload = None
            base = {
                "schema_version": 1,
                "artifact_type": "ndx_dynamic_shadow_immutable_monthly_decision",
                "selector_id": selector_id,
                "universe_track": track,
                "policy_role": role,
                "decision_sequence": decision_sequence,
                "previous_decision_sha256": previous_hash,
                "timing": timing,
                "status": status,
                "selected_candidate": selected_payload,
                "provenance": provenance,
                "fresh_oos": True,
                "historical_consumed": False,
                "independent_lane_only": True,
                "cross_lane_path_splicing_allowed": False,
                "winner_take_all_ex_post_selection_allowed": False,
                "target_scalar_used_for_admission": False,
                "promotion_allowed": False,
                "live_mutation": False,
            }
            base["payload_sha256"] = canonical_sha256(base)
            payloads.append(base)
    if len(payloads) != 10 or len({item["selector_id"] for item in payloads}) != 10:
        raise NdxDynamicShadowRunnerError("monthly decision matrix is not the complete 2 x 5 product")
    return payloads


def write_immutable_monthly_decisions(
    output_root: str | Path, payloads: Iterable[Mapping[str, Any]],
) -> list[Path]:
    items = [dict(item) for item in payloads]
    if len(items) != 10:
        raise NdxDynamicShadowRunnerError("immutable write requires all 10 lane decisions")
    expected_selector_ids = {
        f"{track}__{role.lower()}__v1"
        for track in UNIVERSE_TRACKS for role in POLICY_ROLES
    }
    if {str(item.get("selector_id")) for item in items} != expected_selector_ids:
        raise NdxDynamicShadowRunnerError("immutable write requires the complete 2 x 5 lane matrix")
    for item in items:
        declared_hash = str(item.get("payload_sha256") or "")
        unsigned = dict(item)
        unsigned.pop("payload_sha256", None)
        if canonical_sha256(unsigned) != declared_hash:
            raise NdxDynamicShadowRunnerError("immutable decision payload hash mismatch")
    dates = {str(item["timing"]["decision_date"]) for item in items}
    if len(dates) != 1:
        raise NdxDynamicShadowRunnerError("decision batch spans multiple decision dates")
    destination = Path(output_root) / next(iter(dates))
    paths = [destination / f"{item['selector_id']}.json" for item in items]
    rendered = [json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n" for item in items]
    for path, content in zip(paths, rendered):
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise NdxDynamicShadowRunnerError(f"immutable decision collision: {path}")
    destination.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, rendered):
        if not path.exists():
            atomic_write_text(path, content)
    return paths


def simulate_fresh_lane_path(
    decisions: Iterable[Mapping[str, Any]], *, sessions: pd.DataFrame,
    valuation_prices: pd.DataFrame, execution_prices: pd.DataFrame,
    valuation_end_date: Any,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    items = [dict(item) for item in decisions]
    if not items:
        raise NdxDynamicShadowRunnerError("fresh lane decision chain is empty")
    selector_ids = {str(item.get("selector_id")) for item in items}
    if len(selector_ids) != 1:
        raise NdxDynamicShadowRunnerError("cross-selector path splicing is forbidden")
    schedule = []
    prior_hash = None
    prior_month: pd.Period | None = None
    for sequence, item in enumerate(items, start=1):
        declared_hash = str(item.get("payload_sha256") or "")
        unsigned = dict(item)
        unsigned.pop("payload_sha256", None)
        if canonical_sha256(unsigned) != declared_hash:
            raise NdxDynamicShadowRunnerError("decision payload hash mismatch")
        if item.get("previous_decision_sha256") != prior_hash:
            raise NdxDynamicShadowRunnerError("lane decision hash chain mismatch")
        if item.get("decision_sequence") != sequence:
            raise NdxDynamicShadowRunnerError("lane decision sequence mismatch")
        if item.get("fresh_oos") is not True or item.get("historical_consumed") is not False:
            raise NdxDynamicShadowRunnerError("historical consumed evidence cannot enter fresh path")
        if item.get("status") not in {
            "SELECTED_FRESH_SHADOW_DECISION", "SELECTED_REFERENCE_NOT_FIXED_ANSWER"
        }:
            raise NdxDynamicShadowRunnerError("unavailable lane cannot be simulated")
        timing = item["timing"]
        validate_monthly_session_timing(
            sessions, decision_date=timing["decision_date"],
            execution_date=timing["execution_date"],
            registration_timestamp_utc=timing["registration_timestamp_utc"],
        )
        current_month = pd.Timestamp(timing["decision_date"]).to_period("M")
        if prior_month is not None and current_month.ordinal != prior_month.ordinal + 1:
            raise NdxDynamicShadowRunnerError("fresh lane decision months are not contiguous")
        schedule.append({
            "decision_date": timing["decision_date"],
            "execution_date": timing["execution_date"],
            "targets": item["selected_candidate"]["targets"],
        })
        prior_hash = declared_hash
        prior_month = current_month
    summary, rebalances, trades, path = simulate_dynamic_security_id_whole_lot_path(
        valuation_prices,
        schedule,
        execution_prices=execution_prices,
        require_separate_execution_prices=True,
        require_next_session_execution=True,
        require_issuer_trace=True,
        initial_cash_usd=25000.0,
        minimum_cash_buffer_usd=100.0,
        transaction_cost_bps=10.0,
        valuation_end_date=valuation_end_date,
    )
    summary.update({
        "evidence_role": "FRESH_DYNAMIC_SHADOW_RESEARCH_ONLY",
        "historical_consumed": False,
        "fresh_oos": True,
        "selector_id": next(iter(selector_ids)),
        "target_scalar_used_for_admission": False,
        "promotion_allowed": False,
        "live_mutation": False,
    })
    return summary, rebalances, trades, path


__all__ = [
    "NdxDynamicShadowRunnerError",
    "build_dynamic_shadow_readiness",
    "build_monthly_decision_payloads",
    "canonical_sha256",
    "load_dynamic_shadow_runner_contract",
    "simulate_fresh_lane_path",
    "validate_dynamic_shadow_runner_contract",
    "validate_monthly_session_timing",
    "write_immutable_monthly_decisions",
]
