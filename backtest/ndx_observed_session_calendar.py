"""Append-only calendar of already observed common US-equity OHLC sessions."""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
RECORD_KEYS = {
    "schema_version",
    "sequence",
    "session_date",
    "open_timestamp_ny",
    "close_timestamp_ny",
    "open_timestamp_utc",
    "close_timestamp_utc",
    "close_timestamp_role",
    "completed",
    "common_source_tickers",
    "source_rows",
    "source_snapshot_sha256",
    "origin",
    "decision_eligible",
    "recorded_at_utc",
    "previous_record_sha256",
    "record_sha256",
}
SOURCE_ROW_KEYS = {"ticker", "row_sha256"}
BOOTSTRAP_ORIGIN = "HISTORICAL_BOOTSTRAP_NOT_FRESH_EVIDENCE"
PROSPECTIVE_ORIGIN = "PROSPECTIVE_OBSERVED_APPEND"
CLOSE_TIMESTAMP_ROLE = "CONSERVATIVE_REGULAR_SESSION_COMPLETION_BOUNDARY"


class NdxObservedSessionCalendarError(ValueError):
    """Raised when the observed-session ledger cannot remain immutable."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_date(value: str, label: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise NdxObservedSessionCalendarError(f"invalid {label}: {value}") from exc
    if parsed.isoformat() != str(value):
        raise NdxObservedSessionCalendarError(f"non-canonical {label}: {value}")
    return parsed


def _utc_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise NdxObservedSessionCalendarError(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise NdxObservedSessionCalendarError(f"{label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _normalized_number(value: Any, label: str) -> str:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise NdxObservedSessionCalendarError(f"invalid finite {label}") from exc
    if not number.is_finite():
        raise NdxObservedSessionCalendarError(f"invalid finite {label}")
    normalized = format(number.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def load_ohlc_rows(path: Path, *, ticker: str) -> dict[str, dict[str, Any]]:
    required = ("Date", "Open", "High", "Low", "Close", "Volume")
    rows: dict[str, dict[str, Any]] = {}
    prior: date | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise NdxObservedSessionCalendarError(f"{ticker} OHLC columns are incomplete")
        for raw in reader:
            session = _strict_date(str(raw.get("Date") or ""), f"{ticker} Date")
            if prior is not None and session <= prior:
                raise NdxObservedSessionCalendarError(
                    f"{ticker} OHLC dates must be unique and strictly increasing"
                )
            prior = session
            normalized = {
                "Date": session.isoformat(),
                **{
                    column: _normalized_number(raw.get(column), f"{ticker} {column}")
                    for column in required[1:]
                },
            }
            rows[session.isoformat()] = {
                "row_sha256": canonical_sha256(normalized),
                "normalized": normalized,
            }
    if not rows:
        raise NdxObservedSessionCalendarError(f"{ticker} OHLC is empty")
    return rows


def session_timestamps(session_date: str) -> dict[str, str]:
    session = _strict_date(session_date, "session_date")
    open_ny = datetime.combine(session, time(9, 30), tzinfo=NEW_YORK)
    close_ny = datetime.combine(session, time(16, 0), tzinfo=NEW_YORK)
    return {
        "open_timestamp_ny": open_ny.isoformat(),
        "close_timestamp_ny": close_ny.isoformat(),
        "open_timestamp_utc": open_ny.astimezone(UTC).isoformat(),
        "close_timestamp_utc": close_ny.astimezone(UTC).isoformat(),
    }


def observed_common_dates(
    source_rows: Mapping[str, Mapping[str, Any]],
    *,
    start_date: str,
    observed_at_utc: datetime,
) -> tuple[list[str], list[str]]:
    if observed_at_utc.tzinfo is None:
        raise NdxObservedSessionCalendarError("observed_at_utc must be timezone-aware")
    start = _strict_date(start_date, "start_date")
    source_sets = [set(rows) for rows in source_rows.values()]
    if len(source_sets) < 2:
        raise NdxObservedSessionCalendarError("at least two common OHLC sources are required")
    common = sorted(set.intersection(*source_sets))
    completed: list[str] = []
    not_completed: list[str] = []
    cutoff = observed_at_utc.astimezone(UTC)
    for value in common:
        if _strict_date(value, "source session") < start:
            continue
        close_utc = _utc_datetime(
            session_timestamps(value)["close_timestamp_utc"], "close_timestamp_utc"
        )
        if close_utc <= cutoff:
            completed.append(value)
        else:
            not_completed.append(value)
    return completed, not_completed


def _record_without_hash(record: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value.pop("record_sha256", None)
    return value


def make_record(
    *,
    sequence: int,
    session_date: str,
    tickers: Sequence[str],
    source_rows: Mapping[str, Mapping[str, Any]],
    source_snapshot_sha256: Mapping[str, str],
    origin: str,
    prospective_start_date: str,
    recorded_at_utc: datetime,
    previous_record_sha256: str | None,
) -> dict[str, Any]:
    if origin not in {BOOTSTRAP_ORIGIN, PROSPECTIVE_ORIGIN}:
        raise NdxObservedSessionCalendarError(f"unsupported record origin: {origin}")
    session = _strict_date(session_date, "session_date")
    prospective_start = _strict_date(prospective_start_date, "prospective_start_date")
    decision_eligible = origin == PROSPECTIVE_ORIGIN and session >= prospective_start
    timestamps = session_timestamps(session_date)
    record = {
        "schema_version": 1,
        "sequence": int(sequence),
        "session_date": session.isoformat(),
        **timestamps,
        "close_timestamp_role": CLOSE_TIMESTAMP_ROLE,
        "completed": True,
        "common_source_tickers": list(tickers),
        "source_rows": [
            {"ticker": ticker, "row_sha256": str(source_rows[ticker][session_date]["row_sha256"])}
            for ticker in tickers
        ],
        "source_snapshot_sha256": {
            ticker: str(source_snapshot_sha256[ticker]) for ticker in tickers
        },
        "origin": origin,
        "decision_eligible": decision_eligible,
        "recorded_at_utc": recorded_at_utc.astimezone(UTC).isoformat(),
        "previous_record_sha256": previous_record_sha256,
    }
    record["record_sha256"] = canonical_sha256(record)
    return record


def validate_ledger(
    records: Sequence[Mapping[str, Any]],
    *,
    tickers: Sequence[str],
    prospective_start_date: str,
    current_source_rows: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    expected_tickers = list(tickers)
    prospective_start = _strict_date(prospective_start_date, "prospective_start_date")
    prior_hash: str | None = None
    prior_date: date | None = None
    prior_recorded: datetime | None = None
    for index, raw in enumerate(records, start=1):
        record = dict(raw)
        if set(record) != RECORD_KEYS:
            raise NdxObservedSessionCalendarError("session ledger record schema changed")
        if record.get("schema_version") != 1 or record.get("sequence") != index:
            raise NdxObservedSessionCalendarError("session ledger sequence is invalid")
        session = _strict_date(str(record.get("session_date")), "ledger session_date")
        if prior_date is not None and session <= prior_date:
            raise NdxObservedSessionCalendarError("session ledger dates are not increasing")
        prior_date = session
        if record.get("previous_record_sha256") != prior_hash:
            raise NdxObservedSessionCalendarError("session ledger hash chain is broken")
        observed_hash = str(record.get("record_sha256") or "")
        if len(observed_hash) != 64 or canonical_sha256(_record_without_hash(record)) != observed_hash:
            raise NdxObservedSessionCalendarError("session ledger record hash mismatch")
        prior_hash = observed_hash
        if record.get("completed") is not True:
            raise NdxObservedSessionCalendarError("session ledger contains an incomplete bar")
        if record.get("common_source_tickers") != expected_tickers:
            raise NdxObservedSessionCalendarError("session ledger source ticker set changed")
        source_items = record.get("source_rows")
        if not isinstance(source_items, list) or len(source_items) != len(expected_tickers):
            raise NdxObservedSessionCalendarError("session source-row proof is incomplete")
        if any(set(item) != SOURCE_ROW_KEYS for item in source_items):
            raise NdxObservedSessionCalendarError("session source-row proof schema changed")
        if [item["ticker"] for item in source_items] != expected_tickers:
            raise NdxObservedSessionCalendarError("session source-row ticker order changed")
        if any(
            len(str(item.get("row_sha256") or "")) != 64
            or any(character not in "0123456789abcdef" for character in str(item.get("row_sha256") or ""))
            for item in source_items
        ):
            raise NdxObservedSessionCalendarError("session source-row hash is invalid")
        source_snapshots = record.get("source_snapshot_sha256")
        if not isinstance(source_snapshots, Mapping) or list(source_snapshots) != expected_tickers:
            raise NdxObservedSessionCalendarError("session source snapshot proof is incomplete")
        if any(
            len(str(source_snapshots[ticker])) != 64
            or any(character not in "0123456789abcdef" for character in str(source_snapshots[ticker]))
            for ticker in expected_tickers
        ):
            raise NdxObservedSessionCalendarError("session source snapshot hash is invalid")
        if current_source_rows is not None:
            for item in source_items:
                ticker = str(item["ticker"])
                current = current_source_rows.get(ticker, {}).get(session.isoformat())
                if current is None or current.get("row_sha256") != item.get("row_sha256"):
                    raise NdxObservedSessionCalendarError(
                        f"observed OHLC history changed for {ticker} {session.isoformat()}"
                    )
        timestamps = session_timestamps(session.isoformat())
        for key, expected in timestamps.items():
            if record.get(key) != expected:
                raise NdxObservedSessionCalendarError("session timestamp proof changed")
        if record.get("close_timestamp_role") != CLOSE_TIMESTAMP_ROLE:
            raise NdxObservedSessionCalendarError("close timestamp role changed")
        origin = record.get("origin")
        if origin not in {BOOTSTRAP_ORIGIN, PROSPECTIVE_ORIGIN}:
            raise NdxObservedSessionCalendarError("session origin is invalid")
        expected_eligible = origin == PROSPECTIVE_ORIGIN and session >= prospective_start
        if record.get("decision_eligible") is not expected_eligible:
            raise NdxObservedSessionCalendarError("decision eligibility is inconsistent")
        recorded = _utc_datetime(str(record.get("recorded_at_utc")), "recorded_at_utc")
        close_utc = _utc_datetime(str(record.get("close_timestamp_utc")), "close_timestamp_utc")
        if recorded < close_utc:
            raise NdxObservedSessionCalendarError("session was recorded before completion boundary")
        if prior_recorded is not None and recorded < prior_recorded:
            raise NdxObservedSessionCalendarError("recorded_at_utc is not monotonic")
        prior_recorded = recorded


def load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                raise NdxObservedSessionCalendarError(f"blank ledger row: {number}")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise NdxObservedSessionCalendarError(f"invalid ledger JSON row: {number}") from exc
            if not isinstance(value, dict):
                raise NdxObservedSessionCalendarError(f"ledger row is not an object: {number}")
            records.append(value)
    return records


def append_records_durable(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def prepare_update(
    existing: Sequence[Mapping[str, Any]],
    *,
    completed_dates: Sequence[str],
    tickers: Sequence[str],
    source_rows: Mapping[str, Mapping[str, Any]],
    source_snapshot_sha256: Mapping[str, str],
    prospective_start_date: str,
    recorded_at_utc: datetime,
    bootstrap: bool,
) -> list[dict[str, Any]]:
    validate_ledger(
        existing,
        tickers=tickers,
        prospective_start_date=prospective_start_date,
        current_source_rows=source_rows,
    )
    existing_dates = [str(record["session_date"]) for record in existing]
    completed = list(completed_dates)
    if existing_dates != completed[: len(existing_dates)]:
        raise NdxObservedSessionCalendarError(
            "observed calendar/source prefix changed; retrospective insertion is forbidden"
        )
    pending = completed[len(existing_dates) :]
    if not existing:
        if not bootstrap:
            raise NdxObservedSessionCalendarError(
                "initial historical calendar seed requires explicit bootstrap"
            )
        origin = BOOTSTRAP_ORIGIN
    else:
        if bootstrap:
            raise NdxObservedSessionCalendarError("bootstrap cannot modify an existing ledger")
        if len(pending) > 1:
            raise NdxObservedSessionCalendarError(
                "multiple observed sessions are pending; retrospective calendar backfill is forbidden"
            )
        origin = PROSPECTIVE_ORIGIN
    additions: list[dict[str, Any]] = []
    prior_hash = str(existing[-1]["record_sha256"]) if existing else None
    for offset, session_date in enumerate(pending, start=1):
        record = make_record(
            sequence=len(existing) + offset,
            session_date=session_date,
            tickers=tickers,
            source_rows=source_rows,
            source_snapshot_sha256=source_snapshot_sha256,
            origin=origin,
            prospective_start_date=prospective_start_date,
            recorded_at_utc=recorded_at_utc,
            previous_record_sha256=prior_hash,
        )
        additions.append(record)
        prior_hash = str(record["record_sha256"])
    return additions


def projection_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    dates = [str(record["session_date"]) for record in records]
    for index, record in enumerate(records):
        current = _strict_date(dates[index], "projection session_date")
        prior = _strict_date(dates[index - 1], "projection prior date") if index else None
        first_of_month = prior is None or (prior.year, prior.month) != (current.year, current.month)
        result.append(
            {
                "sequence": int(record["sequence"]),
                "session_date": current.isoformat(),
                "open_timestamp_ny": record["open_timestamp_ny"],
                "close_timestamp_ny": record["close_timestamp_ny"],
                "open_timestamp_utc": record["open_timestamp_utc"],
                "close_timestamp_utc": record["close_timestamp_utc"],
                "completed": True,
                "is_first_observed_session_of_month": first_of_month,
                "next_observed_session_date": dates[index + 1] if index + 1 < len(dates) else "",
                "origin": record["origin"],
                "decision_eligible": bool(record["decision_eligible"]),
                "record_sha256": record["record_sha256"],
            }
        )
    return result


__all__ = [
    "BOOTSTRAP_ORIGIN",
    "CLOSE_TIMESTAMP_ROLE",
    "NdxObservedSessionCalendarError",
    "PROSPECTIVE_ORIGIN",
    "append_records_durable",
    "canonical_sha256",
    "file_sha256",
    "load_ledger",
    "load_ohlc_rows",
    "observed_common_dates",
    "prepare_update",
    "projection_rows",
    "session_timestamps",
    "validate_ledger",
]
