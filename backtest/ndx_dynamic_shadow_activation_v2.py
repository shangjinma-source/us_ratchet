"""Versioned activation contracts for the prospective dynamic shadow.

Version 2 changes only the operational evidence lineage.  It does not change
the v1 objective, selector identities, portfolio search semantics, or any live
trading boundary.  A separate immutable activation manifest is required before
research automation may be registered.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_activation_readiness import (
    verify_observed_session_calendar_manifest,
    verify_original8_control_manifest,
)
from backtest.ndx_dynamic_shadow_runner import load_dynamic_shadow_runner_contract
from backtest.ndx_dynamic_shadow_selector_registry import (
    load_dynamic_shadow_selector_registry,
)
from backtest.ndx_portfolio_objective import load_objective_contract
from data.versioning import file_sha256


class NdxDynamicShadowActivationV2Error(ValueError):
    """Raised when an activation-v2 contract or artifact cannot be rebuilt."""


OBJECTIVE_V1 = "config/ndx_portfolio_objective_v1.yaml"
OBJECTIVE_V2 = "config/ndx_portfolio_objective_v2.yaml"
SELECTOR_V1 = "config/ndx_dynamic_shadow_selector_registry_v1.yaml"
SELECTOR_V2 = "config/ndx_dynamic_shadow_selector_registry_v2.yaml"
RUNNER_V1 = "config/ndx_dynamic_shadow_runner_v1.yaml"
RUNNER_V2 = "config/ndx_dynamic_shadow_runner_v2.yaml"
ACTIVATION_MANIFEST = "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
SYNTHETIC_E2E_MANIFEST = (
    "data/cache/research/ndx_dynamic_shadow_activation_v2_synthetic_e2e_v4/manifest.json"
)

V1_LOCKS = {
    OBJECTIVE_V1: "11a65579617ac8377fb3b75e3d3fdf3650d43972b0565df40b03d70d2e4221bb",
    SELECTOR_V1: "961f066e8f73366ce6a63487db642d6c9aeda3012aa9a10f4e22f598557c284e",
    RUNNER_V1: "f4e9a281a06f6f1e2b6e5fecd73ed8c471394b1f4b8002df8b2c2e0b1dcb1da9",
}

TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowActivationV2Error(f"cannot read activation contract: {path}") from exc
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowActivationV2Error(f"activation contract is not a mapping: {path}")
    return dict(value)


def _canonical(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise NdxDynamicShadowActivationV2Error(f"canonical path escapes repository: {relative}") from exc
    return path


def _require(value: bool, message: str) -> None:
    if not value:
        raise NdxDynamicShadowActivationV2Error(message)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.resolve().as_posix(), "sha256": file_sha256(path)}


def verify_append_only_calendar_prefix(
    prefix_snapshot_path: str | Path, current_ledger_path: str | Path,
) -> dict[str, Any]:
    """Accept current tail extension while rejecting any frozen-prefix rewrite."""
    prefix_path = Path(prefix_snapshot_path)
    current_path = Path(current_ledger_path)
    try:
        prefix_lines = prefix_path.read_text(encoding="utf-8").splitlines()
        current_lines = current_path.read_text(encoding="utf-8").splitlines()
        prefix_records = [json.loads(line) for line in prefix_lines]
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowActivationV2Error("calendar prefix evidence is missing/invalid") from exc
    _require(bool(prefix_lines), "calendar activation prefix is empty")
    _require(
        len(current_lines) >= len(prefix_lines)
        and current_lines[:len(prefix_lines)] == prefix_lines,
        "calendar activation prefix changed instead of append-only extension",
    )
    terminal = prefix_records[-1]
    _require(
        isinstance(terminal, Mapping) and isinstance(terminal.get("record_sha256"), str),
        "calendar activation prefix terminal is invalid",
    )
    return {
        "prefix_rows": len(prefix_lines),
        "current_rows": len(current_lines),
        "appended_rows": len(current_lines) - len(prefix_lines),
        "terminal_record_sha256": terminal["record_sha256"],
    }


def _validate_v1_locks(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative, expected_hash in V1_LOCKS.items():
        path = _canonical(root, relative)
        _require(path.is_file(), f"locked v1 contract is missing: {relative}")
        digest = file_sha256(path)
        _require(digest == expected_hash, f"locked v1 contract hash changed: {relative}")
        hashes[relative] = digest
    load_objective_contract(_canonical(root, OBJECTIVE_V1))
    load_dynamic_shadow_selector_registry(_canonical(root, SELECTOR_V1))
    load_dynamic_shadow_runner_contract(_canonical(root, RUNNER_V1))
    return hashes


def _validate_objective_v2(root: Path) -> dict[str, Any]:
    path = _canonical(root, OBJECTIVE_V2)
    contract = _load_yaml(path)
    lineage = contract.get("lineage") or {}
    optimization = contract.get("portfolio_optimization") or {}
    objective = contract.get("objective_semantics") or {}
    execution = contract.get("execution_contract") or {}
    prospective = contract.get("prospective_contract") or {}
    activation = contract.get("activation_boundary") or {}
    _require(
        contract.get("schema_version") == 2
        and contract.get("contract_id") == "ndx_portfolio_objective_v2"
        and contract.get("status") == "OPERATIONAL_ACTIVATION_LINEAGE_RESEARCH_ONLY"
        and contract.get("research_track") == "portfolio_optimization"
        and contract.get("migration_control_included") is False,
        "objective v2 identity/track changed",
    )
    _require(
        lineage.get("predecessor_path") == OBJECTIVE_V1
        and lineage.get("predecessor_contract_id") == "ndx_portfolio_objective_v1"
        and lineage.get("predecessor_sha256") == V1_LOCKS[OBJECTIVE_V1]
        and lineage.get("target_semantics_changed") is False
        and lineage.get("change_scope") == "operational_activation_evidence_only",
        "objective v2 lineage changed",
    )
    _require(
        optimization.get("cardinality") == "1..point_in_time_eligible_pool_distinct_issuer_count"
        and optimization.get("fixed_holding_count") is None
        and optimization.get("composition_competes_each_decision") is True
        and optimization.get("weights_compete_each_decision") is True
        and optimization.get("one_security_per_issuer_required") is True,
        "objective v2 dynamic portfolio semantics changed",
    )
    preference = optimization.get("user_preference_reference") or {}
    _require(
        set(preference.get("tickers") or []) == {"AMAT", "AVGO", "CDNS", "GOOG"}
        and preference.get("role") == "REFERENCE_NOT_FIXED_ANSWER",
        "objective v2 user-preference reference changed",
    )
    _require(
        objective.get("primary_target") == "012922"
        and objective.get("scalar_target_distance_is_training_or_reporting_only") is True
        and objective.get("scalar_target_distance_can_admit") is False
        and objective.get("formal_target_gate") == "componentwise_return_and_drawdown"
        and objective.get("frozen_original_8_role") == "executable_same_calendar_control_not_structure_answer"
        and objective.get("required_benchmarks") == ["target_012922", "original_8_incumbent"]
        and objective.get("same_calendar_required") is True,
        "objective v2 benchmark semantics changed",
    )
    _require(
        float(execution.get("starting_capital_usd", -1)) == 25000.0
        and float(execution.get("minimum_cash_buffer_usd", -1)) == 100.0
        and float(execution.get("transaction_cost_bps", -1)) == 10.0
        and execution.get("fractional_shares_allowed") is False
        and execution.get("execution_price") == "unadjusted_nominal_open"
        and execution.get("valuation_price") == "unadjusted_nominal_close"
        and execution.get("security_identity_key") == "security_id"
        and execution.get("issuer_identity_continuity_required") is True
        and execution.get("cash_and_integer_shares_continuous") is True
        and execution.get("external_cash_flows_allowed") is False,
        "objective v2 capital/execution semantics changed",
    )
    _require(
        str(prospective.get("first_decision_not_before")) == "2026-10-01"
        and prospective.get("execution_coordinate_rule")
        == "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
        and prospective.get("no_retrospective_backfill") is True
        and prospective.get("historical_candidate_replay_allowed") is False
        and prospective.get("future_outcome_read_at_selection_allowed") is False,
        "objective v2 prospective/no-backfill semantics changed",
    )
    _require(
        activation.get("research_automation_registration_may_be_enabled_by_verified_manifest") is True
        and activation.get("decision_and_path_generation_are_research_only") is True
        and all(
            activation.get(key) is False
            for key in (
                "formal_forward_gate_substitution_allowed",
                "configuration_candidate_promotion_allowed",
                "live_promotion_allowed",
                "live_config_mutation_allowed",
                "state_mutation_allowed",
                "broker_snapshot_mutation_allowed",
                "today_advice_mutation_allowed",
                "order_creation_allowed",
            )
        ),
        "objective v2 activation/live boundary changed",
    )
    return contract


def _validate_selector_v2(root: Path, objective_v2_hash: str) -> dict[str, Any]:
    path = _canonical(root, SELECTOR_V2)
    registry = _load_yaml(path)
    lineage = registry.get("lineage") or {}
    matrix = registry.get("selector_matrix") or {}
    lane = registry.get("per_selector_contract") or {}
    activation = registry.get("activation") or {}
    boundary = registry.get("evidence_and_mutation_boundary") or {}
    _require(
        registry.get("schema_version") == 2
        and registry.get("registry_id") == "ndx_dynamic_shadow_selector_registry_v2"
        and registry.get("status") == "ACTIVATION_MANIFEST_GATED_RESEARCH_ONLY"
        and registry.get("research_track") == "portfolio_optimization"
        and registry.get("migration_control_included") is False,
        "selector registry v2 identity/track changed",
    )
    _require(
        lineage.get("predecessor_path") == SELECTOR_V1
        and lineage.get("predecessor_sha256") == V1_LOCKS[SELECTOR_V1]
        and lineage.get("objective_v2_path") == OBJECTIVE_V2
        and lineage.get("objective_v2_sha256") == objective_v2_hash
        and lineage.get("selection_semantics_changed") is False
        and lineage.get("selector_identity_version_changed") is False,
        "selector registry v2 lineage changed",
    )
    _require(
        tuple(matrix.get("universe_tracks") or ()) == TRACKS
        and tuple(matrix.get("policy_roles") or ()) == ROLES
        and int(matrix.get("expected_selector_count", -1)) == 10
        and matrix.get("selector_id_template") == "{universe_track}__{policy_role_lower}__v1"
        and matrix.get("lane_identity_is_preserved_from_v1") is True,
        "selector registry v2 is not the preserved 2x5 lane matrix",
    )
    _require(
        lane.get("cardinality") == "1..point_in_time_eligible_pool_distinct_issuer_count"
        and lane.get("fixed_holding_count") is None
        and lane.get("composition_and_weights_compete_each_decision") is True
        and lane.get("independent_append_only_path_required") is True
        and lane.get("target_scalar_admission_allowed") is False
        and lane.get("componentwise_012922_forward_gate_required_for_formal_admission") is True
        and lane.get("original_8_no_inferiority_gate_required_for_formal_admission") is True
        and set(lane.get("user_preference_tickers") or ()) == {"AMAT", "AVGO", "CDNS", "GOOG"}
        and lane.get("user_preference_role") == "REFERENCE_NOT_FIXED_ANSWER"
        and all(
            lane.get(key) is False
            for key in (
                "shared_realized_path_allowed", "cross_selector_path_splicing_allowed",
                "winner_take_all_ex_post_selection_allowed",
                "missing_selector_silent_replacement_allowed",
            )
        ),
        "selector registry v2 lane/admission semantics changed",
    )
    _require(
        activation.get("authority") == "verified_ndx_dynamic_shadow_activation_v2_manifest_only"
        and activation.get("default_active") is False
        and activation.get("research_automation_registration_only") is True
        and activation.get("all_canonical_source_and_evidence_hashes_required") is True
        and activation.get("malicious_artifact_reverification_required") is True,
        "selector registry v2 activation authority changed",
    )
    _require(
        boundary.get("evidence_role") == "PARALLEL_DYNAMIC_SHADOW_RESEARCH_ONLY"
        and all(value is False for key, value in boundary.items() if key != "evidence_role"),
        "selector registry v2 promotion/live boundary changed",
    )
    return registry


def _validate_runner_v2(
    root: Path, objective_v2_hash: str, selector_v2_hash: str,
) -> dict[str, Any]:
    path = _canonical(root, RUNNER_V2)
    runner = _load_yaml(path)
    lineage = runner.get("lineage") or {}
    runtime = runner.get("canonical_runtime") or {}
    schedule = runner.get("schedule_contract") or {}
    execution = runner.get("execution_contract") or {}
    evidence = runner.get("evidence_contract") or {}
    activation = runner.get("activation_gate") or {}
    mutation = runner.get("mutation_boundary") or {}
    expected_runtime = {
        "daily_contract": "config/ndx_dynamic_shadow_daily_v1.yaml",
        "daily_module": "backtest/ndx_dynamic_shadow_daily.py",
        "daily_script": "scripts/ndx_dynamic_shadow_daily.py",
        "observed_calendar_manifest": "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json",
        "candidate_generator_contract": "config/ndx_dynamic_shadow_candidate_generator_v1.yaml",
        "candidate_generator_module": "backtest/ndx_dynamic_shadow_candidate_snapshot.py",
        "candidate_generator_script": "scripts/ndx_dynamic_shadow_candidate_generator.py",
        "fresh_search_contract": "config/ndx_dynamic_shadow_fresh_search_v1.yaml",
        "fresh_search_module": "backtest/ndx_dynamic_shadow_fresh_search.py",
        "fresh_search_script": "scripts/ndx_dynamic_shadow_fresh_search.py",
        "original_8_definition_manifest": "data/cache/research/ndx_original_8_control_v1/manifest.json",
        "target_012922_csv": "data/cache/funds/012922.csv",
        "target_012922_source_manifest": "data/cache/funds/012922.csv.manifest.json",
        "daily_output_root": "data/cache/research/ndx_dynamic_shadow_daily_v1",
        "candidate_output_root": "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1",
        "fresh_search_output_root": "data/cache/research/ndx_dynamic_shadow_fresh_search_v1",
    }
    _require(
        runner.get("schema_version") == 2
        and runner.get("runner_id") == "ndx_dynamic_shadow_runner_v2"
        and runner.get("status") == "ACTIVATION_MANIFEST_GATED_RESEARCH_AUTOMATION"
        and runner.get("research_track") == "portfolio_optimization"
        and runner.get("migration_control_included") is False,
        "runner v2 identity/track changed",
    )
    _require(
        lineage.get("predecessor_path") == RUNNER_V1
        and lineage.get("predecessor_sha256") == V1_LOCKS[RUNNER_V1]
        and lineage.get("objective_v2_path") == OBJECTIVE_V2
        and lineage.get("objective_v2_sha256") == objective_v2_hash
        and lineage.get("selector_registry_v2_path") == SELECTOR_V2
        and lineage.get("selector_registry_v2_sha256") == selector_v2_hash
        and lineage.get("objective_and_selection_semantics_changed") is False,
        "runner v2 lineage changed",
    )
    _require(runtime == expected_runtime, "runner v2 canonical runtime paths changed")
    _require(
        str(schedule.get("first_decision_not_before")) == "2026-10-01"
        and schedule.get("execution_coordinate_rule")
        == "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
        and schedule.get("role_freeze_must_precede_realized_open") is True
        and schedule.get("missed_decision_action") == "NO_DECISION_NO_BACKFILL"
        and schedule.get("retrospective_backfill_allowed") is False,
        "runner v2 schedule/no-backfill semantics changed",
    )
    _require(
        float(execution.get("starting_capital_usd", -1)) == 25000.0
        and float(execution.get("minimum_cash_buffer_usd", -1)) == 100.0
        and float(execution.get("transaction_cost_bps", -1)) == 10.0
        and execution.get("fractional_shares_allowed") is False
        and execution.get("execution_price") == "unadjusted_nominal_open"
        and execution.get("valuation_price") == "unadjusted_nominal_close"
        and execution.get("security_identity_key") == "security_id"
        and execution.get("cash_and_integer_shares_continuous") is True
        and execution.get("external_cash_flows_allowed") is False,
        "runner v2 capital/execution semantics changed",
    )
    _require(
        int(evidence.get("independent_selector_lane_count", -1)) == 10
        and evidence.get("dynamic_k") == "1..point_in_time_eligible_pool_distinct_issuer_count"
        and all(
            evidence.get(key) is True
            for key in (
                "all_k_shards_required_before_role_freeze",
                "candidate_decision_seal_ledger_required", "role_seal_ledger_required",
                "realized_decision_batch_commit_required", "ten_append_only_lane_ledgers_required",
                "same_calendar_original_8_executable_control_required",
                "target_012922_no_future_trace_required", "three_way_calendar_binding_required",
                "canonical_price_evidence_required", "componentwise_012922_gate_preserved",
            )
        )
        and evidence.get("historical_candidate_replay_allowed") is False
        and evidence.get("target_scalar_admission_allowed") is False,
        "runner v2 evidence/double-benchmark gate changed",
    )
    _require(
        activation.get("activation_manifest_path") == ACTIVATION_MANIFEST
        and activation.get("reconstructed_verification_required") is True
        and activation.get("self_reported_guard_booleans_sufficient") is False
        and activation.get("research_automation_registration_allowed_only_when_verified") is True
        and activation.get("default_research_automation_registration_allowed") is False
        and activation.get("decision_and_path_generation_research_only") is True
        and activation.get("promotion_allowed") is False
        and activation.get("live_mutation_allowed") is False
        and activation.get("task_registration_performed_by_this_runner") is False,
        "runner v2 activation boundary changed",
    )
    _require(all(value is False for value in mutation.values()), "runner v2 live mutation boundary changed")
    return runner


def validate_versioned_activation_contracts(repository_root: str | Path) -> dict[str, Any]:
    """Validate v1 locks and the no-semantic-change v2 lineage."""
    root = Path(repository_root).resolve()
    v1 = _validate_v1_locks(root)
    objective = _validate_objective_v2(root)
    objective_hash = file_sha256(_canonical(root, OBJECTIVE_V2))
    selector = _validate_selector_v2(root, objective_hash)
    selector_hash = file_sha256(_canonical(root, SELECTOR_V2))
    runner = _validate_runner_v2(root, objective_hash, selector_hash)
    return {
        "status": "VERSIONED_ACTIVATION_CONTRACTS_VERIFIED",
        "v1_locked_hashes": v1,
        "objective_v2_sha256": objective_hash,
        "selector_registry_v2_sha256": selector_hash,
        "runner_v2_sha256": file_sha256(_canonical(root, RUNNER_V2)),
        "objective_semantics_changed": objective["lineage"]["target_semantics_changed"],
        "selection_semantics_changed": selector["lineage"]["selection_semantics_changed"],
        "runner_semantics_changed": runner["lineage"]["objective_and_selection_semantics_changed"],
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
    }


def _synthetic_sessions(root: Path) -> pd.DataFrame:
    calendar_manifest = json.loads(
        _canonical(
            root, "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json",
        ).read_text(encoding="utf-8")
    )
    projection = Path(
        str((calendar_manifest.get("artifacts") or {}).get("session_projection", {}).get("path") or "")
    ).resolve()
    frame = pd.read_csv(projection, low_memory=False)
    if len(frame) < 6:
        raise NdxDynamicShadowActivationV2Error("synthetic E2E needs six canonical observed sessions")
    return frame.tail(6).reset_index(drop=True)


def _synthetic_decisions(
    selector_id: str, *, available: bool, sessions: pd.DataFrame,
) -> list[dict[str, Any]]:
    from backtest.ndx_dynamic_shadow_daily import canonical_sha256

    chain = []
    previous = None
    values = sessions["session_date"].astype(str).tolist()
    coordinates = (
        (values[0], values[1], {
            "security:synthetic:alpha": {
                "ticker": "AAA", "issuer_id": "issuer:synthetic:alpha", "target_weight": 1.0,
            },
        }),
        (values[3], values[4], {
            "security:synthetic:alpha": {
                "ticker": "AAX", "issuer_id": "issuer:synthetic:alpha", "target_weight": 0.6,
            },
            "security:synthetic:beta": {
                "ticker": "BBB", "issuer_id": "issuer:synthetic:beta", "target_weight": 0.4,
            },
        }),
    )
    for sequence, (decision_date, execution_date, targets) in enumerate(coordinates, start=1):
        selected = None if not available else {
            "portfolio_id": f"synthetic_dynamic_k_{len(targets)}",
            "holding_count": len(targets),
            "targets": targets,
        }
        payload = {
            "schema_version": 1,
            "artifact_type": "ndx_dynamic_shadow_realized_monthly_lane_decision",
            "selector_id": selector_id,
            "universe_track": selector_id.split("__", 1)[0],
            "policy_role": selector_id.split("__")[1].upper(),
            "decision_sequence": sequence,
            "previous_decision_sha256": previous,
            "timing": {
                "decision_date": decision_date,
                "execution_date": execution_date,
                "execution_open_timestamp_utc": str(
                    sessions.loc[sessions["session_date"].astype(str).eq(execution_date), "open_timestamp_utc"].iloc[0]
                ),
                "execution_close_timestamp_utc": str(
                    sessions.loc[sessions["session_date"].astype(str).eq(execution_date), "close_timestamp_utc"].iloc[0]
                ),
                "candidate_sealed_at_utc": (
                    pd.Timestamp(
                        sessions.loc[sessions["session_date"].astype(str).eq(execution_date), "open_timestamp_utc"].iloc[0]
                    ) - pd.Timedelta(hours=1)
                ).isoformat(),
                "execution_realized_at_utc": (
                    pd.Timestamp(
                        sessions.loc[sessions["session_date"].astype(str).eq(execution_date), "close_timestamp_utc"].iloc[0]
                    ) + pd.Timedelta(minutes=1)
                ).isoformat(),
            },
            "status": (
                "REFERENCE_UNAVAILABLE_NOT_REPLACED"
                if not available else "SELECTED_FRESH_SHADOW_CANDIDATE"
            ),
            "selected_candidate": selected,
            "provenance": {"synthetic_activation_e2e": True},
            "selection_training_only": True,
            "fresh_oos_outcome_consumed_at_selection": False,
            "historical_candidate_replay_used": False,
            "independent_lane_only": True,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        payload["payload_sha256"] = canonical_sha256(payload)
        previous = payload["payload_sha256"]
        chain.append(payload)
    return chain


def build_synthetic_e2e_manifest(
    output_directory: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Build an immutable two-decision dynamic-k/double-benchmark smoke artifact."""
    from backtest.ndx_dynamic_shadow_daily import (
        append_lane_path,
        append_target_012922_trace,
        canonical_sha256,
        replay_lane_path,
        replay_original8_control_path,
        validate_nominal_price_evidence,
        write_three_way_calendar_manifest,
    )

    root = Path(repository_root).resolve()
    output = Path(output_directory).resolve()
    manifest_path = output / "manifest.json"
    if manifest_path.is_file():
        return verify_synthetic_e2e_manifest(manifest_path, repository_root=root)
    if output.exists() and any(output.iterdir()):
        raise NdxDynamicShadowActivationV2Error("synthetic E2E output is nonempty without a manifest")
    validate_versioned_activation_contracts(root)
    sessions = _synthetic_sessions(root)
    session_path = output / "inputs/sessions.csv"
    _atomic_text(session_path, sessions.to_csv(index=False, lineterminator="\n"))

    original_manifest_path = _canonical(
        root, "data/cache/research/ndx_original_8_control_v1/manifest.json",
    )
    original_manifest = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    frozen_securities = original_manifest["definition"]["securities"]
    candidate_tickers = {"AAA", "AAX", "BBB"}
    tickers = sorted(candidate_tickers | {str(item["ticker"]) for item in frozen_securities})
    price_rows = []
    for date_index, session_date in enumerate(sessions["session_date"], start=1):
        for ticker_index, ticker in enumerate(tickers, start=1):
            open_price = 40.0 + ticker_index * 7.0 + date_index * 0.5
            price_rows.append({
                "Date": session_date,
                "ticker": ticker,
                "Open": open_price,
                "Close": open_price * (1.002 + ticker_index / 10000.0),
            })
    prices = validate_nominal_price_evidence(
        pd.DataFrame(price_rows), sessions, tickers=tickers,
        valuation_end_date=sessions["session_date"].iloc[-1],
    )
    price_path = output / "inputs/nominal_open_close.csv"
    _atomic_text(
        price_path,
        prices.assign(Date=prices["Date"].dt.date.astype(str)).to_csv(index=False, lineterminator="\n"),
    )
    price_manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_synthetic_nominal_price_evidence",
        "tickers": tickers,
        "session_dates": sessions["session_date"].tolist(),
        "execution_field": "Open",
        "valuation_field": "Close",
        "separate_open_close_channels": True,
        "artifact": _artifact(price_path),
    }
    price_manifest["manifest_sha256"] = canonical_sha256(price_manifest)
    price_manifest_path = output / "inputs/nominal_price_manifest.json"
    _atomic_text(
        price_manifest_path,
        json.dumps(price_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    price_hashes = {
        value: file_sha256(price_manifest_path) for value in sessions["session_date"].tolist()
    }
    opens = prices.pivot(index="Date", columns="ticker", values="Open")
    closes = prices.pivot(index="Date", columns="ticker", values="Close")

    selectors = [f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES]
    decision_chains = {
        selector_id: _synthetic_decisions(
            selector_id, available="__user_preference__" not in selector_id,
            sessions=sessions,
        )
        for selector_id in selectors
    }
    decisions_path = output / "inputs/decision_chains.json"
    _atomic_text(
        decisions_path,
        json.dumps(decision_chains, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    lane_artifacts = {}
    path_dates = None
    for selector_id, decisions in decision_chains.items():
        _, rebalances, trades, path = replay_lane_path(
            decisions, sessions=sessions, valuation_closes=closes,
            execution_opens=opens, valuation_end_date=sessions["session_date"].iloc[-1],
        )
        ledger = output / "lane_paths" / f"{selector_id}.jsonl"
        records = append_lane_path(
            ledger, selector_id=selector_id, path=path, rebalances=rebalances,
            trades=trades, price_evidence_sha256_by_date=price_hashes,
        )
        dates = [record["date"] for record in records]
        if path_dates is None:
            path_dates = dates
        elif dates != path_dates:
            raise NdxDynamicShadowActivationV2Error("synthetic selector calendars differ")
        lane_artifacts[selector_id] = {
            **_artifact(ledger), "rows": len(records),
            "terminal_record_sha256": records[-1]["record_sha256"],
        }
    representative = decision_chains[f"{TRACKS[0]}__return__v1"]
    _, control_rebalances, control_trades, control_path = replay_original8_control_path(
        representative, frozen_securities=frozen_securities, sessions=sessions,
        valuation_closes=closes, execution_opens=opens,
        valuation_end_date=sessions["session_date"].iloc[-1],
    )
    original_ledger = output / "benchmark_controls/original_8_incumbent_v0.jsonl"
    original_records = append_lane_path(
        original_ledger, selector_id="ndx_original_8_incumbent_v0", path=control_path,
        rebalances=control_rebalances, trades=control_trades,
        price_evidence_sha256_by_date=price_hashes,
    )

    target_ledger = output / "benchmark_controls/target_012922_asof.jsonl"
    for index, session_date in enumerate(path_dates or (), start=1):
        close_time = pd.Timestamp(f"{session_date}T20:00:00+00:00")
        fetched = close_time + pd.Timedelta(minutes=5)
        observed = close_time + pd.Timedelta(minutes=10)
        nav = pd.DataFrame({
            "Date": list((path_dates or ())[:index]),
            "Close": [1.0 + number * 0.01 for number in range(index)],
        })
        source_directory = target_ledger.parent / "target_012922_sources"
        csv_path = source_directory / f"012922_{session_date}.csv"
        _atomic_text(csv_path, nav.to_csv(index=False, lineterminator="\n"))
        source_manifest = {
            "schema_version": 1,
            "dataset_key": "012922",
            "content_sha256": file_sha256(csv_path),
            "row_count": len(nav),
            "fetched_at": fetched.isoformat(),
            "publication_time_known": False,
        }
        source_manifest_path = source_directory / f"012922_{session_date}.csv.manifest.json"
        _atomic_text(
            source_manifest_path,
            json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        append_target_012922_trace(
            target_ledger, path_dates=(path_dates or ())[:index], target_nav=nav,
            observed_at_utc=observed, source_csv_snapshot_path=csv_path,
            source_manifest_snapshot_path=source_manifest_path,
            source_csv_sha256=file_sha256(csv_path),
            source_manifest_sha256=file_sha256(source_manifest_path),
            source_fetched_at_utc=fetched,
        )
    target_records = __import__(
        "backtest.ndx_dynamic_shadow_daily", fromlist=["load_target_012922_trace_ledger"]
    ).load_target_012922_trace_ledger(target_ledger)
    alignment_directory = output / "three_way_calendar_alignment" / str((path_dates or ())[-1])
    alignment = write_three_way_calendar_manifest(
        alignment_directory,
        selector_lane_ledgers={
            selector_id: output / "lane_paths" / f"{selector_id}.jsonl"
            for selector_id in selectors
        },
        original_8_ledger=original_ledger,
        target_012922_ledger=target_ledger,
        observed_sessions=sessions,
        observed_calendar_manifest_path=_canonical(
            root, "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json",
        ),
    )
    alignment_path = alignment_directory / "manifest.json"
    source_paths = {
        "daily_contract": _canonical(root, "config/ndx_dynamic_shadow_daily_v1.yaml"),
        "daily_module": _canonical(root, "backtest/ndx_dynamic_shadow_daily.py"),
        "daily_script": _canonical(root, "scripts/ndx_dynamic_shadow_daily.py"),
        "whole_lot_engine": _canonical(root, "backtest/ndx_dynamic_whole_lot_path.py"),
        "activation_module": Path(__file__).resolve(),
        "original_8_definition": original_manifest_path,
    }
    manifest = {
        "schema_version": 2,
        "manifest_type": "ndx_dynamic_shadow_activation_v2_synthetic_e2e",
        "status": "REBUILDABLE_SYNTHETIC_E2E_COMPLETE_RESEARCH_ONLY",
        "scenario": {
            "decision_count": 2,
            "dynamic_holding_counts": [1, 2],
            "ticker_rename_same_security_id": ["AAA", "AAX"],
            "selector_lane_count": 10,
            "original_8_executable_control_count": 1,
            "target_012922_trace_count": len(target_records),
            "calendar_dates": path_dates,
        },
        "source_bindings": {name: _artifact(path) for name, path in source_paths.items()},
        "artifacts": {
            "sessions": {**_artifact(session_path), "rows": len(sessions)},
            "prices": {**_artifact(price_path), "rows": len(prices)},
            "price_manifest": _artifact(price_manifest_path),
            "decision_chains": _artifact(decisions_path),
            "selector_lane_ledgers": lane_artifacts,
            "original_8_ledger": {
                **_artifact(original_ledger), "rows": len(original_records),
                "terminal_record_sha256": original_records[-1]["record_sha256"],
            },
            "target_012922_ledger": {
                **_artifact(target_ledger), "rows": len(target_records),
                "terminal_record_sha256": target_records[-1]["record_sha256"],
            },
            "three_way_alignment": {
                **_artifact(alignment_path), "manifest_sha256": alignment["manifest_sha256"],
            },
        },
        "research_automation_registration_evidence_only": True,
        "counts_as_prospective_performance_evidence": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    _atomic_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return verify_synthetic_e2e_manifest(manifest_path, repository_root=root)


def verify_synthetic_e2e_manifest(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Recompute the synthetic path prefixes instead of trusting guard booleans."""
    from backtest.ndx_dynamic_shadow_daily import (
        load_lane_path_ledger,
        load_target_012922_trace_ledger,
        replay_lane_path,
        replay_original8_control_path,
        validate_nominal_price_evidence,
        verify_three_way_calendar_manifest,
    )

    root = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowActivationV2Error("synthetic E2E manifest is missing/invalid") from exc
    unsigned = dict(manifest)
    declared = str(unsigned.pop("manifest_sha256", ""))
    from backtest.ndx_dynamic_shadow_daily import canonical_sha256
    _require(
        canonical_sha256(unsigned) == declared
        and manifest.get("manifest_type") == "ndx_dynamic_shadow_activation_v2_synthetic_e2e"
        and manifest.get("status") == "REBUILDABLE_SYNTHETIC_E2E_COMPLETE_RESEARCH_ONLY"
        and manifest.get("research_automation_registration_evidence_only") is True
        and manifest.get("counts_as_prospective_performance_evidence") is False
        and manifest.get("promotion_allowed") is False
        and manifest.get("live_mutation_allowed") is False,
        "synthetic E2E manifest boundary changed",
    )
    source_bindings = manifest.get("source_bindings") or {}
    expected_sources = {
        "daily_contract": _canonical(root, "config/ndx_dynamic_shadow_daily_v1.yaml"),
        "daily_module": _canonical(root, "backtest/ndx_dynamic_shadow_daily.py"),
        "daily_script": _canonical(root, "scripts/ndx_dynamic_shadow_daily.py"),
        "whole_lot_engine": _canonical(root, "backtest/ndx_dynamic_whole_lot_path.py"),
        "activation_module": Path(__file__).resolve(),
        "original_8_definition": _canonical(
            root, "data/cache/research/ndx_original_8_control_v1/manifest.json",
        ),
    }
    _require(set(source_bindings) == set(expected_sources), "synthetic source registry changed")
    for name, source in expected_sources.items():
        item = source_bindings[name]
        _require(
            Path(str(item.get("path") or "")).resolve() == source
            and source.is_file() and item.get("sha256") == file_sha256(source),
            f"synthetic source binding changed: {name}",
        )
    artifacts = manifest.get("artifacts") or {}

    def artifact_path(name: str) -> Path:
        item = artifacts.get(name) or {}
        value = Path(str(item.get("path") or "")).resolve()
        _require(value.is_file() and item.get("sha256") == file_sha256(value), f"synthetic artifact changed: {name}")
        return value

    sessions_path = artifact_path("sessions")
    prices_path = artifact_path("prices")
    price_manifest_path = artifact_path("price_manifest")
    decisions_path = artifact_path("decision_chains")
    sessions = pd.read_csv(sessions_path)
    prices = pd.read_csv(prices_path)
    price_manifest = json.loads(price_manifest_path.read_text(encoding="utf-8"))
    price_unsigned = dict(price_manifest)
    price_declared = price_unsigned.pop("manifest_sha256", None)
    _require(
        canonical_sha256(price_unsigned) == price_declared
        and price_manifest.get("separate_open_close_channels") is True
        and price_manifest.get("execution_field") == "Open"
        and price_manifest.get("valuation_field") == "Close"
        and (prices["Open"] != prices["Close"]).all(),
        "synthetic price channels are not independently bound",
    )
    prices = validate_nominal_price_evidence(
        prices, sessions, tickers=price_manifest["tickers"],
        valuation_end_date=sessions["session_date"].iloc[-1],
    )
    opens = prices.pivot(index="Date", columns="ticker", values="Open")
    closes = prices.pivot(index="Date", columns="ticker", values="Close")
    decision_chains = json.loads(decisions_path.read_text(encoding="utf-8"))
    expected_selectors = {f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES}
    lane_items = artifacts.get("selector_lane_ledgers") or {}
    _require(set(decision_chains) == expected_selectors == set(lane_items), "synthetic 2x5 lane registry changed")
    expected_dates = None
    for selector_id in sorted(expected_selectors):
        _, _, _, recomputed_path = replay_lane_path(
            decision_chains[selector_id], sessions=sessions, valuation_closes=closes,
            execution_opens=opens, valuation_end_date=sessions["session_date"].iloc[-1],
        )
        item = lane_items[selector_id]
        ledger_path = Path(str(item.get("path") or "")).resolve()
        _require(ledger_path.is_file() and item.get("sha256") == file_sha256(ledger_path), "synthetic lane hash changed")
        records = load_lane_path_ledger(ledger_path, selector_id)
        _require(
            len(records) == int(item.get("rows", -1))
            and records[-1]["record_sha256"] == item.get("terminal_record_sha256"),
            "synthetic lane prefix descriptor changed",
        )
        recomputed = recomputed_path.set_index(recomputed_path["date"].astype(str))
        for record in records:
            state = record["path_state"]
            row = recomputed.loc[str(record["date"])]
            _require(
                np.isclose(float(state["cash_usd"]), float(row["cash_usd"]), atol=1e-8)
                and np.isclose(float(state["holdings_value_usd"]), float(row["holdings_value_usd"]), atol=1e-8)
                and np.isclose(float(state["total_value_usd"]), float(row["total_value_usd"]), atol=1e-8)
                and int(state["holding_count"]) == int(row["holding_count"]),
                "synthetic selector path does not recompute",
            )
        dates = [record["date"] for record in records]
        expected_dates = dates if expected_dates is None else expected_dates
        _require(dates == expected_dates, "synthetic selector calendars differ")
    original_item = artifacts.get("original_8_ledger") or {}
    original_path = Path(str(original_item.get("path") or "")).resolve()
    original_records = load_lane_path_ledger(original_path, "ndx_original_8_incumbent_v0")
    frozen = json.loads(expected_sources["original_8_definition"].read_text(encoding="utf-8"))["definition"]["securities"]
    _, _, _, original_recomputed = replay_original8_control_path(
        decision_chains[f"{TRACKS[0]}__return__v1"], frozen_securities=frozen,
        sessions=sessions, valuation_closes=closes, execution_opens=opens,
        valuation_end_date=sessions["session_date"].iloc[-1],
    )
    _require(
        original_path.is_file() and original_item.get("sha256") == file_sha256(original_path)
        and len(original_records) == int(original_item.get("rows", -1))
        and [record["date"] for record in original_records] == expected_dates
        and original_recomputed["date"].astype(str).tolist() == expected_dates,
        "synthetic original-8 control does not recompute on the selector calendar",
    )
    target_item = artifacts.get("target_012922_ledger") or {}
    target_path = Path(str(target_item.get("path") or "")).resolve()
    target_records = load_target_012922_trace_ledger(target_path)
    _require(
        target_path.is_file() and target_item.get("sha256") == file_sha256(target_path)
        and len(target_records) == int(target_item.get("rows", -1))
        and [record["session_date"] for record in target_records] == expected_dates
        and all(
            record["source_date"] is None
            or str(record["source_date"]) <= str(record["session_date"])
            for record in target_records
        ),
        "synthetic 012922 trace is not no-future/same-calendar",
    )
    alignment_path = artifact_path("three_way_alignment")
    alignment = verify_three_way_calendar_manifest(alignment_path)
    scenario = manifest.get("scenario") or {}
    observed_k = sorted({
        int(item["selected_candidate"]["holding_count"])
        for chain in decision_chains.values() for item in chain
        if item.get("selected_candidate") is not None
    })
    _require(
        scenario.get("decision_count") == 2
        and observed_k == [1, 2] == scenario.get("dynamic_holding_counts")
        and int(scenario.get("selector_lane_count", -1)) == 10
        and int(alignment.get("selector_lane_count", -1)) == 10
        and int(alignment.get("benchmark_control_count", -1)) == 2
        and alignment.get("three_way_calendar_exact") is True,
        "synthetic dynamic-k/double-benchmark scenario changed",
    )
    return manifest


def _activation_source_paths(root: Path) -> dict[str, Path]:
    relative = {
        "objective_v1": OBJECTIVE_V1,
        "objective_v2": OBJECTIVE_V2,
        "selector_registry_v1": SELECTOR_V1,
        "selector_registry_v2": SELECTOR_V2,
        "runner_v1": RUNNER_V1,
        "runner_v2": RUNNER_V2,
        "daily_contract": "config/ndx_dynamic_shadow_daily_v1.yaml",
        "daily_module": "backtest/ndx_dynamic_shadow_daily.py",
        "daily_script": "scripts/ndx_dynamic_shadow_daily.py",
        "candidate_generator_contract": "config/ndx_dynamic_shadow_candidate_generator_v1.yaml",
        "candidate_generator_module": "backtest/ndx_dynamic_shadow_candidate_snapshot.py",
        "candidate_generator_script": "scripts/ndx_dynamic_shadow_candidate_generator.py",
        "fresh_search_contract": "config/ndx_dynamic_shadow_fresh_search_v1.yaml",
        "fresh_search_module": "backtest/ndx_dynamic_shadow_fresh_search.py",
        "fresh_search_script": "scripts/ndx_dynamic_shadow_fresh_search.py",
        "selector_policy": "backtest/ndx_dynamic_candidate_policy.py",
        "whole_lot_engine": "backtest/ndx_dynamic_whole_lot_path.py",
        "observed_calendar_module": "backtest/ndx_observed_session_calendar.py",
        "observed_calendar_script": "scripts/ndx_observed_session_calendar.py",
        "activation_v2_module": "backtest/ndx_dynamic_shadow_activation_v2.py",
        "activation_v2_script": "scripts/ndx_dynamic_shadow_activation_v2.py",
    }
    return {name: _canonical(root, path) for name, path in relative.items()}


def build_activation_v2_manifest(
    repository_root: str | Path, *, as_of_date: Any | None = None,
) -> dict[str, Any]:
    """Build a registration authority payload from independently rebuilt evidence."""
    root = Path(repository_root).resolve()
    contracts = validate_versioned_activation_contracts(root)
    synthetic_path = _canonical(root, SYNTHETIC_E2E_MANIFEST)
    synthetic = verify_synthetic_e2e_manifest(synthetic_path, repository_root=root)
    calendar_path = _canonical(
        root, "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json",
    )
    original8_path = _canonical(
        root, "data/cache/research/ndx_original_8_control_v1/manifest.json",
    )
    calendar = verify_observed_session_calendar_manifest(calendar_path, root)
    original8 = verify_original8_control_manifest(original8_path, root)
    _require(calendar.get("verified") is True, "activation calendar does not rebuild")
    _require(original8.get("verified") is True, "activation original-8 definition does not rebuild")
    calendar_manifest = json.loads(calendar_path.read_text(encoding="utf-8"))
    calendar_ledger = Path(
        str((calendar_manifest.get("artifacts") or {}).get("append_only_ledger", {}).get("path") or "")
    ).resolve()
    expected_calendar_ledger = calendar_path.parent / "sessions.jsonl"
    _require(
        calendar_ledger == expected_calendar_ledger and calendar_ledger.is_file(),
        "activation calendar ledger path is not canonical",
    )
    prefix_snapshot = _canonical(
        root,
        "data/cache/research/ndx_dynamic_shadow_activation_v2/observed_calendar_activation_prefix.jsonl",
    )
    current_prefix_content = calendar_ledger.read_text(encoding="utf-8")
    if prefix_snapshot.is_file():
        stored_lines = prefix_snapshot.read_text(encoding="utf-8").splitlines()
        verify_append_only_calendar_prefix(prefix_snapshot, calendar_ledger)
    else:
        _atomic_text(prefix_snapshot, current_prefix_content)
        stored_lines = current_prefix_content.splitlines()
    _require(bool(stored_lines), "activation calendar prefix is empty")
    terminal_calendar_record = json.loads(stored_lines[-1])
    sources = _activation_source_paths(root)
    for name, source in sources.items():
        _require(source.is_file(), f"activation canonical source is missing: {name}")
    activation_decision_count = sum(
        json.loads(line).get("decision_eligible") is True for line in stored_lines
    )
    prospective = {
        "status_at_activation": "NOT_DUE_AT_ACTIVATION",
        "decision_eligible_session_count_at_activation": activation_decision_count,
        "daily_run_manifest_at_activation": None,
    }
    if activation_decision_count > 0:
        from backtest.ndx_dynamic_shadow_daily import verify_daily_run_manifest

        daily_path = _canonical(
            root, "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json",
        )
        daily = verify_daily_run_manifest(daily_path, repository_root=root)
        prospective = {
            "status_at_activation": "CANONICAL_PREFIX_REBUILT_AT_ACTIVATION",
            "decision_eligible_session_count_at_activation": activation_decision_count,
            "daily_run_manifest_at_activation": _artifact(daily_path),
            "daily_run_status_at_activation": daily["status"],
        }
    manifest = {
        "schema_version": 2,
        "manifest_type": "ndx_dynamic_shadow_activation_v2",
        "status": "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": str(as_of_date or date.today())[:10],
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "versioned_contracts": contracts,
        "canonical_source_bindings": {name: _artifact(path) for name, path in sources.items()},
        "synthetic_e2e": {
            **_artifact(synthetic_path),
            "manifest_sha256": synthetic["manifest_sha256"],
            "counts_as_prospective_performance_evidence": False,
        },
        "observed_calendar": {
            "canonical_manifest_path": calendar_path.as_posix(),
            "canonical_ledger_path": calendar_ledger.as_posix(),
            "manifest_sha256_at_activation": file_sha256(calendar_path),
            "prefix_snapshot": {
                **_artifact(prefix_snapshot),
                "rows": len(stored_lines),
                "terminal_record_sha256": terminal_calendar_record.get("record_sha256"),
            },
            "latest_session_date_at_activation": terminal_calendar_record.get("session_date"),
            "decision_eligible_session_count_at_activation": sum(
                json.loads(line).get("decision_eligible") is True for line in stored_lines
            ),
            "extension_policy": "CURRENT_LEDGER_MUST_REBUILD_AND_PRESERVE_EXACT_ACTIVATION_PREFIX",
        },
        "original_8_definition": {
            **_artifact(original8_path),
            "definition_sha256": original8.get("definition_sha256"),
        },
        "prospective_evidence": prospective,
        "guards": {
            "versioned_contracts_rebuilt": True,
            "canonical_sources_hash_bound": True,
            "synthetic_dynamic_k_rebuilt": True,
            "synthetic_ten_lanes_rebuilt": True,
            "synthetic_original_8_control_rebuilt": True,
            "synthetic_target_no_future_trace_rebuilt": True,
            "synthetic_three_way_calendar_rebuilt": True,
            "prospective_prefix_not_due_or_rebuilt": True,
            "no_backfill_preserved": True,
            "componentwise_gate_preserved": True,
        },
        "research_automation_registration_allowed": True,
        "decision_and_path_generation_research_only": True,
        "task_registration_performed": False,
        "formal_forward_gate_substitution_allowed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
    }
    from backtest.ndx_dynamic_shadow_daily import canonical_sha256

    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def verify_activation_v2_manifest(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Rebuild every registration guard; self-reported booleans are insufficient."""
    root = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    expected = _canonical(root, ACTIVATION_MANIFEST)
    _require(path == expected, "activation v2 manifest path is not canonical")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowActivationV2Error("activation v2 manifest is missing/invalid") from exc
    from backtest.ndx_dynamic_shadow_daily import canonical_sha256

    unsigned = dict(manifest)
    declared = str(unsigned.pop("manifest_sha256", ""))
    _require(
        canonical_sha256(unsigned) == declared
        and manifest.get("schema_version") == 2
        and manifest.get("manifest_type") == "ndx_dynamic_shadow_activation_v2"
        and manifest.get("status") == "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION"
        and manifest.get("research_track") == "portfolio_optimization"
        and manifest.get("migration_control_included") is False,
        "activation v2 identity/hash changed",
    )
    reconstructed_contracts = validate_versioned_activation_contracts(root)
    _require(
        manifest.get("versioned_contracts") == reconstructed_contracts,
        "activation v2 versioned contract evidence changed",
    )
    source_bindings = manifest.get("canonical_source_bindings") or {}
    sources = _activation_source_paths(root)
    _require(set(source_bindings) == set(sources), "activation source registry changed")
    for name, source in sources.items():
        item = source_bindings[name]
        _require(
            Path(str(item.get("path") or "")).resolve() == source
            and source.is_file() and item.get("sha256") == file_sha256(source),
            f"activation canonical source changed: {name}",
        )
    synthetic_item = manifest.get("synthetic_e2e") or {}
    synthetic_path = _canonical(root, SYNTHETIC_E2E_MANIFEST)
    synthetic = verify_synthetic_e2e_manifest(synthetic_path, repository_root=root)
    _require(
        Path(str(synthetic_item.get("path") or "")).resolve() == synthetic_path
        and synthetic_item.get("sha256") == file_sha256(synthetic_path)
        and synthetic_item.get("manifest_sha256") == synthetic["manifest_sha256"]
        and synthetic_item.get("counts_as_prospective_performance_evidence") is False,
        "activation synthetic evidence binding changed",
    )
    calendar_path = _canonical(
        root, "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json",
    )
    calendar = verify_observed_session_calendar_manifest(calendar_path, root)
    original8_path = _canonical(
        root, "data/cache/research/ndx_original_8_control_v1/manifest.json",
    )
    original8 = verify_original8_control_manifest(original8_path, root)
    calendar_item = manifest.get("observed_calendar") or {}
    original_item = manifest.get("original_8_definition") or {}
    canonical_ledger = calendar_path.parent / "sessions.jsonl"
    prefix_item = calendar_item.get("prefix_snapshot") or {}
    prefix_path = _canonical(
        root,
        "data/cache/research/ndx_dynamic_shadow_activation_v2/observed_calendar_activation_prefix.jsonl",
    )
    _require(
        calendar.get("verified") is True
        and Path(str(calendar_item.get("canonical_manifest_path") or "")).resolve() == calendar_path
        and Path(str(calendar_item.get("canonical_ledger_path") or "")).resolve() == canonical_ledger
        and calendar_item.get("extension_policy")
        == "CURRENT_LEDGER_MUST_REBUILD_AND_PRESERVE_EXACT_ACTIVATION_PREFIX"
        and Path(str(prefix_item.get("path") or "")).resolve() == prefix_path
        and prefix_path.is_file() and prefix_item.get("sha256") == file_sha256(prefix_path),
        "activation observed calendar binding changed",
    )
    prefix_lines = prefix_path.read_text(encoding="utf-8").splitlines()
    prefix_audit = verify_append_only_calendar_prefix(prefix_path, canonical_ledger)
    _require(
        len(prefix_lines) == int(prefix_item.get("rows", -1))
        and bool(prefix_lines)
        and prefix_audit["terminal_record_sha256"] == prefix_item.get("terminal_record_sha256")
        and calendar_item.get("latest_session_date_at_activation")
        == json.loads(prefix_lines[-1]).get("session_date"),
        "activation observed calendar prefix changed instead of append-only extension",
    )
    _require(
        original8.get("verified") is True
        and original_item.get("sha256") == file_sha256(original8_path)
        and original_item.get("definition_sha256") == original8.get("definition_sha256"),
        "activation original-8 definition binding changed",
    )
    prospective = manifest.get("prospective_evidence") or {}
    activation_decision_count = sum(
        json.loads(line).get("decision_eligible") is True for line in prefix_lines
    )
    if activation_decision_count == 0:
        _require(
            prospective == {
                "status_at_activation": "NOT_DUE_AT_ACTIVATION",
                "decision_eligible_session_count_at_activation": 0,
                "daily_run_manifest_at_activation": None,
            },
            "activation-time prospective evidence was fabricated",
        )
    else:
        from backtest.ndx_dynamic_shadow_daily import verify_daily_run_manifest

        daily_path = _canonical(
            root, "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json",
        )
        daily = verify_daily_run_manifest(daily_path, repository_root=root)
        daily_item = prospective.get("daily_run_manifest_at_activation") or {}
        _require(
            prospective.get("status_at_activation") == "CANONICAL_PREFIX_REBUILT_AT_ACTIVATION"
            and int(prospective.get("decision_eligible_session_count_at_activation", -1))
            == activation_decision_count
            and Path(str(daily_item.get("path") or "")).resolve() == daily_path
            and daily_item.get("sha256") == file_sha256(daily_path)
            and prospective.get("daily_run_status_at_activation") == daily.get("status"),
            "activation-time prospective daily prefix does not rebuild",
        )
    expected_guards = {
        "versioned_contracts_rebuilt": True,
        "canonical_sources_hash_bound": True,
        "synthetic_dynamic_k_rebuilt": True,
        "synthetic_ten_lanes_rebuilt": True,
        "synthetic_original_8_control_rebuilt": True,
        "synthetic_target_no_future_trace_rebuilt": True,
        "synthetic_three_way_calendar_rebuilt": True,
        "prospective_prefix_not_due_or_rebuilt": True,
        "no_backfill_preserved": True,
        "componentwise_gate_preserved": True,
    }
    _require(manifest.get("guards") == expected_guards, "activation guard registry changed")
    _require(
        manifest.get("research_automation_registration_allowed") is True
        and manifest.get("decision_and_path_generation_research_only") is True
        and manifest.get("task_registration_performed") is False
        and manifest.get("formal_forward_gate_substitution_allowed") is False
        and manifest.get("promotion_allowed") is False
        and manifest.get("live_mutation_allowed") is False,
        "activation authority exceeded research-only registration",
    )
    runtime = {
        "status": "NOT_DUE_YET",
        "current_decision_eligible_session_count": int(
            calendar.get("decision_eligible_session_count", 0)
        ),
        "daily_prefix_rebuilt": False,
    }
    if runtime["current_decision_eligible_session_count"] > 0:
        daily_path = _canonical(
            root, "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json",
        )
        if daily_path.is_file():
            from backtest.ndx_dynamic_shadow_daily import verify_daily_run_manifest

            verify_daily_run_manifest(daily_path, repository_root=root)
            runtime.update({"status": "DUE_PREFIX_REBUILT", "daily_prefix_rebuilt": True})
        else:
            runtime["status"] = "DUE_FIRST_RUN_PENDING_ALLOWED"
    result = dict(manifest)
    result["runtime_verification"] = runtime
    return result


def build_activation_v2_readiness(
    repository_root: str | Path, *, as_of_date: Any | None = None,
) -> dict[str, Any]:
    """Separate implementation readiness from not-yet-due prospective evidence."""
    root = Path(repository_root).resolve()
    contracts = validate_versioned_activation_contracts(root)
    calendar_path = _canonical(
        root, "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json",
    )
    original8_path = _canonical(
        root, "data/cache/research/ndx_original_8_control_v1/manifest.json",
    )
    calendar = verify_observed_session_calendar_manifest(calendar_path, root)
    original8 = verify_original8_control_manifest(original8_path, root)
    implementation_blockers = []
    if not calendar.get("verified"):
        implementation_blockers.append("CANONICAL_OBSERVED_CALENDAR_NOT_REPRODUCIBLE")
    if not original8.get("verified"):
        implementation_blockers.append("CANONICAL_ORIGINAL8_DEFINITION_NOT_REPRODUCIBLE")
    synthetic_path = _canonical(root, SYNTHETIC_E2E_MANIFEST)
    try:
        verify_synthetic_e2e_manifest(synthetic_path, repository_root=root)
    except Exception:
        implementation_blockers.append("REBUILDABLE_SYNTHETIC_E2E_EVIDENCE_MISSING")
    prospective_due = int(calendar.get("decision_eligible_session_count", 0)) > 0
    evidence_status = "DUE_REQUIRES_CANONICAL_PREFIX_VERIFICATION" if prospective_due else "NOT_DUE_YET"
    blockers = list(implementation_blockers)
    if prospective_due:
        try:
            from backtest.ndx_dynamic_shadow_daily import verify_daily_run_manifest

            verify_daily_run_manifest(
                _canonical(
                    root, "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json",
                ),
                repository_root=root,
            )
        except Exception:
            blockers.append("PROSPECTIVE_DAILY_DOUBLE_BENCHMARK_PREFIX_NOT_YET_VERIFIED")
    registration_allowed = not implementation_blockers
    return {
        "schema_version": 2,
        "manifest_type": "ndx_dynamic_shadow_activation_v2_readiness",
        "status": "BLOCKED" if implementation_blockers else "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION",
        "blockers": blockers,
        "implementation_blockers": implementation_blockers,
        "implementation_readiness": "BLOCKED" if implementation_blockers else "READY",
        "prospective_evidence_due": prospective_due,
        "prospective_evidence_status": evidence_status,
        "versioned_contracts": contracts,
        "observed_calendar": calendar,
        "original_8_definition": original8,
        "research_automation_registration_allowed": registration_allowed,
        "decision_and_path_generation_research_only": True,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
    }


__all__ = [
    "ACTIVATION_MANIFEST", "SYNTHETIC_E2E_MANIFEST", "NdxDynamicShadowActivationV2Error",
    "build_activation_v2_manifest", "build_activation_v2_readiness",
    "build_synthetic_e2e_manifest", "validate_versioned_activation_contracts",
    "verify_activation_v2_manifest", "verify_append_only_calendar_prefix",
    "verify_synthetic_e2e_manifest",
]
