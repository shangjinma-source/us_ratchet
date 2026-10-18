r"""Build the original-eight point-in-time execution-attribution projection."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_incumbent_pit_attribution import build_incumbent_pit_attribution
from core.helpers import atomic_write_text
from data.versioning import file_sha256


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run(args: argparse.Namespace) -> dict:
    source_manifest_path = _resolve(args.reviewed_manifest)
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    artifact = (source_manifest.get("artifacts") or {}).get("evidence_reviewed") or {}
    evidence_path = source_manifest_path.parent / str(artifact.get("filename") or "")
    if not evidence_path.is_file() or file_sha256(evidence_path) != artifact.get("sha256"):
        raise ValueError("reviewed incumbent evidence artifact mismatch")
    evidence = pd.read_csv(evidence_path, dtype=str, keep_default_na=False)
    if len(evidence) != int(artifact.get("rows") or -1):
        raise ValueError("reviewed incumbent evidence row count changed")
    selection_dates = [item.strip() for item in args.selection_dates.split(",") if item.strip()]
    projection = build_incumbent_pit_attribution(
        evidence, selection_dates, source_manifest=source_manifest,
    )

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    projection_path = output / "incumbent_pit_attribution.csv"
    _atomic_csv(projection, projection_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_incumbent_pit_execution_attribution",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "EXECUTION_ATTRIBUTION_ONLY_NOT_SELECTION_OR_ADMISSION",
        "selection_dates": selection_dates,
        "ticker_count_per_date": 8,
        "historical_backfill_allowed": False,
        "historical_backfill_created": False,
        "candidate_selection_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "inputs": {
            "reviewed_manifest": {"path": source_manifest_path.as_posix(), "sha256": file_sha256(source_manifest_path)},
            "reviewed_evidence": {"path": evidence_path.as_posix(), "sha256": file_sha256(evidence_path)},
            "source_overlay_historical_backfill_allowed": False,
        },
        "artifacts": {
            "projection": {"path": projection_path.as_posix(), "rows": len(projection), "sha256": file_sha256(projection_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="原八只执行归因专用的时点风险链投影")
    parser.add_argument("--reviewed-manifest", default="data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/manifest.json")
    parser.add_argument("--selection-dates", default="2023-07-03,2024-01-02,2024-06-03")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_incumbent_pit_attribution_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"原八只时点执行归因失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"原八只时点执行归因完成 | dates={len(payload['selection_dates'])} | backfill=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

