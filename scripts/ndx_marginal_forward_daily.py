"""Deterministic post-close refresh/evaluation for the frozen v11 cohort.

This scheduler boundary updates only versioned research caches and reports.  It
never registers a cohort and verifies that live config/state hashes are stable.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256  # noqa: E402


DEFAULT_AUDIT = ROOT / "data" / "cache" / "research" / "ndx_marginal_forward_v1" / "daily_audit.jsonl"
DEFAULT_STATUS = ROOT / "data" / "cache" / "research" / "ndx_marginal_forward_v1" / "daily_status.json"
NEW_YORK = ZoneInfo("America/New_York")


def is_safe_post_close_window(now: datetime | None = None) -> bool:
    """Allow refresh after 18:00 on a New York weekday, well after daily close."""
    current = now or datetime.now(timezone.utc)
    local = current.astimezone(NEW_YORK)
    return local.weekday() < 5 and 18 <= local.hour < 24


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _run_command(command: list[str], timeout_seconds: float) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_daily(
    *,
    audit_path: Path,
    status_path: Path,
    timeout_seconds: float = 1200.0,
    evaluate_only: bool = False,
    runner: Callable[[list[str], float], dict[str, Any]] = _run_command,
) -> tuple[dict[str, Any], int]:
    config_path = ROOT / "config" / "config.yaml"
    state_path = ROOT / "data" / "state.json"
    before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    commands = []
    if not evaluate_only:
        commands.append([
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "ndx_marginal_forward_refresh.py"),
            "--execute",
        ])
    commands.append([
        sys.executable,
        "-B",
        str(ROOT / "scripts" / "ndx_marginal_forward.py"),
        "evaluate",
    ])
    results = []
    error = None
    try:
        for command in commands:
            result = runner(command, timeout_seconds)
            results.append(result)
            if int(result.get("returncode", 1)) != 0:
                error = f"child command failed with exit {result.get('returncode')}"
                break
    except subprocess.TimeoutExpired as exc:
        error = f"child command timed out after {exc.timeout}s"
    except Exception as exc:  # scheduler boundary records unexpected failures
        error = f"{type(exc).__name__}: {exc}"
    after = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    if before != after:
        error = "live config/state hash changed during forward maintenance"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "ok": error is None,
        "recorded_at": now,
        "evaluate_only": bool(evaluate_only),
        "steps": results,
        "error": error,
        "config_sha256_before": before["config"],
        "config_sha256_after": after["config"],
        "state_sha256_before": before["state"],
        "state_sha256_after": after["state"],
        "live_config_changed": before["config"] != after["config"],
        "state_changed": before["state"] != after["state"],
        "today_advice_changed": False,
        "cohort_registration_performed": False,
    }
    _append_jsonl(audit_path, payload)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        status_path,
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload, 0 if error is None else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX v11 冻结批次盘后刷新与评估")
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--status", default=str(DEFAULT_STATUS))
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--evaluate-only", action="store_true")
    parser.add_argument("--ignore-refresh-window", action="store_true")
    args = parser.parse_args()
    if not args.ignore_refresh_window and not is_safe_post_close_window():
        print(json.dumps({
            "ok": True,
            "skipped": True,
            "reason": "OUTSIDE_SAFE_US_POST_CLOSE_WINDOW",
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    payload, exit_code = run_daily(
        audit_path=Path(args.audit),
        status_path=Path(args.status),
        timeout_seconds=float(args.timeout),
        evaluate_only=bool(args.evaluate_only),
    )
    stream = sys.stdout if exit_code == 0 else sys.stderr
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), file=stream)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
