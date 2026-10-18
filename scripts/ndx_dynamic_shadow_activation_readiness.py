from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_activation_readiness import (  # noqa: E402
    REQUIRED_ROLES,
    REQUIRED_TRACKS,
    atomic_write_json,
    estimate_monthly_search_cost,
    evaluate_activation_readiness,
    sha256_file,
    validate_bound_source_hashes,
    validate_selector_matrix,
    verify_observed_session_calendar_manifest,
    verify_original8_control_manifest,
)


DEFAULT_OUTPUT = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_readiness_v1/manifest.json"
PROTECTED_PATHS = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _hashes(paths: tuple[Path, ...]) -> dict[str, str | None]:
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) if path.exists() else None for path in paths}


def _input(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "exists": path.exists(),
        "sha256": sha256_file(path) if path.exists() else None,
    }


def _validated_output(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if resolved.parent != DEFAULT_OUTPUT.parent.resolve():
        raise ValueError(
            "activation readiness output must stay in its canonical research directory"
        )
    return resolved


def _max_selection_date(discovery: Mapping[str, Any]) -> str | None:
    dates = [str(row.get("selection_date")) for row in discovery.get("selections", []) if row.get("selection_date")]
    return max(dates) if dates else None


def _window_summary(path: Path) -> tuple[str | None, dict[str, int]]:
    latest: dict[str, tuple[str, int]] = {}
    if not path.is_file():
        return None, {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            track = str(row.get("universe_track") or "")
            date = str(row.get("selection_date") or "")
            count = row.get("available_issuer_count")
            if track not in REQUIRED_TRACKS or not date or count in (None, ""):
                continue
            candidate = (date, int(count))
            if track not in latest or candidate[0] > latest[track][0]:
                latest[track] = candidate
    return (
        max((value[0] for value in latest.values()), default=None),
        {track: value[1] for track, value in latest.items()},
    )


def _taxonomy_membership_hash(taxonomy: Mapping[str, Any]) -> str | None:
    for row in taxonomy.get("input_versions", []):
        if isinstance(row, Mapping) and row.get("source_name") == "ndx_point_in_time_constituents":
            return str(row.get("content_sha256") or "") or None
    return None


def build_manifest() -> dict[str, Any]:
    registry_path = ROOT / "config/ndx_dynamic_shadow_selector_registry_v1.yaml"
    objective_path = ROOT / "config/ndx_portfolio_objective_v1.yaml"
    walkforward_path = ROOT / "config/ndx_dynamic_walkforward_v1.yaml"
    discovery_spec_path = ROOT / "config/ndx_cardinality_discovery_v1.yaml"
    discovery_path = ROOT / "data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json"
    input_readiness_path = ROOT / "data/cache/research/ndx_variable_cardinality_input_readiness_v3/manifest.json"
    history_path = ROOT / "data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv.manifest.json"
    taxonomy_path = ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json"
    selector_module_path = ROOT / "backtest/ndx_dynamic_candidate_policy.py"
    generator_path = ROOT / "scripts/ndx_cardinality_real_smoke.py"
    runner_path = ROOT / "scripts/ndx_cardinality_real_runner.py"
    future_runner_contract_path = ROOT / "config/ndx_dynamic_shadow_runner_v1.yaml"
    future_runner_module_path = ROOT / "backtest/ndx_dynamic_shadow_runner.py"
    future_runner_script_path = ROOT / "scripts/ndx_dynamic_shadow_runner.py"
    generator_contract_path = ROOT / "config/ndx_dynamic_shadow_candidate_generator_v1.yaml"
    generator_module_path = ROOT / "backtest/ndx_dynamic_shadow_candidate_snapshot.py"
    generator_script_path = ROOT / "scripts/ndx_dynamic_shadow_candidate_generator.py"
    readiness_module_path = ROOT / "backtest/ndx_dynamic_shadow_activation_readiness.py"
    readiness_script_path = ROOT / "scripts/ndx_dynamic_shadow_activation_readiness.py"
    original8_control_path = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"
    windows_path = ROOT / "data/cache/research/ndx_variable_cardinality_discovery_v1/point_in_time_windows.csv"
    observed_calendar_manifest_path = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
    observed_calendar_ledger_path = observed_calendar_manifest_path.parent / "sessions.jsonl"
    observed_calendar_projection_path = observed_calendar_manifest_path.parent / "sessions.csv"
    observed_calendar_engine_path = ROOT / "backtest/ndx_observed_session_calendar.py"
    observed_calendar_script_path = ROOT / "scripts/ndx_observed_session_calendar.py"

    registry = _read_yaml(registry_path)
    objective = _read_yaml(objective_path)
    discovery_spec = _read_yaml(discovery_spec_path)
    discovery = _read_json(discovery_path)
    history = _read_json(history_path)
    taxonomy = _read_json(taxonomy_path)
    input_readiness = _read_json(input_readiness_path)

    shadow = objective.get("dynamic_shadow_path") or {}
    implementation = shadow.get("implementation_readiness") or {}
    activation = registry.get("activation") or {}
    source_contracts = registry.get("source_contracts") or {}
    mutation = registry.get("mutation_boundary") or {}
    per_selector = registry.get("per_selector_contract") or {}
    history_contract = discovery_spec.get("history_contract") or {}

    latest_window_date, latest_pool_sizes = _window_summary(windows_path)
    for row in discovery.get("selections", []):
        track = str(row.get("universe_track") or "")
        count = row.get("eligible_distinct_issuer_count") or row.get("eligible_count")
        if track in REQUIRED_TRACKS and count is not None:
            latest_pool_sizes[track] = max(latest_pool_sizes.get(track, 0), int(count))
    latest_pool_sizes.setdefault("strict_technology", 16)
    latest_pool_sizes.setdefault("technology_plus_adjacent", 21)

    generator_text = generator_path.read_text(encoding="utf-8")
    runner_text = runner_path.read_text(encoding="utf-8")
    selector_text = selector_module_path.read_text(encoding="utf-8")
    future_runner_text = future_runner_module_path.read_text(encoding="utf-8")
    source_hashes_bound = validate_bound_source_hashes(registry, ROOT)
    original8_control = verify_original8_control_manifest(original8_control_path, ROOT)
    observed_calendar = verify_observed_session_calendar_manifest(
        observed_calendar_manifest_path, ROOT
    )

    registry_active = bool(
        registry.get("status") == "ACTIVE"
        and activation.get("active") is True
        and activation.get("runner_registered") is True
        and activation.get("decision_generation_allowed") is True
        and source_hashes_bound
    )
    protected_contract = (
        mutation.get("research_output_only") is True
        and mutation.get("live_configuration_mutation_allowed") is False
        and mutation.get("state_mutation_allowed") is False
        and mutation.get("broker_snapshot_mutation_allowed") is False
        and mutation.get("today_advice_mutation_allowed") is False
        and mutation.get("order_creation_allowed") is False
    )

    # Existing kernels are useful, but the future monthly coordinator does not yet exist.
    # Capabilities that only appear in the historical runner are intentionally not promoted.
    facts = {
        "portfolio_optimization_track_only": registry.get("research_track") == "portfolio_optimization"
        and registry.get("migration_control_included") is False,
        "selector_matrix_exact": validate_selector_matrix(registry),
        "dynamic_k_contract_exact": per_selector.get("dynamic_k")
        == "1..point_in_time_eligible_pool_distinct_issuer_count"
        and per_selector.get("fixed_holding_count") is None,
        "point_in_time_snapshot_builder": all(
            path.is_file() for path in (generator_contract_path, generator_module_path, generator_script_path)
        ),
        "decision_close_cutoff_separated": "information_cutoff: decision_close" in generator_contract_path.read_text(encoding="utf-8")
        and "execution must be strictly after decision close" in generator_module_path.read_text(encoding="utf-8"),
        "verified_us_session_calendar": observed_calendar["verified"],
        "candidate_input_cutoff_recomputed": False,
        "candidate_training_end_recomputed": False,
        "snapshot_sealed_before_execution_open": False,
        "full_dynamic_k_orchestration": False,
        "fresh_search_only_enforced": False,
        "immutable_per_k_checkpoint_resume": "--resume" in runner_text,
        "five_role_lock_deterministic": all(role in selector_text for role in REQUIRED_ROLES),
        "missing_role_fail_closed": "REFERENCE_UNAVAILABLE_NOT_REPLACED" in future_runner_text
        and "missing_lane_replacement_allowed" in future_runner_text,
        "decision_artifact_matrix_exact": False,
        "one_security_per_issuer_enforced": "issuer_id" in generator_text,
        "lifecycle_identity_fail_closed": "security_id" in generator_text and "issuer_id" in generator_text,
        "return_and_execution_price_channels_separate": (ROOT / "scripts/ndx_cardinality_execution_price_refresh.py").exists()
        and (ROOT / "backtest/ndx_dynamic_whole_lot_path.py").exists(),
        "immutable_incumbent_baseline": original8_control["verified"],
        "append_only_monthly_runner": False,
        "artifact_verifier": False,
        "runner_registered": implementation.get("runner_registered") is True and activation.get("runner_registered") is True,
        "selector_registry_active": registry_active,
        "no_backfill_verified": bool((shadow.get("versioning") or {}).get("backfill_allowed") is False),
        "next_session_execution_verified": False,
        "append_only_verified": False,
        "live_isolation_verified": False,
        "fresh_membership_snapshot_available": False,
        "taxonomy_bound_to_membership_hash": False,
        "complete_k_coordinate_set_available": False,
        "training_prices_available_through_decision_close": False,
        "target_nav_asof_available": False,
        "original_8_same_calendar_available": False,
        "target_012922_same_calendar_available": False,
    }
    readiness = evaluate_activation_readiness(facts)

    first_decision = str((shadow.get("availability") or {}).get("planned_first_decision_on_or_after") or "2026-10-01")
    inputs = [
        _input(path)
        for path in (
            registry_path,
            objective_path,
            walkforward_path,
            discovery_spec_path,
            discovery_path,
            input_readiness_path,
            history_path,
            taxonomy_path,
            selector_module_path,
            generator_path,
            runner_path,
            future_runner_contract_path,
            future_runner_module_path,
            future_runner_script_path,
            generator_contract_path,
            generator_module_path,
            generator_script_path,
            readiness_module_path,
            readiness_script_path,
            original8_control_path,
            windows_path,
            observed_calendar_manifest_path,
            observed_calendar_ledger_path,
            observed_calendar_projection_path,
            observed_calendar_engine_path,
            observed_calendar_script_path,
        )
    ]
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_activation_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **readiness,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "first_prospective_decision_on_or_after": first_decision,
        "current_input_evidence": {
            "discovery_history_end_date": history_contract.get("end_date"),
            "discovery_max_selection_date": latest_window_date or _max_selection_date(discovery),
            "nport_data_end": history.get("data_end"),
            "nport_latest_report_date": max((str(value) for value in history.get("report_dates", []) if value), default=None),
            "nport_membership_sha256": history.get("content_sha256"),
            "taxonomy_membership_source_sha256": _taxonomy_membership_hash(taxonomy),
            "taxonomy_classified_security_count": (taxonomy.get("summary") or {}).get("classified_security_count"),
            "taxonomy_unclassified_security_count": (taxonomy.get("summary") or {}).get("unclassified_security_count"),
            "input_readiness_status": input_readiness.get("status"),
            "selector_source_hashes_bound": source_hashes_bound,
            "live_isolation_contract_declared": protected_contract,
            "original_8_control": original8_control,
            "observed_session_calendar": observed_calendar,
        },
        "reusable_kernels": {
            "fresh_search_kernel": generator_path.relative_to(ROOT).as_posix(),
            "historical_checkpoint_runner": runner_path.relative_to(ROOT).as_posix(),
            "five_role_selector": selector_module_path.relative_to(ROOT).as_posix(),
            "dynamic_whole_lot_path": "backtest/ndx_dynamic_whole_lot_path.py",
            "historical_artifacts_may_seed_or_backfill_candidates": False,
        },
        "minimum_missing_implementation": [
            "prospective PIT monthly snapshot builder with decision_time information cutoff",
            "fresh full-k coordinator over both universe tracks with immutable per-k checkpoints",
            "cross-k frontier plus deterministic five-role lock and explicit unavailable roles",
            "append-only next-session Open execution / Close valuation path runner",
            "artifact verifier and hash-bound original-8 plus 012922 controls",
        ],
        "monthly_search_cost_estimate_from_latest_observed_pool": estimate_monthly_search_cost(latest_pool_sizes),
        "long_run_operating_contract": {
            "checkpoint_key_fields": ["snapshot_sha256", "selector_policy_sha256", "universe_track", "decision_date", "k"],
            "seal_only_after_all_required_k_complete": True,
            "missed_execution_window_action": "NO_DECISION_NO_BACKFILL",
            "expected_wall_clock": "tens_of_minutes_to_several_hours_per_month_hardware_dependent",
        },
        "external_data_requirements": {
            "user_supplied_files_required": False,
            "network_sources_required": ["SEC_NPORT_membership", "market_adjusted_training_prices", "nominal_Open_Close_execution_prices", "012922_NAV"],
            "existing_fetch_capability_available": True,
            "conditional_manual_review": "new_or_unclassified_taxonomy_or_ambiguous_security_lifecycle_identity",
        },
        "inputs": inputs,
        "protected_paths": [path.relative_to(ROOT).as_posix() for path in PROTECTED_PATHS],
        "protected_hashes_before": _hashes(PROTECTED_PATHS),
        "protected_hashes_after": _hashes(PROTECTED_PATHS),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit prospective NDX dynamic-shadow activation readiness.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Do not write; exit non-zero unless automation registration is ready.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = _validated_output(args.output)
    protected_before = _hashes(PROTECTED_PATHS)
    manifest = build_manifest()
    if not args.check:
        atomic_write_json(output, manifest)
        protected_after = _hashes(PROTECTED_PATHS)
        if protected_after != protected_before:
            raise RuntimeError("protected live files changed during readiness audit")
        manifest["protected_hashes_before"] = protected_before
        manifest["protected_hashes_after"] = protected_after
        atomic_write_json(output, manifest)
        print(f"dynamic shadow readiness: {manifest['status']} | {output}")
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0 if manifest["automation_registration_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
