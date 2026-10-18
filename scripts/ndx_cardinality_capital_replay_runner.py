r"""Resume-safe $25k replay runner grouped by source batch, track, and date.

Each job prepares its point-in-time inputs once and evaluates every shortlisted
holding count for that track/date.  This is materially smaller than rerunning
the original enumeration and keeps incompatible source batches separate.

PowerShell:
    python -B scripts\ndx_cardinality_capital_replay_runner.py --execute --resume --fail-fast
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text, resolve
from data.versioning import file_sha256


class NdxCardinalityCapitalReplayRunnerError(ValueError):
    pass


def _verified_artifact(manifest: dict, name: str) -> Path:
    artifact = (manifest.get("artifacts") or {}).get(name) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or not path.exists() or file_sha256(path) != artifact.get("sha256"):
        raise NdxCardinalityCapitalReplayRunnerError(f"capital audit artifact mismatch: {name}")
    return path


def _source_run_map(capital_manifest: dict) -> dict[str, dict]:
    result = {}
    for source in capital_manifest.get("source_runs") or []:
        batch = str(source.get("source_batch") or "")
        path = Path(str(source.get("run_manifest") or ""))
        if not batch or not path.is_absolute() or file_sha256(path) != source.get("run_manifest_sha256"):
            raise NdxCardinalityCapitalReplayRunnerError("source runner manifest mismatch")
        result[batch] = json.loads(path.read_text(encoding="utf-8"))
    if not result:
        raise NdxCardinalityCapitalReplayRunnerError("capital audit has no source runners")
    return result


def _result_is_resumable(path: Path, *, shortlist_hash: str, target_cash: float,
                         source_batch: str) -> bool:
    if not path.exists():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    source = manifest.get("candidate_replay_source") or {}
    identity_matches = bool(
        manifest.get("manifest_type") == "ndx_cardinality_real_training_smoke"
        and manifest.get("status") == "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION"
        and manifest.get("candidate_replay_mode") is True
        and manifest.get("promotion_allowed") is False
        and manifest.get("frontier_comparison_scope")
        == "WITHIN_CARDINALITY_AND_CROSS_CARDINALITY"
        and source.get("sha256") == shortlist_hash
        and abs(float(source.get("target_portfolio_cash_usd") or 0.0) - target_cash) <= 0.01
        and source.get("source_batches") == [source_batch]
    )
    if not identity_matches:
        return False
    for name in ("candidates", "frontiers"):
        artifact = (manifest.get("artifacts") or {}).get(name) or {}
        artifact_path = Path(str(artifact.get("path") or ""))
        if (
            not artifact_path.is_absolute() or not artifact_path.exists()
            or file_sha256(artifact_path) != artifact.get("sha256")
        ):
            return False
        try:
            with artifact_path.open("r", encoding="utf-8-sig") as handle:
                header = handle.readline().strip().split(",")
                rows = sum(1 for _ in handle)
        except OSError:
            return False
        if rows != int(artifact.get("rows") or -1):
            return False
        if name == "candidates" and not {
            "decision_data_end", "security_ids", "issuer_ids", "risk_chains",
            "cross_cardinality_frontier_tags",
            "cross_cardinality_constrained_frontier_tags",
        }.issubset(header):
            return False
    return True


def run(args: argparse.Namespace) -> dict:
    if args.max_jobs is not None and int(args.max_jobs) <= 0:
        raise NdxCardinalityCapitalReplayRunnerError("max_jobs must be positive")
    capital_manifest_path = resolve(args.capital_manifest)
    capital_manifest = json.loads(capital_manifest_path.read_text(encoding="utf-8"))
    if (
        capital_manifest.get("manifest_type") != "ndx_cardinality_capital_sensitivity"
        or capital_manifest.get("promotion_allowed") is not False
        or capital_manifest.get("whole_lot_25000_replay_completed") is not False
    ):
        raise NdxCardinalityCapitalReplayRunnerError("unexpected capital sensitivity manifest")
    shortlist_path = _verified_artifact(capital_manifest, "shortlist")
    shortlist_hash = file_sha256(shortlist_path)
    target_cash = float(capital_manifest["target_replay_cash_usd"])
    source_runs = _source_run_map(capital_manifest)
    shortlist = pd.read_csv(shortlist_path, low_memory=False)
    required = {"source_batch", "universe_track", "selection_date", "holding_count"}
    if shortlist.empty or not required.issubset(shortlist.columns):
        raise NdxCardinalityCapitalReplayRunnerError("capital replay shortlist is empty or incomplete")
    if args.only_source_batch:
        shortlist = shortlist.loc[
            shortlist["source_batch"].astype(str).eq(str(args.only_source_batch))
        ].copy()
    if args.only_track:
        shortlist = shortlist.loc[
            shortlist["universe_track"].astype(str).eq(str(args.only_track))
        ].copy()
    if args.only_selection_date:
        shortlist = shortlist.loc[
            shortlist["selection_date"].astype(str).eq(str(args.only_selection_date))
        ].copy()
    if shortlist.empty:
        raise NdxCardinalityCapitalReplayRunnerError("capital replay scope selects no rows")

    grouped = shortlist.groupby(
        ["source_batch", "universe_track", "selection_date"], sort=True, dropna=False
    )
    output_root = resolve(args.output_root)
    jobs = []
    completed = resumed = failed = attempted = 0
    for (source_batch, track, selection_date), rows in grouped:
        if args.max_jobs is not None and len(jobs) >= int(args.max_jobs):
            break
        source_batch = str(source_batch)
        track = str(track)
        selection_date = str(selection_date)
        if source_batch not in source_runs:
            raise NdxCardinalityCapitalReplayRunnerError(f"unknown source batch: {source_batch}")
        run_manifest = source_runs[source_batch]
        run_contract = run_manifest.get("run_contract") or {}
        source_inputs = run_manifest.get("inputs") or {}
        destination = output_root / source_batch / track / selection_date
        result_manifest_path = destination / "manifest.json"
        job = {
            "source_batch": source_batch,
            "universe_track": track,
            "selection_date": selection_date,
            "holding_counts": ";".join(str(value) for value in sorted(rows["holding_count"].astype(int).unique())),
            "shortlist_rows": len(rows),
            "output_dir": destination.as_posix(),
            "status": "PLANNED",
        }
        if args.resume and _result_is_resumable(
            result_manifest_path, shortlist_hash=shortlist_hash,
            target_cash=target_cash, source_batch=source_batch,
        ):
            job["status"] = "RESUMED_COMPLETED"
            completed += 1
            resumed += 1
            jobs.append(job)
            continue
        if not args.execute:
            jobs.append(job)
            continue
        command = [
            sys.executable, "-B", str(ROOT / "scripts" / "ndx_cardinality_real_smoke.py"),
            "--track", track,
            "--selection-date", selection_date,
            "--holding-count", "0",
            "--candidate-sets-file", shortlist_path.as_posix(),
            "--source-batch", source_batch,
            "--portfolio-cash-usd", str(target_cash),
            "--spec", str((source_inputs.get("spec") or {}).get("path") or "config/ndx_cardinality_discovery_v1.yaml"),
            "--input-readiness-manifest", str((source_inputs.get("readiness_manifest") or {}).get("path") or "data/cache/research/ndx_variable_cardinality_input_readiness_v3/manifest.json"),
            "--discovery-manifest", str((source_inputs.get("discovery_manifest") or {}).get("path") or "data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json"),
            "--security-lifecycle", str((source_inputs.get("security_lifecycle") or {}).get("path") or "config/ndx_security_lifecycle.yaml"),
            "--execution-price-manifest", str((source_inputs.get("execution_price_manifest") or {}).get("path") or "data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json"),
            "--minimum-price-rows-before-selection", str(int(run_contract.get("minimum_price_rows_before_selection") or 252)),
            "--training-lookback-days", str(int(run_contract.get("training_lookback_days") or 504)),
            "--fit-days", str(int(run_contract.get("fit_days") or 126)),
            "--window-days", str(int(run_contract.get("window_days") or 126)),
            "--step-days", str(int(run_contract.get("step_days") or 21)),
            "--beam-width", str(int(run_contract.get("beam_width") or 64)),
            "--transaction-cost-bps", str(float(run_contract.get("transaction_cost_bps") or 10.0)),
            "--output-dir", destination.as_posix(),
        ]
        attempted += 1
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        job["return_code"] = process.returncode
        job["stdout_tail"] = process.stdout[-2000:]
        job["stderr_tail"] = process.stderr[-2000:]
        if process.returncode == 0 and _result_is_resumable(
            result_manifest_path, shortlist_hash=shortlist_hash,
            target_cash=target_cash, source_batch=source_batch,
        ):
            job["status"] = "COMPLETED"
            completed += 1
        else:
            job["status"] = "FAILED"
            failed += 1
        jobs.append(job)
        if failed and args.fail_fast:
            break

    output_root.mkdir(parents=True, exist_ok=True)
    index_path = output_root / "job_index.csv"
    pd.DataFrame(jobs).to_csv(index_path, index=False, encoding="utf-8-sig")
    planned = len(jobs) if args.max_jobs is not None else grouped.ngroups
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_capital_replay_runner",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": (
            "CAPITAL_REPLAY_COMPLETE" if completed == planned and failed == 0 else
            "CAPITAL_REPLAY_FAILED" if failed else "CAPITAL_REPLAY_PLANNED_NOT_EXECUTED"
        ),
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "target_portfolio_cash_usd": target_cash,
        "planned_job_count": planned,
        "execution_scope": {
            "only_source_batch": args.only_source_batch,
            "only_track": args.only_track,
            "only_selection_date": args.only_selection_date,
            "max_jobs": args.max_jobs,
        },
        "attempted": attempted,
        "completed": completed,
        "resumed": resumed,
        "failed": failed,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "inputs": {
            "capital_manifest": {"path": capital_manifest_path.as_posix(), "sha256": file_sha256(capital_manifest_path)},
            "shortlist": {"path": shortlist_path.as_posix(), "sha256": shortlist_hash},
        },
        "artifacts": {
            "job_index": {"path": index_path.as_posix(), "rows": len(jobs), "sha256": file_sha256(index_path)},
        },
    }
    atomic_write_text(output_root / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="$25k动态k资本一致性逐点重放runner")
    parser.add_argument("--capital-manifest", default="data/cache/research/ndx_cardinality_capital_sensitivity_v1/manifest.json")
    parser.add_argument("--output-root", default="data/cache/research/ndx_cardinality_capital_replay_v1")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--only-source-batch", default="")
    parser.add_argument("--only-track", choices=["", "strict_technology", "technology_plus_adjacent"], default="")
    parser.add_argument("--only-selection-date", default="")
    parser.add_argument("--max-jobs", type=int)
    return parser.parse_args()


def main() -> int:
    try:
        manifest = run(parse_args())
    except Exception as exc:
        print(f"$25k资本重放runner失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "$25k资本重放runner完成 | "
        f"planned={manifest['planned_job_count']} | attempted={manifest['attempted']} | "
        f"completed={manifest['completed']} | resumed={manifest['resumed']} | "
        f"failed={manifest['failed']} | promotion_allowed=False"
    )
    return 0 if manifest["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
