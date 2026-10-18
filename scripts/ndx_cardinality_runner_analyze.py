r"""Aggregate completed exact/bounded runner batches by date and across starts.

PowerShell/PyCharm:
    python -B scripts\ndx_cardinality_runner_analyze.py --runner-manifest <exact>\manifest.json --runner-manifest <bounded>\manifest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_real_runner import (
    NdxCardinalityRealRunnerError,
    verify_completed_checkpoint,
)
from backtest.ndx_cardinality_capital_sensitivity import (
    evaluation_semantics_payload,
    evaluation_semantics_sha256,
)
from data.versioning import file_sha256
from core.helpers import atomic_write_text
from scripts.ndx_cardinality_cross_start_stability import run as run_stability
from scripts.ndx_cardinality_frontier_aggregate import run as run_frontier_aggregate


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def completed_manifests(runner_manifest_path: Path) -> dict[tuple[str, str], list[Path]]:
    runner = json.loads(runner_manifest_path.read_text(encoding="utf-8"))
    if runner.get("manifest_type") != "ndx_cardinality_real_training_runner":
        raise NdxCardinalityRealRunnerError("unexpected runner manifest type")
    if runner.get("promotion_allowed") is not False:
        raise NdxCardinalityRealRunnerError("runner unexpectedly permits promotion")
    if (
        runner.get("research_track") != "portfolio_optimization"
        or runner.get("migration_control_included") is not False
        or runner.get("fresh_oos_consumed") is not False
        or int(runner.get("run_failed_job_count") or 0) != 0
        or int(runner.get("run_completed_job_count") or 0) != int(runner.get("planned_job_count") or -1)
    ):
        raise NdxCardinalityRealRunnerError("runner completion/governance contract changed")
    artifact = (runner.get("artifacts") or {}).get("checkpoint_index") or {}
    index_path = Path(str(artifact.get("path") or ""))
    if not index_path.is_absolute() or file_sha256(index_path) != artifact.get("sha256"):
        raise NdxCardinalityRealRunnerError("runner checkpoint index mismatch")
    index = pd.read_csv(index_path, low_memory=False)
    if len(index) != int(artifact.get("rows") or -1):
        raise NdxCardinalityRealRunnerError("runner checkpoint index row count changed")
    if index.empty or not index["status"].eq("COMPLETED").all():
        raise NdxCardinalityRealRunnerError("runner batch is not fully completed")
    grouped: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for row in index.to_dict("records"):
        coordinate = {
            "coordinate_id": str(row["coordinate_id"]),
            "source_coordinate_sha256": str(row["source_coordinate_sha256"]),
            "run_fingerprint": str(row["run_fingerprint"]),
            "universe_track": str(row["universe_track"]),
            "selection_date": str(row["selection_date"]),
            "holding_count": int(row["holding_count"]),
            "shard_id": int(row["shard_id"]),
        }
        checkpoint_path = Path(str(row["checkpoint_path"]))
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        result_path = Path(str(checkpoint.get("result_manifest_path") or ""))
        verify_completed_checkpoint(
            checkpoint_path, coordinate=coordinate, expected_output_dir=result_path.parent
        )
        grouped[(coordinate["universe_track"], coordinate["selection_date"])].append(result_path)
    for values in grouped.values():
        values.sort(key=lambda path: int(json.loads(path.read_text(encoding="utf-8"))["holding_count"]))
    return dict(grouped)


def merge_completed_manifest_groups(
    batches: list[dict[tuple[str, str], list[Path]]],
) -> dict[tuple[str, str], list[Path]]:
    merged: dict[tuple[str, str], list[Path]] = defaultdict(list)
    seen: set[tuple[str, str, int]] = set()
    for batch in batches:
        for (track, selection_date), manifests in batch.items():
            for path in manifests:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                identity = (track, selection_date, int(manifest["holding_count"]))
                if identity in seen:
                    raise NdxCardinalityRealRunnerError(
                        f"duplicate completed track/date/k coordinate: {identity}"
                    )
                seen.add(identity)
                merged[(track, selection_date)].append(path)
    for values in merged.values():
        values.sort(key=lambda path: int(json.loads(path.read_text(encoding="utf-8"))["holding_count"]))
    return dict(merged)


def validate_runner_semantics(runner_manifest_paths: list[Path]) -> dict:
    """Reject cross-batch aggregation when evaluator contracts are not identical."""
    rows = []
    for path in runner_manifest_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "path": path.as_posix(),
            "evaluation_semantics_sha256": evaluation_semantics_sha256(manifest),
            "evaluation_semantics": evaluation_semantics_payload(manifest),
        })
    hashes = {row["evaluation_semantics_sha256"] for row in rows}
    if len(hashes) != 1:
        raise NdxCardinalityRealRunnerError(
            "runner evaluator semantics are incompatible; keep batches separate and replay "
            "under one locked contract before aggregation"
        )
    return {"compatible": True, "evaluation_semantics_sha256": next(iter(hashes)), "batches": rows}


def run(args: argparse.Namespace) -> dict:
    values = args.runner_manifest if isinstance(args.runner_manifest, list) else [args.runner_manifest]
    runner_manifest_paths = [_resolve(value) for value in values]
    if len(set(runner_manifest_paths)) != len(runner_manifest_paths):
        raise NdxCardinalityRealRunnerError("runner manifest input is duplicated")
    semantics = validate_runner_semantics(runner_manifest_paths)
    grouped = merge_completed_manifest_groups([
        completed_manifests(path) for path in runner_manifest_paths
    ])
    output = _resolve(args.output_dir)
    frontier_manifests = []
    results = []
    for (track, selection_date), manifests in sorted(grouped.items()):
        date_output = output / "by_date" / track / selection_date
        result = run_frontier_aggregate(SimpleNamespace(
            manifest=[path.as_posix() for path in manifests], output_dir=date_output.as_posix()
        ))
        frontier_manifests.append(date_output / "manifest.json")
        results.append(result)
    stability_manifests = []
    for track in sorted({key[0] for key in grouped}):
        track_frontiers = [
            path for path in frontier_manifests
            if json.loads(path.read_text(encoding="utf-8"))["comparison_identity"]["universe_track"] == track
        ]
        if len(track_frontiers) >= 2:
            stability_output = output / "cross_start_stability" / track
            results.append(run_stability(SimpleNamespace(
                manifest=[path.as_posix() for path in track_frontiers],
                output_dir=stability_output.as_posix(),
            )))
            stability_manifests.append(stability_output / "manifest.json")
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_combined_runner_analysis",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "CURRENT_SEARCHED_TRAINING_FRONTIERS_ONLY",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "runner_batch_count": len(runner_manifest_paths),
        "cross_runner_semantics": semantics,
        "completed_coordinate_count": sum(len(paths) for paths in grouped.values()),
        "universe_tracks": sorted({key[0] for key in grouped}),
        "track_date_count": len(grouped),
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "inputs": {
            "runner_manifests": [
                {"path": path.as_posix(), "sha256": file_sha256(path)}
                for path in runner_manifest_paths
            ],
        },
        "artifacts": {
            "by_date_frontier_manifests": [
                {"path": path.as_posix(), "sha256": file_sha256(path)}
                for path in frontier_manifests
            ],
            "cross_start_stability_manifests": [
                {"path": path.as_posix(), "sha256": file_sha256(path)}
                for path in stability_manifests
            ],
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="runner 批次逐日期前沿与跨起点稳定性聚合")
    parser.add_argument("--runner-manifest", action="append", required=True)
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_runner_analysis_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"runner 批次聚合失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"runner 批次聚合完成 | coordinates={payload['completed_coordinate_count']} | "
        f"track_dates={payload['track_date_count']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
