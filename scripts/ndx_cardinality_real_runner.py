r"""Plan or execute resumable real point-in-time cardinality training jobs.

PowerShell/PyCharm plan-only example:
    python -B scripts\ndx_cardinality_real_runner.py --selection-date 2024-06-03 --holding-count 4 --holding-count 5 --holding-count 6

Execution is historical training discovery only and never changes live advice:
    python -B scripts\ndx_cardinality_real_runner.py --selection-date 2024-06-03 --holding-count 4 --max-jobs 1 --execute --resume
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_real_runner import (
    NdxCardinalityRealRunnerError,
    build_job_queue,
    canonical_sha256,
    checkpoint_with_hash,
    coordinate_payload,
    job_output_dir,
    load_verified_readiness,
    verify_completed_checkpoint,
    verify_result_manifest,
)
from core.helpers import atomic_write_text
from data.versioning import file_sha256


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_checkpoint(path: Path, payload: dict) -> dict:
    checkpoint = checkpoint_with_hash(payload)
    atomic_write_text(path, json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n")
    return checkpoint


def _load_reusable_completed(run_dir: Path) -> dict[tuple[str, str, int, int], dict]:
    plan_path = run_dir / "job_plan.csv"
    index_path = run_dir / "checkpoint_index.csv"
    if not plan_path.is_file() or not index_path.is_file():
        raise NdxCardinalityRealRunnerError("compatible prior run plan/index is missing")
    plan = pd.read_csv(plan_path, low_memory=False)
    index = pd.read_csv(index_path, low_memory=False)
    merged = plan.merge(
        index[["coordinate_id", "status", "checkpoint_path"]],
        on="coordinate_id", how="left", validate="one_to_one",
    )
    reusable = {}
    for row in merged.loc[merged["status"].eq("COMPLETED")].to_dict("records"):
        coordinate = {
            key: row[key] for key in (
                "coordinate_id", "source_coordinate_sha256", "run_fingerprint",
                "universe_track", "selection_date", "holding_count", "shard_id",
            )
        }
        coordinate["holding_count"] = int(coordinate["holding_count"])
        coordinate["shard_id"] = int(coordinate["shard_id"])
        checkpoint_path = Path(str(row["checkpoint_path"]))
        verify_completed_checkpoint(
            checkpoint_path,
            coordinate=coordinate,
            expected_output_dir=Path(str(row["output_dir"])),
        )
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        key = (
            str(row["universe_track"]), str(row["selection_date"]),
            int(row["holding_count"]), int(row["shard_id"]),
        )
        reusable[key] = {
            "coordinate": coordinate,
            "checkpoint": checkpoint,
            "checkpoint_path": checkpoint_path,
        }
    return reusable


def run(args) -> dict:
    if args.seed_compatible_only and (not args.execute or not args.reuse_compatible_run_dir):
        raise NdxCardinalityRealRunnerError(
            "--seed-compatible-only requires --execute and --reuse-compatible-run-dir"
        )
    spec_path = _resolve(args.spec)
    readiness_path = _resolve(args.input_readiness_manifest)
    discovery_path = _resolve(args.discovery_manifest)
    lifecycle_path = _resolve(args.security_lifecycle)
    execution_price_manifest_path = _resolve(args.execution_price_manifest)
    smoke_script = ROOT / "scripts" / "ndx_cardinality_real_smoke.py"
    runner_script = Path(__file__).resolve()
    module_path = ROOT / "backtest" / "ndx_cardinality_real_runner.py"
    discovery_module_path = ROOT / "backtest" / "ndx_cardinality_discovery.py"
    whole_lot_module_path = ROOT / "backtest" / "ndx_whole_lot_rebalance.py"
    config_path = _resolve(args.config)
    state_path = _resolve(args.state)
    protected_before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    readiness, jobs = load_verified_readiness(readiness_path, current_spec_path=spec_path)
    discovery_sha = file_sha256(discovery_path)
    locked_discovery = ((readiness.get("inputs") or {}).get("discovery_manifest") or {}).get("sha256")
    if discovery_sha != locked_discovery:
        raise NdxCardinalityRealRunnerError("readiness discovery manifest hash is stale")
    queue = build_job_queue(
        jobs, tracks=args.track, selection_dates=args.selection_date,
        holding_counts=args.holding_count, search_classes=args.job_search_class,
        max_jobs=args.max_jobs,
    )
    queue_coordinates = [
        {
            "universe_track": str(row["universe_track"]),
            "selection_date": str(row["selection_date"]),
            "holding_count": int(row["holding_count"]),
            "shard_id": int(row["shard_id"]),
            "coordinate_sha256": str(row["coordinate_sha256"]),
        }
        for row in queue.to_dict("records")
    ]
    run_contract = {
        "schema_version": 1,
        "spec_sha256": file_sha256(spec_path),
        "readiness_manifest_sha256": file_sha256(readiness_path),
        "discovery_manifest_sha256": discovery_sha,
        "security_lifecycle_sha256": file_sha256(lifecycle_path),
        "execution_price_manifest_sha256": file_sha256(execution_price_manifest_path),
        "smoke_script_sha256": file_sha256(smoke_script),
        "runner_script_sha256": file_sha256(runner_script),
        "runner_module_sha256": file_sha256(module_path),
        "discovery_module_sha256": file_sha256(discovery_module_path),
        "whole_lot_module_sha256": file_sha256(whole_lot_module_path),
        "search_method": args.search_method,
        "job_search_classes": sorted(args.job_search_class),
        "minimum_price_rows_before_selection": args.minimum_price_rows_before_selection,
        "training_lookback_days": args.training_lookback_days,
        "fit_days": args.fit_days,
        "window_days": args.window_days,
        "step_days": args.step_days,
        "beam_width": args.beam_width,
        "transaction_cost_bps": args.transaction_cost_bps,
        "selected_coordinate_count": len(queue_coordinates),
        "selected_coordinates_sha256": canonical_sha256({"coordinates": queue_coordinates}),
    }
    run_fingerprint = canonical_sha256(run_contract)
    run_dir = _resolve(args.output_root) / "runs" / run_fingerprint
    checkpoint_dir = run_dir / "checkpoints"
    log_dir = run_dir / "logs"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    plan_rows = []
    for row in queue.to_dict("records"):
        coordinate = coordinate_payload(row, run_fingerprint)
        output_dir = job_output_dir(run_dir, coordinate)
        plan_rows.append({**coordinate, "output_dir": output_dir.as_posix()})
    plan = pd.DataFrame(plan_rows)
    plan_path = run_dir / "job_plan.csv"
    _atomic_csv(plan, plan_path)

    reusable = {}
    if args.reuse_compatible_run_dir:
        reusable = _load_reusable_completed(_resolve(args.reuse_compatible_run_dir))

    counters = {"attempted": 0, "completed": 0, "failed": 0, "resumed": 0}
    failures = []
    if args.execute:
        for coordinate in plan_rows:
            checkpoint_path = checkpoint_dir / f"{coordinate['coordinate_id']}.json"
            output_dir = Path(coordinate["output_dir"])
            natural_key = (
                coordinate["universe_track"], coordinate["selection_date"],
                int(coordinate["holding_count"]), int(coordinate["shard_id"]),
            )
            prior = reusable.get(natural_key)
            if not checkpoint_path.exists() and prior is not None:
                if prior["coordinate"]["source_coordinate_sha256"] == coordinate["source_coordinate_sha256"]:
                    prior_checkpoint = prior["checkpoint"]
                    manifest_path = Path(str(prior_checkpoint["result_manifest_path"]))
                    verify_result_manifest(manifest_path, coordinate=coordinate)
                    _write_checkpoint(checkpoint_path, {
                        **coordinate,
                        "completed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                        "return_code": 0,
                        "status": "COMPLETED",
                        "result_manifest_path": manifest_path.as_posix(),
                        "result_manifest_sha256": file_sha256(manifest_path),
                        "result_storage_mode": "REFERENCED_COMPATIBLE_PRIOR_RUN",
                        "source_checkpoint_path": prior["checkpoint_path"].as_posix(),
                        "source_checkpoint_sha256": file_sha256(prior["checkpoint_path"]),
                        "source_run_fingerprint": prior["coordinate"]["run_fingerprint"],
                        "promotion_allowed": False,
                    })
            if checkpoint_path.exists():
                existing = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if existing.get("status") == "COMPLETED":
                    if not args.resume:
                        raise NdxCardinalityRealRunnerError("completed checkpoint exists; use --resume")
                    verify_completed_checkpoint(
                        checkpoint_path, coordinate=coordinate, expected_output_dir=output_dir
                    )
                    counters["resumed"] += 1
                    continue
                if not args.retry_failed:
                    raise NdxCardinalityRealRunnerError("failed checkpoint exists; use --retry-failed")
            if args.seed_compatible_only:
                continue
            command = [
                sys.executable, "-B", str(smoke_script),
                "--track", coordinate["universe_track"],
                "--selection-date", coordinate["selection_date"],
                "--holding-count", str(coordinate["holding_count"]),
                "--spec", str(spec_path),
                "--input-readiness-manifest", str(readiness_path),
                "--discovery-manifest", str(discovery_path),
                "--security-lifecycle", str(lifecycle_path),
                "--execution-price-manifest", str(execution_price_manifest_path),
                "--return-cache-dir", str(_resolve(args.return_cache_dir)),
                "--target-nav", str(_resolve(args.target_nav)),
                "--state", str(state_path), "--config", str(config_path),
                "--output-dir", str(output_dir),
                "--minimum-price-rows-before-selection", str(args.minimum_price_rows_before_selection),
                "--training-lookback-days", str(args.training_lookback_days),
                "--fit-days", str(args.fit_days), "--window-days", str(args.window_days),
                "--step-days", str(args.step_days), "--beam-width", str(args.beam_width),
                "--transaction-cost-bps", str(args.transaction_cost_bps),
                "--search-method", args.search_method,
            ]
            counters["attempted"] += 1
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            stdout_path = log_dir / f"{coordinate['coordinate_id']}.stdout.log"
            stderr_path = log_dir / f"{coordinate['coordinate_id']}.stderr.log"
            atomic_write_text(stdout_path, completed.stdout)
            atomic_write_text(stderr_path, completed.stderr)
            base = {
                **coordinate,
                "completed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "return_code": completed.returncode,
                "stdout_path": stdout_path.as_posix(),
                "stdout_sha256": file_sha256(stdout_path),
                "stderr_path": stderr_path.as_posix(),
                "stderr_sha256": file_sha256(stderr_path),
                "promotion_allowed": False,
            }
            try:
                if completed.returncode:
                    raise NdxCardinalityRealRunnerError(f"worker returned {completed.returncode}")
                manifest_path = output_dir / "manifest.json"
                verify_result_manifest(manifest_path, coordinate=coordinate)
                _write_checkpoint(checkpoint_path, {
                    **base, "status": "COMPLETED",
                    "result_manifest_path": manifest_path.as_posix(),
                    "result_manifest_sha256": file_sha256(manifest_path),
                })
                counters["completed"] += 1
            except Exception as exc:
                _write_checkpoint(checkpoint_path, {
                    **base, "status": "FAILED", "error": f"{type(exc).__name__}:{exc}",
                })
                counters["failed"] += 1
                failures.append({"coordinate_id": coordinate["coordinate_id"], "error": str(exc)})
                if args.fail_fast:
                    break

    checkpoint_rows = []
    for coordinate in plan_rows:
        checkpoint_path = checkpoint_dir / f"{coordinate['coordinate_id']}.json"
        status = "NOT_ATTEMPTED"
        checkpoint_sha = None
        if checkpoint_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            status = str(checkpoint.get("status") or "INVALID")
            checkpoint_sha = file_sha256(checkpoint_path)
            if status == "COMPLETED":
                verify_completed_checkpoint(
                    checkpoint_path,
                    coordinate=coordinate,
                    expected_output_dir=Path(coordinate["output_dir"]),
                )
        checkpoint_rows.append({
            **coordinate, "status": status,
            "checkpoint_path": checkpoint_path.as_posix(),
            "checkpoint_file_sha256": checkpoint_sha,
        })
    checkpoint_index = pd.DataFrame(checkpoint_rows)
    checkpoint_index_path = run_dir / "checkpoint_index.csv"
    _atomic_csv(checkpoint_index, checkpoint_index_path)
    run_completed_count = int(checkpoint_index["status"].eq("COMPLETED").sum()) if len(checkpoint_index) else 0
    run_failed_count = int(checkpoint_index["status"].eq("FAILED").sum()) if len(checkpoint_index) else 0

    protected_after = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    if protected_after != protected_before:
        raise NdxCardinalityRealRunnerError("protected config/state hash changed")
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_real_training_runner",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "execution_requested": bool(args.execute),
        "run_fingerprint": run_fingerprint,
        "run_contract": run_contract,
        "planned_job_count": len(plan),
        **counters,
        "run_completed_job_count": run_completed_count,
        "run_failed_job_count": run_failed_count,
        "failures": failures,
        "return_data_read": bool(run_completed_count or (args.execute and counters["attempted"])),
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "personal_off_strategy_positions_included": False,
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "protected_hashes_unchanged": True,
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "readiness_manifest": {"path": readiness_path.as_posix(), "sha256": file_sha256(readiness_path)},
            "discovery_manifest": {"path": discovery_path.as_posix(), "sha256": discovery_sha},
            "security_lifecycle": {"path": lifecycle_path.as_posix(), "sha256": file_sha256(lifecycle_path)},
            "execution_price_manifest": {"path": execution_price_manifest_path.as_posix(), "sha256": file_sha256(execution_price_manifest_path)},
        },
        "artifacts": {
            "job_plan": {"path": plan_path.as_posix(), "rows": len(plan), "sha256": file_sha256(plan_path)},
            "checkpoint_index": {"path": checkpoint_index_path.as_posix(), "rows": len(checkpoint_index), "sha256": file_sha256(checkpoint_index_path)},
        },
    }
    atomic_write_text(run_dir / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="真实点时动态持仓数可恢复训练 runner")
    parser.add_argument("--track", action="append", default=[])
    parser.add_argument("--selection-date", action="append", default=[])
    parser.add_argument("--holding-count", action="append", type=int, default=[])
    parser.add_argument(
        "--job-search-class", action="append", default=[],
        choices=["EXACT_ENUMERATION", "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"],
    )
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--reuse-compatible-run-dir")
    parser.add_argument("--seed-compatible-only", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--input-readiness-manifest", default="data/cache/research/ndx_variable_cardinality_input_readiness_v3/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--security-lifecycle", default="config/ndx_security_lifecycle.yaml")
    parser.add_argument("--execution-price-manifest", default="data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json")
    parser.add_argument("--return-cache-dir", default="data/cache")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output-root", default="data/cache/research/ndx_cardinality_real_runner_v1")
    parser.add_argument("--minimum-price-rows-before-selection", type=int, default=252)
    parser.add_argument("--training-lookback-days", type=int, default=504)
    parser.add_argument("--fit-days", type=int, default=126)
    parser.add_argument("--window-days", type=int, default=126)
    parser.add_argument("--step-days", type=int, default=21)
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--search-method", choices=["two_stage", "full"], default="two_stage")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = run(args)
    except Exception as exc:
        print(f"真实训练 runner 失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "真实训练 runner 完成 | "
        f"planned={payload['planned_job_count']} | attempted={payload['attempted']} | "
        f"completed={payload['completed']} | resumed={payload['resumed']} | "
        f"failed={payload['failed']} | promotion_allowed=False"
    )
    return 0 if not payload["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
