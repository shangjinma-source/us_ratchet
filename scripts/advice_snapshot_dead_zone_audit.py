"""Create a read-only session audit of executable whole-lot buy availability."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.tactical_dead_zone import summarize_tactical_dead_zone
from core.persist import iter_advice_snapshots


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/advice_snapshots.jsonl")
    parser.add_argument(
        "--output-dir",
        default="data/cache/research/advice_snapshot_dead_zone_audit_v1",
    )
    args = parser.parse_args()
    source = Path(args.input)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = summarize_tactical_dead_zone(iter_advice_snapshots(source))
    csv_path = output / "session_dead_zone.csv"
    fields = list(result["sessions"][0]) if result["sessions"] else ["session_date"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result["sessions"])
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "purpose": "PRODUCTION_TACTICAL_DEAD_ZONE_AUDIT",
        "input": str(source).replace("\\", "/"),
        "input_sha256": _sha256(source),
        "input_bytes": source.stat().st_size,
        "session_count": result["session_count"],
        "zero_whole_lot_buy_session_count": result["zero_whole_lot_buy_session_count"],
        "whole_lot_buy_session_count": result["whole_lot_buy_session_count"],
        "first_session": result["first_session"],
        "last_session": result["last_session"],
        "invalid_session_rows": result["invalid_session_rows"],
        "session_csv": str(csv_path).replace("\\", "/"),
        "session_csv_sha256": _sha256(csv_path),
        "return_data_read": False,
        "fresh_oos_consumed": False,
        "orders_created": False,
        "config_state_today_advice_changed": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "战术整股死区审计完成 | "
        f"sessions={result['session_count']} | "
        f"zero_whole_lot={result['zero_whole_lot_buy_session_count']} | "
        f"whole_lot_seen={result['whole_lot_buy_session_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
