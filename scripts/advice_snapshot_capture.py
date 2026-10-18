"""Capture one durable, read-only advice snapshot from the local API.

The dashboard already appends a compact advice snapshot when ``/api/state``
is requested.  This command provides an independent recorder for OpenClaw or
Windows Task Scheduler, so history does not depend on the browser remaining
open.  The API call may refresh quotes, but it never changes config, portfolio
state, today's advice, or a broker order.

PowerShell / PyCharm::

    python -B scripts\advice_snapshot_capture.py
    python -B scripts\advice_snapshot_capture.py --url http://127.0.0.1:8010/api/state
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_URL = "http://127.0.0.1:8010/api/state"


def summarize_capture_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the API response and return a small scheduler-friendly result."""
    if not isinstance(payload, dict):
        raise ValueError("/api/state 返回的不是 JSON 对象")
    snapshot = payload.get("advice_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("logged") is not True:
        detail = snapshot.get("error") if isinstance(snapshot, dict) else "missing_advice_snapshot"
        raise RuntimeError(f"建议快照未成功落盘: {detail}")

    freshness = payload.get("state_freshness") or {}
    market = payload.get("market") or {}
    execution = payload.get("execution") or {}
    return {
        "captured": True,
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_ts": snapshot.get("ts"),
        "journal_path": snapshot.get("path"),
        "as_of": payload.get("as_of"),
        "latest_closed_session_date": payload.get("latest_closed_session_date"),
        "state_last_run_date": payload.get("state_last_run_date"),
        "state_status": freshness.get("status"),
        "market_regime": market.get("regime"),
        "actionable_count": execution.get("actionable_count"),
        "execution_counts": execution.get("counts") or {},
    }


def capture_snapshot(url: str = DEFAULT_URL, timeout: float = 20.0) -> dict[str, Any]:
    """Request ``/api/state`` and fail closed unless the journal confirms a write."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "us_ratchet_snapshot_capture/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=float(timeout)) as response:
        raw = response.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"/api/state 返回内容无法解析: {exc}") from exc
    return summarize_capture_payload(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="记录一条持久化黄金坑/今日建议快照")
    parser.add_argument("--url", default=DEFAULT_URL, help="本地 us_ratchet /api/state 地址")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP 超时秒数")
    args = parser.parse_args()
    try:
        result = capture_snapshot(args.url, args.timeout)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(json.dumps({"captured": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
