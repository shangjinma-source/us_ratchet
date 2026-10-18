"""Checkpointed research batch for conditional whole-lot path repair.

The input is the immutable, verified 323-row equal-weight schedule-extension
run.  This module does not search candidates or weights.  It copies 280 paths
whose rebalance actions already pass the fixed risk checks and applies the one
predeclared floor/ceil execution repair to the other 43 paths.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from backtest import ndx_equal_weight_schedule_extension_runner as source_runner
from backtest.ndx_whole_lot_repair_path import (
    simulate_conditional_whole_lot_repair_path,
)


SOURCE_OUTPUT_RELATIVE = Path("data/cache/research/eqcad_v1")
OUTPUT_RELATIVE = Path("data/cache/research/eqrepair_v1")
SOURCE_FINGERPRINT = (
    "00f99a002b82735af64b9e933d63f54499917e0adb370f0692e1ec9b73e1eabd"
)
SOURCE_FILE_HASHES = {
    "manifest.json": "23385796fa3e96b5ecf53609cd2b6e0e043ad29d66cc3913aef3de25b0c85d56",
    "plan.json": "120907cd58bee5fe110b57c6edcc262b3184035cfd630d1414cc5f1083223acd",
    "checkpoint_index.json": "8dc1ac8c834030b41ac1717ee7a464fa470bba7261b53ca63a8eb099f4378f2a",
    "results.json": "ce77907f6ca4ed943ee198295af6922b8248aafabdb56040009abca2bbae962b",
}
EXPECTED_COUNTS = {
    "total": 323,
    "CONTROL_EXACT_REUSE": 280,
    "CONDITIONAL_REPAIR": 43,
}
MODULE_RELATIVE = Path("backtest/ndx_conditional_repair_batch.py")
SCRIPT_RELATIVE = Path("scripts/ndx_conditional_repair_batch.py")
REPAIR_PATH_RELATIVE = Path("backtest/ndx_whole_lot_repair_path.py")
REPAIR_KERNEL_RELATIVE = Path("backtest/ndx_whole_lot_repair_diagnostic.py")
SOURCE_RUNNER_RELATIVE = Path(
    "backtest/ndx_equal_weight_schedule_extension_runner.py"
)


class NdxConditionalRepairBatchError(ValueError):
    """Raised when source lineage or a batch artifact fails closed."""


def _sha256(raw: bytes) -> str:
    return source_runner._sha256(raw)


def _canonical_sha256(value: Any) -> str:
    return source_runner._canonical_sha256(value)


def _json_bytes(value: Any) -> bytes:
    return source_runner._json_bytes(value)


def _read_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxConditionalRepairBatchError(f"cannot read {label}") from exc
    return raw, value


def _source_role(result: Mapping[str, Any]) -> str:
    after = result.get("continued_schedule_a")
    if not isinstance(after, Mapping):
        raise NdxConditionalRepairBatchError("source continued path is missing")
    schedule_dates = after.get("schedule_dates")
    audit = after.get("daily_risk_audit")
    if (
        not isinstance(schedule_dates, list)
        or len(schedule_dates) != len(set(schedule_dates))
        or not isinstance(audit, Mapping)
        or not isinstance(audit.get("failure_sessions"), list)
    ):
        raise NdxConditionalRepairBatchError("source continued path is invalid")
    schedule = set(schedule_dates)
    failures_on_rebalance = []
    for failure in audit["failure_sessions"]:
        if (
            not isinstance(failure, Mapping)
            or not isinstance(failure.get("session_date"), str)
            or not isinstance(failure.get("failure_reasons"), list)
        ):
            raise NdxConditionalRepairBatchError("source failure session is invalid")
        if failure["session_date"] in schedule:
            failures_on_rebalance.append(failure["session_date"])
    return "CONDITIONAL_REPAIR" if failures_on_rebalance else "CONTROL_EXACT_REUSE"


def _canonical_source_run(repository_root: Path, source_output_root: Path) -> Path:
    expected = (repository_root / SOURCE_OUTPUT_RELATIVE).resolve()
    if source_output_root.resolve() != expected:
        raise NdxConditionalRepairBatchError("source output root is not canonical")
    run_dir = expected / "runs" / SOURCE_FINGERPRINT
    if not run_dir.is_dir():
        raise NdxConditionalRepairBatchError("canonical source fingerprint is missing")
    extra_runs = [path.name for path in (expected / "runs").iterdir() if path.is_dir()]
    if extra_runs != [SOURCE_FINGERPRINT]:
        raise NdxConditionalRepairBatchError("canonical source run set changed")
    return run_dir


def _resolve_output_root(repository_root: Path, output_root: str | Path | None) -> Path:
    output = (
        Path(output_root).resolve()
        if output_root is not None
        else (repository_root / OUTPUT_RELATIVE).resolve()
    )
    try:
        output.relative_to((repository_root / "data/cache/research").resolve())
    except ValueError as exc:
        raise NdxConditionalRepairBatchError(
            "output root is outside the research namespace"
        ) from exc
    return output


def build_conditional_repair_plan(
    *,
    repository_root: str | Path,
    source_output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the canonical 323-row source once and build a fixed batch plan."""

    root = Path(repository_root).resolve()
    source_root = (
        Path(source_output_root).resolve()
        if source_output_root is not None
        else root / SOURCE_OUTPUT_RELATIVE
    )
    run_dir = _canonical_source_run(root, source_root)
    code_paths = {
        "batch_module": root / MODULE_RELATIVE,
        "batch_cli": root / SCRIPT_RELATIVE,
        "repair_path": root / REPAIR_PATH_RELATIVE,
        "repair_kernel": root / REPAIR_KERNEL_RELATIVE,
        "source_runner": root / SOURCE_RUNNER_RELATIVE,
    }
    code_before = {
        key: {"path": path.resolve().as_posix(), "sha256": _sha256(path.read_bytes())}
        for key, path in code_paths.items()
    }
    verified = source_runner.verify_locked_replay_output(
        repository_root=root,
        output_root=source_root,
    )
    if (
        verified.get("status") != "VERIFIED_COMPLETE"
        or verified.get("verified_candidate_rows") != EXPECTED_COUNTS["total"]
        or verified.get("verified_track_count") != 2
        or verified.get("plan_fingerprint") != SOURCE_FINGERPRINT
    ):
        raise NdxConditionalRepairBatchError("canonical source verifier did not pass")

    source_raw: dict[str, bytes] = {}
    source_values: dict[str, Any] = {}
    for filename, expected_hash in SOURCE_FILE_HASHES.items():
        raw, value = _read_json(run_dir / filename, f"source {filename}")
        if _sha256(raw) != expected_hash:
            raise NdxConditionalRepairBatchError(
                f"canonical source {filename} hash changed"
            )
        source_raw[filename] = raw
        source_values[filename] = value
    source_plan = source_values["plan.json"]
    source_manifest = source_values["manifest.json"]
    source_index = source_values["checkpoint_index.json"]
    source_results = source_values["results.json"]
    if (
        not isinstance(source_plan, Mapping)
        or source_plan.get("plan_fingerprint") != SOURCE_FINGERPRINT
        or not isinstance(source_index, list)
        or len(source_index) != EXPECTED_COUNTS["total"]
        or not isinstance(source_results, Mapping)
        or source_results.get("status") != "COMPLETE"
        or not isinstance(source_results.get("results"), list)
        or len(source_results["results"]) != EXPECTED_COUNTS["total"]
        or not isinstance(source_manifest, Mapping)
        or source_manifest.get("status") != "COMPLETE"
        or source_manifest.get("checkpoint_index", {}).get("sha256")
        != SOURCE_FILE_HASHES["checkpoint_index.json"]
        or source_manifest.get("full_results", {}).get("sha256")
        != SOURCE_FILE_HASHES["results.json"]
    ):
        raise NdxConditionalRepairBatchError("canonical source bundle changed")
    source_candidates = {
        candidate["candidate_key"]: candidate
        for group in source_plan.get("groups", [])
        for candidate in group.get("candidates", [])
    }
    results_by_key = {
        result["candidate_key"]: result for result in source_results["results"]
    }
    index_by_key = {row["candidate_key"]: row for row in source_index}
    if not (
        len(source_candidates)
        == len(results_by_key)
        == len(index_by_key)
        == EXPECTED_COUNTS["total"]
        and set(source_candidates) == set(results_by_key) == set(index_by_key)
    ):
        raise NdxConditionalRepairBatchError("canonical source identities changed")

    candidates = []
    roles: Counter[str] = Counter()
    for key in sorted(source_candidates):
        source_candidate = source_candidates[key]
        result = results_by_key[key]
        index_row = index_by_key[key]
        checkpoint_path = Path(str(index_row.get("path") or "")).resolve()
        expected_checkpoint = (
            run_dir
            / "checkpoints"
            / source_candidate["universe_track"]
            / f"{key}.json"
        ).resolve()
        if (
            index_row.get("status") != "COMPLETED"
            or checkpoint_path != expected_checkpoint
            or not isinstance(index_row.get("sha256"), str)
            or len(index_row["sha256"]) != 64
        ):
            raise NdxConditionalRepairBatchError("source checkpoint index changed")
        checkpoint_raw = checkpoint_path.read_bytes()
        if _sha256(checkpoint_raw) != index_row["sha256"]:
            raise NdxConditionalRepairBatchError("source checkpoint bytes changed")
        checkpoint = source_runner.verify_candidate_checkpoint(
            checkpoint_path,
            plan_fingerprint=SOURCE_FINGERPRINT,
            candidate=source_candidate,
        )
        if checkpoint_path.read_bytes() != checkpoint_raw:
            raise NdxConditionalRepairBatchError(
                "source checkpoint changed during verification"
            )
        if checkpoint["result"] != result:
            raise NdxConditionalRepairBatchError(
                "source results and checkpoint disagree"
            )
        role = _source_role(result)
        roles[role] += 1
        candidates.append(
            {
                "candidate_key": key,
                "candidate_identity_sha256": result["candidate_identity_sha256"],
                "universe_track": result["source_coordinate"]["universe_track"],
                "holding_count": result["holding_count"],
                "processing_role": role,
                "source_checkpoint": {
                    "path": checkpoint_path.as_posix(),
                    "sha256": index_row["sha256"],
                },
                "source_result_sha256": _canonical_sha256(result),
                "source_a_summary": result["continued_schedule_a"]["summary"],
                "source_a_daily_risk_audit_sha256": _canonical_sha256(
                    result["continued_schedule_a"]["daily_risk_audit"]
                ),
                "source_candidate": source_candidate,
            }
        )
    if dict(roles) != {
        "CONTROL_EXACT_REUSE": EXPECTED_COUNTS["CONTROL_EXACT_REUSE"],
        "CONDITIONAL_REPAIR": EXPECTED_COUNTS["CONDITIONAL_REPAIR"],
    }:
        raise NdxConditionalRepairBatchError("canonical repair/control split changed")
    for filename, raw in source_raw.items():
        if (run_dir / filename).read_bytes() != raw:
            raise NdxConditionalRepairBatchError(
                f"canonical source {filename} changed during plan construction"
            )
    code_after = {
        key: _sha256(path.read_bytes()) for key, path in code_paths.items()
    }
    if any(code_before[key]["sha256"] != code_after[key] for key in code_before):
        raise NdxConditionalRepairBatchError("batch source code changed during capture")
    payload = {
        "schema_version": 1,
        "plan_type": "ndx_conditional_whole_lot_repair_batch",
        "status": "LOCKED_HISTORICAL_RESEARCH_PLAN",
        "research_track": "portfolio_optimization_execution_diagnostic",
        "source_plan_fingerprint": SOURCE_FINGERPRINT,
        "source_verifier_status": "VERIFIED_COMPLETE",
        "source_files": {
            filename: {
                "path": (run_dir / filename).resolve().as_posix(),
                "sha256": expected_hash,
            }
            for filename, expected_hash in SOURCE_FILE_HASHES.items()
        },
        "code_bindings": code_before,
        "counts": dict(EXPECTED_COUNTS),
        "max_repair_evaluations_per_rebalance": 262_144,
        "candidates": candidates,
        "candidate_set_or_weight_search_run": False,
        "rebalance_cadence_changed": False,
        "risk_thresholds_changed": False,
        "portfolio_cash_changed": False,
        "transaction_cost_changed": False,
        "cross_track_or_evaluator_ranking_allowed": False,
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    return {**payload, "plan_fingerprint": _canonical_sha256(payload)}


def _validate_plan(plan: Mapping[str, Any]) -> None:
    payload = dict(plan)
    claimed = payload.pop("plan_fingerprint", None)
    if (
        claimed != _canonical_sha256(payload)
        or plan.get("schema_version") != 1
        or plan.get("plan_type") != "ndx_conditional_whole_lot_repair_batch"
        or plan.get("status") != "LOCKED_HISTORICAL_RESEARCH_PLAN"
        or plan.get("research_track")
        != "portfolio_optimization_execution_diagnostic"
        or plan.get("source_plan_fingerprint") != SOURCE_FINGERPRINT
        or plan.get("source_verifier_status") != "VERIFIED_COMPLETE"
        or plan.get("counts") != EXPECTED_COUNTS
        or plan.get("max_repair_evaluations_per_rebalance") != 262_144
        or any(
            plan.get(field) is not False
            for field in (
                "candidate_set_or_weight_search_run",
                "rebalance_cadence_changed",
                "risk_thresholds_changed",
                "portfolio_cash_changed",
                "transaction_cost_changed",
                "cross_track_or_evaluator_ranking_allowed",
                "fresh_oos_consumed",
                "admission_claimed",
                "promotion_allowed",
                "live_mutation_allowed",
                "order_creation_allowed",
            )
        )
    ):
        raise NdxConditionalRepairBatchError("conditional repair plan changed")
    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != EXPECTED_COUNTS["total"]:
        raise NdxConditionalRepairBatchError("conditional repair plan coverage changed")
    keys = [candidate.get("candidate_key") for candidate in candidates]
    roles = Counter(candidate.get("processing_role") for candidate in candidates)
    if len(set(keys)) != len(keys) or roles != Counter(
        {
            "CONTROL_EXACT_REUSE": EXPECTED_COUNTS["CONTROL_EXACT_REUSE"],
            "CONDITIONAL_REPAIR": EXPECTED_COUNTS["CONDITIONAL_REPAIR"],
        }
    ):
        raise NdxConditionalRepairBatchError("conditional repair plan identities changed")


def _load_source_checkpoint(candidate: Mapping[str, Any]) -> dict[str, Any]:
    descriptor = candidate["source_checkpoint"]
    path = Path(descriptor["path"]).resolve()
    raw = path.read_bytes()
    if _sha256(raw) != descriptor["sha256"]:
        raise NdxConditionalRepairBatchError("source checkpoint hash changed")
    checkpoint = source_runner.verify_candidate_checkpoint(
        path,
        plan_fingerprint=SOURCE_FINGERPRINT,
        candidate=candidate["source_candidate"],
    )
    if path.read_bytes() != raw:
        raise NdxConditionalRepairBatchError(
            "source checkpoint changed during candidate verification"
        )
    source_result = checkpoint["result"]
    if (
        source_result.get("candidate_key") != candidate["candidate_key"]
        or source_result.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or _canonical_sha256(source_result) != candidate["source_result_sha256"]
        or source_result["continued_schedule_a"]["summary"]
        != candidate["source_a_summary"]
        or _canonical_sha256(
            source_result["continued_schedule_a"]["daily_risk_audit"]
        )
        != candidate["source_a_daily_risk_audit_sha256"]
        or _source_role(source_result) != candidate["processing_role"]
    ):
        raise NdxConditionalRepairBatchError("source candidate boundary changed")
    return checkpoint


def _capture_to_path_inputs(
    capture: Mapping[str, Any], candidate: Mapping[str, Any]
) -> tuple[pd.DataFrame, list[tuple[pd.Timestamp, dict[str, float]]], dict[str, Any]]:
    tickers = list(candidate["tickers"])
    dates: list[pd.Timestamp] = []
    values: list[list[float]] = []
    for row in capture["price_rows"]:
        raw_date = row["session_date"]
        parsed = date.fromisoformat(raw_date)
        if parsed.isoformat() != raw_date or list(row["closes"]) != tickers:
            raise NdxConditionalRepairBatchError("sealed price capture changed")
        dates.append(pd.Timestamp(parsed))
        values.append([float(row["closes"][ticker]) for ticker in tickers])
    prices = pd.DataFrame(values, index=dates, columns=tickers)
    schedule = []
    for row in capture["original_schedule"]:
        raw_date = row["session_date"]
        parsed = date.fromisoformat(raw_date)
        if parsed.isoformat() != raw_date or list(row["weights"]) != tickers:
            raise NdxConditionalRepairBatchError("sealed schedule capture changed")
        schedule.append(
            (
                pd.Timestamp(parsed),
                {ticker: float(row["weights"][ticker]) for ticker in tickers},
            )
        )
    extended = source_runner.extend_equal_weight_schedule_to_path_end(
        prices, schedule, tickers=tickers, cadence_sessions=21
    )
    return prices, extended, dict(capture["execution_contract"])


def rebuild_candidate_result(
    candidate: Mapping[str, Any], source_checkpoint: Mapping[str, Any]
) -> dict[str, Any]:
    """Rebuild one C path from the exact sealed source checkpoint bytes."""

    source_result = source_checkpoint["result"]
    rebuilt_source = source_runner.rebuild_result_from_capture(
        source_checkpoint["capture"], candidate["source_candidate"]
    )
    if rebuilt_source != source_result:
        raise NdxConditionalRepairBatchError("sealed source result does not rebuild")
    prices, schedule, contract = _capture_to_path_inputs(
        source_checkpoint["capture"], candidate["source_candidate"]
    )
    conditional, ledger = simulate_conditional_whole_lot_repair_path(
        prices,
        schedule,
        max_repair_evaluations=262_144,
        **contract,
    )
    if not conditional["search_complete"] or conditional["summary"] is None:
        raise NdxConditionalRepairBatchError(
            "conditional repair path did not complete its local searches"
        )
    source_a = source_result["continued_schedule_a"]
    if candidate["processing_role"] == "CONTROL_EXACT_REUSE":
        if (
            conditional["repair_invocation_count"] != 0
            or conditional["summary"] != source_a["summary"]
            or conditional["daily_risk_audit"] != source_a["daily_risk_audit"]
            or conditional["legacy_no_trigger_path_reused_exactly"] is not True
        ):
            raise NdxConditionalRepairBatchError(
                "control path no longer exactly reproduces source A"
            )
    elif candidate["processing_role"] == "CONDITIONAL_REPAIR":
        if conditional["repair_invocation_count"] <= 0:
            raise NdxConditionalRepairBatchError(
                "repair-designated path did not invoke the repair"
            )
    else:
        raise NdxConditionalRepairBatchError("candidate processing role changed")
    return {
        "candidate_key": candidate["candidate_key"],
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "universe_track": candidate["universe_track"],
        "holding_count": candidate["holding_count"],
        "processing_role": candidate["processing_role"],
        "source_checkpoint_sha256": candidate["source_checkpoint"]["sha256"],
        "source_result_sha256": candidate["source_result_sha256"],
        "source_a_summary": source_a["summary"],
        "source_a_daily_risk_audit": source_a["daily_risk_audit"],
        "conditional_c": conditional,
        "conditional_c_ledger": ledger.to_dict("records"),
        "candidate_set_or_weight_search_run": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def _checkpoint_payload(
    *, plan_fingerprint: str, candidate: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "checkpoint_type": "ndx_conditional_whole_lot_repair_candidate",
        "status": "COMPLETED",
        "plan_fingerprint": plan_fingerprint,
        "candidate_key": candidate["candidate_key"],
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "processing_role": candidate["processing_role"],
        "source_checkpoint": candidate["source_checkpoint"],
        "result": dict(result),
        "candidate_set_or_weight_search_run": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    return {**payload, "checkpoint_sha256": _canonical_sha256(payload)}


def _checkpoint_path(run_dir: Path, candidate: Mapping[str, Any]) -> Path:
    return (
        run_dir
        / "checkpoints"
        / candidate["universe_track"]
        / f"{candidate['candidate_key']}.json"
    )


def verify_candidate_checkpoint(
    checkpoint_path: str | Path,
    *,
    plan_fingerprint: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    path = Path(checkpoint_path).resolve()
    raw, checkpoint = _read_json(path, "conditional repair checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise NdxConditionalRepairBatchError("candidate checkpoint is invalid")
    payload = dict(checkpoint)
    claimed = payload.pop("checkpoint_sha256", None)
    expected_keys = {
        "schema_version", "checkpoint_type", "status", "plan_fingerprint",
        "candidate_key", "candidate_identity_sha256", "processing_role",
        "source_checkpoint", "result", "candidate_set_or_weight_search_run",
        "admission_claimed", "promotion_allowed", "live_mutation_allowed",
        "order_creation_allowed", "checkpoint_sha256",
    }
    if (
        set(checkpoint) != expected_keys
        or claimed != _canonical_sha256(payload)
        or checkpoint.get("schema_version") != 1
        or checkpoint.get("checkpoint_type")
        != "ndx_conditional_whole_lot_repair_candidate"
        or checkpoint.get("status") != "COMPLETED"
        or checkpoint.get("plan_fingerprint") != plan_fingerprint
        or checkpoint.get("candidate_key") != candidate["candidate_key"]
        or checkpoint.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or checkpoint.get("processing_role") != candidate["processing_role"]
        or checkpoint.get("source_checkpoint") != candidate["source_checkpoint"]
        or any(
            checkpoint.get(field) is not False
            for field in (
                "candidate_set_or_weight_search_run", "admission_claimed",
                "promotion_allowed", "live_mutation_allowed",
                "order_creation_allowed",
            )
        )
    ):
        raise NdxConditionalRepairBatchError("candidate checkpoint contract changed")
    source_checkpoint = _load_source_checkpoint(candidate)
    rebuilt = rebuild_candidate_result(candidate, source_checkpoint)
    if checkpoint["result"] != rebuilt or path.read_bytes() != raw:
        raise NdxConditionalRepairBatchError(
            "candidate checkpoint economic result does not rebuild"
        )
    return dict(checkpoint)


def _result_summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(result["conditional_c"]["status"] for result in results)
    return {
        "candidate_rows": len(results),
        "control_exact_reuse_rows": sum(
            result["processing_role"] == "CONTROL_EXACT_REUSE" for result in results
        ),
        "conditional_repair_rows": sum(
            result["processing_role"] == "CONDITIONAL_REPAIR" for result in results
        ),
        "conditional_c_execution_eligible_rows": sum(
            result["conditional_c"]["execution_eligible"] for result in results
        ),
        "successful_repair_events": sum(
            result["conditional_c"]["successful_repair_count"] for result in results
        ),
        "unresolved_rebalance_events": sum(
            result["conditional_c"]["unresolved_rebalance_count"] for result in results
        ),
        "conditional_c_status_counts": dict(sorted(status_counts.items())),
        "ranking_or_winner_selected": False,
    }


def _build_run_state_payloads(
    run_dir: Path,
    *,
    plan: Mapping[str, Any],
    completed: Mapping[str, Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the exact run-state bytes without mutating the filesystem."""

    checkpoint_rows = []
    for candidate in plan["candidates"]:
        path = _checkpoint_path(run_dir, candidate)
        checkpoint_rows.append(
            {
                "candidate_key": candidate["candidate_key"],
                "universe_track": candidate["universe_track"],
                "processing_role": candidate["processing_role"],
                "status": "COMPLETED" if candidate["candidate_key"] in completed else "NOT_COMPLETED",
                "path": path.resolve().as_posix(),
                "sha256": _sha256(path.read_bytes()) if path.is_file() else None,
            }
        )
    index_raw = _json_bytes(checkpoint_rows)
    complete = len(completed) == EXPECTED_COUNTS["total"] and not failures
    results_descriptor = None
    result_payload = None
    result_raw = None
    if complete:
        ordered_results = [
            completed[candidate["candidate_key"]]["result"]
            for candidate in plan["candidates"]
        ]
        result_payload = {
            "schema_version": 1,
            "result_type": "ndx_conditional_whole_lot_repair_full_report",
            "status": "COMPLETE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "summary": _result_summary(ordered_results),
            "results": ordered_results,
            "candidate_set_or_weight_search_run": False,
            "cross_track_or_evaluator_ranking_performed": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        result_raw = _json_bytes(result_payload)
        result_path = run_dir / "results.json"
        results_descriptor = {
            "path": result_path.resolve().as_posix(),
            "sha256": _sha256(result_raw),
            "rows": len(ordered_results),
        }
    manifest_payload = {
        "schema_version": 1,
        "manifest_type": "ndx_conditional_whole_lot_repair_batch",
        "status": "COMPLETE" if complete else "PARTIAL_OR_FAILED",
        "research_track": "portfolio_optimization_execution_diagnostic",
        "plan_fingerprint": plan["plan_fingerprint"],
        "planned_candidate_rows": EXPECTED_COUNTS["total"],
        "completed_candidate_rows": len(completed),
        "remaining_candidate_rows": EXPECTED_COUNTS["total"] - len(completed),
        "failed_candidate_count": len(failures),
        "failures": list(failures),
        "checkpoint_index": {
            "path": (run_dir / "checkpoint_index.json").resolve().as_posix(),
            "sha256": _sha256(index_raw),
            "rows": len(checkpoint_rows),
        },
        "full_results": results_descriptor,
        "candidate_set_or_weight_search_run": False,
        "cross_track_or_evaluator_ranking_performed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    manifest = {
        **manifest_payload,
        "manifest_sha256": _canonical_sha256(manifest_payload),
    }
    return {
        "checkpoint_index": checkpoint_rows,
        "checkpoint_index_raw": index_raw,
        "results": result_payload,
        "results_raw": result_raw,
        "manifest": manifest,
        "manifest_raw": _json_bytes(manifest),
    }


def _write_run_state(
    run_dir: Path,
    *,
    plan: Mapping[str, Any],
    completed: Mapping[str, Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(completed) == EXPECTED_COUNTS["total"] and not failures:
        _assert_plan_bindings_current(plan)
    state = _build_run_state_payloads(
        run_dir, plan=plan, completed=completed, failures=failures
    )
    source_runner._atomic_write(
        run_dir / "checkpoint_index.json", state["checkpoint_index_raw"]
    )
    if state["results_raw"] is not None:
        result_path = run_dir / "results.json"
        if result_path.exists() and result_path.read_bytes() != state["results_raw"]:
            raise NdxConditionalRepairBatchError("immutable full result collision")
        if not result_path.exists():
            source_runner._atomic_write(result_path, state["results_raw"])
    source_runner._atomic_write(run_dir / "manifest.json", state["manifest_raw"])
    return state["manifest"]


def _assert_plan_bindings_current(plan: Mapping[str, Any]) -> None:
    """Recheck the captured code and source bytes before publishing COMPLETE."""

    for section in ("source_files", "code_bindings"):
        descriptors = plan.get(section)
        if not isinstance(descriptors, Mapping) or not descriptors:
            raise NdxConditionalRepairBatchError(f"plan {section} changed")
        for descriptor in descriptors.values():
            if (
                not isinstance(descriptor, Mapping)
                or set(descriptor) != {"path", "sha256"}
                or not isinstance(descriptor.get("path"), str)
                or not isinstance(descriptor.get("sha256"), str)
            ):
                raise NdxConditionalRepairBatchError(f"plan {section} changed")
            path = Path(descriptor["path"]).resolve()
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise NdxConditionalRepairBatchError(
                    f"plan {section} file is unavailable"
                ) from exc
            if _sha256(raw) != descriptor["sha256"]:
                raise NdxConditionalRepairBatchError(
                    f"plan {section} file changed"
                )


def execute_conditional_repair_batch(
    *,
    repository_root: str | Path,
    output_root: str | Path | None = None,
    resume: bool = False,
    fail_fast: bool = False,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    output = _resolve_output_root(root, output_root)
    if isinstance(max_candidates, bool) or (
        max_candidates is not None
        and (not isinstance(max_candidates, int) or max_candidates <= 0)
    ):
        raise NdxConditionalRepairBatchError("max_candidates must be positive")
    plan = build_conditional_repair_plan(repository_root=root)
    _validate_plan(plan)
    run_dir = output / "runs" / plan["plan_fingerprint"]
    with source_runner._single_instance_lock(run_dir / ".runner.lock"):
        run_dir.mkdir(parents=True, exist_ok=True)
        plan_path = run_dir / "plan.json"
        plan_raw = _json_bytes(plan)
        if plan_path.exists():
            if not resume or plan_path.read_bytes() != plan_raw:
                raise NdxConditionalRepairBatchError(
                    "existing run requires --resume and an identical plan"
                )
        else:
            source_runner._atomic_write(plan_path, plan_raw)
        completed: dict[str, Mapping[str, Any]] = {}
        for candidate in plan["candidates"]:
            path = _checkpoint_path(run_dir, candidate)
            if path.is_file():
                checkpoint = verify_candidate_checkpoint(
                    path,
                    plan_fingerprint=plan["plan_fingerprint"],
                    candidate=candidate,
                )
                completed[candidate["candidate_key"]] = checkpoint
        pending = [
            candidate
            for candidate in plan["candidates"]
            if candidate["candidate_key"] not in completed
        ]
        if max_candidates is not None:
            pending = pending[:max_candidates]
        failures: list[dict[str, Any]] = []
        for candidate in pending:
            try:
                source_checkpoint = _load_source_checkpoint(candidate)
                result = rebuild_candidate_result(candidate, source_checkpoint)
                checkpoint = _checkpoint_payload(
                    plan_fingerprint=plan["plan_fingerprint"],
                    candidate=candidate,
                    result=result,
                )
                path = _checkpoint_path(run_dir, candidate)
                raw = _json_bytes(checkpoint)
                if path.exists():
                    raise NdxConditionalRepairBatchError(
                        "candidate checkpoint unexpectedly exists"
                    )
                source_runner._atomic_write(path, raw)
                verified = verify_candidate_checkpoint(
                    path,
                    plan_fingerprint=plan["plan_fingerprint"],
                    candidate=candidate,
                )
                completed[candidate["candidate_key"]] = verified
            except Exception as exc:
                failures.append(
                    {
                        "candidate_key": candidate["candidate_key"],
                        "reason": f"{type(exc).__name__}:{exc}",
                    }
                )
                if fail_fast:
                    break
            _write_run_state(
                run_dir, plan=plan, completed=completed, failures=failures
            )
        return _write_run_state(
            run_dir, plan=plan, completed=completed, failures=failures
        )


def verify_conditional_repair_batch(
    *,
    repository_root: str | Path,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    output = _resolve_output_root(root, output_root)
    plan = build_conditional_repair_plan(repository_root=root)
    _validate_plan(plan)
    run_dir = output / "runs" / plan["plan_fingerprint"]
    with source_runner._single_instance_lock(run_dir / ".runner.lock"):
        plan_path = run_dir / "plan.json"
        if not plan_path.is_file() or plan_path.read_bytes() != _json_bytes(plan):
            raise NdxConditionalRepairBatchError("published plan changed")
        expected_checkpoint_paths = {
            _checkpoint_path(run_dir, candidate).resolve()
            for candidate in plan["candidates"]
        }
        actual_checkpoint_paths = (
            {path.resolve() for path in (run_dir / "checkpoints").rglob("*.json")}
            if (run_dir / "checkpoints").is_dir()
            else set()
        )
        if actual_checkpoint_paths != expected_checkpoint_paths:
            raise NdxConditionalRepairBatchError(
                "complete output does not contain exactly 323 canonical checkpoints"
            )
        completed = {}
        for candidate in plan["candidates"]:
            checkpoint = verify_candidate_checkpoint(
                _checkpoint_path(run_dir, candidate),
                plan_fingerprint=plan["plan_fingerprint"],
                candidate=candidate,
            )
            completed[candidate["candidate_key"]] = checkpoint
        expected = _build_run_state_payloads(
            run_dir, plan=plan, completed=completed, failures=[]
        )
        existing = {
            "checkpoint_index_raw": (run_dir / "checkpoint_index.json").read_bytes(),
            "results_raw": (run_dir / "results.json").read_bytes(),
            "manifest_raw": (run_dir / "manifest.json").read_bytes(),
        }
        for field, raw in existing.items():
            if raw != expected[field]:
                raise NdxConditionalRepairBatchError(
                    f"published {field.removesuffix('_raw')} does not rebuild"
                )
        _assert_plan_bindings_current(plan)
    return {
        "status": "VERIFIED_COMPLETE",
        "plan_fingerprint": plan["plan_fingerprint"],
        "verified_candidate_rows": len(completed),
        "source_verifier_invocations": 1,
        "economic_candidate_rebuilds": len(completed),
        "candidate_set_or_weight_search_run": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


__all__ = [
    "NdxConditionalRepairBatchError",
    "OUTPUT_RELATIVE",
    "build_conditional_repair_plan",
    "execute_conditional_repair_batch",
    "rebuild_candidate_result",
    "verify_candidate_checkpoint",
    "verify_conditional_repair_batch",
]
