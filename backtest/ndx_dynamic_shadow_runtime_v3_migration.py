"""Fail-closed readiness for the reviewed-calendar research runtime migration.

This module is read-only.  It validates the fully rebuilt activation-v4 gate,
the exact v3 Scheduled Task action, and the expected three-task pre-cutover
inventory.  Registration, cutover and smoke/rollback are owned by the separate
PowerShell installer and require explicit switches there.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from data.versioning import file_sha256


OLD_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily"
FAILED_V2_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"
NEW_V3_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar"
ACTIVATION_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_activation_v4/manifest.json"
)
DAILY_RELATIVE = Path("scripts/ndx_dynamic_shadow_daily_v3.py")
PYTHON = Path(r"D:\python\python.exe")
NEW_ARGUMENTS_TEMPLATE = '-B "{daily}" --execute'
EXPECTED_SETTINGS = {
    "scheduled_days_of_week_bitmask": 124,
    "scheduled_local_time": "11:20",
    "weeks_interval": 1,
    "start_when_available": True,
    "disallow_start_if_on_batteries": False,
    "stop_if_going_on_batteries": False,
    "multiple_instances": "IGNORE_NEW",
    "execution_time_limit": "PT11H",
    "restart_count": 3,
    "restart_interval": "PT10M",
}
AUTHORITY_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_task_migration_v3/"
    "reviewed_source_manifest.json"
)
AUTHORITY_SOURCES = (
    "config/ndx_dynamic_shadow_runtime_v3_design.yaml",
    "backtest/ndx_dynamic_shadow_runtime_v3_migration.py",
    "scripts/ndx_dynamic_shadow_runtime_v3_migration.py",
    "scripts/migrate_ndx_dynamic_shadow_selection_task_v3.ps1",
    "scripts/ndx_dynamic_shadow_runtime_v3_smoke.py",
    "scripts/ndx_dynamic_shadow_task_migration_notary.py",
    "tests/test_ndx_dynamic_shadow_runtime_v3_migration.py",
    "tests/test_migrate_ndx_dynamic_shadow_selection_task_v3.py",
    "tests/test_ndx_dynamic_shadow_runtime_v3_smoke.py",
)


class RuntimeV3MigrationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_runtime_v3_migration_authority(
    *, repository_root: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    sources: dict[str, dict[str, str]] = {}
    for relative in AUTHORITY_SOURCES:
        path = (root / relative).resolve()
        if not path.is_file():
            raise RuntimeV3MigrationError(f"authority source is missing: {relative}")
        sources[relative] = {"path": path.as_posix(), "sha256": _sha256(path)}
    activation = (root / ACTIVATION_RELATIVE).resolve()
    if not activation.is_file():
        raise RuntimeV3MigrationError("activation-v4 manifest is missing")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_runtime_v3_migration_authority",
        "review_required_before_apply": True,
        "sources": sources,
        "activation_v4_manifest": {
            "path": activation.as_posix(),
            "sha256": _sha256(activation),
        },
        "approved_scheduler_contract": dict(EXPECTED_SETTINGS),
        "boundaries": {
            "research_only": True,
            "apply_by_authority_builder_allowed": False,
            "task_deletion_allowed": False,
            "parallel_old_and_new_enable_allowed": False,
            "live_mutation_allowed": False,
            "orders_allowed": False,
        },
    }
    payload["authority_sha256"] = _canonical_sha256(payload)
    return payload


def verify_runtime_v3_migration_authority(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    source = Path(path).resolve()
    if source != (root / AUTHORITY_RELATIVE).resolve():
        raise RuntimeV3MigrationError("migration authority path is not canonical")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeV3MigrationError("migration authority is missing or invalid") from exc
    if payload != build_runtime_v3_migration_authority(repository_root=root):
        raise RuntimeV3MigrationError("migration authority sources or contract changed")
    return payload


def _activation_gate(root: Path) -> dict[str, Any]:
    manifest_path = (root / ACTIVATION_RELATIVE).resolve()
    daily_path = (root / DAILY_RELATIVE).resolve()
    if not PYTHON.is_file() or not manifest_path.is_file() or not daily_path.is_file():
        return {
            "passed": False,
            "reason": "ACTIVATION_V4_OR_RUNTIME_V3_NOT_MATERIALIZED",
            "activation_manifest_path": manifest_path.as_posix(),
        }
    try:
        from backtest.ndx_dynamic_shadow_activation_v4 import (
            verify_activation_v4_manifest,
        )

        manifest = verify_activation_v4_manifest(manifest_path, repository_root=root)
    except Exception as exc:
        return {
            "passed": False,
            "reason": f"ACTIVATION_V4_FULL_VERIFICATION_FAILED:{type(exc).__name__}",
            "activation_manifest_path": manifest_path.as_posix(),
        }
    source = (manifest.get("sources") or {}).get(DAILY_RELATIVE.as_posix())
    source_bound = (
        isinstance(source, Mapping)
        and Path(str(source.get("path") or "")).resolve() == daily_path
        and source.get("sha256") == file_sha256(daily_path)
    )
    passed = (
        manifest.get("manifest_type") == "ndx_dynamic_shadow_activation_v4"
        and manifest.get("status")
        == "READY_FOR_RESEARCH_RUNTIME_V3_MIGRATION_REVIEW_ONLY"
        and source_bound
        and (manifest.get("boundaries") or {}).get("task_registration_performed") is False
        and (manifest.get("boundaries") or {}).get("promotion_allowed") is False
        and (manifest.get("boundaries") or {}).get("live_mutation_allowed") is False
    )
    return {
        "passed": passed,
        "reason": None if passed else "ACTIVATION_V4_IDENTITY_OR_DAILY_BINDING_CHANGED",
        "activation_manifest_path": manifest_path.as_posix(),
        "activation_manifest_sha256": _sha256(manifest_path),
        "daily_v3_path": daily_path.as_posix(),
        "daily_v3_sha256": _sha256(daily_path),
        "full_verifier_replayed": True,
    }


def _task_inventory() -> list[dict[str, Any]]:
    command = r'''
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-ScheduledTask | ForEach-Object {
  $task = $_
  foreach ($action in @($task.Actions)) {
    [ordered]@{
      task_name = [string]$task.TaskName
      task_path = [string]$task.TaskPath
      enabled = ([string]$task.State -ne "Disabled")
      state = [string]$task.State
      execute = [string]$action.Execute
      arguments = [string]$action.Arguments
    }
  }
} | ConvertTo-Json -Depth 5 -Compress
'''
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeV3MigrationError("cannot inspect Windows Scheduled Tasks")
    value = json.loads(completed.stdout or "[]")
    return [value] if isinstance(value, Mapping) else list(value)


def _process_inventory() -> list[dict[str, Any]]:
    command = r'''
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Process | Select-Object @{n="process_id";e={$_.ProcessId}},@{n="command_line";e={[string]$_.CommandLine}} | ConvertTo-Json -Depth 4 -Compress
'''
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeV3MigrationError("cannot inspect Windows process inventory")
    value = json.loads(completed.stdout or "[]")
    return [value] if isinstance(value, Mapping) else list(value)


def _matching_runtime_processes(
    processes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matched = []
    for item in processes:
        text = str(item.get("command_line") or "").lower()
        if "--execute" not in text:
            continue
        if any(
            name in text
            for name in (
                "ndx_dynamic_shadow_daily.py",
                "ndx_dynamic_shadow_daily_v2.py",
                "ndx_dynamic_shadow_daily_v3.py",
                "ndx_dynamic_shadow_fresh_search.py",
                "ndx_dynamic_shadow_fresh_search_v2.py",
                "ndx_dynamic_shadow_fresh_search_v3.py",
            )
        ):
            matched.append(dict(item))
    return matched


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
        if not isinstance(job, Mapping) or job.get("enabled") is not True:
            continue
        serialized = json.dumps(job, ensure_ascii=False).lower()
        if (
            "ndx_dynamic_shadow_daily" in serialized
            or "dynamic_shadow_selection" in serialized
            or "ndx_dynamic_shadow_fresh_search" in serialized
        ):
            found.append({"name": str(job.get("name", "")), "enabled": True})
    return found


def _task_gate(
    inventory: Sequence[Mapping[str, Any]],
    *,
    openclaw_jobs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    relevant = [
        dict(item) for item in inventory
        if str(item.get("task_name") or "")
        in {OLD_TASK, FAILED_V2_TASK, NEW_V3_TASK}
    ]
    root_relevant = [
        item for item in relevant
        if str(item.get("task_path") or "\\") == "\\"
    ]
    by_name = {
        name: [item for item in root_relevant if item.get("task_name") == name]
        for name in (OLD_TASK, FAILED_V2_TASK, NEW_V3_TASK)
    }
    old_ready = (
        len(by_name[OLD_TASK]) == 1
        and by_name[OLD_TASK][0].get("enabled") is True
        and str(by_name[OLD_TASK][0].get("state")) != "Running"
    )
    failed_v2_disabled = (
        len(by_name[FAILED_V2_TASK]) == 1
        and by_name[FAILED_V2_TASK][0].get("enabled") is False
        and str(by_name[FAILED_V2_TASK][0].get("state")) != "Running"
    )
    new_absent = not by_name[NEW_V3_TASK]
    unexpected_enabled = []
    for item in inventory:
        task_name = str(item.get("task_name") or "")
        task_name_lower = task_name.lower()
        action_text = f'{item.get("execute", "")} {item.get("arguments", "")}'.lower()
        related = (
            "dynamic_shadow_selection" in task_name_lower
            or "ndx_dynamic_shadow_daily" in action_text
            or "ndx_dynamic_shadow_fresh_search" in action_text
        )
        if (
            related
            and not (
                str(item.get("task_path") or "\\") == "\\"
                and task_name in {OLD_TASK, FAILED_V2_TASK, NEW_V3_TASK}
            )
            and item.get("enabled") is True
        ):
            unexpected_enabled.append(dict(item))
    active_openclaw = [dict(item) for item in openclaw_jobs if item.get("enabled") is True]
    passed = (
        old_ready
        and failed_v2_disabled
        and new_absent
        and not unexpected_enabled
        and not active_openclaw
    )
    return {
        "passed": passed,
        "reason": None if passed else "PRE_CUTOVER_THREE_TASK_INVENTORY_CHANGED",
        "old_v1_present_enabled_not_running": old_ready,
        "failed_v2_present_disabled_not_running": failed_v2_disabled,
        "new_v3_absent_before_disabled_registration": new_absent,
        "unexpected_enabled_windows_schedulers": unexpected_enabled,
        "active_openclaw_duplicates": active_openclaw,
        "old_and_new_parallel_enable_allowed": False,
        "task_deletion_allowed": False,
        "observed": relevant,
    }


def build_runtime_v3_migration_readiness(
    *, repository_root: str | Path,
    inventory: Sequence[Mapping[str, Any]] | None = None,
    activation_gate: Mapping[str, Any] | None = None,
    openclaw_jobs: Sequence[Mapping[str, Any]] | None = None,
    processes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    activation = dict(activation_gate) if activation_gate is not None else _activation_gate(root)
    tasks = _task_gate(
        _task_inventory() if inventory is None else inventory,
        openclaw_jobs=(
            _openclaw_duplicates() if openclaw_jobs is None else openclaw_jobs
        ),
    )
    matching_processes = _matching_runtime_processes(
        _process_inventory() if processes is None else processes,
    )
    ready = (
        activation.get("passed") is True
        and tasks["passed"] is True
        and not matching_processes
    )
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_runtime_v3_atomic_migration_readiness",
        "mode": "PLAN_ONLY",
        "status": (
            "READY_FOR_EXPLICITLY_AUTHORIZED_V3_DISABLED_REGISTRATION_AND_CUTOVER"
            if ready else "BLOCKED_FAIL_CLOSED"
        ),
        "migration_performed": False,
        "task_mutation_performed": False,
        "old_task": OLD_TASK,
        "failed_v2_task": FAILED_V2_TASK,
        "new_v3_task": NEW_V3_TASK,
        "activation_v4_full_verification_gate": activation,
        "pre_cutover_task_inventory_gate": tasks,
        "runtime_process_gate": {
            "passed": not matching_processes,
            "matching_daily_or_fresh_search_processes": matching_processes,
        },
        "new_action": {
            "execute": str(PYTHON),
            "arguments": NEW_ARGUMENTS_TEMPLATE.format(
                daily=(root / DAILY_RELATIVE).resolve(),
            ),
            "working_directory": root.as_posix(),
        },
        "approved_scheduler_contract": dict(EXPECTED_SETTINGS),
        "cutover_contract": [
            "VERIFY_ACTIVATION_V4_FULL_NOT_STATIC_ONLY",
            "VERIFY_OLD_V1_ENABLED_AND_NOT_RUNNING",
            "VERIFY_FAILED_V2_REMAINS_DISABLED_AND_NOT_RUNNING",
            "REGISTER_NEW_V3_DISABLED_WITHOUT_FORCE_OR_REPLACEMENT",
            "VERIFY_NEW_V3_DISABLED_EXACT_ACTION_TRIGGER_SETTINGS_AND_PRINCIPAL",
            "DISABLE_OLD_V1_THEN_ENABLE_NEW_V3_WITHOUT_PARALLEL_ENABLE",
            "RUN_REAL_V3_SMOKE_AND_FULL_ACTIVATION_VERIFIER",
            "ON_ANY_FAILURE_DISABLE_AND_STOP_NEW_V3_THEN_REENABLE_OLD_V1",
        ],
        "rollback_contract": {
            "delete_any_task_allowed": False,
            "failed_v2_must_remain_disabled": True,
            "action": "DISABLE_STOP_NEW_V3_THEN_REENABLE_OLD_V1",
            "real_smoke_failure_requires_rollback": True,
            "preserve_all_old_and_new_evidence": True,
        },
        "previous_v2_smoke_failure": {
            "evidence_root": (
                root / "data/cache/research/ndx_dynamic_shadow_task_migration_v2"
            ).as_posix(),
            "failure": "V1_HASH_ONLY_CALENDAR_CURRENT_VENDOR_REVISION",
            "scheduler_rollback_completed": True,
            "runtime_datachain_recovery_proven": False,
            "v3_real_smoke_still_required": True,
        },
        "new_evidence_root": (
            root / "data/cache/research/ndx_dynamic_shadow_task_migration_v3"
        ).as_posix(),
        "old_v2_evidence_overwrite_allowed": False,
        "interrupted_disabled_registration_recovery": {
            "automatic_resume_allowed": False,
            "required_action": (
                "VERIFY_OWN_IMMUTABLE_PRE_AND_DISABLED_RECORDS_THEN_REQUEST_"
                "EXPLICIT_RECOVERY_REVIEW; NEVER_REPLACE_OR_DELETE_THE_TASK"
            ),
        },
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "orders_allowed": False,
    }


__all__ = [
    "AUTHORITY_RELATIVE",
    "EXPECTED_SETTINGS",
    "FAILED_V2_TASK",
    "NEW_V3_TASK",
    "OLD_TASK",
    "RuntimeV3MigrationError",
    "build_runtime_v3_migration_authority",
    "build_runtime_v3_migration_readiness",
    "verify_runtime_v3_migration_authority",
]
