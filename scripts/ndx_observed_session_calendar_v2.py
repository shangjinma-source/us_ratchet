r"""Read-only readiness audit for the reviewed observed-session calendar v2.

This entry point deliberately cannot create or activate the v2 ledger.  It
proves the legacy boundary and reports vendor revisions before a separately
reviewed versioned migration is built.

PowerShell:
    python -B scripts\ndx_observed_session_calendar_v2.py --readiness
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_observed_session_calendar_v2 import (  # noqa: E402
    NdxObservedSessionCalendarV2Error,
    build_migration_readiness,
    capture_source_snapshot,
    write_canonical_reviewed_calendar_v2,
)


V1_ROOT = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1"
V1_MANIFEST = V1_ROOT / "manifest.json"
V1_LEDGER = V1_ROOT / "sessions.jsonl"
DEFAULT_SOURCES = {
    "QQQ": ROOT / "data/cache/QQQ.csv",
    "SPY": ROOT / "data/cache/SPY.csv",
}


def readiness() -> dict:
    missing = [path.as_posix() for path in [V1_MANIFEST, V1_LEDGER, *DEFAULT_SOURCES.values()] if not path.is_file()]
    if missing:
        raise NdxObservedSessionCalendarV2Error(
            "required canonical input is missing: " + ", ".join(missing)
        )
    current_snapshot = capture_source_snapshot(
        DEFAULT_SOURCES, tickers=list(DEFAULT_SOURCES), start_date="2026-07-01",
        observed_at_utc=datetime.now(timezone.utc),
    )
    return build_migration_readiness(
        v1_manifest_path=V1_MANIFEST,
        v1_ledger_path=V1_LEDGER,
        current_snapshot=current_snapshot,
        tickers=list(DEFAULT_SOURCES),
        calendar_start_date="2026-07-01",
        prospective_start_date="2026-10-01",
    )


def execute(*, initialize_reviewed_v1: bool) -> dict:
    missing = [path.as_posix() for path in DEFAULT_SOURCES.values() if not path.is_file()]
    if missing:
        raise NdxObservedSessionCalendarV2Error(
            "required canonical source is missing: " + ", ".join(missing)
        )
    snapshot = capture_source_snapshot(
        DEFAULT_SOURCES, tickers=list(DEFAULT_SOURCES), start_date="2026-07-01",
        observed_at_utc=datetime.now(timezone.utc),
    )
    verified = write_canonical_reviewed_calendar_v2(
        repository_root=ROOT, snapshot=snapshot,
        calendar_start_date="2026-07-01", prospective_start_date="2026-10-01",
        initialize_reviewed_v1=initialize_reviewed_v1,
    )
    return {
        "manifest_type": verified.manifest["manifest_type"],
        "status": verified.manifest["status"],
        "session_count": verified.manifest["session_count"],
        "event_count": verified.manifest["event_count"],
        "decision_eligible_session_count": verified.manifest["decision_eligible_session_count"],
        "manifest_path": verified.manifest_path.as_posix(),
        "manifest_sha256": verified.manifest["manifest_sha256"],
        "automation_registration_allowed": False,
    }
def main() -> int:
    parser = argparse.ArgumentParser(description="Reviewed calendar v2 readiness")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--readiness", action="store_true")
    mode.add_argument("--initialize-reviewed-v1", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        payload = readiness() if args.readiness else execute(
            initialize_reviewed_v1=bool(args.initialize_reviewed_v1),
        )
    except (NdxObservedSessionCalendarV2Error, OSError, ValueError) as exc:
        print(f"reviewed calendar v2 readiness fail-closed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
