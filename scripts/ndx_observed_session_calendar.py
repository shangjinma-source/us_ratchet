r"""Build or verify the append-only observed US-session calendar.

PowerShell bootstrap:
    python -B scripts\ndx_observed_session_calendar.py --execute --bootstrap
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_observed_session_calendar import (  # noqa: E402
    BOOTSTRAP_ORIGIN,
    NdxObservedSessionCalendarError,
    append_records_durable,
    file_sha256,
    load_ledger,
    load_ohlc_rows,
    observed_common_dates,
    prepare_update,
    projection_rows,
    validate_ledger,
)
from core.helpers import atomic_write_text  # noqa: E402


DEFAULT_OUTPUT = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1"
DEFAULT_SOURCES = ("QQQ=data/cache/QQQ.csv", "SPY=data/cache/SPY.csv")
PROTECTED = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _parse_sources(values: list[str] | None) -> dict[str, Path]:
    entries = list(values or DEFAULT_SOURCES)
    sources: dict[str, Path] = {}
    for entry in entries:
        ticker, separator, raw_path = entry.partition("=")
        ticker = ticker.strip().upper()
        if separator != "=" or not ticker or not raw_path.strip():
            raise NdxObservedSessionCalendarError(f"invalid --source: {entry}")
        if ticker in sources:
            raise NdxObservedSessionCalendarError(f"duplicate source ticker: {ticker}")
        path = _resolve(raw_path.strip())
        if not path.is_file():
            raise NdxObservedSessionCalendarError(f"source OHLC file missing: {path}")
        source_root = (ROOT / "data/cache").resolve()
        if not path.is_relative_to(source_root):
            raise NdxObservedSessionCalendarError(f"source OHLC must stay under data/cache: {path}")
        sources[ticker] = path
    if list(sources) != sorted(sources):
        sources = dict(sorted(sources.items()))
    if len(sources) < 2 or "QQQ" not in sources:
        raise NdxObservedSessionCalendarError("sources require QQQ plus at least one common reference")
    return sources


def _parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise NdxObservedSessionCalendarError("--as-of-utc must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise NdxObservedSessionCalendarError("--as-of-utc must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _protected_hashes() -> dict[str, str | None]:
    return {
        path.relative_to(ROOT).as_posix(): file_sha256(path) if path.is_file() else None
        for path in PROTECTED
    }


def _projection_text(rows: list[dict[str, Any]]) -> str:
    fieldnames = [
        "sequence",
        "session_date",
        "open_timestamp_ny",
        "close_timestamp_ny",
        "open_timestamp_utc",
        "close_timestamp_utc",
        "completed",
        "is_first_observed_session_of_month",
        "next_observed_session_date",
        "origin",
        "decision_eligible",
        "record_sha256",
    ]
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _write_projection(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_text(path, _projection_text(rows))


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NdxObservedSessionCalendarError(f"{label} must be a mapping")
    return value


def _verify_saved_manifest(
    *,
    manifest_path: Path,
    ledger_path: Path,
    projection_path: Path,
    records: list[dict[str, Any]],
    projection: list[dict[str, Any]],
    sources: Mapping[str, Path],
    source_hashes: Mapping[str, str],
    start_date: str,
    prospective_start_date: str,
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise NdxObservedSessionCalendarError("calendar manifest is missing")
    try:
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NdxObservedSessionCalendarError("calendar manifest JSON is invalid") from exc
    if not isinstance(saved, dict):
        raise NdxObservedSessionCalendarError("calendar manifest must be an object")
    required_false = (
        "actual_early_close_timestamp_asserted",
        "future_or_in_progress_sessions_included",
        "retrospective_backfill_allowed",
        "bootstrap_history_counts_as_fresh_evidence",
        "source_history_revision_allowed",
        "promotion_allowed",
        "live_mutation_allowed",
        "state_changed",
        "broker_snapshot_changed",
        "today_advice_changed",
        "order_creation_allowed",
    )
    if (
        saved.get("manifest_type") != "ndx_observed_us_session_calendar"
        or saved.get("append_only_ledger") is not True
        or any(saved.get(key) is not False for key in required_false)
        or saved.get("calendar_scope") != "OBSERVED_COMMON_QQQ_REFERENCE_OHLC_ONLY"
        or saved.get("timezone") != "America/New_York"
        or saved.get("start_date") != start_date
        or saved.get("prospective_start_date") != prospective_start_date
    ):
        raise NdxObservedSessionCalendarError("calendar manifest safety contract changed")
    if int(saved.get("session_count", -1)) != len(records):
        raise NdxObservedSessionCalendarError("calendar manifest session count mismatch")
    expected_head = records[-1]["record_sha256"] if records else None
    if saved.get("latest_record_sha256") != expected_head:
        raise NdxObservedSessionCalendarError("calendar manifest ledger head mismatch")
    artifacts = _required_mapping(saved.get("artifacts"), "calendar artifacts")
    ledger_item = _required_mapping(artifacts.get("append_only_ledger"), "ledger artifact")
    projection_item = _required_mapping(artifacts.get("session_projection"), "projection artifact")
    if (
        Path(str(ledger_item.get("path"))).resolve() != ledger_path.resolve()
        or int(ledger_item.get("rows", -1)) != len(records)
        or ledger_item.get("sha256") != file_sha256(ledger_path)
    ):
        raise NdxObservedSessionCalendarError("calendar ledger artifact verification failed")
    if not projection_path.is_file() or projection_path.read_text(encoding="utf-8") != _projection_text(projection):
        raise NdxObservedSessionCalendarError("calendar projection is not derived from ledger")
    if (
        Path(str(projection_item.get("path"))).resolve() != projection_path.resolve()
        or int(projection_item.get("rows", -1)) != len(projection)
        or projection_item.get("sha256") != file_sha256(projection_path)
        or projection_item.get("derived_from_ledger") is not True
    ):
        raise NdxObservedSessionCalendarError("calendar projection artifact verification failed")
    inputs = _required_mapping(saved.get("inputs"), "calendar inputs")
    source_items = inputs.get("sources")
    if not isinstance(source_items, list) or len(source_items) != len(sources):
        raise NdxObservedSessionCalendarError("calendar source manifest is incomplete")
    for item, (ticker, path) in zip(source_items, sources.items(), strict=True):
        if not isinstance(item, Mapping) or (
            item.get("ticker") != ticker
            or Path(str(item.get("path"))).resolve() != path.resolve()
            or item.get("sha256") != source_hashes[ticker]
        ):
            raise NdxObservedSessionCalendarError("calendar source identity/hash changed")
    for name, current in (
        ("engine", ROOT / "backtest/ndx_observed_session_calendar.py"),
        ("runner", Path(__file__).resolve()),
    ):
        item = _required_mapping(inputs.get(name), f"calendar {name} input")
        if (
            Path(str(item.get("path"))).resolve() != current.resolve()
            or item.get("sha256") != file_sha256(current)
        ):
            raise NdxObservedSessionCalendarError(f"calendar {name} identity/hash changed")
    return saved


def run(args: argparse.Namespace) -> dict[str, Any]:
    sources = _parse_sources(args.source)
    output = _resolve(args.output_dir)
    research_root = (ROOT / "data/cache/research").resolve()
    if not output.is_relative_to(research_root):
        raise NdxObservedSessionCalendarError("calendar output must stay under data/cache/research")
    ledger_path = output / "sessions.jsonl"
    projection_path = output / "sessions.csv"
    manifest_path = output / "manifest.json"
    observed_at = _parse_as_of(args.as_of_utc)
    protected_before = _protected_hashes()
    source_rows = {
        ticker: load_ohlc_rows(path, ticker=ticker) for ticker, path in sources.items()
    }
    source_hashes = {ticker: file_sha256(path) for ticker, path in sources.items()}
    completed_dates, excluded_not_completed = observed_common_dates(
        source_rows, start_date=args.start_date, observed_at_utc=observed_at
    )
    existing = load_ledger(ledger_path)
    prior_manifest = None
    if manifest_path.is_file():
        try:
            prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise NdxObservedSessionCalendarError("existing calendar manifest JSON is invalid") from exc
        legacy_boundary_upgrade = (
            prior_manifest.get("start_date") is None
            and prior_manifest.get("prospective_start_date") is None
            and int(prior_manifest.get("prospective_observed_session_count", -1)) == 0
        )
        if not legacy_boundary_upgrade and (
            prior_manifest.get("start_date") != args.start_date
            or prior_manifest.get("prospective_start_date") != args.prospective_start_date
        ):
            raise NdxObservedSessionCalendarError("calendar version boundaries cannot change in place")
    additions = prepare_update(
        existing,
        completed_dates=completed_dates,
        tickers=list(sources),
        source_rows=source_rows,
        source_snapshot_sha256=source_hashes,
        prospective_start_date=args.prospective_start_date,
        recorded_at_utc=observed_at,
        bootstrap=bool(args.bootstrap),
    )
    if args.verify_only:
        if additions:
            raise NdxObservedSessionCalendarError(
                "observed source contains an unsealed session; execute append before verify-only"
            )
    elif not args.execute:
        raise NdxObservedSessionCalendarError("add --execute or --verify-only")
    else:
        output.mkdir(parents=True, exist_ok=True)
        append_records_durable(ledger_path, additions)

    records = load_ledger(ledger_path) if ledger_path.exists() else list(existing)
    validate_ledger(
        records,
        tickers=list(sources),
        prospective_start_date=args.prospective_start_date,
        current_source_rows=source_rows,
    )
    if [record["session_date"] for record in records] != completed_dates[: len(records)]:
        raise NdxObservedSessionCalendarError("sealed session prefix differs from observed sources")
    if len(records) != len(completed_dates):
        raise NdxObservedSessionCalendarError("unsealed observed sessions remain")
    projection = projection_rows(records)
    if args.execute:
        _write_projection(projection_path, projection)

    protected_after = _protected_hashes()
    if protected_before != protected_after:
        raise NdxObservedSessionCalendarError("protected live files changed")
    status = (
        "HISTORICAL_BOOTSTRAP_SEALED_NOT_FRESH_EVIDENCE"
        if additions and all(record["origin"] == BOOTSTRAP_ORIGIN for record in additions)
        else "PROSPECTIVE_OBSERVED_SESSION_APPENDED"
        if additions
        else "OBSERVED_SESSION_CALENDAR_CURRENT"
    )
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_observed_us_session_calendar",
        "generated_at": observed_at.astimezone(timezone.utc).isoformat(),
        "status": status,
        "calendar_scope": "OBSERVED_COMMON_QQQ_REFERENCE_OHLC_ONLY",
        "start_date": args.start_date,
        "prospective_start_date": args.prospective_start_date,
        "timezone": "America/New_York",
        "open_time_policy": "NOMINAL_REGULAR_SESSION_09_30_NEW_YORK",
        "close_time_policy": "CONSERVATIVE_REGULAR_SESSION_COMPLETION_BOUNDARY_16_00_NEW_YORK",
        "actual_early_close_timestamp_asserted": False,
        "future_or_in_progress_sessions_included": False,
        "append_only_ledger": True,
        "retrospective_backfill_allowed": False,
        "missed_multiple_session_action": "FAIL_CLOSED_REQUIRE_NEW_REVIEWED_CALENDAR_VERSION",
        "bootstrap_history_counts_as_fresh_evidence": False,
        "source_history_revision_allowed": False,
        "session_count": len(records),
        "bootstrap_session_count": sum(record["origin"] == BOOTSTRAP_ORIGIN for record in records),
        "prospective_observed_session_count": sum(record["origin"] != BOOTSTRAP_ORIGIN for record in records),
        "decision_eligible_session_count": sum(bool(record["decision_eligible"]) for record in records),
        "latest_session_date": records[-1]["session_date"] if records else None,
        "latest_record_sha256": records[-1]["record_sha256"] if records else None,
        "excluded_not_completed_source_dates": excluded_not_completed,
        "monthly_first_session_dates": [
            row["session_date"] for row in projection if row["is_first_observed_session_of_month"]
        ],
        "verified_next_session_link_count": max(len(records) - 1, 0),
        "inputs": {
            "sources": [
                {
                    "ticker": ticker,
                    "path": path.as_posix(),
                    "sha256": source_hashes[ticker],
                    "rows": len(source_rows[ticker]),
                    "data_start": min(source_rows[ticker]),
                    "data_end": max(source_rows[ticker]),
                }
                for ticker, path in sources.items()
            ],
            "engine": {
                "path": (ROOT / "backtest/ndx_observed_session_calendar.py").as_posix(),
                "sha256": file_sha256(ROOT / "backtest/ndx_observed_session_calendar.py"),
            },
            "runner": {
                "path": Path(__file__).resolve().as_posix(),
                "sha256": file_sha256(Path(__file__).resolve()),
            },
        },
        "artifacts": {
            "append_only_ledger": {
                "path": ledger_path.as_posix(),
                "rows": len(records),
                "sha256": file_sha256(ledger_path) if ledger_path.is_file() else None,
            },
            "session_projection": {
                "path": projection_path.as_posix(),
                "rows": len(projection),
                "sha256": file_sha256(projection_path) if projection_path.is_file() else None,
                "derived_from_ledger": True,
            },
        },
        "protected_hashes_before": protected_before,
        "protected_hashes_after": protected_after,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "state_changed": False,
        "broker_snapshot_changed": False,
        "today_advice_changed": False,
        "order_creation_allowed": False,
    }
    if args.execute:
        atomic_write_text(manifest_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        _verify_saved_manifest(
            manifest_path=manifest_path,
            ledger_path=ledger_path,
            projection_path=projection_path,
            records=records,
            projection=projection,
            sources=sources,
            source_hashes=source_hashes,
            start_date=args.start_date,
            prospective_start_date=args.prospective_start_date,
        )
    elif args.verify_only:
        _verify_saved_manifest(
            manifest_path=manifest_path,
            ledger_path=ledger_path,
            projection_path=projection_path,
            records=records,
            projection=projection,
            sources=sources,
            source_hashes=source_hashes,
            start_date=args.start_date,
            prospective_start_date=args.prospective_start_date,
        )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Observed common US-session calendar ledger")
    parser.add_argument("--source", action="append", default=None, help="TICKER=OHLC_CSV")
    parser.add_argument("--start-date", default="2026-07-01")
    parser.add_argument("--prospective-start-date", default="2026-10-01")
    parser.add_argument("--as-of-utc", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.execute and args.verify_only:
        parser.error("--execute and --verify-only are mutually exclusive")
    if args.bootstrap and not args.execute:
        parser.error("--bootstrap requires --execute")
    return args


def main() -> int:
    try:
        result = run(parse_args())
    except (NdxObservedSessionCalendarError, OSError, ValueError) as exc:
        print(f"observed US session calendar fail-closed: {exc}", file=sys.stderr)
        return 2
    print(
        "observed US session calendar | "
        f"status={result['status']} | sessions={result['session_count']} | "
        f"latest={result['latest_session_date']} | decision_eligible={result['decision_eligible_session_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
