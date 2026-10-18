"""Read-only, fail-closed runtime4 migration planning; no authority or installer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OLD_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily"
FAILED_V2_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"
OLD_V3_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar"
NEW_V4_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v4_accepted_receipts"
PYTHON = Path(r"D:\python\python.exe")
ACTIVATION_RELATIVE = Path("data/cache/research/ndx_dynamic_shadow_activation_v5/manifest.json")
DAILY_RELATIVE = Path("scripts/ndx_dynamic_shadow_daily_v4.py")
OLD_DAILY_RELATIVE = Path("scripts/ndx_dynamic_shadow_daily_v3.py")
RELATED = re.compile(r"dynamic_shadow_selection|ndx_dynamic_shadow_(?:daily|fresh_search|candidate_generator)", re.I)
RUNTIME = re.compile(r'''ndx_dynamic_shadow_(daily|fresh_search|candidate_generator)(?:_v\d+)?(?:\.py)?(?=[\s"']|$)''', re.I)


class RuntimeV4MigrationError(ValueError):
    pass


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _activation_gate(root):
    from backtest.ndx_dynamic_shadow_activation_v5 import verify_activation_v5_manifest, STATUS
    path = root / ACTIVATION_RELATIVE
    daily_path = root / DAILY_RELATIVE
    if not PYTHON.is_file() or not path.is_file() or not daily_path.is_file():
        return {"passed": False, "full_verifier_replayed": False,
                "reason": "ACTIVATION_V5_OR_RUNTIME_NOT_MATERIALIZED"}
    before = _digest(path)
    manifest = verify_activation_v5_manifest(path, repository_root=root)
    source = manifest["sources"].get(DAILY_RELATIVE.as_posix(), {})
    boundaries = manifest.get("boundaries", {})
    passed = (manifest.get("manifest_type") == "ndx_dynamic_shadow_activation_v5"
              and manifest.get("status") == STATUS
              and Path(source.get("path", "")).resolve() == daily_path.resolve()
              and source.get("sha256") == _digest(daily_path)
              and boundaries.get("research_only") is True
              and boundaries.get("task_registration_performed") is False
              and boundaries.get("promotion_allowed") is False
              and boundaries.get("live_mutation_allowed") is False
              and _digest(path) == before)
    return {"passed": passed, "full_verifier_replayed": True,
            "reason": None if passed else "ACTIVATION_V5_BINDING_CHANGED",
            "activation_manifest_path": path.as_posix(), "activation_manifest_sha256": before,
            "daily_v4_sha256": _digest(daily_path),
            "verified_source_bindings": manifest["sources"]}


def _recheck_activation_bindings(root, activation):
    sources = activation.get("verified_source_bindings")
    if not isinstance(sources, dict) or not sources:
        raise RuntimeV4MigrationError("activation source bindings absent")
    for name, descriptor in sources.items():
        path = (root / name).resolve()
        if (not path.is_relative_to(root) or Path(descriptor["path"]).resolve() != path
                or _digest(path) != descriptor["sha256"]):
            raise RuntimeV4MigrationError("activation sources changed after full verification")
    if _digest(root / ACTIVATION_RELATIVE) != activation["activation_manifest_sha256"]:
        raise RuntimeV4MigrationError("activation manifest changed after full verification")


def _powershell_json(command):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode != 0:
        raise RuntimeV4MigrationError("Windows inventory collection failed")
    if not result.stdout.strip():
        raise RuntimeV4MigrationError("Windows inventory returned empty protocol")
    value = json.loads(result.stdout)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise RuntimeV4MigrationError("Windows inventory schema invalid")
    return value


def _task_inventory():
    return _powershell_json(r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$rows = @(Get-ScheduledTask | ForEach-Object {
  $task = $_
  $actions = @($task.Actions)
  $related = ([string]$task.TaskName -match 'dynamic_shadow_selection') -or
    (($actions | ForEach-Object { [string]$_.Execute + ' ' + [string]$_.Arguments }) -match 'ndx_dynamic_shadow_(daily|fresh_search|candidate_generator)')
  if ($related) {
    if ($actions.Count -eq 0) { $actions = @($null) }
    foreach ($action in $actions) {
      [ordered]@{task_name=[string]$task.TaskName;task_path=[string]$task.TaskPath;
        enabled=([string]$task.State -ne 'Disabled');state=[string]$task.State;
        execute=[string]$action.Execute;arguments=[string]$action.Arguments;
        working_directory=[string]$action.WorkingDirectory}
    }
  }
})
ConvertTo-Json -InputObject $rows -Depth 5 -Compress
''')


def _process_inventory():
    # Filter before returning data: never expose a full-machine command inventory.
    return _powershell_json(r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$processes = @(Get-CimInstance Win32_Process)
if (@($processes | Where-Object {
  $_.Name -match '^python(w|\d+(\.\d+)*)?\.exe$' -and [string]::IsNullOrWhiteSpace([string]$_.CommandLine)
}).Count -gt 0) { throw 'Python process command line unavailable' }
$rows = @($processes | Where-Object {
  $_.ProcessId -ne $PID -and ([string]$_.CommandLine -match 'ndx_dynamic_shadow_(daily|fresh_search|candidate_generator)(_v\d+)?(\.py)?(?=[\s"'']|$)')
} | ForEach-Object { [ordered]@{process_id=[int]$_.ProcessId;command_line=[string]$_.CommandLine} })
ConvertTo-Json -InputObject $rows -Depth 4 -Compress
''')


def _openclaw_duplicates():
    profile = os.environ.get("USERPROFILE")
    if not profile or not Path(profile).is_absolute():
        raise RuntimeV4MigrationError("OpenClaw profile unavailable")
    path = Path(profile) / ".openclaw/cron/jobs.json"
    before = path.read_bytes()
    payload = json.loads(before)
    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(jobs, list):
        raise RuntimeV4MigrationError("OpenClaw jobs schema invalid")
    matches = []
    for job in jobs:
        if not isinstance(job, dict) or type(job.get("enabled")) is not bool:
            raise RuntimeV4MigrationError("OpenClaw enabled state unknown")
        if job["enabled"] and RELATED.search(_canonical(job)):
            matches.append({"name": str(job.get("name", "")), "enabled": True})
    if path.read_bytes() != before:
        raise RuntimeV4MigrationError("OpenClaw inventory changed while reading")
    return sorted(matches, key=lambda item: item["name"])


def _task_gate(inventory, root):
    required = {"task_name", "task_path", "enabled", "state", "execute", "arguments", "working_directory"}
    if not isinstance(inventory, list) or any(not isinstance(row, dict) or not required <= set(row)
            or type(row["enabled"]) is not bool for row in inventory):
        raise RuntimeV4MigrationError("task inventory schema incomplete")
    names = (OLD_TASK, FAILED_V2_TASK, OLD_V3_TASK, NEW_V4_TASK)
    related = [row for row in inventory if row["task_name"] in names
               or RELATED.search(f'{row["task_name"]} {row["execute"]} {row["arguments"]}')]
    grouped = {name: [row for row in related if str(row["task_name"]).casefold() == name.casefold()] for name in names}
    reasons = []
    for name in names[:3]:
        rows = grouped[name]
        if len(rows) != 1 or rows[0]["task_path"] != "\\":
            reasons.append("EXPECTED_SINGLE_ROOT_TASK:" + name)
            continue
        task = rows[0]
        if name in (OLD_TASK, FAILED_V2_TASK):
            if task["enabled"] is not False or task["state"] != "Disabled":
                reasons.append("LEGACY_TASK_NOT_DISABLED:" + name)
        else:
            if task["enabled"] is not True or task["state"] != "Ready":
                reasons.append("V3_NOT_ENABLED_READY")
            expected_arguments = f'-B "{root / OLD_DAILY_RELATIVE}" --execute'
            if (task["execute"] != str(PYTHON) or task["arguments"] != expected_arguments
                    or task["working_directory"] != str(root)):
                reasons.append("V3_ACTION_OR_WORKING_DIRECTORY_CHANGED")
    if grouped[NEW_V4_TASK]:
        reasons.append("V4_ALREADY_EXISTS")
    for task in related:
        expected = task["task_name"] in names[:3] and task["task_path"] == "\\"
        if not expected and task["enabled"]:
            reasons.append("UNEXPECTED_ENABLED_WINDOWS_SCHEDULER")
    return {"passed": not reasons, "reasons": sorted(set(reasons)),
            "observed": [{key: row[key] for key in ("task_name", "task_path", "enabled", "state")} for row in related]}


def _runtime_processes(processes):
    if not isinstance(processes, list):
        raise RuntimeV4MigrationError("process inventory schema invalid")
    matched = []
    for row in processes:
        if (not isinstance(row, dict) or type(row.get("process_id")) is not int
                or not isinstance(row.get("command_line"), str) or not row["command_line"].strip()):
            raise RuntimeV4MigrationError("process inventory row invalid")
        command = row["command_line"]
        found = RUNTIME.search(command)
        # Existing CLIs accept argparse abbreviations. Do not infer idleness
        # from an absent exact action flag; even verification work must finish
        # before a reviewed cutover. This only blocks readiness, never stops it.
        if found:
            matched.append({"process_id": row["process_id"], "runtime_script": found.group(0)})
    return sorted(matched, key=lambda row: (row["process_id"], row["runtime_script"]))


def _inventory_snapshot():
    tasks = _task_inventory()
    processes = _process_inventory()
    openclaw = _openclaw_duplicates()
    if not isinstance(openclaw, list) or any(not isinstance(row, dict) or row.get("enabled") is not True for row in openclaw):
        raise RuntimeV4MigrationError("OpenClaw duplicate inventory invalid")
    return {"tasks": sorted(tasks, key=_canonical), "processes": _runtime_processes(processes),
            "openclaw": sorted(openclaw, key=_canonical)}


def build_runtime_v4_migration_readiness(repository_root):
    root = Path(repository_root).resolve()
    errors = []
    activation = {"passed": False, "full_verifier_replayed": False}
    task_gate = {"passed": False, "reasons": ["NOT_COLLECTED"]}
    inventory = {"processes": [], "openclaw": []}
    stable = False
    try:
        if root != REPOSITORY_ROOT.resolve():
            raise RuntimeV4MigrationError("repository root is not canonical")
        local_sources = {path: _digest(path) for path in (
            root / "backtest/ndx_dynamic_shadow_runtime_v4_migration.py",
            root / "scripts/ndx_dynamic_shadow_runtime_v4_migration.py")}
        inventory = _inventory_snapshot()
        task_gate = _task_gate(inventory["tasks"], root)
        activation = _activation_gate(root)
        repeated = _inventory_snapshot()
        stable = _canonical(inventory) == _canonical(repeated)
        if not stable:
            errors.append("INVENTORY_CHANGED_DURING_FULL_ACTIVATION")
        if activation.get("passed") is True:
            _recheck_activation_bindings(root, activation)
        if any(_digest(path) != digest for path, digest in local_sources.items()):
            raise RuntimeV4MigrationError("readiness source changed during collection")
    except Exception as exc:
        # Exception messages may contain command lines or private paths: expose type only.
        errors.append("READINESS_COLLECTION_OR_VERIFICATION_FAILED:" + type(exc).__name__)
    ready = (not errors and stable and activation.get("passed") is True
             and activation.get("full_verifier_replayed") is True and task_gate["passed"] is True
             and not inventory["processes"] and not inventory["openclaw"])
    return {"schema_version": 1, "manifest_type": "ndx_dynamic_shadow_runtime_v4_migration_readiness",
            "mode": "PLAN_ONLY", "status": "READY_FOR_V4_MIGRATION_REVIEW_ONLY" if ready else "BLOCKED_FAIL_CLOSED",
            "migration_performed": False, "task_mutation_performed": False,
            "authority_created": False, "registration_authorized": False, "cutover_authorized": False,
            "promotion_allowed": False, "live_mutation_allowed": False, "orders_allowed": False,
            "activation_v5_full_verification_gate": activation, "pre_cutover_task_inventory_gate": task_gate,
            "inventory_stable": stable, "matching_runtime_processes": inventory["processes"],
            "active_openclaw_duplicates": inventory["openclaw"], "errors": errors,
            "new_task": NEW_V4_TASK,
            "new_action": {"execute": str(PYTHON), "arguments": f'-B "{root / DAILY_RELATIVE}" --execute',
                           "working_directory": str(root)},
            "smoke_requirements": {"before_first_decision": "FRESH_CURRENT_TASK_RUN_AND_LEGAL_EMPTY_DECISIONS",
                                   "after_first_legal_decision": "REAL_RECEIPTS_BATCHES_AND_ELEVEN_ECONOMIC_PATHS",
                                   "empty_run_proves_economic_execution": False},
            "explicit_v4_migration_authorization_still_required": True}
