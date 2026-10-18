r"""Inventory $5k-trained dynamic-k candidates for a new $25k whole-lot replay.

This pass reuses immutable historical return metrics and never relabels a
candidate as $25k-executable.  It emits a bounded, multifrontier replay set;
the next phase must run each selected weight path through the $25k execution
engine before any frontier is recomputed.

PowerShell:
    python -B scripts\ndx_cardinality_capital_sensitivity.py
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_capital_sensitivity import (
    WHOLE_LOT_FAILURE,
    capital_replay_reason,
    evaluation_semantics_payload,
    evaluation_semantics_sha256,
    failure_codes,
    is_user_preference,
    noncapital_constraints_passed,
)
from core.helpers import atomic_write_text, resolve
from data.versioning import file_sha256


OUTPUT_FIELDS = (
    "source_batch", "source_manifest", "universe_track", "selection_date",
    "holding_count", "portfolio_id", "weight_spec", "tickers", "weights",
    "return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90",
    "paired_return_p50_vs_incumbent", "paired_return_p10_vs_incumbent",
    "paired_drawdown_cost_p50_vs_incumbent", "paired_drawdown_cost_p90_vs_incumbent",
    "return_p50_vs_012922", "return_p10_vs_012922",
    "max_drawdown_p50_vs_012922", "max_drawdown_p90_vs_012922",
    "target_012922_distance", "turnover", "declared_constraints_passed",
    "constraint_failure_reasons", "portfolio_cash_usd", "minimum_cash_buffer_usd",
    "whole_lot_executable_all_windows", "whole_lot_constraints_preserved_all_days",
    "whole_lot_min_cash_usd", "whole_lot_path_return_net",
    "whole_lot_path_max_drawdown", "whole_lot_rebalance_trace_sha256",
    "search_mode", "capital_replay_frontiers", "capital_replay_reason",
)


def _number(row: dict, key: str, default: float) -> float:
    try:
        value = float(row.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def _compact(row: dict, *, source_batch: str, source_manifest: str,
             source_cash: float, target_cash: float) -> dict:
    out = {field: row.get(field, "") for field in OUTPUT_FIELDS}
    out["source_batch"] = source_batch
    out["source_manifest"] = source_manifest
    out["capital_replay_reason"] = capital_replay_reason(row, source_cash, target_cash)
    out["capital_replay_frontiers"] = ""
    return out


def _dominates(left: dict, right: dict) -> bool:
    pairs = [
        (_number(left, "return_p50", -1e99), _number(right, "return_p50", -1e99), True),
        (_number(left, "return_p10", -1e99), _number(right, "return_p10", -1e99), True),
        (_number(left, "max_drawdown_p50", 1e99), _number(right, "max_drawdown_p50", 1e99), False),
        (_number(left, "max_drawdown_p90", 1e99), _number(right, "max_drawdown_p90", 1e99), False),
        (_number(left, "target_012922_distance", 1e99), _number(right, "target_012922_distance", 1e99), False),
        (_number(left, "turnover", 1e99), _number(right, "turnover", 1e99), False),
    ]
    weak = [a >= b if maximize else a <= b for a, b, maximize in pairs]
    strict = [a > b if maximize else a < b for a, b, maximize in pairs]
    return all(weak) and any(strict)


class CoordinateAccumulator:
    def __init__(self, limit: int, preference: list[str]):
        self.limit = limit
        self.preference = preference
        self.total = 0
        self.source_passed = 0
        self.noncapital_eligible = 0
        self.whole_lot_only_failed = 0
        self.user_preference_rows = 0
        self.top: dict[str, list[dict]] = {
            "RETURN": [], "BAD_TAIL": [], "DRAWDOWN": [], "012922_DISTANCE": [],
        }
        self.pareto_candidates: list[dict] = []
        self.preferences: list[dict] = []

    def _push(self, frontier: str, row: dict) -> None:
        items = self.top[frontier]
        items.append(row)
        keys = {
            "RETURN": lambda x: -_number(x, "return_p50", -1e99),
            "BAD_TAIL": lambda x: -_number(x, "return_p10", -1e99),
            "DRAWDOWN": lambda x: _number(x, "max_drawdown_p90", 1e99),
            "012922_DISTANCE": lambda x: _number(x, "target_012922_distance", 1e99),
        }
        items.sort(key=keys[frontier])
        del items[self.limit:]

    def add(self, raw: dict, compact: dict) -> None:
        self.total += 1
        if str(raw.get("declared_constraints_passed") or "").lower() == "true":
            self.source_passed += 1
        codes = failure_codes(raw)
        if codes == {WHOLE_LOT_FAILURE}:
            self.whole_lot_only_failed += 1
        if not noncapital_constraints_passed(raw):
            return
        self.noncapital_eligible += 1
        for frontier in self.top:
            self._push(frontier, compact)
        if is_user_preference(raw, self.preference):
            self.user_preference_rows += 1
            self.preferences.append(compact)
        self.pareto_candidates.append(compact)

    def finish(self) -> list[dict]:
        selected: dict[tuple[str, str, str, str], dict] = {}

        def add(frontier: str, rows: list[dict]) -> None:
            for rank, row in enumerate(rows, 1):
                key = (
                    str(row.get("portfolio_id")), str(row.get("weight_spec")),
                    str(row.get("tickers")), str(row.get("weights")),
                )
                item = selected.setdefault(key, dict(row))
                tags = {x for x in str(item.get("capital_replay_frontiers") or "").split(";") if x}
                tags.add(frontier)
                item["capital_replay_frontiers"] = ";".join(sorted(tags))
                item[f"{frontier.lower()}_replay_rank"] = rank

        for frontier, rows in self.top.items():
            add(frontier, rows)
        # A complete best-first ordering means a later row cannot dominate an
        # earlier row.  We therefore need retain only the first ``limit``
        # nondominated rows, making the exact shortlist scan O(N * limit)
        # instead of maintaining a potentially large O(N^2) streaming front.
        ordered = sorted(self.pareto_candidates, key=lambda row: (
            -_number(row, "return_p50", -1e99), -_number(row, "return_p10", -1e99),
            _number(row, "max_drawdown_p50", 1e99),
            _number(row, "max_drawdown_p90", 1e99),
            _number(row, "target_012922_distance", 1e99),
            _number(row, "turnover", 1e99),
            str(row.get("portfolio_id") or ""), str(row.get("weight_spec") or ""),
        ))
        pareto: list[dict] = []
        for row in ordered:
            if not any(_dominates(item, row) for item in pareto):
                pareto.append(row)
                if len(pareto) == self.limit:
                    break
        add("PARETO", pareto)
        add("USER_PREFERENCE", self.preferences)
        return list(selected.values())


def _latest_complete_run(root: Path) -> tuple[Path, dict]:
    candidates = []
    for manifest_path in (root / "runs").glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if int(manifest.get("run_completed_job_count") or 0) != int(manifest.get("planned_job_count") or -1):
            continue
        if int(manifest.get("run_failed_job_count") or 0):
            continue
        candidates.append((str(manifest.get("generated_at") or ""), manifest_path, manifest))
    if not candidates:
        raise ValueError(f"no complete runner manifest under {root}")
    _, path, manifest = max(candidates, key=lambda item: item[0])
    return path, manifest


def _candidate_manifests(run_manifest_path: Path, run_manifest: dict) -> list[Path]:
    artifact = (run_manifest.get("artifacts") or {}).get("checkpoint_index") or {}
    checkpoint_index = Path(str(artifact.get("path") or ""))
    if (
        not checkpoint_index.is_absolute()
        or not checkpoint_index.is_file()
        or file_sha256(checkpoint_index) != artifact.get("sha256")
    ):
        raise ValueError(f"checkpoint index artifact mismatch: {run_manifest_path}")
    out = []
    with checkpoint_index.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        if len(rows) != int(artifact.get("rows") or -1):
            raise ValueError(f"checkpoint index row count mismatch: {checkpoint_index}")
        for row in rows:
            if row.get("status") != "COMPLETED":
                raise ValueError(f"complete runner contains non-completed checkpoint: {checkpoint_index}")
            checkpoint = Path(row["checkpoint_path"])
            if (
                not checkpoint.is_absolute()
                or not checkpoint.is_file()
                or file_sha256(checkpoint) != row.get("checkpoint_file_sha256")
            ):
                raise ValueError(f"checkpoint artifact mismatch: {checkpoint}")
            payload = json.loads(checkpoint.read_text(encoding="utf-8"))
            result = Path(payload["result_manifest_path"])
            if (
                payload.get("status") != "COMPLETED"
                or not result.is_absolute()
                or not result.is_file()
                or file_sha256(result) != payload.get("result_manifest_sha256")
            ):
                raise ValueError(f"referenced result manifest is incomplete: {result}")
            out.append(result)
    if len(out) != int(run_manifest.get("planned_job_count") or -1):
        raise ValueError(f"complete runner checkpoint coverage mismatch: {run_manifest_path}")
    return out


def _validate_capital_contract(capital: dict) -> tuple[float, float, float, float]:
    try:
        source_cash = float(capital["source_training_cash_usd"])
        target_cash = float(capital["primary_full_sleeve_cash_usd"])
        buffer = float(capital["minimum_cash_buffer_usd"])
        transaction_cost_bps = float(capital["transaction_cost_bps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("capital contract is incomplete") from exc
    if (
        not all(isfinite(value) for value in (source_cash, target_cash, buffer, transaction_cost_bps))
        or source_cash <= buffer
        or target_cash <= buffer
        or buffer < 0
        or transaction_cost_bps < 0
    ):
        raise ValueError("capital contract cash, buffer, and cost must be feasible finite values")
    return source_cash, target_cash, buffer, transaction_cost_bps


def _validate_source_run_contract(
    run_manifest_path: Path,
    run_manifest: dict,
    *,
    transaction_cost_bps: float,
) -> None:
    if (
        run_manifest.get("manifest_type") != "ndx_cardinality_real_training_runner"
        or run_manifest.get("research_track") != "portfolio_optimization"
        or run_manifest.get("migration_control_included") is not False
        or run_manifest.get("promotion_allowed") is not False
    ):
        raise ValueError(f"unsafe source runner contract: {run_manifest_path}")
    run_contract = run_manifest.get("run_contract") or {}
    if abs(float(run_contract.get("transaction_cost_bps") or -1.0) - transaction_cost_bps) > 1e-12:
        raise ValueError(f"source runner transaction cost mismatch: {run_manifest_path}")
    spec_artifact = (run_manifest.get("inputs") or {}).get("spec") or {}
    source_spec_path = Path(str(spec_artifact.get("path") or ""))
    if (
        not source_spec_path.is_absolute()
        or spec_artifact.get("sha256") != run_contract.get("spec_sha256")
    ):
        raise ValueError(f"source runner locked spec identity mismatch: {run_manifest_path}")


def _verified_candidate_path(
    result_path: Path,
    result_manifest: dict,
    *,
    source_cash: float,
) -> tuple[Path, int]:
    declared_cash = result_manifest.get("portfolio_cash_usd")
    manifest_cash_matches = (
        declared_cash in {None, ""}
        or abs(float(declared_cash) - source_cash) <= 0.01
    )
    if (
        result_manifest.get("manifest_type") != "ndx_cardinality_real_training_smoke"
        or result_manifest.get("research_track") != "portfolio_optimization"
        or result_manifest.get("migration_control_included") is not False
        or result_manifest.get("promotion_allowed") is not False
        or not manifest_cash_matches
    ):
        raise ValueError(f"source result capital/safety contract mismatch: {result_path}")
    artifact = (result_manifest.get("artifacts") or {}).get("candidates") or {}
    candidate_path = Path(str(artifact.get("path") or ""))
    rows = int(artifact.get("rows") or -1)
    if (
        not candidate_path.is_absolute()
        or not candidate_path.is_file()
        or rows <= 0
        or file_sha256(candidate_path) != artifact.get("sha256")
    ):
        raise ValueError(f"source candidate artifact mismatch: {result_path}")
    return candidate_path, rows


def _csv_text(rows: list[dict], preferred_fields: tuple[str, ...] = ()) -> str:
    preferred = list(preferred_fields)
    extras = sorted({key for row in rows for key in row} - set(preferred))
    fields = preferred + extras
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def build(args) -> dict:
    spec_path = resolve(args.spec)
    output_dir = resolve(args.output_dir)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    candidate_contract = spec["candidate_contract"]
    capital = spec["capital_contract"]
    source_cash, target_cash, cash_buffer, transaction_cost_bps = (
        _validate_capital_contract(capital)
    )
    limit = int(candidate_contract["shortlist_per_frontier_per_coordinate"])
    preference = list(candidate_contract["user_preference_reference"])
    protected = [resolve("config/config.yaml"), resolve("data/state.json")]
    hashes_before = {str(path): file_sha256(path) for path in protected}

    shortlist: list[dict] = []
    coordinate_summaries: list[dict] = []
    source_runs = []
    for raw_root in spec["source_runner_roots"]:
        runner_root = resolve(raw_root)
        run_path, run_manifest = _latest_complete_run(runner_root)
        _validate_source_run_contract(
            run_path,
            run_manifest,
            transaction_cost_bps=transaction_cost_bps,
        )
        batch = runner_root.name
        semantics_hash = evaluation_semantics_sha256(run_manifest)
        result_manifests = _candidate_manifests(run_path, run_manifest)
        source_runs.append({
            "source_batch": batch,
            "run_manifest": run_path.as_posix(),
            "run_manifest_sha256": file_sha256(run_path),
            "coordinate_count": len(result_manifests),
            "evaluation_semantics_sha256": semantics_hash,
            "evaluation_semantics": evaluation_semantics_payload(run_manifest),
        })
        for result_path in result_manifests:
            result_manifest = json.loads(result_path.read_text(encoding="utf-8"))
            candidate_path, expected_candidate_rows = _verified_candidate_path(
                result_path, result_manifest, source_cash=source_cash,
            )
            accumulator = CoordinateAccumulator(limit, preference)
            with candidate_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for raw in csv.DictReader(handle):
                    observed_cash = _number(raw, "portfolio_cash_usd", float("nan"))
                    observed_buffer = _number(
                        raw, "minimum_cash_buffer_usd", float("nan")
                    )
                    if (
                        not isfinite(observed_cash)
                        or not isfinite(observed_buffer)
                        or abs(observed_cash - source_cash) > 0.01
                        or abs(observed_buffer - cash_buffer) > 0.01
                    ):
                        raise ValueError(f"source candidate capital fields mismatch: {candidate_path}")
                    compact = _compact(
                        raw, source_batch=batch, source_manifest=result_path.as_posix(),
                        source_cash=source_cash, target_cash=target_cash,
                    )
                    accumulator.add(raw, compact)
            if accumulator.total != expected_candidate_rows:
                raise ValueError(f"source candidate row count mismatch: {candidate_path}")
            selected = accumulator.finish()
            shortlist.extend(selected)
            coordinate_summaries.append({
                "source_batch": batch,
                "universe_track": result_manifest.get("universe_track"),
                "selection_date": result_manifest.get("selection_date"),
                "holding_count": result_manifest.get("holding_count"),
                "candidate_rows": accumulator.total,
                "source_declared_constraints_passed_rows": accumulator.source_passed,
                "noncapital_eligible_rows": accumulator.noncapital_eligible,
                "whole_lot_only_failed_rows": accumulator.whole_lot_only_failed,
                "user_preference_rows": accumulator.user_preference_rows,
                "capital_replay_shortlist_rows": len(selected),
                "source_candidate_path": candidate_path.as_posix(),
            })

    semantics = {row["evaluation_semantics_sha256"] for row in source_runs}
    compatible = len(semantics) == 1
    output_dir.mkdir(parents=True, exist_ok=True)
    shortlist_path = output_dir / "capital_replay_shortlist.csv"
    summary_path = output_dir / "coordinate_summary.csv"
    atomic_write_text(shortlist_path, _csv_text(shortlist, OUTPUT_FIELDS))
    atomic_write_text(summary_path, _csv_text(coordinate_summaries))
    hashes_after = {str(path): file_sha256(path) for path in protected}
    if hashes_before != hashes_after:
        raise RuntimeError("protected config/state changed during capital sensitivity audit")
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_capital_sensitivity",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": (
            "CAPITAL_REPLAY_SHORTLIST_READY_RUNNERS_SEPARATE"
            if not compatible else "CAPITAL_REPLAY_SHORTLIST_READY"
        ),
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "source_training_cash_usd": source_cash,
        "target_replay_cash_usd": target_cash,
        "minimum_cash_buffer_usd": cash_buffer,
        "transaction_cost_bps": transaction_cost_bps,
        "source_capital_contract_validated": True,
        "target_capital_contract_validated": True,
        "historical_return_metrics_reused": True,
        "historical_returns_recomputed": False,
        "whole_lot_25000_replay_completed": False,
        "capital_reclassification_allowed": False,
        "cross_runner_semantics_compatible": compatible,
        "cross_runner_merge_allowed": compatible,
        "source_runs": source_runs,
        "counts": {
            "coordinates": len(coordinate_summaries),
            "candidate_rows": sum(int(row["candidate_rows"]) for row in coordinate_summaries),
            "source_declared_constraints_passed_rows": sum(int(row["source_declared_constraints_passed_rows"]) for row in coordinate_summaries),
            "noncapital_eligible_rows": sum(int(row["noncapital_eligible_rows"]) for row in coordinate_summaries),
            "whole_lot_only_failed_rows": sum(int(row["whole_lot_only_failed_rows"]) for row in coordinate_summaries),
            "capital_replay_shortlist_rows": len(shortlist),
        },
        "user_preference": {
            "tickers": preference,
            "shortlist_rows": sum(
                1 for row in shortlist
                if "USER_PREFERENCE" in str(row.get("capital_replay_frontiers") or "").split(";")
            ),
            "role": "REFERENCE_NOT_FIXED_ANSWER",
        },
        "next_required_step": (
            "replay each batch separately at $25k under its locked evaluator semantics; "
            "do not merge exact and bounded results until semantic contracts match"
            if not compatible else
            "replay shortlisted weight paths at $25k and recompute dynamic-k execution frontiers"
        ),
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "protected_hashes_unchanged": True,
        "inputs": {"spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)}},
        "artifacts": {
            "shortlist": {"path": shortlist_path.as_posix(), "rows": len(shortlist), "sha256": file_sha256(shortlist_path)},
            "coordinate_summary": {"path": summary_path.as_posix(), "rows": len(coordinate_summaries), "sha256": file_sha256(summary_path)},
        },
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="动态k训练资本一致性重放短名单")
    parser.add_argument("--spec", default="config/ndx_cardinality_capital_sensitivity_v1.yaml")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_capital_sensitivity_v1")
    args = parser.parse_args()
    try:
        manifest = build(args)
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"资本一致性审计失败: {exc}", file=sys.stderr)
        return 2
    counts = manifest["counts"]
    print(
        "资本一致性重放短名单完成 | "
        f"coordinates={counts['coordinates']} | candidates={counts['candidate_rows']} | "
        f"noncapital_eligible={counts['noncapital_eligible_rows']} | "
        f"whole_lot_only_failed={counts['whole_lot_only_failed_rows']} | "
        f"shortlist={counts['capital_replay_shortlist_rows']} | "
        f"semantics_compatible={manifest['cross_runner_semantics_compatible']}"
    )
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
