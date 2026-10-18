from __future__ import annotations

import hashlib
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.ndx_original8_control import build_original8_control, canonical_sha256
from backtest.ndx_observed_session_calendar import (
    BOOTSTRAP_ORIGIN,
    PROSPECTIVE_ORIGIN,
    load_ledger,
    load_ohlc_rows,
    projection_rows,
    validate_ledger,
)


REQUIRED_TRACKS = ("strict_technology", "technology_plus_adjacent")
REQUIRED_ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
READY_STATUS = "READY_FOR_AUTOMATION_REGISTRATION"
BLOCKED_STATUS = "BLOCKED"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bool(value: Any) -> bool:
    return value is True


def estimate_monthly_search_cost(
    eligible_issuer_counts: Mapping[str, int],
    *,
    exact_enumeration_limit: int = 50_000,
) -> dict[str, Any]:
    """Describe full dynamic-k work without confusing k with a fixed portfolio size."""
    tracks: list[dict[str, Any]] = []
    total_shards = 0
    exact_shards = 0
    bounded_shards = 0
    for track in REQUIRED_TRACKS:
        count = int(eligible_issuer_counts.get(track, 0))
        if count < 1:
            tracks.append({"universe_track": track, "eligible_issuer_count": count, "k_shards": []})
            continue
        shards: list[dict[str, Any]] = []
        for k in range(1, count + 1):
            combinations = math.comb(count, k)
            search_class = "EXACT_ENUMERATION" if combinations <= exact_enumeration_limit else "BOUNDED_SEARCH"
            shards.append(
                {
                    "k": k,
                    "theoretical_combinations": combinations,
                    "search_class": search_class,
                }
            )
            total_shards += 1
            if search_class == "EXACT_ENUMERATION":
                exact_shards += 1
            else:
                bounded_shards += 1
        tracks.append({"universe_track": track, "eligible_issuer_count": count, "k_shards": shards})
    return {
        "exact_enumeration_limit": int(exact_enumeration_limit),
        "total_track_k_shards": total_shards,
        "exact_shards": exact_shards,
        "bounded_shards": bounded_shards,
        "tracks": tracks,
    }


def evaluate_activation_readiness(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed readiness decision for prospective dynamic-shadow automation.

    ``facts`` are descriptive diagnostics only.  Caller-supplied booleans can
    never activate automation; an immutable artifact verifier must replace this
    evaluator before readiness can become true.  Historical runners and frozen
    forward cohorts are never valid monthly candidate sources.
    """
    blockers: list[dict[str, str]] = []
    checks: dict[str, bool] = {}

    def require(code: str, reason: str, *, severity: str = "P0", section: str = "implementation") -> None:
        passed = _bool(facts.get(code))
        checks[code] = passed
        if not passed:
            blockers.append({"severity": severity, "section": section, "code": code, "reason": reason})

    require("portfolio_optimization_track_only", "selector must be portfolio_optimization, not migration_control")
    require("selector_matrix_exact", "both universe tracks and all five policy roles must be preregistered")
    require("dynamic_k_contract_exact", "candidate k must be exactly 1..PIT eligible distinct issuer count")
    require("point_in_time_snapshot_builder", "no prospective monthly PIT universe/taxonomy snapshot builder is registered")
    require("decision_close_cutoff_separated", "decision close, information cutoff, and next-session execution must be separate fields")
    require("verified_us_session_calendar", "decision and execution dates require a hash-bound US session calendar")
    require("candidate_input_cutoff_recomputed", "candidate input timestamps must be recomputed and bounded by decision close")
    require("candidate_training_end_recomputed", "candidate training end must be recomputed from source rows, not self-reported")
    require("snapshot_sealed_before_execution_open", "the candidate snapshot must be sealed before next-session Open")
    require("full_dynamic_k_orchestration", "runner must search every eligible k rather than require one fixed holding_count")
    require("fresh_search_only_enforced", "monthly runner must reject historical candidate-set replay and registry backfill")
    require("immutable_per_k_checkpoint_resume", "long search must checkpoint by source hashes, track, decision date, and k")
    require("five_role_lock_deterministic", "the completed cross-k frontier must deterministically lock five roles")
    require("missing_role_fail_closed", "an unavailable role must be explicit and must not be silently substituted")
    require("decision_artifact_matrix_exact", "each monthly batch must contain exactly the 2 x 5 independent lane matrix")
    require("one_security_per_issuer_enforced", "candidate construction must enforce issuer uniqueness")
    require("lifecycle_identity_fail_closed", "security_id and issuer_id lifecycle resolution must be complete and unambiguous")
    require("return_and_execution_price_channels_separate", "adjusted training returns and nominal Open/Close execution prices must be isolated")
    require("immutable_incumbent_baseline", "original-8 control weights must be hash-bound, not read from mutable live state")
    require("append_only_monthly_runner", "prospective monthly selections and paths need an append-only runner")
    require("artifact_verifier", "self-reported guard booleans are insufficient without an immutable artifact verifier")
    require("runner_registered", "the objective contract says the prospective runner is not registered")
    require("selector_registry_active", "selector registry is inactive and its source hashes are not activation-bound")
    require("no_backfill_verified", "monthly decisions must be sealed without retrospective backfill")
    require("next_session_execution_verified", "first common session Open execution and Close valuation must be verified")
    require("append_only_verified", "selection, trade, cash, and daily path artifacts must be append-only and hash verified")
    require("live_isolation_verified", "research automation must prove it cannot mutate live config/state/advice/orders")

    # These are temporal coordinate facts, not a reason to weaken implementation gates.
    decision_checks: dict[str, bool] = {}
    decision_blockers: list[dict[str, str]] = []

    def require_decision(code: str, reason: str) -> None:
        passed = _bool(facts.get(code))
        decision_checks[code] = passed
        if not passed:
            decision_blockers.append(
                {"severity": "P1", "section": "prospective_input", "code": code, "reason": reason}
            )

    require_decision("fresh_membership_snapshot_available", "first decision PIT membership snapshot is not yet sealed")
    require_decision("taxonomy_bound_to_membership_hash", "taxonomy must be rebuilt and hash-bound to that membership snapshot")
    require_decision("complete_k_coordinate_set_available", "both tracks must contain every k from 1 through eligible issuer count")
    require_decision("training_prices_available_through_decision_close", "training inputs must be available no later than decision close")
    require_decision("target_nav_asof_available", "012922 target NAV must have a disclosed non-future as-of date")
    require_decision("original_8_same_calendar_available", "original-8 control must be valued on the candidate path sessions")
    require_decision("target_012922_same_calendar_available", "012922 as-of trace must cover the same candidate path sessions")

    guards = {
        "runner_registered": checks["runner_registered"],
        "selector_registry_active": checks["selector_registry_active"],
        "decision_generation_allowed": False,
        "no_backfill_verified": checks["no_backfill_verified"],
        "next_session_execution_verified": checks["next_session_execution_verified"],
        "append_only_verified": checks["append_only_verified"],
        "live_isolation_verified": checks["live_isolation_verified"],
        "immutable_artifact_evidence_verified": False,
    }
    blockers.append({
        "severity": "P0",
        "section": "evidence",
        "code": "immutable_artifact_evidence_not_evaluated",
        "reason": (
            "caller-supplied booleans are diagnostic only; a path-bound immutable "
            "artifact verifier is not implemented"
        ),
    })
    implementation_ready = False
    prospective_input_ready = not decision_blockers
    decision_generation_allowed = False
    guards["decision_generation_allowed"] = decision_generation_allowed
    automation_registration_allowed = implementation_ready and all(guards.values())

    return {
        "status": READY_STATUS if automation_registration_allowed else BLOCKED_STATUS,
        "automation_registration_allowed": automation_registration_allowed,
        "decision_generation_allowed": decision_generation_allowed,
        "implementation_ready": implementation_ready,
        "prospective_input_ready": prospective_input_ready,
        "guards": guards,
        "checks": checks,
        "prospective_input_checks": decision_checks,
        "blockers": blockers,
        "prospective_input_blockers": decision_blockers,
        "historical_candidate_replay_allowed": False,
        "retrospective_backfill_allowed": False,
        "frozen_forward_candidates_allowed_as_dynamic_source": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "caller_supplied_booleans_can_activate": False,
        "evidence_mode": "DESCRIPTIVE_DIAGNOSTIC_NOT_VERIFIED_ACTIVATION_EVIDENCE",
    }


def validate_selector_matrix(registry: Mapping[str, Any]) -> bool:
    matrix = registry.get("selector_matrix") or {}
    selectors = matrix.get("selectors") or []
    expected = {(track, role) for track in REQUIRED_TRACKS for role in REQUIRED_ROLES}
    observed = {
        (str(row.get("universe_track")), str(row.get("policy_role")))
        for row in selectors
        if isinstance(row, Mapping)
    }
    return (
        len(selectors) == len(expected)
        and
        tuple(matrix.get("universe_tracks") or ()) == REQUIRED_TRACKS
        and tuple(matrix.get("policy_roles") or ()) == REQUIRED_ROLES
        and int(matrix.get("expected_selector_count") or 0) == len(expected)
        and observed == expected
    )


def validate_bound_source_hashes(registry: Mapping[str, Any], repository_root: Path) -> bool:
    """Verify declared registry paths and hashes against canonical local files."""
    root = repository_root.resolve()
    sources = registry.get("source_contracts") or {}
    bindings = (
        (
            "objective", "objective_sha256",
            "config/ndx_portfolio_objective_v1.yaml",
        ),
        (
            "dynamic_walkforward", "dynamic_walkforward_sha256",
            "config/ndx_dynamic_walkforward_v1.yaml",
        ),
        (
            "selector_policy_module", "selector_policy_module_sha256",
            "backtest/ndx_dynamic_candidate_policy.py",
        ),
    )
    try:
        for section, hash_key, canonical_relative_path in bindings:
            declared = sources.get(section) or {}
            if declared.get("path") != canonical_relative_path:
                return False
            path = (root / canonical_relative_path).resolve()
            path.relative_to(root)
            digest = str(sources.get(hash_key) or "").lower()
            if not path.is_file() or len(digest) != 64 or sha256_file(path) != digest:
                return False
    except (AttributeError, OSError, ValueError):
        return False
    return True


def verify_observed_session_calendar_manifest(
    manifest_path: Path, repository_root: Path,
) -> dict[str, Any]:
    """Rebuild the canonical observed-session proof from its immutable artifacts."""
    root = repository_root.resolve()
    expected_directory = (
        root / "data/cache/research/ndx_observed_us_session_calendar_v1"
    ).resolve()
    expected_manifest = (expected_directory / "manifest.json").resolve()
    expected_ledger = (expected_directory / "sessions.jsonl").resolve()
    expected_projection = (expected_directory / "sessions.csv").resolve()
    expected_engine = (root / "backtest/ndx_observed_session_calendar.py").resolve()
    expected_runner = (root / "scripts/ndx_observed_session_calendar.py").resolve()
    expected_sources = {
        "QQQ": (root / "data/cache/QQQ.csv").resolve(),
        "SPY": (root / "data/cache/SPY.csv").resolve(),
    }
    path = manifest_path.resolve()
    evidence: dict[str, Any] = {
        "path": path.as_posix(),
        "verified": False,
        "manifest_sha256": sha256_file(path) if path.is_file() else None,
        "ledger_sha256": None,
        "projection_sha256": None,
        "latest_session_date": None,
        "session_count": 0,
        "prospective_observed_session_count": 0,
        "decision_eligible_session_count": 0,
        "error": None,
    }
    try:
        if path != expected_manifest or not path.is_file():
            raise ValueError("observed-session calendar manifest path is not canonical")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("observed-session calendar manifest is not an object")
        required_values = {
            "schema_version": 1,
            "manifest_type": "ndx_observed_us_session_calendar",
            "status": "OBSERVED_SESSION_CALENDAR_CURRENT",
            "calendar_scope": "OBSERVED_COMMON_QQQ_REFERENCE_OHLC_ONLY",
            "prospective_start_date": "2026-10-01",
            "timezone": "America/New_York",
            "open_time_policy": "NOMINAL_REGULAR_SESSION_09_30_NEW_YORK",
            "close_time_policy": "CONSERVATIVE_REGULAR_SESSION_COMPLETION_BOUNDARY_16_00_NEW_YORK",
            "actual_early_close_timestamp_asserted": False,
            "future_or_in_progress_sessions_included": False,
            "append_only_ledger": True,
            "retrospective_backfill_allowed": False,
            "bootstrap_history_counts_as_fresh_evidence": False,
            "source_history_revision_allowed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "state_changed": False,
            "broker_snapshot_changed": False,
            "today_advice_changed": False,
            "order_creation_allowed": False,
        }
        if any(manifest.get(key) != value for key, value in required_values.items()):
            raise ValueError("observed-session calendar safety contract changed")
        if manifest.get("missed_multiple_session_action") != "FAIL_CLOSED_REQUIRE_NEW_REVIEWED_CALENDAR_VERSION":
            raise ValueError("observed-session calendar no-backfill action changed")

        inputs = manifest.get("inputs")
        if not isinstance(inputs, Mapping) or set(inputs) != {"sources", "engine", "runner"}:
            raise ValueError("observed-session calendar input schema changed")
        source_entries = inputs.get("sources")
        if not isinstance(source_entries, list) or [row.get("ticker") for row in source_entries] != ["QQQ", "SPY"]:
            raise ValueError("observed-session calendar source set changed")
        source_rows: dict[str, dict[str, Any]] = {}
        for item in source_entries:
            if not isinstance(item, Mapping):
                raise ValueError("observed-session calendar source entry is invalid")
            ticker = str(item.get("ticker"))
            source_path = Path(str(item.get("path") or "")).resolve()
            if source_path != expected_sources[ticker] or not source_path.is_file():
                raise ValueError(f"observed-session source path is not canonical: {ticker}")
            if item.get("sha256") != sha256_file(source_path):
                raise ValueError(f"observed-session source hash mismatch: {ticker}")
            rows = load_ohlc_rows(source_path, ticker=ticker)
            if (
                int(item.get("rows", -1)) != len(rows)
                or item.get("data_start") != min(rows)
                or item.get("data_end") != max(rows)
            ):
                raise ValueError(f"observed-session source summary mismatch: {ticker}")
            source_rows[ticker] = rows

        for key, expected_path in (("engine", expected_engine), ("runner", expected_runner)):
            item = inputs.get(key)
            if not isinstance(item, Mapping):
                raise ValueError(f"observed-session {key} identity is missing")
            declared_path = Path(str(item.get("path") or "")).resolve()
            if declared_path != expected_path or not declared_path.is_file():
                raise ValueError(f"observed-session {key} path is not canonical")
            if item.get("sha256") != sha256_file(declared_path):
                raise ValueError(f"observed-session {key} hash mismatch")

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, Mapping) or set(artifacts) != {"append_only_ledger", "session_projection"}:
            raise ValueError("observed-session calendar artifact schema changed")
        ledger_item = artifacts.get("append_only_ledger")
        projection_item = artifacts.get("session_projection")
        if not isinstance(ledger_item, Mapping) or not isinstance(projection_item, Mapping):
            raise ValueError("observed-session calendar artifact entry is invalid")
        ledger_path = Path(str(ledger_item.get("path") or "")).resolve()
        projection_path = Path(str(projection_item.get("path") or "")).resolve()
        if ledger_path != expected_ledger or projection_path != expected_projection:
            raise ValueError("observed-session calendar artifact path is not canonical")
        if not ledger_path.is_file() or ledger_item.get("sha256") != sha256_file(ledger_path):
            raise ValueError("observed-session ledger hash mismatch")
        if not projection_path.is_file() or projection_item.get("sha256") != sha256_file(projection_path):
            raise ValueError("observed-session projection hash mismatch")
        if projection_item.get("derived_from_ledger") is not True:
            raise ValueError("observed-session projection is not declared ledger-derived")

        records = load_ledger(ledger_path)
        validate_ledger(
            records,
            tickers=("QQQ", "SPY"),
            prospective_start_date="2026-10-01",
            current_source_rows=source_rows,
        )
        expected_rows = projection_rows(records)
        with projection_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual_rows = list(reader)
            actual_columns = list(reader.fieldnames or ())
        expected_columns = list(expected_rows[0]) if expected_rows else []
        if actual_columns != expected_columns or len(actual_rows) != len(expected_rows):
            raise ValueError("observed-session projection schema or row count changed")
        for actual, expected in zip(actual_rows, expected_rows):
            normalized = {key: "" if value is None else str(value) for key, value in expected.items()}
            if actual != normalized:
                raise ValueError("observed-session projection does not reproduce from ledger")

        session_count = len(records)
        prospective_count = sum(row.get("origin") == PROSPECTIVE_ORIGIN for row in records)
        eligible_count = sum(row.get("decision_eligible") is True for row in records)
        bootstrap_count = sum(row.get("origin") == BOOTSTRAP_ORIGIN for row in records)
        monthly_first = [
            str(row["session_date"])
            for row in expected_rows
            if row["is_first_observed_session_of_month"] is True
        ]
        latest_date = str(records[-1]["session_date"]) if records else None
        latest_hash = str(records[-1]["record_sha256"]) if records else None
        if (
            int(ledger_item.get("rows", -1)) != session_count
            or int(projection_item.get("rows", -1)) != session_count
            or int(manifest.get("session_count", -1)) != session_count
            or int(manifest.get("bootstrap_session_count", -1)) != bootstrap_count
            or int(manifest.get("prospective_observed_session_count", -1)) != prospective_count
            or int(manifest.get("decision_eligible_session_count", -1)) != eligible_count
            or manifest.get("latest_session_date") != latest_date
            or manifest.get("latest_record_sha256") != latest_hash
            or manifest.get("monthly_first_session_dates") != monthly_first
            or int(manifest.get("verified_next_session_link_count", -1)) != max(session_count - 1, 0)
        ):
            raise ValueError("observed-session calendar manifest summary does not reproduce")
        evidence.update({
            "verified": True,
            "ledger_sha256": sha256_file(ledger_path),
            "projection_sha256": sha256_file(projection_path),
            "latest_session_date": latest_date,
            "session_count": session_count,
            "prospective_observed_session_count": prospective_count,
            "decision_eligible_session_count": eligible_count,
            "error": None,
        })
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        evidence["error"] = str(exc)
    return evidence


def verify_original8_control_manifest(
    manifest_path: Path, repository_root: Path,
) -> dict[str, Any]:
    """Rebuild and compare the frozen control from canonical source artifacts."""
    root = repository_root.resolve()
    expected_manifest_path = (
        root / "data/cache/research/ndx_original_8_control_v1/manifest.json"
    ).resolve()
    dynamic_path = (
        root / "data/cache/research/ndx_dynamic_walkforward_v1/manifest.json"
    ).resolve()
    identity_path = (
        root / "data/cache/research/ndx_incumbent_pit_attribution_v1/manifest.json"
    ).resolve()
    path = manifest_path.resolve()
    evidence = {
        "path": path.as_posix(),
        "verified": False,
        "manifest_sha256": sha256_file(path) if path.is_file() else None,
        "definition_sha256": None,
        "error": None,
    }
    try:
        if path != expected_manifest_path or not path.is_file():
            raise ValueError("original-eight control path is not canonical")
        actual = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(actual, dict):
            raise ValueError("original-eight control manifest is not an object")
        inputs = actual.get("inputs") or {}
        if (
            Path(str((inputs.get("dynamic_walkforward_manifest") or {}).get("path") or "")).resolve()
            != dynamic_path
            or Path(str((inputs.get("identity_manifest") or {}).get("path") or "")).resolve()
            != identity_path
        ):
            raise ValueError("original-eight source path binding mismatch")
        rebuilt = build_original8_control(
            root,
            dynamic_manifest_path=dynamic_path,
            identity_manifest_path=identity_path,
        )
        if set(actual) != set(rebuilt):
            raise ValueError("original-eight manifest keys mismatch")
        actual_comparable = dict(actual)
        rebuilt_comparable = dict(rebuilt)
        actual_comparable.pop("generated_at", None)
        rebuilt_comparable.pop("generated_at", None)
        if actual_comparable != rebuilt_comparable:
            raise ValueError("original-eight manifest does not reproduce from canonical inputs")
        definition = actual.get("definition") or {}
        if canonical_sha256(definition) != actual.get("definition_sha256"):
            raise ValueError("original-eight definition hash mismatch")
        evidence.update({
            "verified": True,
            "definition_sha256": actual["definition_sha256"],
            "security_count": len(definition.get("securities") or []),
            "broker_current_overlay_included": actual.get("broker_current_overlay_included"),
            "source_state_sha256": actual.get("source_state_sha256"),
            "error": None,
        })
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        evidence["error"] = str(exc)
    return evidence


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
