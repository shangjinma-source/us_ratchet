"""Read-only live Windows task metadata plus current-run artifact verification.

The installer owns the immutable before snapshot and independently verifies
registration settings. This tool never starts a task or grants authorization.
Metadata is not a signed Task Scheduler event-instance audit.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import ndx_dynamic_shadow_runtime_v4_smoke as smoke
from backtest.ndx_dynamic_shadow_runtime_v4_migration import NEW_V4_TASK, PYTHON, DAILY_RELATIVE

TASK_FIELDS = {"task_name", "task_path", "state", "execute", "arguments", "working_directory",
               "definition_sha256", "last_run_utc", "last_result"}
BEFORE_FIELDS = {"schema_version", "captured_at_utc", "task_before", "artifact_before"}


def _task(root):
    command = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$task = Get-ScheduledTask -TaskPath '\' -TaskName 'us_ratchet_ndx_dynamic_shadow_selection_daily_v4_accepted_receipts'
if (@($task).Count -ne 1 -or @($task.Actions).Count -ne 1) { throw 'Expected one task and one action' }
$info = $task | Get-ScheduledTaskInfo
$xml = Export-ScheduledTask -TaskPath '\' -TaskName $task.TaskName
[ordered]@{task_name=[string]$task.TaskName;task_path=[string]$task.TaskPath;state=[string]$task.State;
 execute=[string]$task.Actions[0].Execute;arguments=[string]$task.Actions[0].Arguments;
 working_directory=[string]$task.Actions[0].WorkingDirectory;definition_xml=[string]$xml;
 last_run_utc=$info.LastRunTime.ToUniversalTime().ToString('o');last_result=[long]$info.LastTaskResult
} | ConvertTo-Json -Depth 4 -Compress
'''
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    if result.returncode:
        raise ValueError("live task observation failed")
    value = smoke._read_json(result.stdout)
    if not isinstance(value, dict) or not isinstance(value.get("definition_xml"), str) or not value["definition_xml"]:
        raise ValueError("task definition observation missing")
    value["definition_sha256"] = hashlib.sha256(value.pop("definition_xml").encode()).hexdigest()
    _validate_task(value, root)
    return value


def _validate_task(value, root):
    if not isinstance(value, dict) or set(value) != TASK_FIELDS:
        raise ValueError("task observation fields invalid")
    if (value["task_name"] != NEW_V4_TASK or value["task_path"] != "\\"
            or value["state"] != "Ready" or value["execute"] != str(PYTHON)
            or value["arguments"] != f'-B "{root / DAILY_RELATIVE}" --execute'
            or value["working_directory"] != str(root) or type(value["last_result"]) is not int):
        raise ValueError("task identity, action, state or result type invalid")
    digest = value["definition_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("task definition hash invalid")
    smoke._time(value["last_run_utc"])


def snapshot(root):
    root = Path(root).resolve()
    task = _task(root)
    _validate_task(task, root)
    artifact = smoke.snapshot(root)
    if smoke._json(_task(root)) != smoke._json(task):
        raise ValueError("task changed during before snapshot")
    return {"schema_version": 1, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "task_before": task, "artifact_before": artifact}


def verify(root, before):
    root = Path(root).resolve()
    if (not isinstance(before, dict) or set(before) != BEFORE_FIELDS
            or type(before["schema_version"]) is not int or before["schema_version"] != 1):
        raise ValueError("before task snapshot invalid")
    captured = smoke._time(before["captured_at_utc"])
    if captured > datetime.now(timezone.utc):
        raise ValueError("before snapshot is in the future")
    if smoke._time(before["artifact_before"]["captured_at_utc"]) > captured:
        raise ValueError("artifact snapshot was not captured before task snapshot completed")
    prior = before["task_before"]
    _validate_task(prior, root)
    observed = _task(root)
    _validate_task(observed, root)
    started = smoke._time(observed["last_run_utc"])
    if (observed["last_result"] != 0 or started <= captured
            or started <= smoke._time(prior["last_run_utc"])
            or started > datetime.now(timezone.utc)
            or observed["definition_sha256"] != prior["definition_sha256"]):
        raise ValueError("no new successful run of the unchanged task definition")
    artifact = smoke.verify(root, before=before["artifact_before"])
    if smoke._time(artifact["run_generated_at"]) < started:
        raise ValueError("artifact predates this task run")
    if smoke._json(_task(root)) != smoke._json(observed):
        raise ValueError("task changed during artifact verification")
    return {"schema_version": 1, "manifest_type": "ndx_dynamic_shadow_runtime_v4_task_evidence",
            "task_observation": observed, "artifact_verification": artifact,
            "evidence_source": "LIVE_WINDOWS_TASK_METADATA_AND_CURRENT_RUN_ARTIFACT",
            "task_metadata_and_artifact_verified": True, "task_instance_event_log_verified": False,
            "before_snapshot_sha256": hashlib.sha256(smoke._json(before).encode()).hexdigest(),
            "task_mutation_performed": False, "authorization_granted": False,
            "live_mutation_allowed": False, "promotion_allowed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--before-path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.snapshot:
            if args.before_path:
                raise ValueError("snapshot takes no input")
            result = snapshot(ROOT)
        elif args.before_path:
            result = verify(ROOT, smoke._read_json(args.before_path.read_text(encoding="utf-8-sig")))
        else:
            raise ValueError("verify requires before-path")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"task evidence failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
