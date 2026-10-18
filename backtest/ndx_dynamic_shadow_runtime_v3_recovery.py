"""Read-only gate for recovery from the first disabled-registration attempt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.ndx_dynamic_shadow_runtime_v3_migration import (
    AUTHORITY_RELATIVE,
    FAILED_V2_TASK,
    NEW_V3_TASK,
    OLD_TASK,
    _activation_gate,
    _matching_runtime_processes,
    _openclaw_duplicates,
    _process_inventory,
    _task_inventory,
    verify_runtime_v3_migration_authority,
)


FAILED_ATTEMPT_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_task_migration_v3/attempts/"
    "20260905T2020425499105Z_84f18f027ff34a3bb639e40976169081"
)
RECOVERY_AUTHORITY_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_task_migration_v3_recovery/"
    "reviewed_source_manifest.json"
)
RECOVERY_SOURCES = (
    "backtest/ndx_dynamic_shadow_runtime_v3_recovery.py",
    "scripts/ndx_dynamic_shadow_runtime_v3_recovery.py",
    "scripts/recover_ndx_dynamic_shadow_selection_task_v3.ps1",
    "tests/test_ndx_dynamic_shadow_runtime_v3_recovery.py",
    "tests/test_recover_ndx_dynamic_shadow_selection_task_v3.py",
)


class RuntimeV3RecoveryError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        payload_text = value["record_payload_json"]
        declared = value["record_sha256"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeV3RecoveryError(f"failed attempt record invalid: {path.name}") from exc
    if (
        value.get("record_hash_algorithm")
        != "SHA256_UTF8_EXACT_RECORD_PAYLOAD_JSON_V1"
        or hashlib.sha256(payload_text.encode()).hexdigest() != declared
    ):
        raise RuntimeV3RecoveryError(f"failed attempt record hash invalid: {path.name}")
    unsigned = {
        key: item for key, item in value.items()
        if key not in {"record_hash_algorithm", "record_payload_json", "record_sha256"}
    }
    if json.loads(payload_text) != unsigned:
        raise RuntimeV3RecoveryError(f"failed attempt record envelope invalid: {path.name}")
    return value


def verify_failed_attempt(repository_root: str | Path) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    attempt = (root / FAILED_ATTEMPT_RELATIVE).resolve()
    pre_path, rollback_path = attempt / "pre_cutover.json", attempt / "rollback.json"
    if (attempt / "new_disabled.json").exists() or (attempt / "post_cutover.json").exists():
        raise RuntimeV3RecoveryError("failed attempt unexpectedly contains later success evidence")
    pre, rollback = _record(pre_path), _record(rollback_path)
    if (
        rollback.get("pre_cutover_record_sha256") != pre.get("record_sha256")
        or rollback.get("disabled_registration_record_sha256") is not None
        or rollback.get("reason")
        != "New v3 Scheduled Task differs from the approved exact contract."
        or rollback.get("new_task_secured_before_old_restore") is not True
        or rollback.get("old_task_restored") is not True
        or (rollback.get("new_task") or {}).get("state") != "Disabled"
        or (rollback.get("new_task") or {}).get("enabled") is not False
    ):
        raise RuntimeV3RecoveryError("failed attempt is not the reviewed disabled-registration rollback")
    verify_runtime_v3_migration_authority(root / AUTHORITY_RELATIVE, repository_root=root)
    return {
        "path": attempt.as_posix(),
        "pre_cutover": {"path": pre_path.as_posix(), "sha256": _sha(pre_path)},
        "rollback": {"path": rollback_path.as_posix(), "sha256": _sha(rollback_path)},
        "pre_record_sha256": pre["record_sha256"],
        "rollback_record_sha256": rollback["record_sha256"],
        "new_task_xml_sha256": rollback["new_task"]["task_xml_sha256"],
        "old_task_xml_sha256": rollback["old_task"]["task_xml_sha256"],
        "failed_v2_task_xml_sha256": rollback["failed_v2_task"]["task_xml_sha256"],
        "original_migration_authority_sha256": _sha(root / AUTHORITY_RELATIVE),
    }


def build_recovery_authority(*, repository_root: str | Path) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    sources = {}
    for relative in RECOVERY_SOURCES:
        path = (root / relative).resolve()
        if not path.is_file():
            raise RuntimeV3RecoveryError(f"recovery authority source missing: {relative}")
        sources[relative] = {"path": path.as_posix(), "sha256": _sha(path)}
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_runtime_v3_recovery_authority",
        "failed_attempt": verify_failed_attempt(root),
        "sources": sources,
        "boundaries": {
            "reuse_existing_disabled_v3_task_only": True,
            "task_registration_allowed": False,
            "task_deletion_allowed": False,
            "research_only": True,
            "live_mutation_allowed": False,
        },
    }
    payload["authority_sha256"] = _canonical_sha(payload)
    return payload


def verify_recovery_authority(path: str | Path, *, repository_root: str | Path) -> dict[str, Any]:
    root, source = Path(repository_root).resolve(), Path(path).resolve()
    if source != (root / RECOVERY_AUTHORITY_RELATIVE).resolve():
        raise RuntimeV3RecoveryError("recovery authority path is not canonical")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeV3RecoveryError("recovery authority missing or invalid") from exc
    if value != build_recovery_authority(repository_root=root):
        raise RuntimeV3RecoveryError("recovery authority sources or failed-attempt binding changed")
    return value


def build_recovery_readiness(
    *,
    repository_root: str | Path,
    inventory: Sequence[Mapping[str, Any]] | None = None,
    processes: Sequence[Mapping[str, Any]] | None = None,
    openclaw_jobs: Sequence[Mapping[str, Any]] | None = None,
    activation_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    failed_attempt = verify_failed_attempt(root)
    activation = dict(activation_gate) if activation_gate is not None else _activation_gate(root)
    rows = list(_task_inventory() if inventory is None else inventory)
    relevant_rows = [
        row for row in rows
        if row.get("task_name") in {OLD_TASK, FAILED_V2_TASK, NEW_V3_TASK}
    ]
    by_name = {
        name: [row for row in rows if row.get("task_name") == name and str(row.get("task_path") or "\\") == "\\"]
        for name in (OLD_TASK, FAILED_V2_TASK, NEW_V3_TASK)
    }
    unexpected_enabled = []
    for row in rows:
        name = str(row.get("task_name") or "")
        text = f'{row.get("execute", "")} {row.get("arguments", "")}'.lower()
        related = (
            "dynamic_shadow_selection" in name.lower()
            or "ndx_dynamic_shadow_daily" in text
            or "ndx_dynamic_shadow_fresh_search" in text
        )
        canonical = (
            str(row.get("task_path") or "\\") == "\\"
            and name in {OLD_TASK, FAILED_V2_TASK, NEW_V3_TASK}
        )
        if related and not canonical and row.get("enabled") is True:
            unexpected_enabled.append({
                "task_name": name,
                "task_path": str(row.get("task_path") or ""),
                "state": str(row.get("state") or ""),
                "enabled": True,
            })
    tasks_passed = (
        all(len(by_name[name]) == 1 for name in by_name)
        and by_name[OLD_TASK][0].get("enabled") is True
        and by_name[OLD_TASK][0].get("state") != "Running"
        and by_name[FAILED_V2_TASK][0].get("enabled") is False
        and by_name[FAILED_V2_TASK][0].get("state") != "Running"
        and by_name[NEW_V3_TASK][0].get("enabled") is False
        and by_name[NEW_V3_TASK][0].get("state") != "Running"
        and not unexpected_enabled
    )
    runtime = _matching_runtime_processes(_process_inventory() if processes is None else processes)
    openclaw = _openclaw_duplicates() if openclaw_jobs is None else list(openclaw_jobs)
    ready = activation.get("passed") is True and tasks_passed and not runtime and not openclaw
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_runtime_v3_recovery_readiness",
        "mode": "PLAN_ONLY",
        "status": "READY_FOR_REVIEWED_EXISTING_TASK_RECOVERY" if ready else "BLOCKED_FAIL_CLOSED",
        "failed_attempt": failed_attempt,
        "activation_v4_full_verification_gate": activation,
        "task_gate": {
            "passed": tasks_passed,
            "observed": [{
                "task_name": str(row.get("task_name") or ""),
                "task_path": str(row.get("task_path") or ""),
                "state": str(row.get("state") or ""),
                "enabled": row.get("enabled") is True,
            } for row in relevant_rows],
            "unexpected_enabled_duplicates": unexpected_enabled,
        },
        "runtime_process_gate": {"passed": not runtime, "observed": runtime},
        "openclaw_gate": {"passed": not openclaw, "observed": openclaw},
        "registration_allowed": False,
        "task_deletion_allowed": False,
        "mutation_performed": False,
    }


__all__ = [
    "FAILED_ATTEMPT_RELATIVE", "RECOVERY_AUTHORITY_RELATIVE", "RuntimeV3RecoveryError",
    "build_recovery_authority", "build_recovery_readiness", "verify_failed_attempt",
    "verify_recovery_authority",
]
