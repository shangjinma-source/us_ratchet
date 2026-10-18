"""Fail-closed planning and checkpoint verification for real cardinality jobs."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from data.versioning import file_sha256


class NdxCardinalityRealRunnerError(ValueError):
    pass


SAFE_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def safe_part(value: object) -> str:
    text = str(value)
    if not text or not SAFE_PART.fullmatch(text) or text in {".", ".."}:
        raise NdxCardinalityRealRunnerError(f"unsafe coordinate path part: {text!r}")
    return text


def verified_csv_artifact(manifest: Mapping[str, Any], key: str) -> tuple[pd.DataFrame, Path]:
    artifact = (manifest.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or not path.is_file():
        raise NdxCardinalityRealRunnerError(f"missing absolute artifact: {key}")
    if file_sha256(path) != str(artifact.get("sha256") or ""):
        raise NdxCardinalityRealRunnerError(f"artifact hash mismatch: {key}")
    frame = pd.read_csv(path, low_memory=False)
    if len(frame) != int(artifact.get("rows", -1)):
        raise NdxCardinalityRealRunnerError(f"artifact row count mismatch: {key}")
    return frame, path


def load_verified_readiness(path: Path, *, current_spec_path: Path) -> tuple[dict, pd.DataFrame]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "ndx_cardinality_real_input_readiness":
        raise NdxCardinalityRealRunnerError("unexpected readiness manifest type")
    if manifest.get("promotion_allowed") is not False:
        raise NdxCardinalityRealRunnerError("readiness unexpectedly permits promotion")
    locked_spec = (manifest.get("inputs") or {}).get("spec") or {}
    if file_sha256(current_spec_path) != str(locked_spec.get("sha256") or ""):
        raise NdxCardinalityRealRunnerError("readiness spec hash is stale; rebuild readiness")
    jobs, _ = verified_csv_artifact(manifest, "job_readiness")
    return manifest, jobs


def build_job_queue(
    jobs: pd.DataFrame,
    *,
    tracks: Iterable[str] = (),
    selection_dates: Iterable[str] = (),
    holding_counts: Iterable[int] = (),
    search_classes: Iterable[str] = (),
    max_jobs: int | None = None,
) -> pd.DataFrame:
    required = {
        "universe_track", "selection_date", "holding_count", "shard_id",
        "coordinate_sha256", "degraded_research_job_ready",
    }
    missing = sorted(required - set(jobs.columns))
    if missing:
        raise NdxCardinalityRealRunnerError(f"job readiness columns missing: {missing}")
    ready = jobs["degraded_research_job_ready"].astype(str).str.lower().eq("true")
    queue = jobs.loc[ready].copy()
    track_set = {str(item) for item in tracks}
    date_set = {pd.Timestamp(item).date().isoformat() for item in selection_dates}
    k_set = {int(item) for item in holding_counts}
    search_class_set = {str(item) for item in search_classes}
    if track_set:
        queue = queue.loc[queue["universe_track"].astype(str).isin(track_set)]
    if date_set:
        queue = queue.loc[queue["selection_date"].astype(str).isin(date_set)]
    if k_set:
        queue = queue.loc[pd.to_numeric(queue["holding_count"]).astype(int).isin(k_set)]
    if search_class_set:
        if "degraded_search_method" not in queue.columns:
            raise NdxCardinalityRealRunnerError("job readiness search class is missing")
        queue = queue.loc[queue["degraded_search_method"].astype(str).isin(search_class_set)]
    queue = queue.sort_values(
        ["universe_track", "selection_date", "holding_count", "shard_id"],
        kind="stable",
    ).reset_index(drop=True)
    if max_jobs is not None:
        if max_jobs <= 0:
            raise NdxCardinalityRealRunnerError("max_jobs must be positive")
        queue = queue.head(max_jobs).copy()
    return queue


def coordinate_payload(row: Mapping[str, Any], run_fingerprint: str) -> dict[str, Any]:
    payload = {
        "universe_track": safe_part(row["universe_track"]),
        "selection_date": pd.Timestamp(row["selection_date"]).date().isoformat(),
        "holding_count": int(row["holding_count"]),
        "shard_id": int(row["shard_id"]),
        "source_coordinate_sha256": str(row["coordinate_sha256"]),
        "run_fingerprint": run_fingerprint,
    }
    payload["coordinate_id"] = canonical_sha256(payload)[:24]
    return payload


def job_output_dir(run_dir: Path, coordinate: Mapping[str, Any]) -> Path:
    track = safe_part(coordinate["universe_track"])
    date = safe_part(coordinate["selection_date"])
    k = int(coordinate["holding_count"])
    shard = int(coordinate["shard_id"])
    if k <= 0 or shard < 0:
        raise NdxCardinalityRealRunnerError("invalid k/shard coordinate")
    path = run_dir / "jobs" / track / date / f"k{k}" / f"shard{shard:04d}"
    if run_dir.resolve() not in path.resolve().parents:
        raise NdxCardinalityRealRunnerError("job output path escaped run directory")
    return path


def checkpoint_with_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = dict(payload)
    checkpoint.pop("checkpoint_sha256", None)
    checkpoint["checkpoint_sha256"] = canonical_sha256(checkpoint)
    return checkpoint


def verify_result_manifest(path: Path, *, coordinate: Mapping[str, Any]) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "manifest_type": "ndx_cardinality_real_training_smoke",
        "universe_track": coordinate["universe_track"],
        "selection_date": coordinate["selection_date"],
        "holding_count": int(coordinate["holding_count"]),
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "whole_lot_execution_mode": "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES",
        "whole_lot_execution_price_basis": "unadjusted_nominal_trade_price",
        "adjusted_return_prices_used_for_whole_lot_shares": False,
        "selection_date_or_later_execution_prices_used": False,
        "whole_lot_shares_and_cash_carried_between_rebalances": True,
        "whole_lot_transaction_costs_deducted_from_cash": True,
        "whole_lot_constraints_checked_daily": True,
        "promotion_allowed": False,
        "fresh_oos_consumed": False,
        "selection_date_or_later_returns_read": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise NdxCardinalityRealRunnerError(f"result manifest contract mismatch: {key}")
    root = path.parent.resolve()
    for key, artifact in (manifest.get("artifacts") or {}).items():
        artifact_path = Path(str(artifact.get("path") or ""))
        if not artifact_path.is_absolute() or root not in artifact_path.resolve().parents:
            raise NdxCardinalityRealRunnerError(f"result artifact escaped job directory: {key}")
        if not artifact_path.is_file() or file_sha256(artifact_path) != artifact.get("sha256"):
            raise NdxCardinalityRealRunnerError(f"result artifact hash mismatch: {key}")
        rows = artifact.get("rows")
        if rows is not None and artifact_path.suffix.lower() == ".csv":
            if len(pd.read_csv(artifact_path, low_memory=False)) != int(rows):
                raise NdxCardinalityRealRunnerError(f"result artifact row mismatch: {key}")
    return manifest


def verify_completed_checkpoint(
    path: Path, *, coordinate: Mapping[str, Any], expected_output_dir: Path
) -> dict:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    supplied_hash = checkpoint.pop("checkpoint_sha256", None)
    if supplied_hash != canonical_sha256(checkpoint):
        raise NdxCardinalityRealRunnerError("checkpoint content hash mismatch")
    if checkpoint.get("status") != "COMPLETED":
        raise NdxCardinalityRealRunnerError("checkpoint is not completed")
    for key in (
        "coordinate_id", "source_coordinate_sha256", "run_fingerprint",
        "universe_track", "selection_date", "holding_count", "shard_id",
    ):
        if checkpoint.get(key) != coordinate.get(key):
            raise NdxCardinalityRealRunnerError(f"checkpoint coordinate mismatch: {key}")
    manifest_path = Path(str(checkpoint.get("result_manifest_path") or ""))
    if manifest_path != expected_output_dir / "manifest.json":
        if checkpoint.get("result_storage_mode") != "REFERENCED_COMPATIBLE_PRIOR_RUN":
            raise NdxCardinalityRealRunnerError("checkpoint result path mismatch")
        source_checkpoint_path = Path(str(checkpoint.get("source_checkpoint_path") or ""))
        if (
            not manifest_path.is_absolute()
            or not source_checkpoint_path.is_absolute()
            or not source_checkpoint_path.is_file()
            or file_sha256(source_checkpoint_path) != checkpoint.get("source_checkpoint_sha256")
        ):
            raise NdxCardinalityRealRunnerError("referenced prior checkpoint proof mismatch")
    if file_sha256(manifest_path) != checkpoint.get("result_manifest_sha256"):
        raise NdxCardinalityRealRunnerError("checkpoint result manifest hash mismatch")
    verify_result_manifest(manifest_path, coordinate=coordinate)
    checkpoint["checkpoint_sha256"] = supplied_hash
    return checkpoint
