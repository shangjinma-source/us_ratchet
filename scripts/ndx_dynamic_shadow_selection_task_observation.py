r"""Observe or verify the registered dynamic-shadow selection task.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_selection_task_observation.py --observe
    python -B scripts\ndx_dynamic_shadow_selection_task_observation.py --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_selection_task_observation import (  # noqa: E402
    SelectionTaskObservationError,
    append_observation,
    build_observation_record,
    load_observation_ledger,
    verify_observation_ledger,
)


TASK_NAME = "us_ratchet_ndx_dynamic_shadow_selection_daily"
INSTALLER = ROOT / "scripts/install_ndx_dynamic_shadow_selection_task.ps1"
REGISTRATION = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/selection_task_registration.json"
ACTIVATION = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
LEDGER = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/selection_task_registration_observations.jsonl"
PROTECTED = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)


def _protected_hashes() -> dict[str, str | None]:
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        for path in PROTECTED
    }


def _task_snapshot() -> dict[str, Any]:
    command = r'''
$task = Get-ScheduledTask -TaskName $env:NDX_SELECTION_TASK_NAME -ErrorAction Stop
$actions = @($task.Actions)
$triggers = @($task.Triggers)
if ($actions.Count -ne 1 -or $triggers.Count -ne 1) { throw "expected one action and trigger" }
$xml = Export-ScheduledTask -TaskName $env:NDX_SELECTION_TASK_NAME
[ordered]@{
  state = $task.State.ToString()
  enabled = ($task.State.ToString() -ne "Disabled")
  task_xml = $xml
  action = [ordered]@{
    execute = [string]$actions[0].Execute
    arguments = [string]$actions[0].Arguments
    working_directory = [string]$actions[0].WorkingDirectory
  }
  trigger = [ordered]@{
    start_boundary = [string]$triggers[0].StartBoundary
    days_of_week_bitmask = [int]$triggers[0].DaysOfWeek
    weeks_interval = [int]$triggers[0].WeeksInterval
    timezone = "Asia/Shanghai"
  }
  settings = [ordered]@{
    start_when_available = [bool]$task.Settings.StartWhenAvailable
    multiple_instances = $task.Settings.MultipleInstances.ToString().ToUpperInvariant()
    restart_count = [int]$task.Settings.RestartCount
    restart_interval = [string]$task.Settings.RestartInterval
    execution_time_limit = [string]$task.Settings.ExecutionTimeLimit
    disallow_start_if_on_batteries = [bool]$task.Settings.DisallowStartIfOnBatteries
    stop_if_going_on_batteries = [bool]$task.Settings.StopIfGoingOnBatteries
    use_unified_scheduling_engine = [bool]$task.Settings.UseUnifiedSchedulingEngine
  }
  principal = [ordered]@{
    user_id = [string]$task.Principal.UserId
    logon_type = $task.Principal.LogonType.ToString()
    run_level = $task.Principal.RunLevel.ToString()
  }
} | ConvertTo-Json -Depth 12 -Compress
'''
    environment = os.environ.copy()
    environment["NDX_SELECTION_TASK_NAME"] = TASK_NAME
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT, env=environment, check=False, capture_output=True,
        text=True, encoding="utf-8",
    )
    if completed.returncode != 0:
        raise SelectionTaskObservationError(
            f"cannot export current Scheduled Task: {completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SelectionTaskObservationError("Scheduled Task export is invalid JSON") from exc


def _installer_verifies() -> bool:
    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(INSTALLER),
            "-ProjectRoot", str(ROOT), "-VerifyRegistrationEvidence",
        ],
        cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
    )
    return completed.returncode == 0 and "RESULT=registration_evidence_verified" in completed.stdout


def observe() -> dict[str, Any]:
    snapshot = _task_snapshot()
    existing = load_observation_ledger(LEDGER)
    record = build_observation_record(
        sequence=len(existing) + 1,
        previous_record_sha256=existing[-1]["record_sha256"] if existing else None,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
        registration_evidence_path=REGISTRATION,
        activation_manifest_path=ACTIVATION,
        installer_path=INSTALLER,
        current_task_snapshot=snapshot,
        installer_registration_verifier_passed=_installer_verifies(),
    )
    append_observation(LEDGER, record)
    result = verify_observation_ledger(
        LEDGER,
        registration_evidence_path=REGISTRATION,
        activation_manifest_path=ACTIVATION,
        installer_path=INSTALLER,
        latest_current_task_snapshot=snapshot,
    )
    result["observation_appended"] = True
    return result


def verify() -> dict[str, Any]:
    result = verify_observation_ledger(
        LEDGER,
        registration_evidence_path=REGISTRATION,
        activation_manifest_path=ACTIVATION,
        installer_path=INSTALLER,
        latest_current_task_snapshot=_task_snapshot(),
    )
    result["observation_appended"] = False
    result["installer_registration_verifier_passed"] = _installer_verifies()
    if not result["installer_registration_verifier_passed"]:
        result["status"] = "DRIFT_DETECTED_FAIL_CLOSED"
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Observe registered selection task without mutating it")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--observe", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before = _protected_hashes()
    try:
        result = observe() if args.observe else verify()
        if _protected_hashes() != before:
            raise SelectionTaskObservationError("protected live files changed")
    except Exception as exc:
        print(f"selection task observation fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
