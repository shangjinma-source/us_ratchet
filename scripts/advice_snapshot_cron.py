"""Deterministic scheduler wrapper for the local advice snapshot recorder.

OpenClaw should execute this command exactly once per cron turn.  HTTP retry,
failure counting, durable audit output, and alert escalation are handled here
instead of asking an LLM turn to sleep or maintain files.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from scripts.advice_snapshot_capture import DEFAULT_URL, capture_snapshot  # noqa: E402


DEFAULT_COUNTER = ROOT / "data" / ".cron_failure_count"
DEFAULT_AUDIT = ROOT / "data" / "advice_snapshot_cron.jsonl"
DEFAULT_ALERT = ROOT / "data" / "advice_snapshot_cron_alert.json"
NEW_YORK = ZoneInfo("America/New_York")


def is_us_capture_window(now: datetime | None = None) -> bool:
    """Return true during the configured weekday 09:00--15:59 New York window."""
    current = now or datetime.now(timezone.utc)
    local = current.astimezone(NEW_YORK)
    return local.weekday() < 5 and 9 <= local.hour < 16


def _read_counter(path: Path) -> int:
    try:
        return max(0, int(path.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def _write_counter(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, f"{max(0, int(value))}\n")


def _append_audit(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_alert(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )


def run_scheduled_capture(
    capture: Callable[[], dict[str, Any]],
    *,
    counter_path: Path,
    audit_path: Path,
    alert_path: Path | None = None,
    attempts: int = 2,
    retry_delay_seconds: float = 2.0,
    alert_after: int = 3,
) -> tuple[dict[str, Any], int]:
    """Run bounded retries and return a scheduler-readable result and exit code."""
    if attempts < 1 or alert_after < 1:
        raise ValueError("attempts and alert_after must be positive")
    errors = []
    result = None
    for attempt in range(1, attempts + 1):
        try:
            result = capture()
            if result.get("captured") is not True:
                raise RuntimeError("capture result is not confirmed")
            break
        except Exception as exc:  # scheduler boundary records the exact failure
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < attempts and retry_delay_seconds > 0:
                time.sleep(float(retry_delay_seconds))

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if result is not None:
        _write_counter(counter_path, 0)
        payload = {
            "ok": True,
            "captured": True,
            "attempts": len(errors) + 1,
            "consecutive_failures": 0,
            "alert_required": False,
            "snapshot_id": result.get("snapshot_id"),
            "snapshot_ts": result.get("snapshot_ts"),
            "state_status": result.get("state_status"),
            "recorded_at": now,
        }
        _append_audit(audit_path, payload)
        if alert_path is not None:
            _write_alert(alert_path, {
                "active": False,
                "resolved_at": now,
                "last_snapshot_id": result.get("snapshot_id"),
            })
        return payload, 0

    consecutive = _read_counter(counter_path) + 1
    alert_required = consecutive >= int(alert_after)
    stored_counter = 0 if alert_required else consecutive
    _write_counter(counter_path, stored_counter)
    payload = {
        "ok": False,
        "captured": False,
        "attempts": attempts,
        "consecutive_failures": consecutive,
        "alert_required": alert_required,
        "failure_counter_after_run": stored_counter,
        "error": errors[-1] if errors else "unknown capture failure",
        "error_history": errors,
        "recorded_at": now,
        "prohibited_live_mutations_performed": False,
    }
    _append_audit(audit_path, payload)
    if alert_required and alert_path is not None:
        _write_alert(alert_path, {
            "active": True,
            "alert_type": "ADVICE_SNAPSHOT_CAPTURE_FAILED",
            "consecutive_failures": consecutive,
            "error": payload["error"],
            "raised_at": now,
            "prohibited_live_mutations_performed": False,
        })
    return payload, 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OpenClaw/任务计划用建议快照采集包装器"
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--alert-after", type=int, default=3)
    parser.add_argument("--counter", default=str(DEFAULT_COUNTER))
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--alert", default=str(DEFAULT_ALERT))
    parser.add_argument(
        "--ignore-market-window",
        action="store_true",
        help="仅供手工 smoke；计划任务默认只在纽约工作日 09:00--15:59 采集",
    )
    args = parser.parse_args()
    if not args.ignore_market_window and not is_us_capture_window():
        print(json.dumps({
            "ok": True,
            "captured": False,
            "skipped": True,
            "reason": "OUTSIDE_US_CAPTURE_WINDOW",
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    payload, exit_code = run_scheduled_capture(
        lambda: capture_snapshot(args.url, args.timeout),
        counter_path=Path(args.counter),
        audit_path=Path(args.audit),
        alert_path=Path(args.alert),
        attempts=int(args.attempts),
        retry_delay_seconds=float(args.retry_delay),
        alert_after=int(args.alert_after),
    )
    stream = sys.stdout if exit_code == 0 else sys.stderr
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=stream)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
