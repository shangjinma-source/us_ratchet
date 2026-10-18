"""Rebuildable activation-v3 gate for the unscheduled budgeted controller."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backtest.ndx_dynamic_shadow_activation_v2 import (
    _activation_source_paths, validate_versioned_activation_contracts,
    verify_activation_v2_manifest, verify_append_only_calendar_prefix,
    verify_synthetic_e2e_manifest,
)
from backtest.ndx_dynamic_shadow_search_budget import build_deadline_budget_plan
from backtest.ndx_dynamic_shadow_fresh_search import coordinate_hash, write_completed_shard, verify_completed_shard
from backtest.ndx_dynamic_shadow_fresh_search_v2 import (
    NdxDynamicShadowFreshSearchV2Error, verify_v2_job_plan,
    verify_controller_checkpoint_inventory,
)
from data.versioning import file_sha256


class NdxDynamicShadowActivationV3Error(ValueError):
    pass


SOURCES = (
    "config/ndx_dynamic_shadow_search_budget_v1.yaml",
    "backtest/ndx_dynamic_shadow_search_budget.py",
    "scripts/ndx_dynamic_shadow_search_budget.py",
    "scripts/ndx_dynamic_shadow_fresh_search_v2.py",
    "scripts/ndx_dynamic_shadow_daily_v2.py",
    "backtest/ndx_dynamic_shadow_fresh_search_v2.py",
    "backtest/ndx_dynamic_shadow_activation_v3.py",
    "scripts/ndx_dynamic_shadow_activation_v3.py",
    "scripts/ndx_dynamic_shadow_fresh_search.py",
    "scripts/ndx_dynamic_shadow_daily.py",
    "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json",
)
SYNTHETIC = "data/cache/research/ndx_dynamic_shadow_activation_v3/synthetic_budget_e2e.json"
MANIFEST = "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json"


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _archive_existing_activation(root: Path) -> None:
    manifest_path = (root / MANIFEST).resolve()
    if not manifest_path.is_file():
        return
    digest = file_sha256(manifest_path)
    archive = manifest_path.parent / "archive" / digest
    manifest_copy = archive / "manifest.json"
    synthetic_path = (root / SYNTHETIC).resolve()
    archive.mkdir(parents=True, exist_ok=True)
    if manifest_copy.exists() and manifest_copy.read_bytes() != manifest_path.read_bytes():
        raise NdxDynamicShadowActivationV3Error("activation archive collision")
    if not manifest_copy.exists():
        manifest_copy.write_bytes(manifest_path.read_bytes())
    if synthetic_path.is_file():
        synthetic_copy = archive / "synthetic_budget_e2e.json"
        if synthetic_copy.exists() and synthetic_copy.read_bytes() != synthetic_path.read_bytes():
            raise NdxDynamicShadowActivationV3Error("synthetic archive collision")
        if not synthetic_copy.exists():
            synthetic_copy.write_bytes(synthetic_path.read_bytes())
    evidence = {
        "archived_activation_sha256": digest,
        "archived_synthetic_sha256": file_sha256(synthetic_path) if synthetic_path.is_file() else None,
    }
    evidence_path = archive / "archive_evidence.json"
    if not evidence_path.exists():
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jobs() -> list[dict]:
    return [
        {"checkpoint_key": "sealed/track/k1", "universe_track": "strict_technology",
         "holding_count": 1, "job_search_class": "EXACT_ENUMERATION",
         "theoretical_issuer_combinations": 500_000},
        {"checkpoint_key": "sealed/track/k2", "universe_track": "strict_technology",
         "holding_count": 2, "job_search_class": "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND",
         "theoretical_issuer_combinations": 2_000_000},
    ]


def _full_k_jobs(issuer_count: int = 20) -> list[dict]:
    rows = []
    for track in ("strict_technology", "technology_plus_adjacent"):
        for k in range(1, issuer_count + 1):
            combinations = math.comb(issuer_count, k)
            rows.append({
                "snapshot_fingerprint": "1" * 64,
                "checkpoint_key": f"sealed/{track}/k{k}",
                "universe_track": track,
                "decision_date": "2026-10-01",
                "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
                "decision_data_end": "2026-10-01",
                "eligible_security_count": issuer_count,
                "eligible_issuer_count": issuer_count,
                "holding_count": k,
                "one_security_per_issuer_required": True,
                "job_search_class": (
                    "EXACT_ENUMERATION" if combinations <= 50_000
                    else "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"
                ),
                "theoretical_issuer_combinations": combinations,
                "global_optimality_claimed": False,
                "search_completion_status": "PLANNED_NOT_EXECUTED",
                "bounded_search_disclosure": (
                    "EXHAUSTIVE_ENUMERATION_REQUIRED_NOT_YET_EXECUTED"
                    if combinations <= 50_000 else "HEURISTIC_NO_GLOBAL_OPTIMALITY_CLAIM"
                ),
                "historical_candidate_replay_allowed": False,
                "promotion_allowed": False,
            })
    return rows


def _rejected(jobs: list[dict]) -> bool:
    try:
        verify_v2_job_plan(jobs)
    except NdxDynamicShadowFreshSearchV2Error:
        return True
    return False


def _checkpoint_and_controller_proof() -> dict:
    jobs = _full_k_jobs()
    snapshot_hash, executor_hash, original_hash = "2" * 64, "3" * 64, "4" * 64
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        inventory = []
        for job in jobs:
            identity = coordinate_hash(
                job, snapshot_manifest_sha256=snapshot_hash,
                executor_sha256=executor_hash, original_8_sha256=original_hash,
            )
            checkpoint_dir = (root / "shards" / job["snapshot_fingerprint"][:16]
                              / job["universe_track"] / job["decision_date"]
                              / f"holding_count_{job['holding_count']:04d}")
            results = pd.DataFrame([{"coordinate_hash": identity, "portfolio_id": "synthetic"}])
            audit = {"search_audit": {
                "snapshot_fingerprint": job["snapshot_fingerprint"],
                "checkpoint_key": job["checkpoint_key"],
                "job_search_class": job["job_search_class"],
                "historical_candidate_replay_used": False, "promotion_allowed": False,
            }}
            write_completed_shard(checkpoint_dir, results, audit, coordinate_hash=identity)
            checkpoint_path = checkpoint_dir / "checkpoint.json"
            verify_completed_shard(checkpoint_path, coordinate_hash=identity, expected_job=job)
            inventory.append({"checkpoint_key": job["checkpoint_key"], "coordinate_hash": identity,
                              "path": checkpoint_path.resolve().as_posix(), "sha256": file_sha256(checkpoint_path)})
        verify_controller_checkpoint_inventory(
            jobs, inventory, snapshot_manifest_sha256=snapshot_hash,
            executor_sha256=executor_hash, original_8_sha256=original_hash, output_root=root,
        )
        bogus = [dict(item) for item in inventory]
        bogus[0]["path"] = (root / "bogus.json").as_posix()
        bogus_rejected = False
        try:
            verify_controller_checkpoint_inventory(
                jobs, bogus, snapshot_manifest_sha256=snapshot_hash,
                executor_sha256=executor_hash, original_8_sha256=original_hash, output_root=root,
            )
        except NdxDynamicShadowFreshSearchV2Error:
            bogus_rejected = True
    return {
        "real_temp_checkpoint_verified": True,
        "verified_checkpoint_count": len(jobs),
        "controller_run_rebuilt_with_canonical_hashes": True,
        "caller_supplied_keys_can_activate": False,
        "bogus_self_consistent_checkpoint_rejected": bogus_rejected,
    }


def _rebuild_scenarios() -> dict[str, dict]:
    now = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    jobs = _jobs()
    near = build_deadline_budget_plan(
        jobs, verified_completed_checkpoint_keys=[], now_utc=now,
        role_seal_deadline_utc=now + timedelta(minutes=20),
    )
    resume = build_deadline_budget_plan(
        jobs, verified_completed_checkpoint_keys=[jobs[0]["checkpoint_key"]], now_utc=now,
        role_seal_deadline_utc=now + timedelta(hours=2),
    )
    complete = build_deadline_budget_plan(
        jobs, verified_completed_checkpoint_keys=[job["checkpoint_key"] for job in jobs],
        now_utc=now, role_seal_deadline_utc=now + timedelta(minutes=5),
    )
    full = _full_k_jobs()
    verify_v2_job_plan(full)
    missing_track = [row for row in full if row["universe_track"] == "strict_technology"]
    missing_k = [row for row in full if not (
        row["universe_track"] == "strict_technology" and row["holding_count"] == 3
    )]
    duplicate = full + [dict(full[0])]
    evil = [dict(row) for row in full]
    evil[0]["job_search_class"] = "EVIL"
    unknown = [dict(row) for row in full]
    unknown[0]["unknown_future_runner_override"] = True
    bounded_as_exact = [dict(row) for row in full]
    bounded_row = next(row for row in bounded_as_exact if row["job_search_class"].startswith("MULTI"))
    bounded_row["job_search_class"] = "EXACT_ENUMERATION"
    return {
        "near_deadline_exact_refused": near,
        "verified_resume": resume,
        "complete": complete,
        "checkpoint_proof": _checkpoint_and_controller_proof(),
        "dual_track_full_k": {
            "verified": True,
            "tracks": {track: list(range(1, 21)) for track in (
                "strict_technology", "technology_plus_adjacent"
            )},
        },
        "malicious_rejections": {
            "missing_track": _rejected(missing_track),
            "missing_k": _rejected(missing_k),
            "duplicate": _rejected(duplicate),
            "evil_search_class": _rejected(evil),
            "unknown_job_field": _rejected(unknown),
            "bounded_masquerading_as_exact": _rejected(bounded_as_exact),
        },
    }


def build_synthetic_budget_e2e(repository_root: str | Path) -> dict:
    root = Path(repository_root).resolve()
    scenarios = _rebuild_scenarios()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_activation_v3_synthetic_budget_e2e",
        "status": "SYNTHETIC_DEADLINE_RESUME_GATES_VERIFIED",
        "scenarios": scenarios,
        "claims": {
            "near_deadline_large_exact_launch_refused": not scenarios["near_deadline_exact_refused"]["next_shard_admitted"],
            "resume_uses_verified_checkpoint_only": scenarios["verified_resume"]["pending_shard_count"] == 1,
            "partial_aggregation_allowed": False,
            "complete_role_seal_allowed_before_deadline": scenarios["complete"]["role_seal_allowed"],
            "real_checkpoint_and_controller_verifiers_exercised": (
                scenarios["checkpoint_proof"]["real_temp_checkpoint_verified"]
                and scenarios["checkpoint_proof"]["controller_run_rebuilt_with_canonical_hashes"]
                and scenarios["checkpoint_proof"]["verified_checkpoint_count"] == 40
                and scenarios["checkpoint_proof"]["bogus_self_consistent_checkpoint_rejected"]
            ),
            "dual_track_full_dynamic_k_verified": scenarios["dual_track_full_k"]["verified"],
            "malicious_job_plans_all_rejected": all(scenarios["malicious_rejections"].values()),
            "counts_as_prospective_performance_evidence": False,
            "promotion_allowed": False,
            "live_allowed": False,
        },
    }
    payload["manifest_sha256"] = _canonical_hash(payload)
    _atomic(root / SYNTHETIC, payload)
    return verify_synthetic_budget_e2e(root / SYNTHETIC)


def verify_synthetic_budget_e2e(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    declared = payload.pop("manifest_sha256", None)
    if declared != _canonical_hash(payload):
        raise NdxDynamicShadowActivationV3Error("synthetic budget manifest hash mismatch")
    expected = _rebuild_scenarios()
    if payload.get("scenarios") != expected:
        raise NdxDynamicShadowActivationV3Error("synthetic budget scenarios do not rebuild")
    claims = payload.get("claims") or {}
    if not (
        claims.get("near_deadline_large_exact_launch_refused") is True
        and claims.get("resume_uses_verified_checkpoint_only") is True
        and claims.get("partial_aggregation_allowed") is False
        and claims.get("complete_role_seal_allowed_before_deadline") is True
        and claims.get("real_checkpoint_and_controller_verifiers_exercised") is True
        and claims.get("dual_track_full_dynamic_k_verified") is True
        and claims.get("malicious_job_plans_all_rejected") is True
        and claims.get("promotion_allowed") is False
        and claims.get("live_allowed") is False
    ):
        raise NdxDynamicShadowActivationV3Error("synthetic budget claims changed")
    payload["manifest_sha256"] = declared
    return payload


def build_activation_v3_manifest(repository_root: str | Path) -> dict:
    root = Path(repository_root).resolve()
    _archive_existing_activation(root)
    verify_activation_v2_manifest(
        root / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json",
        repository_root=root,
    )
    synthetic = build_synthetic_budget_e2e(root)
    inputs = {}
    for relative in SOURCES:
        path = (root / relative).resolve()
        if not path.is_file():
            raise NdxDynamicShadowActivationV3Error(f"activation source missing: {relative}")
        inputs[relative] = {"path": path.as_posix(), "sha256": file_sha256(path)}
    synthetic_path = root / SYNTHETIC
    payload = {
        "schema_version": 3,
        "manifest_type": "ndx_dynamic_shadow_activation_v3",
        "status": "READY_FOR_RESEARCH_AUTOMATION_MIGRATION_PLAN_ONLY",
        "lineage": {
            "activation_v2_sha256": file_sha256(root / SOURCES[-1]),
            "v1_artifact_namespace_preserved": True,
            "registered_v1_task_changed": False,
        },
        "inputs": inputs,
        "synthetic_e2e": {"path": synthetic_path.resolve().as_posix(),
                          "sha256": file_sha256(synthetic_path),
                          "manifest_sha256": synthetic["manifest_sha256"]},
        "controller_verifier": {
            "controller_path": (root / "scripts/ndx_dynamic_shadow_fresh_search_v2.py").resolve().as_posix(),
            "controller_sha256": file_sha256(root / "scripts/ndx_dynamic_shadow_fresh_search_v2.py"),
            "verifier_path": (root / "backtest/ndx_dynamic_shadow_fresh_search_v2.py").resolve().as_posix(),
            "verifier_sha256": file_sha256(root / "backtest/ndx_dynamic_shadow_fresh_search_v2.py"),
            "verified": True,
        },
        "guards": {
            "deadline_aware_one_shard_launch": True,
            "verified_checkpoint_resume_only": True,
            "partial_aggregation_forbidden": True,
            "role_seal_reserve_seconds": 900,
            "role_seal_deadline_local": "21:30:00 Asia/Shanghai",
            "old_and_new_task_parallel_enable_allowed": False,
            "external_task_migration_performed": False,
            "promotion_allowed": False,
            "live_allowed": False,
        },
    }
    payload["manifest_sha256"] = _canonical_hash(payload)
    _atomic(root / MANIFEST, payload)
    return verify_activation_v3_manifest(root / MANIFEST, repository_root=root)


def _verify_activation_v2_static(root: Path) -> dict:
    path = root / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    declared = unsigned.pop("manifest_sha256", None)
    if (declared != _canonical_hash(unsigned)
            or payload.get("manifest_type") != "ndx_dynamic_shadow_activation_v2"
            or payload.get("status") != "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION"):
        raise NdxDynamicShadowActivationV3Error("activation v2 static identity/hash changed")
    if payload.get("versioned_contracts") != validate_versioned_activation_contracts(root):
        raise NdxDynamicShadowActivationV3Error("activation v2 static contracts changed")
    bindings = payload.get("canonical_source_bindings") or {}
    sources = _activation_source_paths(root)
    if set(bindings) != set(sources):
        raise NdxDynamicShadowActivationV3Error("activation v2 static source set changed")
    for name, source in sources.items():
        item = bindings[name]
        if Path(item.get("path", "")).resolve() != source or item.get("sha256") != file_sha256(source):
            raise NdxDynamicShadowActivationV3Error(f"activation v2 static source changed: {name}")
    synthetic_item = payload.get("synthetic_e2e") or {}
    synthetic_path = Path(str(synthetic_item.get("path") or "")).resolve()
    synthetic = verify_synthetic_e2e_manifest(synthetic_path, repository_root=root)
    if (synthetic_item.get("sha256") != file_sha256(synthetic_path)
            or synthetic_item.get("manifest_sha256") != synthetic["manifest_sha256"]):
        raise NdxDynamicShadowActivationV3Error("activation v2 static synthetic changed")
    calendar = payload.get("observed_calendar") or {}
    prefix = calendar.get("prefix_snapshot") or {}
    prefix_path = Path(str(prefix.get("path") or "")).resolve()
    ledger_path = Path(str(calendar.get("canonical_ledger_path") or "")).resolve()
    if (not prefix_path.is_file() or prefix.get("sha256") != file_sha256(prefix_path)
            or not ledger_path.is_file()):
        raise NdxDynamicShadowActivationV3Error("activation v2 static calendar prefix changed")
    verify_append_only_calendar_prefix(prefix_path, ledger_path)
    return payload


def verify_activation_v3_static_sources(
    path: str | Path, *, repository_root: str | Path,
) -> dict:
    """Verify immutable code/contracts and calendar prefix before refreshing its tail."""
    root = Path(repository_root).resolve()
    canonical = (root / MANIFEST).resolve()
    if Path(path).resolve() != canonical:
        raise NdxDynamicShadowActivationV3Error("activation v3 path is not canonical")
    payload = json.loads(canonical.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    declared = unsigned.pop("manifest_sha256", None)
    if (declared != _canonical_hash(unsigned)
            or payload.get("status") != "READY_FOR_RESEARCH_AUTOMATION_MIGRATION_PLAN_ONLY"):
        raise NdxDynamicShadowActivationV3Error("activation v3 static identity/hash changed")
    _verify_activation_v2_static(root)
    inputs = payload.get("inputs") or {}
    if set(inputs) != set(SOURCES):
        raise NdxDynamicShadowActivationV3Error("activation v3 static source set changed")
    for relative, item in inputs.items():
        source = (root / relative).resolve()
        if Path(item.get("path", "")).resolve() != source or item.get("sha256") != file_sha256(source):
            raise NdxDynamicShadowActivationV3Error(f"activation v3 static source changed: {relative}")
    synthetic_path = (root / SYNTHETIC).resolve()
    synthetic = verify_synthetic_budget_e2e(synthetic_path)
    if (payload.get("synthetic_e2e") or {}).get("manifest_sha256") != synthetic["manifest_sha256"]:
        raise NdxDynamicShadowActivationV3Error("activation v3 static synthetic changed")
    return payload


def verify_activation_v3_manifest(path: str | Path, *, repository_root: str | Path) -> dict:
    root = Path(repository_root).resolve()
    canonical = (root / MANIFEST).resolve()
    if Path(path).resolve() != canonical:
        raise NdxDynamicShadowActivationV3Error("activation v3 path is not canonical")
    verify_activation_v3_static_sources(canonical, repository_root=root)
    payload = json.loads(canonical.read_text(encoding="utf-8"))
    declared = payload.pop("manifest_sha256", None)
    if declared != _canonical_hash(payload):
        raise NdxDynamicShadowActivationV3Error("activation v3 manifest hash mismatch")
    if payload.get("status") != "READY_FOR_RESEARCH_AUTOMATION_MIGRATION_PLAN_ONLY":
        raise NdxDynamicShadowActivationV3Error("activation v3 status changed")
    verify_activation_v2_manifest(root / SOURCES[-1], repository_root=root)
    if set(payload.get("inputs") or {}) != set(SOURCES):
        raise NdxDynamicShadowActivationV3Error("activation v3 source set changed")
    for relative, item in payload["inputs"].items():
        source = (root / relative).resolve()
        if Path(item.get("path", "")).resolve() != source or file_sha256(source) != item.get("sha256"):
            raise NdxDynamicShadowActivationV3Error(f"activation v3 source changed: {relative}")
    synthetic_path = root / SYNTHETIC
    synthetic = verify_synthetic_budget_e2e(synthetic_path)
    item = payload.get("synthetic_e2e") or {}
    if item.get("sha256") != file_sha256(synthetic_path) or item.get("manifest_sha256") != synthetic["manifest_sha256"]:
        raise NdxDynamicShadowActivationV3Error("activation v3 synthetic binding changed")
    controller_item = payload.get("controller_verifier") or {}
    controller_path = (root / "scripts/ndx_dynamic_shadow_fresh_search_v2.py").resolve()
    verifier_path = (root / "backtest/ndx_dynamic_shadow_fresh_search_v2.py").resolve()
    if not (
        Path(controller_item.get("controller_path", "")).resolve() == controller_path
        and controller_item.get("controller_sha256") == file_sha256(controller_path)
        and Path(controller_item.get("verifier_path", "")).resolve() == verifier_path
        and controller_item.get("verifier_sha256") == file_sha256(verifier_path)
        and controller_item.get("verified") is True
    ):
        raise NdxDynamicShadowActivationV3Error("activation v3 controller verifier binding changed")
    guards = payload.get("guards") or {}
    if not (
        guards.get("deadline_aware_one_shard_launch") is True
        and guards.get("verified_checkpoint_resume_only") is True
        and guards.get("partial_aggregation_forbidden") is True
        and guards.get("role_seal_reserve_seconds") == 900
        and guards.get("old_and_new_task_parallel_enable_allowed") is False
        and guards.get("external_task_migration_performed") is False
        and guards.get("promotion_allowed") is False
        and guards.get("live_allowed") is False
    ):
        raise NdxDynamicShadowActivationV3Error("activation v3 guards changed")
    payload["manifest_sha256"] = declared
    return payload


__all__ = ["build_activation_v3_manifest", "build_synthetic_budget_e2e",
           "verify_activation_v3_manifest", "verify_activation_v3_static_sources",
           "verify_synthetic_budget_e2e"]
