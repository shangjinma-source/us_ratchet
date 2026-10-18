"""Plan or import an authenticated Nasdaq GIW NDX corporate-action export."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from data.ndx_giw_event_evidence import (  # noqa: E402
    NdxGiwEventEvidenceError,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    normalize_giw_export,
)
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest  # noqa: E402


DEFAULT_OUTPUT = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "gral_giw_evidence_intake"
GIW_PAGE = "https://indexes.nasdaq.com/Index/CorpActions/NDX"


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def write_plan(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "plan_type": "ndx_gral_authenticated_giw_evidence_intake",
        "generated_at": utc_now_iso(),
        "official_source_page": GIW_PAGE,
        "access_requirement": "NASDAQ_GIW_AUTHENTICATED_EXPORT",
        "requested_index_symbol": "NDX",
        "requested_date_start": "2024-06-01",
        "requested_date_end": "2024-07-31",
        "requested_ticker": "GRAL",
        "required_fields": list(REQUIRED_FIELDS),
        "optional_fields": list(OPTIONAL_FIELDS),
        "accepted_file_types": ["csv", "txt", "xlsx", "xls"],
        "manual_action_classification_required": True,
        "exact_registry_mutation_allowed": False,
        "historical_backtest_allowed": False,
        "v11_execution_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
        "note": "Export NDX corporate actions from authenticated GIW. The importer hashes and preserves matching rows but never guesses the GRAL removal date.",
    }
    atomic_write_text(
        output_dir / "plan.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload


def import_export(input_path: Path, output_dir: Path) -> dict:
    rows, summary = normalize_giw_export(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_hash = file_sha256(input_path)
    raw_path = raw_dir / f"ndx_corporate_actions_{raw_hash[:16]}{input_path.suffix.lower()}"
    if raw_path.exists() and file_sha256(raw_path) != raw_hash:
        raise NdxGiwEventEvidenceError(f"immutable raw export collision: {raw_path}")
    if not raw_path.exists():
        shutil.copyfile(input_path, raw_path)
    rows_path = output_dir / "gral_candidate_rows.csv"
    temporary = rows_path.with_name(rows_path.name + ".tmp")
    rows.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(rows_path)
    write_dataset_manifest(
        rows_path,
        dataset_type="ndx_giw_corporate_action_evidence_intake",
        dataset_key="ndx_gral_giw_evidence_intake_v1",
        source="Nasdaq Global Index Watch authenticated user export",
        source_locator=GIW_PAGE,
        fetched_at=utc_now_iso(),
        fetched_at_evidence="user_supplied_authenticated_export",
        row_count=len(rows),
        data_start=min(summary["effective_dates"]),
        data_end=max(summary["effective_dates"]),
        extra={**summary, "raw_export_sha256": raw_hash, "raw_export_path": raw_path.as_posix()},
    )
    manifest = {
        "schema_version": 1,
        "dataset_key": "ndx_gral_giw_evidence_intake_v1",
        "generated_at": utc_now_iso(),
        **summary,
        "official_source_page": GIW_PAGE,
        "raw_export_path": raw_path.as_posix(),
        "raw_export_sha256": raw_hash,
        "normalized_rows_path": rows_path.as_posix(),
        "normalized_rows_sha256": file_sha256(rows_path),
        "exact_registry_mutation_performed": False,
        "event_gap_disposition_mutation_performed": False,
    }
    atomic_write_text(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Nasdaq GIW GRAL 公司行动证据导入")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--import-export", default="")
    args = parser.parse_args()
    output_dir = _resolve(args.output_dir)
    try:
        payload = (
            write_plan(output_dir)
            if args.plan_only
            else import_export(_resolve(args.import_export), output_dir)
        )
    except (NdxGiwEventEvidenceError, OSError, ValueError) as exc:
        print(f"GIW 证据导入失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
