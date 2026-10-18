"""Cross-host verifier and append-only notary for the failed v2 task cutover.

The original evidence bytes are never rewritten.  Their serializer is declared
by filename because the first three records were produced by Windows
PowerShell 5.1 while rollback.json was produced by PowerShell 7.6.  Verification
never tries alternate algorithms until one happens to match.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVIDENCE_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_task_migration_v2"
NOTARY_LEDGER = EVIDENCE_ROOT / "rollback_notary_observations.jsonl"
OLD_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily"
NEW_TASK = "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"
PS51 = "WINDOWS_POWERSHELL_5_1_CONVERTTOJSON_DEPTH20_COMPRESS_UTF8_SHA256"
PS76 = "POWERSHELL_7_6_DATEKIND_STRING_CONVERTTOJSON_DEPTH20_COMPRESS_UTF8_SHA256"
EVIDENCE_ALGORITHMS = {
    "pre_cutover.json": PS51,
    "new_disabled.json": PS51,
    "post_cutover.json": PS51,
    "rollback.json": PS76,
}
PROTECTED = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)
CALENDAR_LEDGER = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1/sessions.jsonl"
PRICE_SOURCES = {
    "QQQ": ROOT / "data/cache/QQQ.csv",
    "SPY": ROOT / "data/cache/SPY.csv",
}


class TaskMigrationNotaryError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_POWERSHELL_VERIFY = r'''
$ErrorActionPreference = "Stop"
$record = Get-Content -LiteralPath $env:NDX_EVIDENCE_PATH -Raw -Encoding UTF8 | ConvertFrom-Json
$declared = [string]$record.record_sha256
$record.PSObject.Properties.Remove("record_sha256")
$unsigned = $record | ConvertTo-Json -Depth 20 -Compress
$algorithm = [System.Security.Cryptography.SHA256]::Create()
try {
  $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($unsigned)
  $computed = ([System.BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
} finally { $algorithm.Dispose() }
[ordered]@{ declared = $declared; computed = $computed; host = $PSVersionTable.PSVersion.ToString() } |
  ConvertTo-Json -Compress
'''

_PWSH_VERIFY = r'''
$ErrorActionPreference = "Stop"
$record = Get-Content -LiteralPath $env:NDX_EVIDENCE_PATH -Raw -Encoding UTF8 |
  ConvertFrom-Json -DateKind String
$declared = [string]$record.record_sha256
$record.PSObject.Properties.Remove("record_sha256")
$unsigned = $record | ConvertTo-Json -Depth 20 -Compress
$algorithm = [System.Security.Cryptography.SHA256]::Create()
try {
  $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($unsigned)
  $computed = ([System.BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
} finally { $algorithm.Dispose() }
[ordered]@{ declared = $declared; computed = $computed; host = $PSVersionTable.PSVersion.ToString() } |
  ConvertTo-Json -Compress
'''


def verify_declared_record(path: Path, algorithm: str) -> dict[str, Any]:
    if path.name not in EVIDENCE_ALGORITHMS or EVIDENCE_ALGORITHMS[path.name] != algorithm:
        raise TaskMigrationNotaryError("evidence serializer is not the declared filename algorithm")
    if not path.is_file():
        raise TaskMigrationNotaryError(f"evidence is missing: {path}")
    if algorithm == PS51:
        executable, command = "powershell.exe", _POWERSHELL_VERIFY
    elif algorithm == PS76:
        executable, command = "pwsh.exe", _PWSH_VERIFY
    else:
        raise TaskMigrationNotaryError("unknown evidence serializer")
    environment = os.environ.copy()
    environment["NDX_EVIDENCE_PATH"] = str(path.resolve())
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT, env=environment, check=False, capture_output=True,
        text=True, encoding="utf-8",
    )
    if completed.returncode != 0:
        raise TaskMigrationNotaryError(
            f"declared serializer failed for {path.name}: {completed.stderr.strip()}"
        )
    result = json.loads(completed.stdout)
    expected_host = "5.1." if algorithm == PS51 else "7.6."
    if not str(result.get("host", "")).startswith(expected_host):
        raise TaskMigrationNotaryError(f"unexpected serializer host for {path.name}")
    if result.get("declared") != result.get("computed"):
        raise TaskMigrationNotaryError(f"record hash mismatch: {path.name}")
    return {
        "path": path.resolve().as_posix(),
        "file_sha256": sha256_file(path),
        "record_sha256": result["declared"],
        "serializer": algorithm,
        "verified_with_host": result["host"],
    }


def _task_snapshots() -> dict[str, dict[str, Any]]:
    command = r'''
$ErrorActionPreference = "Stop"
$rows = @()
foreach ($name in @($env:NDX_OLD_TASK, $env:NDX_NEW_TASK)) {
  $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
  $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction Stop
  $xml = Export-ScheduledTask -TaskName $name
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($xml)
    $xmlHash = ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
  } finally { $sha.Dispose() }
  $rows += [ordered]@{
    task_name = $name
    state = $task.State.ToString()
    enabled = ($task.State.ToString() -ne "Disabled")
    action = [ordered]@{
      execute = [string]$task.Actions[0].Execute
      arguments = [string]$task.Actions[0].Arguments
      working_directory = [string]$task.Actions[0].WorkingDirectory
    }
    settings = [ordered]@{
      disallow_start_if_on_batteries = [bool]$task.Settings.DisallowStartIfOnBatteries
      stop_if_going_on_batteries = [bool]$task.Settings.StopIfGoingOnBatteries
    }
    last_run_time = $info.LastRunTime.ToUniversalTime().ToString("o")
    last_task_result = [int]$info.LastTaskResult
    next_run_time = $info.NextRunTime.ToUniversalTime().ToString("o")
    task_xml_sha256 = $xmlHash
  }
}
$rows | ConvertTo-Json -Depth 8 -Compress
'''
    environment = os.environ.copy()
    environment.update({"NDX_OLD_TASK": OLD_TASK, "NDX_NEW_TASK": NEW_TASK})
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT, env=environment, check=False, capture_output=True,
        text=True, encoding="utf-8",
    )
    if completed.returncode != 0:
        raise TaskMigrationNotaryError(f"cannot inspect tasks: {completed.stderr.strip()}")
    rows = json.loads(completed.stdout)
    if not isinstance(rows, list) or len(rows) != 2:
        raise TaskMigrationNotaryError("task snapshot cardinality changed")
    return {row["task_name"]: row for row in rows}


def _source_revision_audit() -> dict[str, Any]:
    from backtest.ndx_observed_session_calendar import load_ohlc_rows

    records = [json.loads(line) for line in CALENDAR_LEDGER.read_text(encoding="utf-8").splitlines()]
    record = next((row for row in records if row.get("session_date") == "2026-09-04"), None)
    if record is None:
        raise TaskMigrationNotaryError("sealed 2026-09-04 calendar record is missing")
    sealed = {row["ticker"]: row["row_sha256"] for row in record["source_rows"]}
    current_rows = {
        ticker: load_ohlc_rows(path, ticker=ticker)["2026-09-04"]
        for ticker, path in PRICE_SOURCES.items()
    }
    recorded = datetime.fromisoformat(record["recorded_at_utc"])
    closed = datetime.fromisoformat(record["close_timestamp_utc"])
    return {
        "session_date": "2026-09-04",
        "recorded_at_utc": record["recorded_at_utc"],
        "close_timestamp_utc": record["close_timestamp_utc"],
        "seconds_after_close_when_recorded": int((recorded - closed).total_seconds()),
        "recorded_during_session": False,
        "sealed_row_sha256": sealed,
        "current_row_sha256": {
            ticker: item["row_sha256"] for ticker, item in current_rows.items()
        },
        "current_normalized_ohlcv": {
            ticker: item["normalized"] for ticker, item in current_rows.items()
        },
        "current_source_file_sha256": {
            ticker: sha256_file(path) for ticker, path in PRICE_SOURCES.items()
        },
        "sealed_normalized_ohlcv_archived": False,
        "sealed_provider_identity_recorded": False,
        "original_sealed_values_recoverable_from_v1_artifacts": False,
        "runtime_calendar_revision_unresolved": any(
            sealed[ticker] != current_rows[ticker]["row_sha256"] for ticker in PRICE_SOURCES
        ),
    }


def _load_evidence() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    verified = {
        name: verify_declared_record(EVIDENCE_ROOT / name, algorithm)
        for name, algorithm in EVIDENCE_ALGORITHMS.items()
    }
    payloads = {
        name: json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8"))
        for name in EVIDENCE_ALGORITHMS
    }
    if (
        payloads["post_cutover.json"].get("pre_cutover_record_sha256")
        != payloads["pre_cutover.json"].get("record_sha256")
        or payloads["post_cutover.json"].get("disabled_registration_record_sha256")
        != payloads["new_disabled.json"].get("record_sha256")
        or payloads["rollback.json"].get("post_cutover_record_sha256")
        != payloads["post_cutover.json"].get("record_sha256")
    ):
        raise TaskMigrationNotaryError("migration evidence chain link mismatch")
    return verified, payloads


def _verify_notary_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    previous = None
    for sequence, raw in enumerate(records, 1):
        record = dict(raw)
        declared = record.pop("record_sha256", None)
        if (
            raw.get("sequence") != sequence
            or raw.get("previous_record_sha256") != previous
            or declared != canonical_sha256(record)
        ):
            raise TaskMigrationNotaryError("notary ledger chain/hash mismatch")
        previous = declared
    return records


def build_observation() -> dict[str, Any]:
    evidence, payloads = _load_evidence()
    tasks = _task_snapshots()
    rollback = payloads["rollback.json"]
    if (
        tasks[OLD_TASK]["enabled"] is not True
        or tasks[NEW_TASK]["enabled"] is not False
        or tasks[OLD_TASK]["task_xml_sha256"] != rollback["old_task"]["task_xml_sha256"]
        or tasks[NEW_TASK]["task_xml_sha256"] != rollback["new_task"]["task_xml_sha256"]
    ):
        raise TaskMigrationNotaryError("current tasks do not match rollback evidence")
    protected = {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in PROTECTED}
    expected_protected = {
        Path(key).resolve().relative_to(ROOT).as_posix(): value
        for key, value in rollback["protected_hashes"].items()
    }
    if protected != expected_protected:
        raise TaskMigrationNotaryError("protected live hashes differ from rollback evidence")
    source_audit = _source_revision_audit()
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_task_migration_rollback_notary",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
        "task_state": tasks,
        "protected_hashes": protected,
        "source_revision_audit": source_audit,
        "scheduler_rollback_verified": True,
        "runtime_recovery_claimed": False,
        "runtime_calendar_revision_unresolved": source_audit["runtime_calendar_revision_unresolved"],
        "live_mutation_performed": False,
        "calendar_mutation_performed": False,
        "task_mutation_performed": False,
        "verifier": {
            "path": Path(__file__).resolve().as_posix(),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
    }


def append_notary() -> dict[str, Any]:
    existing = _verify_notary_ledger(NOTARY_LEDGER)
    record = build_observation()
    record["sequence"] = len(existing) + 1
    record["previous_record_sha256"] = existing[-1]["record_sha256"] if existing else None
    record["record_sha256"] = canonical_sha256(record)
    NOTARY_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with NOTARY_LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    _verify_notary_ledger(NOTARY_LEDGER)
    return record


def verify() -> dict[str, Any]:
    observation = build_observation()
    records = _verify_notary_ledger(NOTARY_LEDGER)
    return {
        "status": "SCHEDULER_ROLLBACK_VERIFIED_RUNTIME_CALENDAR_STILL_BLOCKED",
        "evidence_verified": True,
        "notary_record_count": len(records),
        "latest_notary_record_sha256": records[-1]["record_sha256"] if records else None,
        "task_state": observation["task_state"],
        "source_revision_audit": observation["source_revision_audit"],
        "runtime_recovery_claimed": False,
        "live_mutation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true")
    group.add_argument("--append-notary", action="store_true")
    args = parser.parse_args()
    try:
        result = append_notary() if args.append_notary else verify()
    except Exception as exc:
        print(f"task migration notary fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
