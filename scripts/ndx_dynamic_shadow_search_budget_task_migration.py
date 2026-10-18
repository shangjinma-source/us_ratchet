r"""Build a fail-closed, plan-only migration readiness document.

This script never registers, enables, disables, replaces, or deletes a Windows
Scheduled Task.  It proves that the currently registered v1 selection task is
still bound to its immutable evidence before describing a separately approved
v2 cutover.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"D:\python\python.exe")
OLD_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily"
NEW_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"
OLD_REGISTRATION = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/selection_task_registration.json"
OLD_OBSERVATIONS = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/selection_task_registration_observations.jsonl"
OLD_OBSERVER = ROOT / "scripts/ndx_dynamic_shadow_selection_task_observation.py"
NEW_ACTIVATION = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json"
NEW_ACTIVATION_SCRIPT = ROOT / "scripts/ndx_dynamic_shadow_activation_v3.py"
NEW_DAILY = ROOT / "scripts/ndx_dynamic_shadow_daily_v2.py"
EXPECTED_ACTIVATION_TYPE = "ndx_dynamic_shadow_activation_v3"
EXPECTED_ACTIVATION_STATUS = "READY_FOR_RESEARCH_AUTOMATION_MIGRATION_PLAN_ONLY"
NEW_ARGUMENTS = f'-B "{NEW_DAILY}" --execute'
SELF_BOUND_SOURCES = {
    "backtest/ndx_dynamic_shadow_activation_v3.py",
    "scripts/ndx_dynamic_shadow_activation_v3.py",
}


class MigrationReadinessError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), cwd=ROOT, check=False, capture_output=True,
        text=True, encoding="utf-8",
    )


def _old_lineage_gate() -> dict[str, Any]:
    required = (OLD_REGISTRATION, OLD_OBSERVATIONS, OLD_OBSERVER)
    if not all(path.is_file() for path in required):
        return {"passed": False, "reason": "OLD_LINEAGE_ARTIFACT_MISSING"}
    completed = _run([str(PYTHON), "-B", str(OLD_OBSERVER), "--verify"])
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        result = {}
    passed = completed.returncode == 0 and result.get("status") == "VERIFIED"
    return {
        "passed": passed,
        "reason": None if passed else "OLD_REGISTRATION_OR_OBSERVATION_DRIFT",
        "registration": {"path": str(OLD_REGISTRATION), "sha256": _sha256(OLD_REGISTRATION)},
        "observation_ledger": {"path": str(OLD_OBSERVATIONS), "sha256": _sha256(OLD_OBSERVATIONS)},
        "observer": {"path": str(OLD_OBSERVER), "sha256": _sha256(OLD_OBSERVER)},
        "verifier_exit_code": completed.returncode,
        "verifier_status": result.get("status"),
    }


def _source_binding(manifest: Mapping[str, Any], path: Path) -> Mapping[str, Any] | None:
    wanted = path.resolve()
    bindings = manifest.get("canonical_source_bindings", manifest.get("inputs", []))
    items = list(bindings.values()) if isinstance(bindings, Mapping) else bindings
    for raw in items if isinstance(items, (list, tuple)) else []:
        if not isinstance(raw, Mapping) or not raw.get("path"):
            continue
        candidate = Path(str(raw["path"]))
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.resolve() == wanted:
            return raw
    return None


def _canonical_bound_file(item: Mapping[str, Any], *, expected: Path | None = None) -> bool:
    try:
        path = Path(str(item["path"])).resolve()
        if expected is not None and path != expected.resolve():
            return False
        return path.is_file() and str(item["sha256"]) == _sha256(path)
    except (KeyError, OSError, ValueError):
        return False


def _p0_activation_evidence(manifest: Mapping[str, Any]) -> dict[str, Any]:
    inputs = manifest.get("inputs")
    self_bound = isinstance(inputs, Mapping) and SELF_BOUND_SOURCES.issubset(inputs)
    if self_bound:
        self_bound = all(
            _canonical_bound_file(inputs[relative], expected=ROOT / relative)
            for relative in SELF_BOUND_SOURCES
        )

    controller = manifest.get("controller_verifier")
    controller_bound = (
        isinstance(controller, Mapping)
        and set(controller) == {
            "controller_path", "controller_sha256", "verified",
            "verifier_path", "verifier_sha256",
        }
        and controller.get("verified") is True
    )
    for prefix in ("controller", "verifier"):
        if not controller_bound:
            break
        controller_bound = _canonical_bound_file({
            "path": controller.get(f"{prefix}_path"),
            "sha256": controller.get(f"{prefix}_sha256"),
        })

    proof_ok = False
    proof_reason = "SYNTHETIC_CHECKPOINT_PROOF_MISSING"
    synthetic_item = manifest.get("synthetic_e2e")
    if isinstance(synthetic_item, Mapping) and _canonical_bound_file(synthetic_item):
        try:
            synthetic = json.loads(Path(str(synthetic_item["path"])).read_text(encoding="utf-8"))
            scenarios = synthetic.get("scenarios", {})
            proof = scenarios.get("checkpoint_proof", {})
            dual = scenarios.get("dual_track_full_k", {})
            tracks = dual.get("tracks", {})
            malicious = scenarios.get("malicious_rejections", {})
            claims = synthetic.get("claims", {})
            proof_ok = (
                set(proof) == {
                    "bogus_self_consistent_checkpoint_rejected",
                    "caller_supplied_keys_can_activate",
                    "controller_run_rebuilt_with_canonical_hashes",
                    "real_temp_checkpoint_verified",
                    "verified_checkpoint_count",
                }
                and proof.get("real_temp_checkpoint_verified") is True
                and proof.get("controller_run_rebuilt_with_canonical_hashes") is True
                and proof.get("bogus_self_consistent_checkpoint_rejected") is True
                and proof.get("caller_supplied_keys_can_activate") is False
                and proof.get("verified_checkpoint_count") == 40
                and set(dual) == {"tracks", "verified"}
                and dual.get("verified") is True
                and set(tracks) == {"strict_technology", "technology_plus_adjacent"}
                and all(values == list(range(1, 21)) for values in tracks.values())
                and set(malicious) == {
                    "bounded_masquerading_as_exact", "duplicate", "evil_search_class",
                    "missing_k", "missing_track", "unknown_job_field",
                }
                and all(value is True for value in malicious.values())
                and claims.get("real_checkpoint_and_controller_verifiers_exercised") is True
                and claims.get("dual_track_full_dynamic_k_verified") is True
                and claims.get("malicious_job_plans_all_rejected") is True
                and set(claims) == {
                    "complete_role_seal_allowed_before_deadline",
                    "counts_as_prospective_performance_evidence",
                    "dual_track_full_dynamic_k_verified", "live_allowed",
                    "malicious_job_plans_all_rejected",
                    "near_deadline_large_exact_launch_refused",
                    "partial_aggregation_allowed", "promotion_allowed",
                    "real_checkpoint_and_controller_verifiers_exercised",
                    "resume_uses_verified_checkpoint_only",
                }
                and claims.get("counts_as_prospective_performance_evidence") is False
                and claims.get("promotion_allowed") is False
                and claims.get("live_allowed") is False
            )
            proof_reason = None if proof_ok else "DUAL_TRACK_FULL_K_CHECKPOINT_PROOF_INVALID"
        except (OSError, ValueError, json.JSONDecodeError):
            proof_reason = "SYNTHETIC_CHECKPOINT_PROOF_INVALID"
    return {
        "passed": self_bound and controller_bound and proof_ok,
        "activation_self_module_and_cli_hash_bound": self_bound,
        "controller_verifier_and_hash_bound": controller_bound,
        "dual_track_full_k_real_checkpoint_proof": proof_ok,
        "reason": None if self_bound and controller_bound and proof_ok else proof_reason,
    }


def _activation_and_action_gate() -> dict[str, Any]:
    required = (PYTHON, NEW_ACTIVATION, NEW_ACTIVATION_SCRIPT, NEW_DAILY)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {"passed": False, "reason": "VERSIONED_LINEAGE_NOT_YET_MATERIALIZED", "missing": missing}
    try:
        manifest = json.loads(NEW_ACTIVATION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "reason": f"ACTIVATION_MANIFEST_INVALID:{type(exc).__name__}"}
    completed = _run([
        str(PYTHON), "-B", str(NEW_ACTIVATION_SCRIPT), "--verify-activation-manifest",
    ])
    daily_binding = _source_binding(manifest, NEW_DAILY)
    daily_sha = _sha256(NEW_DAILY)
    binding_matches = bool(daily_binding and str(daily_binding.get("sha256")) == daily_sha)
    guards = manifest.get("guards", {})
    p0_evidence = _p0_activation_evidence(manifest)
    passed = (
        completed.returncode == 0
        and manifest.get("manifest_type") == EXPECTED_ACTIVATION_TYPE
        and manifest.get("status") == EXPECTED_ACTIVATION_STATUS
        and binding_matches
        and p0_evidence["passed"]
        and guards.get("external_task_migration_performed") is False
        and guards.get("old_and_new_task_parallel_enable_allowed") is False
        and guards.get("promotion_allowed") is False
        and guards.get("live_allowed") is False
    )
    return {
        "passed": passed,
        "reason": None if passed else "NEW_ACTIVATION_ACTION_OR_HASH_GATE_FAILED",
        "manifest": {"path": str(NEW_ACTIVATION), "sha256": _sha256(NEW_ACTIVATION)},
        "manifest_type": manifest.get("manifest_type"),
        "status": manifest.get("status"),
        "verifier_exit_code": completed.returncode,
        "p0_evidence": p0_evidence,
        "action": {
            "execute": str(PYTHON), "arguments": NEW_ARGUMENTS,
            "working_directory": str(ROOT), "script_sha256": daily_sha,
            "activation_source_binding_matches": binding_matches,
        },
    }


def _task_inventory() -> list[dict[str, Any]]:
    command = r'''
Get-ScheduledTask | ForEach-Object {
  $task = $_
  foreach ($action in @($task.Actions)) {
    [ordered]@{
      task_name = [string]$task.TaskName
      enabled = ([string]$task.State -ne "Disabled")
      state = [string]$task.State
      execute = [string]$action.Execute
      arguments = [string]$action.Arguments
    }
  }
} | ConvertTo-Json -Depth 5 -Compress
'''
    completed = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command])
    if completed.returncode != 0:
        raise MigrationReadinessError("cannot enumerate Scheduled Tasks")
    raw = json.loads(completed.stdout or "[]")
    return [raw] if isinstance(raw, Mapping) else list(raw)


def _openclaw_duplicates() -> list[dict[str, Any]]:
    path = Path(os.environ.get("USERPROFILE", "")) / ".openclaw/cron/jobs.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [{"name": "PARSE_ERROR_FAIL_CLOSED", "enabled": True}]
    jobs = raw.get("jobs", []) if isinstance(raw, Mapping) else raw
    found = []
    for job in jobs if isinstance(jobs, list) else []:
        text = json.dumps(job, ensure_ascii=False)
        if "ndx_dynamic_shadow_daily" in text or "dynamic_shadow_selection" in text:
            if job.get("enabled") is True:
                found.append({"name": str(job.get("name", "")), "enabled": True})
    return found


def _scheduler_gate(inventory: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    relevant = []
    for item in inventory:
        text = f'{item.get("execute", "")} {item.get("arguments", "")}'
        if "ndx_dynamic_shadow_daily" in text or "dynamic_shadow_selection" in str(item.get("task_name", "")):
            relevant.append(dict(item))
    old = [item for item in relevant if item.get("task_name") == OLD_TASK]
    new = [item for item in relevant if item.get("task_name") == NEW_TASK]
    third = [item for item in relevant if item.get("task_name") not in {OLD_TASK, NEW_TASK} and item.get("enabled")]
    openclaw = _openclaw_duplicates()
    old_enabled = len(old) == 1 and old[0].get("enabled") is True
    passed = old_enabled and not new and not third and not openclaw
    return {
        "passed": passed,
        "expected_predecessor_present_and_enabled": old_enabled,
        "new_task_absent": not new,
        "unexpected_active_windows": third,
        "active_openclaw_duplicates": openclaw,
        "old_and_new_parallel_enable_allowed": False,
    }


def build_readiness(*, inventory: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    old_gate = _old_lineage_gate()
    new_gate = _activation_and_action_gate()
    scheduler_gate = _scheduler_gate(_task_inventory() if inventory is None else inventory)
    passed = old_gate.get("passed") is True and new_gate.get("passed") is True and scheduler_gate["passed"]
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_search_budget_task_migration_readiness",
        "mode": "PLAN_ONLY",
        "status": "READY_FOR_EXPLICITLY_AUTHORIZED_ATOMIC_MIGRATION" if passed else "BLOCKED_FAIL_CLOSED",
        "migration_allowed_by_this_run": False,
        "scheduled_task_mutation_performed": False,
        "old_task": OLD_TASK,
        "new_task": NEW_TASK,
        "old_lineage_gate": old_gate,
        "new_activation_and_action_gate": new_gate,
        "duplicate_scheduler_gate": scheduler_gate,
        "desired_new_task_settings": {
            "start_when_available": True,
            "disallow_start_if_on_batteries": False,
            "stop_if_going_on_batteries": False,
            "multiple_instances": "IGNORE_NEW",
            "execution_time_limit": "PT11H",
        },
        "atomic_cutover_contract": [
            "VERIFY_OLD_REGISTRATION_AND_LATEST_OBSERVATION",
            "VERIFY_NEW_ACTIVATION_AND_EXACT_ACTION_HASH",
            "WITH_SEPARATE_APPROVAL_REGISTER_NEW_TASK_DISABLED",
            "VERIFY_NEW_DISABLED_TASK_AND_CAPTURE_NEW_IMMUTABLE_EVIDENCE",
            "ATOMICALLY_DISABLE_OLD_AND_ENABLE_NEW_WITHOUT_PARALLEL_RUN",
            "APPEND_POST_CUTOVER_OBSERVATIONS_FOR_BOTH_LINEAGES",
        ],
        "rollback_contract": {
            "delete_either_task_allowed": False,
            "action": "DISABLE_NEW_THEN_REENABLE_OLD",
            "requires_old_registration_and_observation_reverification": True,
            "preserve_both_evidence_lineages": True,
        },
        "protected_live_files_or_orders_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", action="store_true")
    args = parser.parse_args()
    if not args.readiness:
        parser.error("only --readiness is supported")
    try:
        result = build_readiness()
    except Exception as exc:
        print(f"migration readiness fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"].startswith("READY_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
