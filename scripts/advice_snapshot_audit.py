"""Audit and optionally repair the append-only advice snapshot journal.

PowerShell / PyCharm:
    python -B scripts\advice_snapshot_audit.py
    python -B scripts\advice_snapshot_audit.py --repair-meta

The default mode is read-only.  ``--repair-meta`` only rewrites the sidecar
health metadata; it never changes the JSONL journal, config, state, or advice.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text
from core.persist import (
    advice_snapshot_storage,
    rebuild_advice_snapshot_meta,
    scan_advice_snapshot_journal,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="审计/修复建议快照日志侧车")
    parser.add_argument("--path", default="data/advice_snapshots.jsonl")
    parser.add_argument("--repair-meta", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-invalid", action="store_true")
    args = parser.parse_args()

    scan = scan_advice_snapshot_journal(args.path)
    meta = rebuild_advice_snapshot_meta(args.path) if args.repair_meta else None
    storage = advice_snapshot_storage(args.path)
    if meta is not None:
        storage = {**storage, **meta}
    compared_fields = (
        "row_count", "valid_row_count", "invalid_row_count", "first_ts",
        "last_ts", "last_snapshot_id",
    )
    mismatches = {
        field: {"sidecar": storage.get(field), "scan": scan.get(field)}
        for field in compared_fields
        if storage.get(field) != scan.get(field)
    }
    payload = {
        "path": str(Path(args.path).resolve()),
        "repair_meta": bool(args.repair_meta),
        "audited_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "full_scan": scan,
        "storage": storage,
        "sidecar_consistent": not mismatches,
        "sidecar_mismatches": mismatches,
        "ok": not mismatches and int(scan.get("invalid_row_count") or 0) == 0,
        "prohibited_live_mutations_performed": False,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        atomic_write_text(Path(args.output), encoded)
    print(encoded, end="")
    if args.fail_on_invalid and not payload["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
