"""Strict verifier for the deadline-aware v2 fresh-search controller."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from backtest.ndx_dynamic_shadow_candidate_snapshot import verify_snapshot_bundle
from backtest.ndx_dynamic_shadow_fresh_search import (
    canonical_sha256 as executor_canonical_sha256, coordinate_hash,
    load_frozen_original_8_definition, verify_completed_shard,
)
from data.versioning import file_sha256

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1"
OUTPUT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_fresh_search_v1"
CONTROLLER_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_fresh_search_v2_controller"
ORIGINAL8 = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"
TRACKS = ("strict_technology", "technology_plus_adjacent")
EXACT = "EXACT_ENUMERATION"
BOUNDED = "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"
JOB_FIELDS = {
    "snapshot_fingerprint", "universe_track", "decision_date", "execution_coordinate_rule",
    "decision_data_end", "holding_count", "eligible_security_count", "eligible_issuer_count",
    "one_security_per_issuer_required", "theoretical_issuer_combinations", "job_search_class",
    "search_completion_status", "global_optimality_claimed", "bounded_search_disclosure",
    "checkpoint_key", "historical_candidate_replay_allowed", "promotion_allowed",
}


class NdxDynamicShadowFreshSearchV2Error(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def verify_v2_job_plan(jobs: Sequence[Mapping[str, Any]], *, exact_limit: int = 50_000) -> list[dict]:
    rows = [dict(row) for row in jobs]
    if not rows or int(exact_limit) < 1 or any(set(row) != JOB_FIELDS for row in rows):
        raise NdxDynamicShadowFreshSearchV2Error("job plan must use the sealed nonempty exact schema")
    keys = [str(row["checkpoint_key"]) for row in rows]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise NdxDynamicShadowFreshSearchV2Error("checkpoint keys must be unique")
    if set(str(row["universe_track"]) for row in rows) != set(TRACKS):
        raise NdxDynamicShadowFreshSearchV2Error("job plan must contain both canonical tracks")
    if len({str(row["snapshot_fingerprint"]) for row in rows}) != 1 or len({str(row["decision_date"]) for row in rows}) != 1:
        raise NdxDynamicShadowFreshSearchV2Error("job plan snapshot/date identity is mixed")
    for track in TRACKS:
        scoped = [row for row in rows if str(row["universe_track"]) == track]
        counts = {int(row["eligible_issuer_count"]) for row in scoped}
        if len(counts) != 1 or next(iter(counts)) < 1:
            raise NdxDynamicShadowFreshSearchV2Error("eligible issuer count is inconsistent")
        count = next(iter(counts))
        if sorted(int(row["holding_count"]) for row in scoped) != list(range(1, count + 1)):
            raise NdxDynamicShadowFreshSearchV2Error(f"dynamic k coverage is incomplete: {track}")
        for row in scoped:
            combinations = math.comb(count, int(row["holding_count"]))
            expected_class = EXACT if combinations <= exact_limit else BOUNDED
            if int(row["theoretical_issuer_combinations"]) != combinations or row["job_search_class"] != expected_class:
                raise NdxDynamicShadowFreshSearchV2Error("theoretical combinations or exact/bounded class is forged")
            if (row["global_optimality_claimed"] is not False
                    or row["historical_candidate_replay_allowed"] is not False
                    or row["promotion_allowed"] is not False):
                raise NdxDynamicShadowFreshSearchV2Error("planned shard crossed its evidence boundary")
    return rows


def _shard_checkpoint(root: Path, job: Mapping[str, Any]) -> Path:
    return (root / "shards" / str(job["snapshot_fingerprint"])[:16]
            / str(job["universe_track"]) / str(job["decision_date"])
            / f"holding_count_{int(job['holding_count']):04d}" / "checkpoint.json").resolve()


def verify_controller_checkpoint_inventory(
    jobs: Sequence[Mapping[str, Any]], inventory: Sequence[Mapping[str, Any]], *,
    snapshot_manifest_sha256: str, executor_sha256: str, original_8_sha256: str,
    output_root: str | Path,
) -> list[dict]:
    rows = verify_v2_job_plan(jobs)
    by_key = {str(row["checkpoint_key"]): row for row in rows}
    items = [dict(item) for item in inventory]
    keys = [str(item.get("checkpoint_key") or "") for item in items]
    if any(not key for key in keys) or len(keys) != len(set(keys)) or not set(keys).issubset(by_key):
        raise NdxDynamicShadowFreshSearchV2Error("checkpoint inventory identities are invalid")
    root = Path(output_root).resolve()
    existing = {str(job["checkpoint_key"]) for job in rows if _shard_checkpoint(root, job).is_file()}
    if set(keys) != existing:
        raise NdxDynamicShadowFreshSearchV2Error("checkpoint inventory omits or invents a canonical shard")
    for item in items:
        job = by_key[str(item["checkpoint_key"])]
        expected_coordinate = coordinate_hash(
            job, snapshot_manifest_sha256=snapshot_manifest_sha256,
            executor_sha256=executor_sha256, original_8_sha256=original_8_sha256,
        )
        checkpoint = _shard_checkpoint(root, job)
        if (Path(str(item.get("path") or "")).resolve() != checkpoint
                or item.get("sha256") != file_sha256(checkpoint)
                or item.get("coordinate_hash") != expected_coordinate):
            raise NdxDynamicShadowFreshSearchV2Error("checkpoint canonical path/hash/coordinate changed")
        verify_completed_shard(checkpoint, coordinate_hash=expected_coordinate, expected_job=job)
    return items


def _artifact_jobs(snapshot_path: Path, manifest: Mapping[str, Any]) -> pd.DataFrame:
    item = (manifest.get("artifacts") or {}).get("job_plan") or {}
    filename = str(item.get("filename") or "")
    path = snapshot_path.parent / filename
    if Path(filename).name != filename or not path.is_file() or file_sha256(path) != item.get("sha256"):
        raise NdxDynamicShadowFreshSearchV2Error("sealed job plan binding changed")
    frame = pd.read_csv(path, low_memory=False)
    if len(frame) != int(item.get("rows", -1)):
        raise NdxDynamicShadowFreshSearchV2Error("sealed job plan row count changed")
    verify_v2_job_plan(frame.to_dict("records"))
    return frame


def _v1_executor_sha256() -> str:
    return executor_canonical_sha256({
        "contract_sha256": file_sha256(ROOT / "config/ndx_dynamic_shadow_fresh_search_v1.yaml"),
        "module_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_fresh_search.py"),
        "script_sha256": file_sha256(ROOT / "scripts/ndx_dynamic_shadow_fresh_search.py"),
        "search_kernel_sha256": file_sha256(ROOT / "backtest/ndx_cardinality_discovery.py"),
        "selector_policy_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_candidate_policy.py"),
        "selector_registry_sha256": file_sha256(ROOT / "config/ndx_dynamic_shadow_selector_registry_v1.yaml"),
        "selector_registry_validator_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_selector_registry.py"),
    })


def _controller_sources(snapshot_path: Path) -> dict[str, Path]:
    return {
        "controller_script": ROOT / "scripts/ndx_dynamic_shadow_fresh_search_v2.py",
        "controller_verifier": Path(__file__).resolve(),
        "budget_module": ROOT / "backtest/ndx_dynamic_shadow_search_budget.py",
        "budget_policy": ROOT / "config/ndx_dynamic_shadow_search_budget_v1.yaml",
        "snapshot_manifest": snapshot_path,
        "original_8_manifest": ORIGINAL8,
    }


def write_controller_run(path: str | Path, payload: Mapping[str, Any], *, snapshot_path: Path) -> dict:
    target = Path(path).resolve()
    body = dict(payload)
    body["controller_sources"] = {
        key: {"path": value.resolve().as_posix(), "sha256": file_sha256(value)}
        for key, value in sorted(_controller_sources(snapshot_path).items())
    }
    body["controller_run_sha256"] = canonical_sha256(body)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return verify_controller_run(target)


def verify_controller_run(path: str | Path) -> dict:
    source = Path(path).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    decision_date = str(payload.get("decision_date") or "")
    expected = (CONTROLLER_ROOT / decision_date / "latest.json").resolve()
    if source != expected:
        raise NdxDynamicShadowFreshSearchV2Error("controller progress path is not canonical")
    declared = payload.pop("controller_run_sha256", None)
    if declared != canonical_sha256(payload):
        raise NdxDynamicShadowFreshSearchV2Error("controller progress hash mismatch")
    snapshot_path = (SNAPSHOT_ROOT / decision_date / "manifest.json").resolve()
    sources = _controller_sources(snapshot_path)
    observed = payload.get("controller_sources") or {}
    if set(observed) != set(sources):
        raise NdxDynamicShadowFreshSearchV2Error("controller source set changed")
    for key, source_path in sources.items():
        item = observed[key]
        if Path(item.get("path", "")).resolve() != source_path.resolve() or item.get("sha256") != file_sha256(source_path):
            raise NdxDynamicShadowFreshSearchV2Error(f"controller source changed: {key}")
    snapshot = verify_snapshot_bundle(snapshot_path)
    jobs = _artifact_jobs(snapshot_path, snapshot).to_dict("records")
    _, _, original_hash = load_frozen_original_8_definition(ORIGINAL8)
    executor_hash = _v1_executor_sha256()
    if payload.get("snapshot_manifest_sha256") != file_sha256(snapshot_path) or payload.get("v1_executor_sha256") != executor_hash:
        raise NdxDynamicShadowFreshSearchV2Error("controller input/executor identity changed")
    inventory = payload.get("verified_checkpoint_inventory") or []
    if (payload.get("verified_checkpoint_inventory_sha256") != canonical_sha256(inventory)
            or len(inventory) != int(payload.get("verified_completed_shard_count", -1))):
        raise NdxDynamicShadowFreshSearchV2Error("controller checkpoint inventory summary changed")
    verify_controller_checkpoint_inventory(
        jobs, inventory, snapshot_manifest_sha256=file_sha256(snapshot_path),
        executor_sha256=executor_hash, original_8_sha256=original_hash, output_root=OUTPUT_ROOT,
    )
    if payload.get("partial_or_timed_out_shard_completion_claimed") is not False:
        raise NdxDynamicShadowFreshSearchV2Error("controller progress claims partial completion")
    if payload.get("promotion_allowed") is not False or payload.get("live_allowed") is not False:
        raise NdxDynamicShadowFreshSearchV2Error("controller crossed research boundary")
    payload["controller_run_sha256"] = declared
    return payload


__all__ = ["JOB_FIELDS", "NdxDynamicShadowFreshSearchV2Error", "verify_v2_job_plan",
           "verify_controller_checkpoint_inventory", "write_controller_run", "verify_controller_run"]
