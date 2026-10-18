"""Deadline-aware controller around the immutable v1 fresh-search engine.

The controller admits at most one missing shard per invocation, using only
cryptographically verified v1 checkpoints.  It keeps the v1 artifact namespace
so an eventual task migration does not fork prospective evidence.  It does not
register or alter any task.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.ndx_dynamic_shadow_fresh_search as v1
from backtest.ndx_dynamic_shadow_candidate_snapshot import verify_snapshot_bundle
from backtest.ndx_dynamic_shadow_fresh_search import (
    canonical_sha256, coordinate_hash, load_frozen_original_8_definition,
    verify_completed_shard, verify_final_candidate_snapshot,
    verify_final_role_seal_record,
)
from backtest.ndx_dynamic_shadow_search_budget import build_deadline_budget_plan
from backtest.ndx_dynamic_shadow_fresh_search_v2 import (
    verify_v2_job_plan, write_controller_run,
)
from data.versioning import file_sha256

OUTPUT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_fresh_search_v1"
CONTROL_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_fresh_search_v2_controller"
ORIGINAL8 = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"


def _executor_hash() -> str:
    return canonical_sha256({
        "contract_sha256": file_sha256(ROOT / "config/ndx_dynamic_shadow_fresh_search_v1.yaml"),
        "module_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_fresh_search.py"),
        "script_sha256": file_sha256(ROOT / "scripts/ndx_dynamic_shadow_fresh_search.py"),
        "search_kernel_sha256": file_sha256(ROOT / "backtest/ndx_cardinality_discovery.py"),
        "selector_policy_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_candidate_policy.py"),
        "selector_registry_sha256": file_sha256(ROOT / "config/ndx_dynamic_shadow_selector_registry_v1.yaml"),
        "selector_registry_validator_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_selector_registry.py"),
    })


def _verified_completed(snapshot_path: Path, snapshot: dict, jobs: pd.DataFrame) -> tuple[list[str], list[dict]]:
    _, _, original_hash = load_frozen_original_8_definition(ORIGINAL8)
    snapshot_hash = file_sha256(snapshot_path)
    executor_hash = _executor_hash()
    completed: list[str] = []
    inventory: list[dict] = []
    for row in jobs.itertuples(index=False):
        job = row._asdict()
        identity = coordinate_hash(
            job, snapshot_manifest_sha256=snapshot_hash,
            executor_sha256=executor_hash, original_8_sha256=original_hash,
        )
        checkpoint = v1._shard_dir(OUTPUT_ROOT, job) / "checkpoint.json"
        if checkpoint.is_file():
            verify_completed_shard(checkpoint, coordinate_hash=identity, expected_job=job)
            completed.append(str(job["checkpoint_key"]))
            inventory.append({
                "checkpoint_key": str(job["checkpoint_key"]),
                "coordinate_hash": identity,
                "path": checkpoint.resolve().as_posix(),
                "sha256": file_sha256(checkpoint),
            })
    return completed, inventory


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_process_tree(command: list[str], *, timeout_seconds: float) -> int:
    process = subprocess.Popen(
        command, cwd=ROOT,
        start_new_session=(os.name != "nt"),
    )
    try:
        return process.wait(timeout=max(0.001, float(timeout_seconds)))
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        raise


def execute_one(snapshot_path: Path) -> dict:
    snapshot_path = snapshot_path.resolve()
    snapshot = verify_snapshot_bundle(snapshot_path)
    expected = v1.CANONICAL_SNAPSHOT_ROOT / str(snapshot["decision_date"]) / "manifest.json"
    if snapshot_path != expected.resolve():
        raise ValueError("v2 controller requires the canonical sealed decision snapshot")
    from scripts.ndx_dynamic_shadow_candidate_generator import _verify_manifest_seal_record
    _verify_manifest_seal_record(snapshot_path, snapshot)
    jobs = v1._artifact(snapshot_path, snapshot, "job_plan")
    verify_v2_job_plan(jobs.to_dict("records"))
    completed, inventory = _verified_completed(snapshot_path, snapshot, jobs)
    verified_before = len(completed)
    now = datetime.now(timezone.utc)
    deadline = pd.Timestamp(snapshot["conservative_seal_deadline_utc"]).to_pydatetime()
    plan = build_deadline_budget_plan(
        jobs.to_dict("records"), verified_completed_checkpoint_keys=completed,
        now_utc=now, role_seal_deadline_utc=deadline,
    )
    invoked = False
    timed_out = False
    if plan["role_seal_allowed"] or plan["next_shard_admitted"]:
        invoked = True
        timeout = (
            max(1, plan["seconds_to_role_seal_deadline"])
            if plan["role_seal_allowed"]
            else max(1, int(plan["next_shard"]["estimated_budget_seconds"]))
        )
        command = [
            sys.executable, "-B", str(ROOT / "scripts/ndx_dynamic_shadow_fresh_search.py"),
            "--execute", "--resume", "--max-jobs", "1",
            "--snapshot-manifest", str(snapshot_path),
        ]
        try:
            return_code = run_process_tree(command, timeout_seconds=timeout)
            if return_code != 0:
                raise RuntimeError(f"v1 fresh-search shard failed with rc={return_code}")
        except subprocess.TimeoutExpired:
            timed_out = True
        completed, inventory = _verified_completed(snapshot_path, snapshot, jobs)
        plan = build_deadline_budget_plan(
            jobs.to_dict("records"), verified_completed_checkpoint_keys=completed,
            now_utc=datetime.now(timezone.utc), role_seal_deadline_utc=deadline,
        )
    final_path = OUTPUT_ROOT / "final" / str(snapshot["decision_date"]) / "manifest.json"
    final_verified = False
    if final_path.is_file():
        verify_final_candidate_snapshot(final_path)
        verify_final_role_seal_record(
            final_path, OUTPUT_ROOT / "role_seals.jsonl",
            expected_final_root=OUTPUT_ROOT / "final",
        )
        final_verified = True
    result = {
        **plan,
        "controller_manifest_type": "ndx_dynamic_shadow_fresh_search_v2_controller_run",
        "controller_status": (
            "FINAL_ROLE_SEAL_VERIFIED" if final_verified
            else "SHARD_TIMEOUT_INCOMPLETE_RESUMABLE" if timed_out
            else "INCOMPLETE_RESUMABLE_NO_AGGREGATION"
        ),
        "decision_date": str(snapshot["decision_date"]),
        "v1_engine_invoked": invoked,
        "shard_timed_out": timed_out,
        "verified_before_shard_count": verified_before,
        "v1_artifact_namespace_preserved": True,
        "final_role_seal_verified": final_verified,
        "snapshot_manifest_sha256": file_sha256(snapshot_path),
        "v1_executor_sha256": _executor_hash(),
        "verified_checkpoint_inventory": inventory,
        "verified_checkpoint_inventory_sha256": canonical_sha256(inventory),
        "promotion_allowed": False,
        "live_allowed": False,
    }
    latest = CONTROL_ROOT / str(snapshot["decision_date"]) / "latest.json"
    return write_controller_run(latest, result, snapshot_path=snapshot_path)


def execute(snapshot_path: Path) -> dict:
    snapshot = verify_snapshot_bundle(snapshot_path.resolve())
    jobs = v1._artifact(snapshot_path.resolve(), snapshot, "job_plan")
    maximum_iterations = len(jobs) + 1
    result: dict = {}
    for iteration in range(1, maximum_iterations + 1):
        result = execute_one(snapshot_path)
        result["controller_loop_iterations"] = iteration
        if result["final_role_seal_verified"]:
            result["controller_stop_reason"] = "FINAL_ROLE_SEAL_VERIFIED"
            return result
        if result["shard_timed_out"]:
            result["controller_stop_reason"] = "SHARD_TIMEOUT_PROCESS_TREE_TERMINATED"
            return result
        if not result["v1_engine_invoked"]:
            result["controller_stop_reason"] = "DEADLINE_BUDGET_DID_NOT_ADMIT_NEXT_SHARD"
            return result
        if result["verified_completed_shard_count"] <= result["verified_before_shard_count"]:
            result["controller_stop_reason"] = "NO_VERIFIED_PROGRESS_FAIL_CLOSED"
            return result
        if result["pending_shard_count"] and not result["next_shard_admitted"]:
            result["controller_stop_reason"] = "NEXT_SHARD_NOT_ADMITTED_BEFORE_ROLE_SEAL_RESERVE"
            return result
    result["controller_stop_reason"] = "ITERATION_BOUND_REACHED_FAIL_CLOSED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--snapshot-manifest", default="")
    args = parser.parse_args()
    if not args.execute or not args.snapshot_manifest:
        parser.error("--execute and --snapshot-manifest are required")
    try:
        result = execute(Path(args.snapshot_manifest))
    except Exception as exc:
        print(f"fresh-search v2 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
