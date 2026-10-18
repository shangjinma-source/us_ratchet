"""Reviewed v2 observed-session calendar with immutable source-row evidence.

Version 1 stored only hashes for observed OHLC rows.  Once a data vendor revises
one of those rows, the original values cannot be reconstructed.  This module
therefore imports v1 sessions as explicitly unrecoverable ``legacy hash-only``
evidence.  New v2 sessions freeze the complete normalized OHLC rows.  Later
vendor revisions are append-only diagnostic events and never rewrite a sealed
session or silently substitute revised prices for the values first observed.

This is a research-only engine.  It does not register a task or mutate a live
configuration, state, broker snapshot, advice, or orders.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import hashlib
import io
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

import pandas as pd

from backtest.ndx_observed_session_calendar import (
    BOOTSTRAP_ORIGIN,
    CLOSE_TIMESTAMP_ROLE,
    PROSPECTIVE_ORIGIN,
    canonical_sha256,
    file_sha256,
    observed_common_dates,
    session_timestamps,
    validate_ledger as validate_v1_ledger,
)


UTC = timezone.utc
SCHEMA_VERSION = 2
LEGACY_SESSION_EVENT = "LEGACY_V1_HASH_ONLY_SESSION_IMPORTED"
PROSPECTIVE_SESSION_EVENT = "PROSPECTIVE_V2_SESSION_OBSERVED"
SOURCE_REVISION_EVENT = "SOURCE_ROW_REVISION_OBSERVED"
LEGACY_EVIDENCE_MODE = "LEGACY_HASH_ONLY_ORIGINAL_VALUES_UNRECOVERABLE"
FROZEN_EVIDENCE_MODE = "FULL_NORMALIZED_OHLC_FROZEN_AS_OBSERVED"
REVISION_ROLE = "DIAGNOSTIC_ONLY_DOES_NOT_REWRITE_SEALED_SESSION"
NORMALIZED_ROW_KEYS = {"Date", "Open", "High", "Low", "Close", "Volume"}
COMMON_EVENT_KEYS = {
    "schema_version",
    "event_sequence",
    "event_type",
    "event_recorded_at_utc",
    "previous_event_sha256",
    "event_sha256",
}
SESSION_EVENT_KEYS = COMMON_EVENT_KEYS | {
    "session_date",
    "open_timestamp_ny",
    "close_timestamp_ny",
    "open_timestamp_utc",
    "close_timestamp_utc",
    "close_timestamp_role",
    "completed",
    "common_source_tickers",
    "source_observations",
    "source_snapshot_id",
    "source_snapshot_sha256",
    "origin",
    "decision_eligible",
    "source_observed_at_utc",
    "legacy_v1_binding",
}
REVISION_EVENT_KEYS = COMMON_EVENT_KEYS | {
    "session_date",
    "ticker",
    "sealed_session_event_sha256",
    "sealed_row_sha256",
    "sealed_evidence_mode",
    "prior_observed_row_sha256",
    "revised_row_sha256",
    "revised_normalized_ohlc",
    "source_snapshot_id",
    "revised_source_snapshot_sha256",
    "revision_kind",
    "revision_role",
    "calendar_membership_changed",
    "sealed_as_observed_value_changed",
}
LEGACY_OBSERVATION_KEYS = {
    "ticker", "evidence_mode", "as_observed_row_sha256",
    "normalized_ohlc", "price_replay_available",
}
FROZEN_OBSERVATION_KEYS = set(LEGACY_OBSERVATION_KEYS)
CANONICAL_ROOT_RELATIVE = Path(
    "data/cache/research/ndx_observed_us_session_calendar_v2"
)
CANONICAL_MANIFEST_RELATIVE = CANONICAL_ROOT_RELATIVE / "manifest.json"
V2_MANIFEST_TYPE = "ndx_observed_us_session_calendar_v2"
V2_BOUNDARIES = {
    "research_only": True,
    "append_only_event_ledger": True,
    "legacy_normalized_ohlc_recoverable": False,
    "current_vendor_values_may_substitute_for_legacy_original": False,
    "source_revision_rewrites_sealed_session": False,
    "retrospective_session_backfill_allowed": False,
    "future_or_in_progress_sessions_allowed": False,
    "execution_price_evidence_is_separate": True,
    "automation_registration_allowed": False,
    "promotion_allowed": False,
    "live_mutation_allowed": False,
    "order_creation_allowed": False,
}
V2_MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "generated_at_utc", "status",
    "calendar_start_date", "prospective_start_date", "tickers",
    "session_count", "event_count", "revision_event_count",
    "decision_eligible_session_count", "latest_session_date",
    "latest_event_sha256", "inputs", "legacy_boundary", "source_snapshots",
    "artifacts", "boundaries", "protected_hashes_before",
    "protected_hashes_after", "commit_transaction_id", "manifest_sha256",
}
SNAPSHOT_MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "snapshot_id", "observed_at_utc",
    "start_date", "tickers", "completed_dates",
    "excluded_not_completed_dates", "sources", "manifest_sha256",
}
PROJECTION_FIELDS = [
    "session_sequence", "session_date", "open_timestamp_utc",
    "close_timestamp_utc", "is_first_observed_session_of_month",
    "next_observed_session_date", "origin", "decision_eligible",
    "source_price_replay_available", "session_event_sha256",
]


class NdxObservedSessionCalendarV2Error(ValueError):
    """Raised when reviewed calendar evidence is incomplete or mutable."""


@dataclass(frozen=True)
class LegacyV1Evidence:
    path: Path
    raw_bytes: bytes
    sha256: str
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CapturedSourceSnapshot:
    source_paths: Mapping[str, Path]
    raw_bytes: Mapping[str, bytes]
    source_sha256: Mapping[str, str]
    source_rows: Mapping[str, Mapping[str, Any]]
    completed_dates: tuple[str, ...]
    excluded_not_completed_dates: tuple[str, ...]
    observed_at_utc: datetime
    start_date: str


@dataclass(frozen=True)
class VerifiedReviewedCalendarV2:
    manifest: dict[str, Any]
    manifest_path: Path
    events: tuple[dict[str, Any], ...]
    session_projection: tuple[dict[str, Any], ...]
    legacy_v1_evidence: LegacyV1Evidence
    source_snapshots: Mapping[str, CapturedSourceSnapshot]


def _hash_without_event_hash(event: Mapping[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_sha256", None)
    return canonical_sha256(payload)


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _utc_datetime(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise NdxObservedSessionCalendarV2Error(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise NdxObservedSessionCalendarV2Error(f"{label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _normalized_decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise NdxObservedSessionCalendarV2Error(f"invalid finite {label}") from exc
    if not number.is_finite():
        raise NdxObservedSessionCalendarV2Error(f"invalid finite {label}")
    canonical = format(number.normalize(), "f")
    if canonical in {"-0", ""}:
        canonical = "0"
    if str(value) != canonical:
        raise NdxObservedSessionCalendarV2Error(f"non-canonical normalized {label}")
    return number


def _normalize_source_number(value: Any, label: str) -> str:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise NdxObservedSessionCalendarV2Error(f"invalid finite {label}") from exc
    if not number.is_finite():
        raise NdxObservedSessionCalendarV2Error(f"invalid finite {label}")
    normalized = format(number.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def _parse_source_bytes(raw_bytes: bytes, *, ticker: str) -> dict[str, dict[str, Any]]:
    required = ("Date", "Open", "High", "Low", "Close", "Volume")
    try:
        text = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
    except UnicodeDecodeError as exc:
        raise NdxObservedSessionCalendarV2Error(f"cannot decode {ticker} source bytes") from exc
    if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
        raise NdxObservedSessionCalendarV2Error(f"{ticker} OHLC columns are incomplete")
    rows: dict[str, dict[str, Any]] = {}
    prior: str | None = None
    for raw in reader:
        session = str(raw.get("Date") or "")
        try:
            # session_timestamps performs the same strict ISO-date validation as v1.
            session_timestamps(session)
        except ValueError as exc:
            raise NdxObservedSessionCalendarV2Error(f"invalid {ticker} Date") from exc
        if prior is not None and session <= prior:
            raise NdxObservedSessionCalendarV2Error(
                f"{ticker} OHLC dates must be unique and strictly increasing"
            )
        prior = session
        normalized = {
            "Date": session,
            **{
                column: _normalize_source_number(raw.get(column), f"{ticker} {column}")
                for column in required[1:]
            },
        }
        # The source files contain history predating the reviewed calendar
        # boundary.  Preserve those bytes and normalized values without making
        # an old vendor anomaly a new calendar fact.  Full OHLC range checks
        # run when a row is actually sealed as a v2 session or revision event.
        values = {
            key: _normalized_decimal(normalized[key], f"{ticker} {key}")
            for key in ("Open", "High", "Low", "Close", "Volume")
        }
        if any(values[key] <= 0 for key in ("Open", "High", "Low", "Close")):
            raise NdxObservedSessionCalendarV2Error(f"{ticker} source price must be positive")
        if values["Volume"] < 0 or values["Volume"] != values["Volume"].to_integral_value():
            raise NdxObservedSessionCalendarV2Error(f"{ticker} source volume is invalid")
        rows[session] = {
            "row_sha256": canonical_sha256(normalized),
            "normalized": normalized,
        }
    if not rows:
        raise NdxObservedSessionCalendarV2Error(f"{ticker} OHLC is empty")
    return rows


def load_legacy_v1_evidence(
    path: str | Path, *, tickers: Sequence[str], prospective_start_date: str,
) -> LegacyV1Evidence:
    source = Path(path).resolve()
    try:
        raw_bytes = source.read_bytes()
    except OSError as exc:
        raise NdxObservedSessionCalendarV2Error("cannot read canonical v1 ledger bytes") from exc
    records: list[dict[str, Any]] = []
    try:
        for number, line in enumerate(raw_bytes.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                raise NdxObservedSessionCalendarV2Error(f"blank v1 ledger row: {number}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise NdxObservedSessionCalendarV2Error(f"v1 ledger row is not an object: {number}")
            records.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("cannot parse canonical v1 ledger bytes") from exc
    validate_v1_ledger(
        records, tickers=list(tickers), prospective_start_date=prospective_start_date,
        current_source_rows=None,
    )
    return LegacyV1Evidence(
        path=source,
        raw_bytes=raw_bytes,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        records=tuple(records),
    )


def _verify_legacy_evidence(
    evidence: LegacyV1Evidence, *, tickers: Sequence[str], prospective_start_date: str,
) -> None:
    if hashlib.sha256(evidence.raw_bytes).hexdigest() != evidence.sha256:
        raise NdxObservedSessionCalendarV2Error("captured v1 ledger hash changed")
    try:
        reparsed = tuple(
            json.loads(line) for line in evidence.raw_bytes.decode("utf-8").splitlines()
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("captured v1 ledger bytes are invalid") from exc
    if reparsed != evidence.records:
        raise NdxObservedSessionCalendarV2Error("captured v1 records do not match ledger bytes")
    validate_v1_ledger(
        evidence.records, tickers=list(tickers),
        prospective_start_date=prospective_start_date, current_source_rows=None,
    )


def capture_source_snapshot(
    source_paths: Mapping[str, str | Path], *, tickers: Sequence[str],
    start_date: str, observed_at_utc: datetime,
) -> CapturedSourceSnapshot:
    """Read every canonical source once and derive rows and dates from those bytes."""

    expected_tickers = list(tickers)
    if list(source_paths) != expected_tickers or len(expected_tickers) < 2:
        raise NdxObservedSessionCalendarV2Error("source snapshot ticker set/order changed")
    paths: dict[str, Path] = {}
    raw_by_ticker: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    rows: dict[str, Mapping[str, Any]] = {}
    for ticker in expected_tickers:
        path = Path(source_paths[ticker]).resolve()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise NdxObservedSessionCalendarV2Error(f"cannot read {ticker} snapshot bytes") from exc
        paths[ticker] = path
        raw_by_ticker[ticker] = raw
        hashes[ticker] = hashlib.sha256(raw).hexdigest()
        rows[ticker] = _parse_source_bytes(raw, ticker=ticker)
    completed, excluded = observed_common_dates(
        rows, start_date=start_date, observed_at_utc=observed_at_utc,
    )
    return CapturedSourceSnapshot(
        source_paths=paths,
        raw_bytes=raw_by_ticker,
        source_sha256=hashes,
        source_rows=rows,
        completed_dates=tuple(completed),
        excluded_not_completed_dates=tuple(excluded),
        observed_at_utc=observed_at_utc.astimezone(UTC),
        start_date=start_date,
    )


def _verify_captured_snapshot(
    snapshot: CapturedSourceSnapshot, *, tickers: Sequence[str], required_start_date: str,
) -> None:
    expected_tickers = list(tickers)
    if (
        list(snapshot.source_paths) != expected_tickers
        or list(snapshot.raw_bytes) != expected_tickers
        or list(snapshot.source_sha256) != expected_tickers
        or list(snapshot.source_rows) != expected_tickers
    ):
        raise NdxObservedSessionCalendarV2Error("captured source snapshot coverage changed")
    if snapshot.start_date != required_start_date:
        raise NdxObservedSessionCalendarV2Error("captured source start boundary changed")
    reparsed: dict[str, Mapping[str, Any]] = {}
    for ticker in expected_tickers:
        raw = snapshot.raw_bytes[ticker]
        if hashlib.sha256(raw).hexdigest() != snapshot.source_sha256[ticker]:
            raise NdxObservedSessionCalendarV2Error("captured source snapshot hash changed")
        reparsed[ticker] = _parse_source_bytes(raw, ticker=ticker)
        if reparsed[ticker] != snapshot.source_rows[ticker]:
            raise NdxObservedSessionCalendarV2Error("captured source rows do not match captured bytes")
    completed, excluded = observed_common_dates(
        reparsed, start_date=snapshot.start_date,
        observed_at_utc=snapshot.observed_at_utc,
    )
    if tuple(completed) != snapshot.completed_dates or tuple(excluded) != snapshot.excluded_not_completed_dates:
        raise NdxObservedSessionCalendarV2Error("captured common completed dates changed")


def source_snapshot_id(
    snapshot: CapturedSourceSnapshot, *, tickers: Sequence[str],
) -> str:
    _verify_captured_snapshot(
        snapshot, tickers=tickers, required_start_date=snapshot.start_date,
    )
    return canonical_sha256({
        "schema_version": 1,
        "tickers": list(tickers),
        "observed_at_utc": snapshot.observed_at_utc.astimezone(UTC).isoformat(),
        "start_date": snapshot.start_date,
        "source_sha256": {
            ticker: snapshot.source_sha256[ticker] for ticker in tickers
        },
        "completed_dates": list(snapshot.completed_dates),
        "excluded_not_completed_dates": list(snapshot.excluded_not_completed_dates),
    })


def validate_normalized_ohlc(value: Mapping[str, Any], *, session_date: str) -> dict[str, str]:
    """Validate one exact, finite normalized source row."""

    if not isinstance(value, Mapping) or set(value) != NORMALIZED_ROW_KEYS:
        raise NdxObservedSessionCalendarV2Error("normalized OHLC schema changed")
    if str(value.get("Date")) != session_date:
        raise NdxObservedSessionCalendarV2Error("normalized OHLC date changed")
    normalized = {key: str(value[key]) for key in ("Date", "Open", "High", "Low", "Close", "Volume")}
    numbers = {
        key: _normalized_decimal(normalized[key], key)
        for key in ("Open", "High", "Low", "Close", "Volume")
    }
    if any(numbers[key] <= 0 for key in ("Open", "High", "Low", "Close")):
        raise NdxObservedSessionCalendarV2Error("OHLC price must be positive")
    if numbers["Volume"] < 0 or numbers["Volume"] != numbers["Volume"].to_integral_value():
        raise NdxObservedSessionCalendarV2Error("volume must be a non-negative integer")
    if (
        numbers["High"] < max(numbers["Open"], numbers["Close"], numbers["Low"])
        or numbers["Low"] > min(numbers["Open"], numbers["Close"], numbers["High"])
    ):
        raise NdxObservedSessionCalendarV2Error("OHLC range is inconsistent")
    return normalized


def _finalize_event(event: dict[str, Any]) -> dict[str, Any]:
    event["event_sha256"] = _hash_without_event_hash(event)
    return event


def _common_event(
    *, sequence: int, event_type: str, recorded_at_utc: datetime,
    previous_event_sha256: str | None,
) -> dict[str, Any]:
    if recorded_at_utc.tzinfo is None:
        raise NdxObservedSessionCalendarV2Error("recorded_at_utc must be timezone-aware")
    return {
        "schema_version": SCHEMA_VERSION,
        "event_sequence": int(sequence),
        "event_type": event_type,
        "event_recorded_at_utc": recorded_at_utc.astimezone(UTC).isoformat(),
        "previous_event_sha256": previous_event_sha256,
    }


def import_v1_legacy_records(
    evidence: LegacyV1Evidence, *, tickers: Sequence[str], prospective_start_date: str,
    imported_at_utc: datetime,
) -> list[dict[str, Any]]:
    """Build a v2 import without inventing the normalized values absent from v1."""

    _verify_legacy_evidence(
        evidence, tickers=tickers, prospective_start_date=prospective_start_date,
    )
    records = evidence.records
    events: list[dict[str, Any]] = []
    prior_hash: str | None = None
    for record in records:
        source_rows = record["source_rows"]
        event = {
            **_common_event(
                sequence=len(events) + 1,
                event_type=LEGACY_SESSION_EVENT,
                recorded_at_utc=imported_at_utc,
                previous_event_sha256=prior_hash,
            ),
            "session_date": record["session_date"],
            **{
                key: record[key]
                for key in (
                    "open_timestamp_ny", "close_timestamp_ny",
                    "open_timestamp_utc", "close_timestamp_utc",
                )
            },
            "close_timestamp_role": CLOSE_TIMESTAMP_ROLE,
            "completed": True,
            "common_source_tickers": list(tickers),
            "source_observations": [
                {
                    "ticker": str(item["ticker"]),
                    "evidence_mode": LEGACY_EVIDENCE_MODE,
                    "as_observed_row_sha256": str(item["row_sha256"]),
                    "normalized_ohlc": None,
                    "price_replay_available": False,
                }
                for item in source_rows
            ],
            "source_snapshot_sha256": dict(record["source_snapshot_sha256"]),
            "source_snapshot_id": None,
            "origin": record["origin"],
            "decision_eligible": bool(record["decision_eligible"]),
            "source_observed_at_utc": record["recorded_at_utc"],
            "legacy_v1_binding": {
                "v1_sequence": int(record["sequence"]),
                "v1_record_sha256": str(record["record_sha256"]),
                "v1_ledger_sha256": evidence.sha256,
                "original_normalized_ohlc_available": False,
                "current_vendor_values_may_substitute_for_original": False,
            },
        }
        _finalize_event(event)
        events.append(event)
        prior_hash = event["event_sha256"]
    validate_event_ledger(
        events, tickers=tickers, prospective_start_date=prospective_start_date,
        legacy_v1_evidence=evidence,
    )
    return events


def _source_observations(
    *, session_date: str, tickers: Sequence[str],
    source_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for ticker in tickers:
        item = source_rows.get(ticker, {}).get(session_date)
        if not isinstance(item, Mapping):
            raise NdxObservedSessionCalendarV2Error(
                f"missing source row for {ticker} {session_date}"
            )
        normalized = validate_normalized_ohlc(
            item.get("normalized") or {}, session_date=session_date,
        )
        expected_hash = canonical_sha256(normalized)
        if item.get("row_sha256") != expected_hash:
            raise NdxObservedSessionCalendarV2Error("source row hash mismatch")
        observations.append({
            "ticker": ticker,
            "evidence_mode": FROZEN_EVIDENCE_MODE,
            "as_observed_row_sha256": expected_hash,
            "normalized_ohlc": normalized,
            "price_replay_available": True,
        })
    return observations


def make_prospective_session_event(
    *, sequence: int, session_date: str, tickers: Sequence[str],
    source_rows: Mapping[str, Mapping[str, Any]],
    source_snapshot_sha256: Mapping[str, str], source_snapshot_id: str,
    prospective_start_date: str,
    observed_at_utc: datetime, previous_event_sha256: str | None,
) -> dict[str, Any]:
    timestamps = session_timestamps(session_date)
    if _utc_datetime(observed_at_utc.isoformat(), "observed_at_utc") < _utc_datetime(
        timestamps["close_timestamp_utc"], "close_timestamp_utc"
    ):
        raise NdxObservedSessionCalendarV2Error("session observed before completion boundary")
    if list(source_snapshot_sha256) != list(tickers) or any(
        not _is_sha256(source_snapshot_sha256[ticker]) for ticker in tickers
    ):
        raise NdxObservedSessionCalendarV2Error("source snapshot proof is incomplete")
    if not _is_sha256(source_snapshot_id):
        raise NdxObservedSessionCalendarV2Error("source snapshot id is invalid")
    event = {
        **_common_event(
            sequence=sequence, event_type=PROSPECTIVE_SESSION_EVENT,
            recorded_at_utc=observed_at_utc,
            previous_event_sha256=previous_event_sha256,
        ),
        "session_date": session_date,
        **timestamps,
        "close_timestamp_role": CLOSE_TIMESTAMP_ROLE,
        "completed": True,
        "common_source_tickers": list(tickers),
        "source_observations": _source_observations(
            session_date=session_date, tickers=tickers, source_rows=source_rows,
        ),
        "source_snapshot_sha256": {
            ticker: source_snapshot_sha256[ticker] for ticker in tickers
        },
        "source_snapshot_id": source_snapshot_id,
        "origin": PROSPECTIVE_ORIGIN,
        "decision_eligible": session_date >= prospective_start_date,
        "source_observed_at_utc": observed_at_utc.astimezone(UTC).isoformat(),
        "legacy_v1_binding": None,
    }
    return _finalize_event(event)


def _session_events(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        event for event in events
        if event.get("event_type") in {LEGACY_SESSION_EVENT, PROSPECTIVE_SESSION_EVENT}
    ]


def validate_event_ledger(
    events: Sequence[Mapping[str, Any]], *, tickers: Sequence[str],
    prospective_start_date: str,
    legacy_v1_evidence: LegacyV1Evidence | None = None,
) -> None:
    """Rebuild and verify the complete v2 event chain."""

    expected_tickers = list(tickers)
    prior_hash: str | None = None
    prior_event_time: datetime | None = None
    prior_session_date: str | None = None
    sessions: dict[str, Mapping[str, Any]] = {}
    latest_observed_hash: dict[tuple[str, str], str] = {}
    if legacy_v1_evidence is not None:
        _verify_legacy_evidence(
            legacy_v1_evidence, tickers=tickers,
            prospective_start_date=prospective_start_date,
        )
    legacy_by_sequence = {
        int(record["sequence"]): record
        for record in (() if legacy_v1_evidence is None else legacy_v1_evidence.records)
    }
    seen_legacy_sequences: set[int] = set()
    prospective_seen = False

    for index, raw in enumerate(events, start=1):
        event = dict(raw)
        event_type = event.get("event_type")
        expected_keys = (
            SESSION_EVENT_KEYS
            if event_type in {LEGACY_SESSION_EVENT, PROSPECTIVE_SESSION_EVENT}
            else REVISION_EVENT_KEYS
            if event_type == SOURCE_REVISION_EVENT
            else None
        )
        if expected_keys is None or set(event) != expected_keys:
            raise NdxObservedSessionCalendarV2Error("v2 event schema changed")
        if event.get("schema_version") != SCHEMA_VERSION or event.get("event_sequence") != index:
            raise NdxObservedSessionCalendarV2Error("v2 event sequence is invalid")
        if event.get("previous_event_sha256") != prior_hash:
            raise NdxObservedSessionCalendarV2Error("v2 event hash chain is broken")
        if not _is_sha256(event.get("event_sha256")) or _hash_without_event_hash(event) != event["event_sha256"]:
            raise NdxObservedSessionCalendarV2Error("v2 event hash mismatch")
        event_time = _utc_datetime(event["event_recorded_at_utc"], "event_recorded_at_utc")
        if prior_event_time is not None and event_time < prior_event_time:
            raise NdxObservedSessionCalendarV2Error("v2 event time is not monotonic")
        prior_event_time = event_time
        prior_hash = str(event["event_sha256"])

        if event_type in {LEGACY_SESSION_EVENT, PROSPECTIVE_SESSION_EVENT}:
            session_date = str(event["session_date"])
            timestamps = session_timestamps(session_date)
            if session_date in sessions or (prior_session_date is not None and session_date <= prior_session_date):
                raise NdxObservedSessionCalendarV2Error("session dates are duplicated or not increasing")
            prior_session_date = session_date
            if any(event[key] != expected for key, expected in timestamps.items()):
                raise NdxObservedSessionCalendarV2Error("session timestamp proof changed")
            if (
                event["completed"] is not True
                or event["close_timestamp_role"] != CLOSE_TIMESTAMP_ROLE
                or event["common_source_tickers"] != expected_tickers
                or _utc_datetime(event["source_observed_at_utc"], "source_observed_at_utc")
                < _utc_datetime(event["close_timestamp_utc"], "close_timestamp_utc")
            ):
                raise NdxObservedSessionCalendarV2Error("session completion evidence changed")
            if event_time < _utc_datetime(event["source_observed_at_utc"], "source_observed_at_utc"):
                raise NdxObservedSessionCalendarV2Error("session imported before its source observation")
            source_snapshots = event["source_snapshot_sha256"]
            if not isinstance(source_snapshots, Mapping) or list(source_snapshots) != expected_tickers or any(
                not _is_sha256(source_snapshots[ticker]) for ticker in expected_tickers
            ):
                raise NdxObservedSessionCalendarV2Error("session snapshot evidence is incomplete")
            observations = event["source_observations"]
            if not isinstance(observations, list) or len(observations) != len(expected_tickers):
                raise NdxObservedSessionCalendarV2Error("session source evidence is incomplete")
            if [item.get("ticker") for item in observations] != expected_tickers:
                raise NdxObservedSessionCalendarV2Error("session source order changed")

            if event_type == LEGACY_SESSION_EVENT:
                if legacy_v1_evidence is None:
                    raise NdxObservedSessionCalendarV2Error(
                        "legacy session requires captured canonical v1 evidence"
                    )
                if prospective_seen:
                    raise NdxObservedSessionCalendarV2Error("legacy import cannot follow v2 observations")
                binding = event["legacy_v1_binding"]
                if not isinstance(binding, Mapping) or set(binding) != {
                    "v1_sequence", "v1_record_sha256", "v1_ledger_sha256",
                    "original_normalized_ohlc_available",
                    "current_vendor_values_may_substitute_for_original",
                }:
                    raise NdxObservedSessionCalendarV2Error("legacy v1 binding is incomplete")
                if (
                    binding["original_normalized_ohlc_available"] is not False
                    or binding["current_vendor_values_may_substitute_for_original"] is not False
                    or not _is_sha256(binding["v1_record_sha256"])
                    or not _is_sha256(binding["v1_ledger_sha256"])
                ):
                    raise NdxObservedSessionCalendarV2Error("legacy values were misrepresented")
                if event["source_snapshot_id"] is not None:
                    raise NdxObservedSessionCalendarV2Error("legacy row cannot claim a recovered source snapshot")
                for item in observations:
                    if (
                        set(item) != LEGACY_OBSERVATION_KEYS
                        or item["evidence_mode"] != LEGACY_EVIDENCE_MODE
                        or item["normalized_ohlc"] is not None
                        or item["price_replay_available"] is not False
                        or not _is_sha256(item["as_observed_row_sha256"])
                    ):
                        raise NdxObservedSessionCalendarV2Error("legacy OHLC evidence was fabricated")
                expected_eligible = (
                    event["origin"] == PROSPECTIVE_ORIGIN
                    and session_date >= prospective_start_date
                )
                if (
                    event["origin"] not in {BOOTSTRAP_ORIGIN, PROSPECTIVE_ORIGIN}
                    or event["decision_eligible"] is not expected_eligible
                ):
                    raise NdxObservedSessionCalendarV2Error("legacy session eligibility changed")
                v1_sequence = int(binding["v1_sequence"])
                reference = legacy_by_sequence.get(v1_sequence)
                if reference is None:
                    raise NdxObservedSessionCalendarV2Error("legacy record is not in canonical v1 ledger")
                expected_hashes = [row["row_sha256"] for row in reference["source_rows"]]
                if (
                    binding["v1_record_sha256"] != reference["record_sha256"]
                    or binding["v1_ledger_sha256"] != legacy_v1_evidence.sha256
                    or event["session_date"] != reference["session_date"]
                    or [row["as_observed_row_sha256"] for row in observations] != expected_hashes
                    or event["source_snapshot_sha256"] != reference["source_snapshot_sha256"]
                    or event["source_observed_at_utc"] != reference["recorded_at_utc"]
                    or event["origin"] != reference["origin"]
                    or event["common_source_tickers"] != reference["common_source_tickers"]
                    or any(event[key] != reference[key] for key in (
                        "open_timestamp_ny", "close_timestamp_ny",
                        "open_timestamp_utc", "close_timestamp_utc",
                    ))
                    or event["decision_eligible"] is not bool(reference["decision_eligible"])
                ):
                    raise NdxObservedSessionCalendarV2Error("legacy import differs from canonical v1")
                seen_legacy_sequences.add(v1_sequence)
            else:
                prospective_seen = True
                if (
                    event["legacy_v1_binding"] is not None
                    or event["origin"] != PROSPECTIVE_ORIGIN
                    or event["decision_eligible"] is not (session_date >= prospective_start_date)
                ):
                    raise NdxObservedSessionCalendarV2Error("prospective v2 session boundary changed")
                if not _is_sha256(event["source_snapshot_id"]):
                    raise NdxObservedSessionCalendarV2Error("prospective source snapshot id is invalid")
                for item in observations:
                    if (
                        set(item) != FROZEN_OBSERVATION_KEYS
                        or item["evidence_mode"] != FROZEN_EVIDENCE_MODE
                        or item["price_replay_available"] is not True
                    ):
                        raise NdxObservedSessionCalendarV2Error("prospective source evidence changed")
                    normalized = validate_normalized_ohlc(
                        item["normalized_ohlc"], session_date=session_date,
                    )
                    if canonical_sha256(normalized) != item["as_observed_row_sha256"]:
                        raise NdxObservedSessionCalendarV2Error("frozen source row hash mismatch")
            sessions[session_date] = event
            for observation in observations:
                latest_observed_hash[(session_date, str(observation["ticker"]))] = str(
                    observation["as_observed_row_sha256"]
                )
            continue

        session_date = str(event["session_date"])
        sealed = sessions.get(session_date)
        if sealed is None:
            raise NdxObservedSessionCalendarV2Error("revision precedes sealed session")
        ticker = str(event["ticker"])
        if ticker not in expected_tickers:
            raise NdxObservedSessionCalendarV2Error("revision ticker is outside calendar sources")
        observation = next(item for item in sealed["source_observations"] if item["ticker"] == ticker)
        normalized = validate_normalized_ohlc(
            event["revised_normalized_ohlc"], session_date=session_date,
        )
        revised_hash = canonical_sha256(normalized)
        source_key = (session_date, ticker)
        prior_observed_hash = latest_observed_hash[source_key]
        expected_kind = (
            "RESTORED_TO_SEALED_HASH"
            if revised_hash == observation["as_observed_row_sha256"]
            else "REVISED_AWAY_FROM_SEALED_HASH"
            if prior_observed_hash == observation["as_observed_row_sha256"]
            else "REVISED_AGAIN"
        )
        if (
            event["sealed_session_event_sha256"] != sealed["event_sha256"]
            or event["sealed_row_sha256"] != observation["as_observed_row_sha256"]
            or event["sealed_evidence_mode"] != observation["evidence_mode"]
            or event["prior_observed_row_sha256"] != prior_observed_hash
            or event["revised_row_sha256"] != revised_hash
            or revised_hash == prior_observed_hash
            or not _is_sha256(event["revised_source_snapshot_sha256"])
            or not _is_sha256(event["source_snapshot_id"])
            or event["revision_kind"] != expected_kind
            or event["revision_role"] != REVISION_ROLE
            or event["calendar_membership_changed"] is not False
            or event["sealed_as_observed_value_changed"] is not False
        ):
            raise NdxObservedSessionCalendarV2Error("source revision evidence is invalid")
        latest_observed_hash[source_key] = revised_hash

    if legacy_v1_evidence is not None and seen_legacy_sequences != set(legacy_by_sequence):
        raise NdxObservedSessionCalendarV2Error("canonical v1 import is incomplete")


def prepare_reviewed_update(
    existing: Sequence[Mapping[str, Any]], *, snapshot: CapturedSourceSnapshot,
    tickers: Sequence[str], calendar_start_date: str, prospective_start_date: str,
    legacy_v1_evidence: LegacyV1Evidence,
) -> list[dict[str, Any]]:
    """Append revision diagnostics and at most one genuinely new session."""

    if not existing:
        raise NdxObservedSessionCalendarV2Error("v2 requires an explicit reviewed v1 import")
    _verify_captured_snapshot(
        snapshot, tickers=tickers, required_start_date=calendar_start_date,
    )
    if (
        not legacy_v1_evidence.records
        or str(legacy_v1_evidence.records[0]["session_date"]) != calendar_start_date
    ):
        raise NdxObservedSessionCalendarV2Error("calendar start does not match canonical v1 prefix")
    source_rows = snapshot.source_rows
    source_snapshot_sha256 = snapshot.source_sha256
    completed_dates = snapshot.completed_dates
    observed_at_utc = snapshot.observed_at_utc
    snapshot_id = source_snapshot_id(snapshot, tickers=tickers)
    validate_event_ledger(
        existing, tickers=tickers, prospective_start_date=prospective_start_date,
        legacy_v1_evidence=legacy_v1_evidence,
    )
    sessions = _session_events(existing)
    sealed_dates = [str(event["session_date"]) for event in sessions]
    completed = list(completed_dates)
    if sealed_dates != completed[: len(sealed_dates)]:
        raise NdxObservedSessionCalendarV2Error(
            "observed session-date prefix changed; reviewed calendar version required"
        )
    pending_dates = completed[len(sealed_dates):]
    if len(pending_dates) > 1:
        raise NdxObservedSessionCalendarV2Error(
            "multiple completed sessions are pending; no retrospective backfill"
        )
    additions: list[dict[str, Any]] = []
    prior_hash = str(existing[-1]["event_sha256"])
    latest_observed_hash = {
        (str(session["session_date"]), str(observation["ticker"])):
        str(observation["as_observed_row_sha256"])
        for session in sessions for observation in session["source_observations"]
    }
    for prior_event in existing:
        if prior_event["event_type"] == SOURCE_REVISION_EVENT:
            latest_observed_hash[(str(prior_event["session_date"]), str(prior_event["ticker"]))] = str(
                prior_event["revised_row_sha256"]
            )
    for sealed in sessions:
        session_date = str(sealed["session_date"])
        for observation in sealed["source_observations"]:
            ticker = str(observation["ticker"])
            current = source_rows.get(ticker, {}).get(session_date)
            if not isinstance(current, Mapping):
                raise NdxObservedSessionCalendarV2Error(
                    f"sealed session disappeared from source: {ticker} {session_date}"
                )
            normalized = validate_normalized_ohlc(
                current.get("normalized") or {}, session_date=session_date,
            )
            revised_hash = canonical_sha256(normalized)
            if current.get("row_sha256") != revised_hash:
                raise NdxObservedSessionCalendarV2Error("current source row hash mismatch")
            source_key = (session_date, ticker)
            prior_observed_hash = latest_observed_hash[source_key]
            if revised_hash == prior_observed_hash:
                continue
            revision_kind = (
                "RESTORED_TO_SEALED_HASH"
                if revised_hash == observation["as_observed_row_sha256"]
                else "REVISED_AWAY_FROM_SEALED_HASH"
                if prior_observed_hash == observation["as_observed_row_sha256"]
                else "REVISED_AGAIN"
            )
            event = {
                **_common_event(
                    sequence=len(existing) + len(additions) + 1,
                    event_type=SOURCE_REVISION_EVENT,
                    recorded_at_utc=observed_at_utc,
                    previous_event_sha256=prior_hash,
                ),
                "session_date": session_date,
                "ticker": ticker,
                "sealed_session_event_sha256": sealed["event_sha256"],
                "sealed_row_sha256": observation["as_observed_row_sha256"],
                "sealed_evidence_mode": observation["evidence_mode"],
                "prior_observed_row_sha256": prior_observed_hash,
                "revised_row_sha256": revised_hash,
                "revised_normalized_ohlc": normalized,
                "source_snapshot_id": snapshot_id,
                "revised_source_snapshot_sha256": source_snapshot_sha256[ticker],
                "revision_kind": revision_kind,
                "revision_role": REVISION_ROLE,
                "calendar_membership_changed": False,
                "sealed_as_observed_value_changed": False,
            }
            _finalize_event(event)
            additions.append(event)
            prior_hash = event["event_sha256"]
            latest_observed_hash[source_key] = revised_hash
    if pending_dates:
        event = make_prospective_session_event(
            sequence=len(existing) + len(additions) + 1,
            session_date=pending_dates[0], tickers=tickers,
            source_rows=source_rows, source_snapshot_sha256=source_snapshot_sha256,
            source_snapshot_id=snapshot_id,
            prospective_start_date=prospective_start_date,
            observed_at_utc=observed_at_utc, previous_event_sha256=prior_hash,
        )
        additions.append(event)
    combined = [*existing, *additions]
    validate_event_ledger(
        combined, tickers=tickers, prospective_start_date=prospective_start_date,
        legacy_v1_evidence=legacy_v1_evidence,
    )
    return additions


def projection_rows(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sessions = _session_events(events)
    dates = [str(event["session_date"]) for event in sessions]
    result: list[dict[str, Any]] = []
    for index, event in enumerate(sessions):
        prior = dates[index - 1] if index else None
        current = dates[index]
        result.append({
            "session_sequence": index + 1,
            "session_date": current,
            "open_timestamp_utc": event["open_timestamp_utc"],
            "close_timestamp_utc": event["close_timestamp_utc"],
            "is_first_observed_session_of_month": (
                prior is None or prior[:7] != current[:7]
            ),
            "next_observed_session_date": dates[index + 1] if index + 1 < len(dates) else "",
            "origin": event["origin"],
            "decision_eligible": bool(event["decision_eligible"]),
            "source_price_replay_available": all(
                item["price_replay_available"] for item in event["source_observations"]
            ),
            "session_event_sha256": event["event_sha256"],
        })
    return result


def build_migration_readiness(
    *, v1_manifest_path: str | Path, v1_ledger_path: str | Path,
    current_snapshot: CapturedSourceSnapshot, tickers: Sequence[str],
    calendar_start_date: str, prospective_start_date: str,
) -> dict[str, Any]:
    """Audit the v1→v2 boundary without writing or activating anything."""

    manifest_path = Path(v1_manifest_path).resolve()
    ledger_path = Path(v1_ledger_path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("cannot load canonical v1 evidence") from exc
    evidence = load_legacy_v1_evidence(
        ledger_path, tickers=tickers, prospective_start_date=prospective_start_date,
    )
    records = list(evidence.records)
    _verify_captured_snapshot(
        current_snapshot, tickers=tickers, required_start_date=calendar_start_date,
    )
    if not records or records[0]["session_date"] != calendar_start_date:
        raise NdxObservedSessionCalendarV2Error("canonical v1 calendar start changed")
    current_source_rows = current_snapshot.source_rows
    ledger_item = ((manifest.get("artifacts") or {}).get("append_only_ledger") or {})
    if (
        manifest.get("manifest_type") != "ndx_observed_us_session_calendar"
        or manifest.get("start_date") != calendar_start_date
        or manifest.get("prospective_start_date") != prospective_start_date
        or Path(str(ledger_item.get("path") or "")).resolve() != ledger_path
        or ledger_item.get("sha256") != evidence.sha256
        or int(ledger_item.get("rows", -1)) != len(records)
    ):
        raise NdxObservedSessionCalendarV2Error("canonical v1 manifest/ledger binding changed")
    revisions: list[dict[str, Any]] = []
    for record in records:
        for item in record["source_rows"]:
            ticker = str(item["ticker"])
            current = current_source_rows.get(ticker, {}).get(record["session_date"])
            if current is None:
                revisions.append({
                    "session_date": record["session_date"], "ticker": ticker,
                    "status": "SOURCE_ROW_MISSING",
                    "sealed_row_sha256": item["row_sha256"], "current_row_sha256": None,
                })
            elif current["row_sha256"] != item["row_sha256"]:
                revisions.append({
                    "session_date": record["session_date"], "ticker": ticker,
                    "status": "SOURCE_ROW_REVISED_VALUES_NOT_ORIGINAL",
                    "sealed_row_sha256": item["row_sha256"],
                    "current_row_sha256": current["row_sha256"],
                })
    return {
        "schema_version": 1,
        "manifest_type": "ndx_observed_session_calendar_v2_migration_readiness",
        "status": "BLOCKED_REVIEWED_CALENDAR_V2_NOT_ACTIVATED",
        "blockers": [
            "V2_CANONICAL_LEDGER_NOT_CREATED",
            "V2_ACTIVATION_LINEAGE_NOT_BUILT",
            "V2_SCHEDULED_TASK_NOT_REVIEWED_OR_REGISTERED",
        ],
        "v1_manifest": {"path": manifest_path.as_posix(), "sha256": file_sha256(manifest_path)},
        "v1_ledger": {
            "path": ledger_path.as_posix(), "sha256": evidence.sha256,
            "records": len(records), "latest_record_sha256": records[-1]["record_sha256"] if records else None,
        },
        "legacy_hash_only_session_count": len(records),
        "legacy_normalized_ohlc_recoverable": False,
        "current_vendor_values_may_substitute_for_legacy_original": False,
        "source_revision_count": len(revisions),
        "source_revisions": revisions,
        "v2_contract": {
            "new_sessions_freeze_complete_normalized_ohlc": True,
            "later_source_revisions_append_diagnostic_events": True,
            "sealed_session_rewrite_allowed": False,
            "retrospective_session_backfill_allowed": False,
            "decision_eligibility_uses_observed_common_session_dates": True,
            "execution_price_evidence_remains_separate": True,
        },
        "required_next_lineage": {
            "calendar": "ndx_observed_us_session_calendar_v2",
            "daily": "NEW_VERSION_REQUIRED_DO_NOT_HOT_EDIT_DAILY_V2",
            "activation": "NEW_VERSION_REQUIRED_DO_NOT_OVERWRITE_ACTIVATION_V3",
            "task_migration": "SEPARATE_REVIEW_AND_USER_AUTHORIZATION_REQUIRED",
        },
        "automation_registration_allowed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "state_changed": False,
        "broker_snapshot_changed": False,
        "today_advice_changed": False,
        "order_creation_allowed": False,
    }


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _load_event_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise NdxObservedSessionCalendarV2Error("cannot read canonical v2 event ledger") from exc
    events: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            raise NdxObservedSessionCalendarV2Error(f"blank v2 event row: {number}")
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise NdxObservedSessionCalendarV2Error(f"invalid v2 event row: {number}") from exc
        if not isinstance(item, dict):
            raise NdxObservedSessionCalendarV2Error(f"v2 event row is not an object: {number}")
        events.append(item)
    return events


def _event_ledger_bytes(events: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for event in events
    ).encode("utf-8")


def _projection_csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=PROJECTION_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _protected_hashes(repository_root: Path) -> dict[str, str | None]:
    return {
        relative: file_sha256(repository_root / relative)
        if (repository_root / relative).is_file() else None
        for relative in (
            "config/config.yaml", "data/state.json", "data/broker_positions.json",
        )
    }


def _snapshot_manifest_hash(payload: Mapping[str, Any]) -> str:
    clean = dict(payload)
    clean.pop("manifest_sha256", None)
    return canonical_sha256(clean)


def _source_snapshot_manifest(
    snapshot: CapturedSourceSnapshot, *, snapshot_id_value: str,
    tickers: Sequence[str], repository_root: Path,
) -> dict[str, Any]:
    output = repository_root / CANONICAL_ROOT_RELATIVE / "source_snapshots" / snapshot_id_value
    payload: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "ndx_observed_session_calendar_v2_source_snapshot",
        "snapshot_id": snapshot_id_value,
        "observed_at_utc": snapshot.observed_at_utc.astimezone(UTC).isoformat(),
        "start_date": snapshot.start_date,
        "tickers": list(tickers),
        "completed_dates": list(snapshot.completed_dates),
        "excluded_not_completed_dates": list(snapshot.excluded_not_completed_dates),
        "sources": [
            {
                "ticker": ticker,
                "source_path": snapshot.source_paths[ticker].as_posix(),
                "source_sha256": snapshot.source_sha256[ticker],
                "frozen_path": (output / f"{ticker}.csv").as_posix(),
                "frozen_sha256": snapshot.source_sha256[ticker],
            }
            for ticker in tickers
        ],
    }
    payload["manifest_sha256"] = _snapshot_manifest_hash(payload)
    return payload


def _write_source_snapshot_archive(
    snapshot: CapturedSourceSnapshot, *, tickers: Sequence[str], repository_root: Path,
) -> dict[str, Any]:
    root = repository_root.resolve()
    expected_source_root = (root / "data/cache").resolve()
    _verify_captured_snapshot(
        snapshot, tickers=tickers, required_start_date=snapshot.start_date,
    )
    for ticker in tickers:
        expected_source = (expected_source_root / f"{ticker}.csv").resolve()
        if snapshot.source_paths[ticker].resolve() != expected_source:
            raise NdxObservedSessionCalendarV2Error(
                f"{ticker} source snapshot path is not canonical"
            )
    snapshot_id_value = source_snapshot_id(snapshot, tickers=tickers)
    final_dir = root / CANONICAL_ROOT_RELATIVE / "source_snapshots" / snapshot_id_value
    manifest_path = final_dir / "manifest.json"
    if manifest_path.exists():
        verified = _verify_source_snapshot_archive(
            manifest_path, repository_root=root, expected_snapshot_id=snapshot_id_value,
        )
        if verified.source_sha256 != snapshot.source_sha256:
            raise NdxObservedSessionCalendarV2Error("existing source snapshot identity collision")
        return {
            "snapshot_id": snapshot_id_value,
            "path": manifest_path.as_posix(),
            "sha256": file_sha256(manifest_path),
        }
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{snapshot_id_value}.", dir=final_dir.parent))
    try:
        for ticker in tickers:
            (temporary / f"{ticker}.csv").write_bytes(snapshot.raw_bytes[ticker])
        payload = _source_snapshot_manifest(
            snapshot, snapshot_id_value=snapshot_id_value,
            tickers=tickers, repository_root=root,
        )
        (temporary / "manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        try:
            os.replace(temporary, final_dir)
        except OSError:
            if manifest_path.exists():
                shutil.rmtree(temporary)
            else:
                raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    _verify_source_snapshot_archive(
        manifest_path, repository_root=root, expected_snapshot_id=snapshot_id_value,
    )
    return {
        "snapshot_id": snapshot_id_value,
        "path": manifest_path.as_posix(),
        "sha256": file_sha256(manifest_path),
    }


def _verify_source_snapshot_archive(
    manifest_path: Path, *, repository_root: Path, expected_snapshot_id: str,
) -> CapturedSourceSnapshot:
    root = repository_root.resolve()
    expected_path = (
        root / CANONICAL_ROOT_RELATIVE / "source_snapshots"
        / expected_snapshot_id / "manifest.json"
    ).resolve()
    if manifest_path.resolve() != expected_path or not expected_path.is_file():
        raise NdxObservedSessionCalendarV2Error("v2 source snapshot manifest path is not canonical")
    try:
        payload = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("cannot read v2 source snapshot manifest") from exc
    if (
        set(payload) != SNAPSHOT_MANIFEST_FIELDS
        or payload.get("schema_version") != 1
        or payload.get("manifest_type") != "ndx_observed_session_calendar_v2_source_snapshot"
        or payload.get("snapshot_id") != expected_snapshot_id
        or payload.get("manifest_sha256") != _snapshot_manifest_hash(payload)
    ):
        raise NdxObservedSessionCalendarV2Error("v2 source snapshot manifest changed")
    tickers = payload.get("tickers")
    sources = payload.get("sources")
    if not isinstance(tickers, list) or not isinstance(sources, list) or len(sources) != len(tickers):
        raise NdxObservedSessionCalendarV2Error("v2 source snapshot coverage is incomplete")
    paths: dict[str, Path] = {}
    raw_bytes: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    rows: dict[str, Mapping[str, Any]] = {}
    if [item.get("ticker") for item in sources] != tickers:
        raise NdxObservedSessionCalendarV2Error("v2 source snapshot ticker order changed")
    for item in sources:
        if set(item) != {"ticker", "source_path", "source_sha256", "frozen_path", "frozen_sha256"}:
            raise NdxObservedSessionCalendarV2Error("v2 source snapshot source fields changed")
        ticker = str(item["ticker"])
        source_path = (root / "data/cache" / f"{ticker}.csv").resolve()
        frozen_path = expected_path.parent / f"{ticker}.csv"
        if (
            Path(str(item["source_path"])).resolve() != source_path
            or Path(str(item["frozen_path"])).resolve() != frozen_path.resolve()
            or item["source_sha256"] != item["frozen_sha256"]
            or not frozen_path.is_file()
        ):
            raise NdxObservedSessionCalendarV2Error("v2 source snapshot file binding changed")
        raw = frozen_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item["frozen_sha256"]:
            raise NdxObservedSessionCalendarV2Error("v2 frozen source snapshot bytes changed")
        paths[ticker] = source_path
        raw_bytes[ticker] = raw
        hashes[ticker] = digest
        rows[ticker] = _parse_source_bytes(raw, ticker=ticker)
    snapshot = CapturedSourceSnapshot(
        source_paths=paths, raw_bytes=raw_bytes, source_sha256=hashes,
        source_rows=rows,
        completed_dates=tuple(str(item) for item in payload["completed_dates"]),
        excluded_not_completed_dates=tuple(
            str(item) for item in payload["excluded_not_completed_dates"]
        ),
        observed_at_utc=_utc_datetime(payload["observed_at_utc"], "snapshot observed_at_utc"),
        start_date=str(payload["start_date"]),
    )
    _verify_captured_snapshot(
        snapshot, tickers=tickers, required_start_date=snapshot.start_date,
    )
    if source_snapshot_id(snapshot, tickers=tickers) != expected_snapshot_id:
        raise NdxObservedSessionCalendarV2Error("v2 source snapshot id changed")
    return snapshot


def _manifest_hash(payload: Mapping[str, Any]) -> str:
    clean = dict(payload)
    clean.pop("manifest_sha256", None)
    return canonical_sha256(clean)


def _load_archived_legacy_evidence(
    *, repository_root: Path, legacy_boundary: Mapping[str, Any],
    tickers: Sequence[str], prospective_start_date: str,
) -> LegacyV1Evidence:
    root = repository_root.resolve()
    expected_manifest = root / CANONICAL_ROOT_RELATIVE / "legacy_v1/manifest.json"
    expected_ledger = root / CANONICAL_ROOT_RELATIVE / "legacy_v1/sessions.jsonl"
    if set(legacy_boundary) != {"source_manifest", "source_ledger", "frozen_manifest", "frozen_ledger"}:
        raise NdxObservedSessionCalendarV2Error("v2 legacy boundary fields changed")
    for key, expected in (("frozen_manifest", expected_manifest), ("frozen_ledger", expected_ledger)):
        item = legacy_boundary[key]
        if (
            set(item) != {"path", "sha256"}
            or Path(str(item["path"])).resolve() != expected.resolve()
            or not expected.is_file()
            or file_sha256(expected) != item["sha256"]
        ):
            raise NdxObservedSessionCalendarV2Error(f"v2 legacy {key} binding changed")
    evidence = load_legacy_v1_evidence(
        expected_ledger, tickers=tickers, prospective_start_date=prospective_start_date,
    )
    archived_manifest = json.loads(expected_manifest.read_text(encoding="utf-8"))
    ledger_item = ((archived_manifest.get("artifacts") or {}).get("append_only_ledger") or {})
    if (
        ledger_item.get("sha256") != evidence.sha256
        or int(ledger_item.get("rows", -1)) != len(evidence.records)
    ):
        raise NdxObservedSessionCalendarV2Error("archived v1 manifest does not bind archived ledger bytes")
    return evidence


def verify_canonical_reviewed_calendar_v2(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> VerifiedReviewedCalendarV2:
    """Rebuild the canonical v2 session projection without current vendor data."""

    root = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    expected = (root / CANONICAL_MANIFEST_RELATIVE).resolve()
    if path != expected or not path.is_file():
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 manifest path is not canonical")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("cannot read reviewed calendar v2 manifest") from exc
    if (
        set(payload) != V2_MANIFEST_FIELDS
        or payload.get("schema_version") != 1
        or payload.get("manifest_type") != V2_MANIFEST_TYPE
        or payload.get("status") != "REVIEWED_CALENDAR_V2_RESEARCH_ONLY_NOT_ACTIVATED"
        or payload.get("boundaries") != V2_BOUNDARIES
        or payload.get("manifest_sha256") != _manifest_hash(payload)
    ):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 manifest changed")
    tickers = payload.get("tickers")
    if not isinstance(tickers, list) or len(tickers) < 2 or tickers != sorted(set(tickers)):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 ticker set changed")
    inputs = payload.get("inputs") or {}
    if set(inputs) != {"engine", "runner"}:
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 input fields changed")
    for name, expected_input in (
        ("engine", root / "backtest/ndx_observed_session_calendar_v2.py"),
        ("runner", root / "scripts/ndx_observed_session_calendar_v2.py"),
    ):
        item = inputs[name]
        if (
            set(item) != {"path", "sha256"}
            or Path(str(item["path"])).resolve() != expected_input.resolve()
            or not expected_input.is_file()
            or item["sha256"] != file_sha256(expected_input)
        ):
            raise NdxObservedSessionCalendarV2Error(f"reviewed calendar v2 {name} changed")
    legacy = _load_archived_legacy_evidence(
        repository_root=root, legacy_boundary=payload["legacy_boundary"],
        tickers=tickers, prospective_start_date=payload["prospective_start_date"],
    )
    artifacts = payload.get("artifacts") or {}
    if set(artifacts) != {"event_ledger", "session_projection"}:
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 artifacts changed")
    ledger_path = root / CANONICAL_ROOT_RELATIVE / "events.jsonl"
    projection_path = root / CANONICAL_ROOT_RELATIVE / "sessions.csv"
    ledger_item = artifacts["event_ledger"]
    projection_item = artifacts["session_projection"]
    if (
        set(ledger_item) != {"path", "sha256", "rows", "latest_event_sha256"}
        or Path(str(ledger_item["path"])).resolve() != ledger_path.resolve()
        or not ledger_path.is_file()
        or ledger_item["sha256"] != file_sha256(ledger_path)
    ):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 event ledger changed")
    events = _load_event_ledger(ledger_path)
    if (
        int(ledger_item["rows"]) != len(events)
        or ledger_item["latest_event_sha256"] != (events[-1]["event_sha256"] if events else None)
    ):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 event count/head changed")
    validate_event_ledger(
        events, tickers=tickers, prospective_start_date=payload["prospective_start_date"],
        legacy_v1_evidence=legacy,
    )
    snapshot_items = payload.get("source_snapshots")
    if not isinstance(snapshot_items, list):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 snapshot inventory is invalid")
    referenced_ids = sorted({
        str(event["source_snapshot_id"])
        for event in events if event["source_snapshot_id"] is not None
    })
    if [item.get("snapshot_id") for item in snapshot_items] != referenced_ids:
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 snapshot coverage changed")
    snapshots: dict[str, CapturedSourceSnapshot] = {}
    for item in snapshot_items:
        if set(item) != {"snapshot_id", "path", "sha256"}:
            raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 snapshot item changed")
        snapshot_id_value = str(item["snapshot_id"])
        snapshot_path = root / CANONICAL_ROOT_RELATIVE / "source_snapshots" / snapshot_id_value / "manifest.json"
        if (
            Path(str(item["path"])).resolve() != snapshot_path.resolve()
            or not snapshot_path.is_file()
            or file_sha256(snapshot_path) != item["sha256"]
        ):
            raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 snapshot binding changed")
        snapshots[snapshot_id_value] = _verify_source_snapshot_archive(
            snapshot_path, repository_root=root, expected_snapshot_id=snapshot_id_value,
        )
    for event in events:
        if event["source_snapshot_id"] is None:
            continue
        snapshot = snapshots[event["source_snapshot_id"]]
        if event["event_type"] == PROSPECTIVE_SESSION_EVENT:
            expected_observations = _source_observations(
                session_date=event["session_date"], tickers=tickers,
                source_rows=snapshot.source_rows,
            )
            if (
                event["source_observations"] != expected_observations
                or event["source_snapshot_sha256"] != snapshot.source_sha256
                or event["source_observed_at_utc"]
                != snapshot.observed_at_utc.astimezone(UTC).isoformat()
            ):
                raise NdxObservedSessionCalendarV2Error("v2 session does not match frozen snapshot")
        elif event["event_type"] == SOURCE_REVISION_EVENT:
            current = snapshot.source_rows[event["ticker"]][event["session_date"]]
            if (
                event["revised_normalized_ohlc"] != current["normalized"]
                or event["revised_row_sha256"] != current["row_sha256"]
                or event["revised_source_snapshot_sha256"]
                != snapshot.source_sha256[event["ticker"]]
            ):
                raise NdxObservedSessionCalendarV2Error("v2 revision does not match frozen snapshot")
    projection = projection_rows(events)
    expected_projection_bytes = _projection_csv_bytes(projection)
    if (
        set(projection_item) != {"path", "sha256", "rows", "derived_from_event_ledger"}
        or Path(str(projection_item["path"])).resolve() != projection_path.resolve()
        or not projection_path.is_file()
        or projection_path.read_bytes() != expected_projection_bytes
        or projection_item["sha256"] != file_sha256(projection_path)
        or int(projection_item["rows"]) != len(projection)
        or projection_item["derived_from_event_ledger"] is not True
    ):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 projection changed")
    sessions = _session_events(events)
    if (
        payload["session_count"] != len(sessions)
        or payload["event_count"] != len(events)
        or payload["revision_event_count"]
        != sum(event["event_type"] == SOURCE_REVISION_EVENT for event in events)
        or payload["decision_eligible_session_count"]
        != sum(row["decision_eligible"] and row["source_price_replay_available"] for row in projection)
        or payload["latest_session_date"] != (sessions[-1]["session_date"] if sessions else None)
        or payload["latest_event_sha256"] != (events[-1]["event_sha256"] if events else None)
    ):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 summary changed")
    if payload["protected_hashes_before"] != payload["protected_hashes_after"]:
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 reports protected mutation")
    transaction_id = payload.get("commit_transaction_id")
    if not _is_sha256(transaction_id):
        raise NdxObservedSessionCalendarV2Error("reviewed calendar v2 transaction id changed")
    committed_receipt_path = (
        root / CANONICAL_ROOT_RELATIVE / "committed_transactions"
        / f"{transaction_id}.json"
    )
    if not committed_receipt_path.is_file():
        raise NdxObservedSessionCalendarV2Error(
            "reviewed calendar v2 committed transaction is missing"
        )
    try:
        committed_receipt = json.loads(
            committed_receipt_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error(
            "reviewed calendar v2 committed transaction is unreadable"
        ) from exc
    _validate_transaction_receipt(committed_receipt, expected_manifest=payload)
    old_size = int(committed_receipt["old_ledger_size"])
    ledger_bytes = ledger_path.read_bytes()
    try:
        old_events = (
            [json.loads(line) for line in ledger_bytes[:old_size].decode("utf-8").splitlines()]
            if old_size else []
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error(
            "reviewed calendar v2 committed transaction old prefix is invalid"
        ) from exc
    if (
        len(ledger_bytes) < old_size
        or hashlib.sha256(ledger_bytes[:old_size]).hexdigest()
        != committed_receipt["old_ledger_sha256"]
        or len(old_events) != int(committed_receipt["old_event_count"])
        or (old_events[-1]["event_sha256"] if old_events else None)
        != committed_receipt["old_event_head_sha256"]
        or ledger_bytes
        != ledger_bytes[:old_size]
        + _event_ledger_bytes(committed_receipt["additions"])
    ):
        raise NdxObservedSessionCalendarV2Error(
            "reviewed calendar v2 committed transaction ledger proof changed"
        )
    return VerifiedReviewedCalendarV2(
        manifest=payload, manifest_path=path, events=tuple(events),
        session_projection=tuple(projection), legacy_v1_evidence=legacy,
        source_snapshots=snapshots,
    )


def load_verified_decision_sessions_v2(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> pd.DataFrame:
    """Return only full-observation, policy-eligible v2 decision sessions."""

    verified = verify_canonical_reviewed_calendar_v2(
        manifest_path, repository_root=repository_root,
    )
    frame = pd.DataFrame(list(verified.session_projection), columns=PROJECTION_FIELDS)
    if frame.empty:
        return frame
    result = frame.loc[
        frame["decision_eligible"].eq(True)
        & frame["source_price_replay_available"].eq(True)
    ].copy()
    if not result.empty and not result["origin"].eq(PROSPECTIVE_ORIGIN).all():
        raise NdxObservedSessionCalendarV2Error("legacy session entered v2 decision proof")
    return result.reset_index(drop=True)


def _transaction_receipt_hash(payload: Mapping[str, Any]) -> str:
    clean = dict(payload)
    clean.pop("receipt_sha256", None)
    return canonical_sha256(clean)


def _fault_point(label: str) -> None:
    """No-op seam patched only by crash-recovery tests."""


def _validate_transaction_receipt(
    receipt: Mapping[str, Any], *, expected_manifest: Mapping[str, Any] | None = None,
) -> None:
    required = {
        "schema_version", "manifest_type", "transaction_id", "created_at_utc",
        "old_ledger_size", "old_ledger_sha256", "old_event_count",
        "old_event_head_sha256", "additions", "planned_manifest", "receipt_sha256",
    }
    if (
        set(receipt) != required
        or receipt.get("schema_version") != 1
        or receipt.get("manifest_type")
        != "ndx_observed_session_calendar_v2_pending_transaction"
        or not _is_sha256(receipt.get("transaction_id"))
        or receipt.get("receipt_sha256") != _transaction_receipt_hash(receipt)
    ):
        raise NdxObservedSessionCalendarV2Error("pending v2 transaction changed")
    planned = receipt.get("planned_manifest")
    additions = receipt.get("additions")
    if (
        not isinstance(planned, Mapping)
        or set(planned) != V2_MANIFEST_FIELDS
        or planned.get("commit_transaction_id") != receipt.get("transaction_id")
        or planned.get("manifest_sha256") != _manifest_hash(planned)
        or not isinstance(additions, list)
        or not additions
        or not isinstance(receipt.get("old_ledger_size"), int)
        or int(receipt["old_ledger_size"]) < 0
        or not _is_sha256(receipt.get("old_ledger_sha256"))
        or not isinstance(receipt.get("old_event_count"), int)
        or int(receipt["old_event_count"]) < 0
    ):
        raise NdxObservedSessionCalendarV2Error("pending v2 planned manifest changed")
    expected_old_head = receipt.get("old_event_head_sha256")
    if expected_old_head is not None and not _is_sha256(expected_old_head):
        raise NdxObservedSessionCalendarV2Error("pending v2 old event head changed")
    if expected_manifest is not None and dict(planned) != dict(expected_manifest):
        raise NdxObservedSessionCalendarV2Error(
            "committed v2 transaction does not bind current manifest"
        )


def _build_v2_manifest_payload(
    *, repository_root: Path, events: Sequence[Mapping[str, Any]],
    projection: Sequence[Mapping[str, Any]], calendar_start_date: str,
    prospective_start_date: str, tickers: Sequence[str],
    legacy_boundary: Mapping[str, Any], snapshot_items: Sequence[Mapping[str, Any]],
    generated_at_utc: datetime, protected_hashes: Mapping[str, str | None],
    commit_transaction_id: str,
) -> dict[str, Any]:
    root = repository_root.resolve()
    output = root / CANONICAL_ROOT_RELATIVE
    ledger_path = output / "events.jsonl"
    projection_path = output / "sessions.csv"
    ledger_bytes = _event_ledger_bytes(events)
    projection_bytes = _projection_csv_bytes(projection)
    sessions = _session_events(events)
    engine_path = root / "backtest/ndx_observed_session_calendar_v2.py"
    runner_path = root / "scripts/ndx_observed_session_calendar_v2.py"
    if not engine_path.is_file() or not runner_path.is_file():
        raise NdxObservedSessionCalendarV2Error("canonical v2 engine/runner is missing")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": V2_MANIFEST_TYPE,
        "generated_at_utc": generated_at_utc.astimezone(UTC).isoformat(),
        "status": "REVIEWED_CALENDAR_V2_RESEARCH_ONLY_NOT_ACTIVATED",
        "calendar_start_date": calendar_start_date,
        "prospective_start_date": prospective_start_date,
        "tickers": list(tickers),
        "session_count": len(sessions),
        "event_count": len(events),
        "revision_event_count": sum(
            event["event_type"] == SOURCE_REVISION_EVENT for event in events
        ),
        "decision_eligible_session_count": sum(
            row["decision_eligible"] and row["source_price_replay_available"]
            for row in projection
        ),
        "latest_session_date": sessions[-1]["session_date"] if sessions else None,
        "latest_event_sha256": events[-1]["event_sha256"] if events else None,
        "inputs": {
            "engine": {"path": engine_path.resolve().as_posix(), "sha256": file_sha256(engine_path)},
            "runner": {"path": runner_path.resolve().as_posix(), "sha256": file_sha256(runner_path)},
        },
        "legacy_boundary": dict(legacy_boundary),
        "source_snapshots": list(snapshot_items),
        "artifacts": {
            "event_ledger": {
                "path": ledger_path.resolve().as_posix(),
                "sha256": hashlib.sha256(ledger_bytes).hexdigest(),
                "rows": len(events),
                "latest_event_sha256": events[-1]["event_sha256"] if events else None,
            },
            "session_projection": {
                "path": projection_path.resolve().as_posix(),
                "sha256": hashlib.sha256(projection_bytes).hexdigest(),
                "rows": len(projection), "derived_from_event_ledger": True,
            },
        },
        "boundaries": dict(V2_BOUNDARIES),
        "protected_hashes_before": dict(protected_hashes),
        "protected_hashes_after": dict(protected_hashes),
        "commit_transaction_id": commit_transaction_id,
    }
    payload["manifest_sha256"] = _manifest_hash(payload)
    return payload


def _commit_pending_transaction(*, repository_root: Path) -> bool:
    root = repository_root.resolve()
    output = root / CANONICAL_ROOT_RELATIVE
    pending = output / "pending_transaction.json"
    if not pending.is_file():
        return False
    try:
        receipt = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("pending v2 transaction is unreadable") from exc
    _validate_transaction_receipt(receipt)
    planned = receipt["planned_manifest"]
    ledger_path = output / "events.jsonl"
    current_bytes = ledger_path.read_bytes() if ledger_path.is_file() else b""
    old_size = int(receipt["old_ledger_size"])
    if len(current_bytes) < old_size:
        raise NdxObservedSessionCalendarV2Error("v2 ledger is shorter than committed prefix")
    old_prefix = current_bytes[:old_size]
    if hashlib.sha256(old_prefix).hexdigest() != receipt["old_ledger_sha256"]:
        raise NdxObservedSessionCalendarV2Error("v2 committed ledger prefix changed")
    if old_prefix:
        try:
            old_events = [
                json.loads(line) for line in old_prefix.decode("utf-8").splitlines()
            ]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NdxObservedSessionCalendarV2Error(
                "v2 committed ledger prefix is not complete JSONL"
            ) from exc
    else:
        old_events = []
    if (
        len(old_events) != int(receipt["old_event_count"])
        or (old_events[-1]["event_sha256"] if old_events else None)
        != receipt["old_event_head_sha256"]
    ):
        raise NdxObservedSessionCalendarV2Error("v2 committed ledger prefix metadata changed")
    additions = receipt.get("additions")
    if not isinstance(additions, list) or not additions:
        raise NdxObservedSessionCalendarV2Error("pending v2 transaction has no additions")
    expected_bytes = old_prefix + _event_ledger_bytes(additions)
    if not expected_bytes.startswith(current_bytes):
        raise NdxObservedSessionCalendarV2Error("v2 partial ledger differs from pending transaction")
    if len(current_bytes) < len(expected_bytes):
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("ab") as handle:
            handle.write(expected_bytes[len(current_bytes):])
            handle.flush()
            os.fsync(handle.fileno())
    _fault_point("AFTER_EVENT_LEDGER")
    if file_sha256(ledger_path) != planned["artifacts"]["event_ledger"]["sha256"]:
        raise NdxObservedSessionCalendarV2Error("v2 completed ledger differs from planned hash")
    events = _load_event_ledger(ledger_path)
    projection = projection_rows(events)
    projection_path = output / "sessions.csv"
    _atomic_write_bytes(projection_path, _projection_csv_bytes(projection))
    _fault_point("AFTER_SESSION_PROJECTION")
    if file_sha256(projection_path) != planned["artifacts"]["session_projection"]["sha256"]:
        raise NdxObservedSessionCalendarV2Error("v2 projection differs from planned hash")
    manifest_path = output / "manifest.json"
    _atomic_write_json(manifest_path, planned)
    _fault_point("AFTER_CURRENT_MANIFEST")
    committed = output / "committed_transactions" / f"{receipt['transaction_id']}.json"
    committed.parent.mkdir(parents=True, exist_ok=True)
    if committed.exists() and committed.read_bytes() != pending.read_bytes():
        raise NdxObservedSessionCalendarV2Error("v2 committed transaction id collision")
    if committed.exists():
        pending.unlink()
    else:
        os.replace(pending, committed)
    return True


def _freeze_legacy_v1_boundary(
    *, repository_root: Path, v1_manifest_path: Path, v1_ledger_path: Path,
    tickers: Sequence[str], prospective_start_date: str,
) -> tuple[dict[str, Any], LegacyV1Evidence]:
    root = repository_root.resolve()
    expected_v1_root = root / "data/cache/research/ndx_observed_us_session_calendar_v1"
    if (
        v1_manifest_path.resolve() != (expected_v1_root / "manifest.json").resolve()
        or v1_ledger_path.resolve() != (expected_v1_root / "sessions.jsonl").resolve()
    ):
        raise NdxObservedSessionCalendarV2Error("v1 import paths are not canonical")
    evidence = load_legacy_v1_evidence(
        v1_ledger_path, tickers=tickers, prospective_start_date=prospective_start_date,
    )
    try:
        manifest_bytes = v1_manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxObservedSessionCalendarV2Error("cannot freeze canonical v1 manifest") from exc
    ledger_item = ((manifest.get("artifacts") or {}).get("append_only_ledger") or {})
    if (
        Path(str(ledger_item.get("path") or "")).resolve() != v1_ledger_path.resolve()
        or ledger_item.get("sha256") != evidence.sha256
        or int(ledger_item.get("rows", -1)) != len(evidence.records)
        or manifest.get("prospective_start_date") != prospective_start_date
    ):
        raise NdxObservedSessionCalendarV2Error("v1 import manifest/ledger boundary changed")
    archive = root / CANONICAL_ROOT_RELATIVE / "legacy_v1"
    frozen_manifest = archive / "manifest.json"
    frozen_ledger = archive / "sessions.jsonl"
    for path, raw in (
        (frozen_manifest, manifest_bytes), (frozen_ledger, evidence.raw_bytes),
    ):
        if path.exists():
            if path.read_bytes() != raw:
                raise NdxObservedSessionCalendarV2Error("existing frozen v1 boundary differs")
        else:
            _atomic_write_bytes(path, raw)
    frozen_evidence = load_legacy_v1_evidence(
        frozen_ledger, tickers=tickers, prospective_start_date=prospective_start_date,
    )
    return ({
        "source_manifest": {
            "path": v1_manifest_path.resolve().as_posix(),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        },
        "source_ledger": {
            "path": v1_ledger_path.resolve().as_posix(), "sha256": evidence.sha256,
        },
        "frozen_manifest": {
            "path": frozen_manifest.resolve().as_posix(), "sha256": file_sha256(frozen_manifest),
        },
        "frozen_ledger": {
            "path": frozen_ledger.resolve().as_posix(), "sha256": file_sha256(frozen_ledger),
        },
    }, frozen_evidence)


def write_canonical_reviewed_calendar_v2(
    *, repository_root: str | Path, snapshot: CapturedSourceSnapshot,
    calendar_start_date: str, prospective_start_date: str,
    initialize_reviewed_v1: bool,
) -> VerifiedReviewedCalendarV2:
    """Initialize explicitly or append to the canonical research-only v2 ledger."""

    root = Path(repository_root).resolve()
    output = root / CANONICAL_ROOT_RELATIVE
    manifest_path = output / "manifest.json"
    ledger_path = output / "events.jsonl"
    tickers = sorted(snapshot.source_paths)
    if tickers != ["QQQ", "SPY"]:
        raise NdxObservedSessionCalendarV2Error("canonical v2 currently requires exact QQQ/SPY sources")
    _verify_captured_snapshot(
        snapshot, tickers=tickers, required_start_date=calendar_start_date,
    )
    recovered = _commit_pending_transaction(repository_root=root)
    before = _protected_hashes(root)
    if manifest_path.exists():
        if initialize_reviewed_v1 and not recovered:
            raise NdxObservedSessionCalendarV2Error("reviewed v1 initialization is one-time only")
        verified = verify_canonical_reviewed_calendar_v2(
            manifest_path, repository_root=root,
        )
        if (
            verified.manifest["calendar_start_date"] != calendar_start_date
            or verified.manifest["prospective_start_date"] != prospective_start_date
            or verified.manifest["tickers"] != tickers
        ):
            raise NdxObservedSessionCalendarV2Error("v2 calendar boundaries cannot change in place")
        if initialize_reviewed_v1:
            return verified
        base_events = list(verified.events)
        legacy_boundary = verified.manifest["legacy_boundary"]
        legacy_evidence = verified.legacy_v1_evidence
    else:
        if not initialize_reviewed_v1:
            raise NdxObservedSessionCalendarV2Error(
                "canonical v2 is absent; explicit reviewed v1 initialization is required"
            )
        v1_root = root / "data/cache/research/ndx_observed_us_session_calendar_v1"
        legacy_boundary, legacy_evidence = _freeze_legacy_v1_boundary(
            repository_root=root, v1_manifest_path=v1_root / "manifest.json",
            v1_ledger_path=v1_root / "sessions.jsonl", tickers=tickers,
            prospective_start_date=prospective_start_date,
        )
        if (
            not legacy_evidence.records
            or legacy_evidence.records[0]["session_date"] != calendar_start_date
        ):
            raise NdxObservedSessionCalendarV2Error("v1 first session does not match v2 start")
        base_events = import_v1_legacy_records(
            legacy_evidence, tickers=tickers,
            prospective_start_date=prospective_start_date,
            imported_at_utc=snapshot.observed_at_utc,
        )
    additions = prepare_reviewed_update(
        base_events, snapshot=snapshot, tickers=tickers,
        calendar_start_date=calendar_start_date,
        prospective_start_date=prospective_start_date,
        legacy_v1_evidence=legacy_evidence,
    )
    initializing = not ledger_path.exists()
    transaction_additions = [*base_events, *additions] if initializing else additions
    if not transaction_additions:
        return verify_canonical_reviewed_calendar_v2(manifest_path, repository_root=root)
    if additions:
        _write_source_snapshot_archive(snapshot, tickers=tickers, repository_root=root)
    all_events = [*base_events, *additions]
    validate_event_ledger(
        all_events, tickers=tickers, prospective_start_date=prospective_start_date,
        legacy_v1_evidence=legacy_evidence,
    )
    projection = projection_rows(all_events)
    referenced_ids = sorted({
        str(event["source_snapshot_id"])
        for event in all_events if event["source_snapshot_id"] is not None
    })
    snapshot_items = []
    for snapshot_id_value in referenced_ids:
        source_manifest = output / "source_snapshots" / snapshot_id_value / "manifest.json"
        _verify_source_snapshot_archive(
            source_manifest, repository_root=root, expected_snapshot_id=snapshot_id_value,
        )
        snapshot_items.append({
            "snapshot_id": snapshot_id_value, "path": source_manifest.resolve().as_posix(),
            "sha256": file_sha256(source_manifest),
        })
    engine_path = root / "backtest/ndx_observed_session_calendar_v2.py"
    runner_path = root / "scripts/ndx_observed_session_calendar_v2.py"
    if not engine_path.is_file() or not runner_path.is_file():
        raise NdxObservedSessionCalendarV2Error("canonical v2 engine/runner is missing")
    after = _protected_hashes(root)
    if before != after:
        raise NdxObservedSessionCalendarV2Error("protected live files changed during v2 write")
    old_ledger_bytes = ledger_path.read_bytes() if ledger_path.is_file() else b""
    old_event_count = len(base_events) if not initializing else 0
    old_event_head = base_events[-1]["event_sha256"] if old_event_count else None
    transaction_id = canonical_sha256({
        "old_ledger_sha256": hashlib.sha256(old_ledger_bytes).hexdigest(),
        "new_ledger_sha256": hashlib.sha256(_event_ledger_bytes(all_events)).hexdigest(),
        "generated_at_utc": snapshot.observed_at_utc.astimezone(UTC).isoformat(),
        "source_snapshot_ids": referenced_ids,
    })
    payload = _build_v2_manifest_payload(
        repository_root=root, events=all_events, projection=projection,
        calendar_start_date=calendar_start_date,
        prospective_start_date=prospective_start_date, tickers=tickers,
        legacy_boundary=legacy_boundary, snapshot_items=snapshot_items,
        generated_at_utc=snapshot.observed_at_utc,
        protected_hashes=before, commit_transaction_id=transaction_id,
    )
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "ndx_observed_session_calendar_v2_pending_transaction",
        "transaction_id": transaction_id,
        "created_at_utc": snapshot.observed_at_utc.astimezone(UTC).isoformat(),
        "old_ledger_size": len(old_ledger_bytes),
        "old_ledger_sha256": hashlib.sha256(old_ledger_bytes).hexdigest(),
        "old_event_count": old_event_count,
        "old_event_head_sha256": old_event_head,
        "additions": transaction_additions,
        "planned_manifest": payload,
    }
    receipt["receipt_sha256"] = _transaction_receipt_hash(receipt)
    output.mkdir(parents=True, exist_ok=True)
    pending_path = output / "pending_transaction.json"
    if pending_path.exists():
        raise NdxObservedSessionCalendarV2Error("unexpected pending v2 transaction")
    _atomic_write_json(pending_path, receipt)
    _fault_point("AFTER_PENDING_RECEIPT")
    _commit_pending_transaction(repository_root=root)
    return verify_canonical_reviewed_calendar_v2(manifest_path, repository_root=root)


__all__ = [
    "FROZEN_EVIDENCE_MODE",
    "CANONICAL_MANIFEST_RELATIVE",
    "CapturedSourceSnapshot",
    "LEGACY_EVIDENCE_MODE",
    "LEGACY_SESSION_EVENT",
    "NdxObservedSessionCalendarV2Error",
    "PROSPECTIVE_SESSION_EVENT",
    "SOURCE_REVISION_EVENT",
    "VerifiedReviewedCalendarV2",
    "build_migration_readiness",
    "capture_source_snapshot",
    "import_v1_legacy_records",
    "load_legacy_v1_evidence",
    "load_verified_decision_sessions_v2",
    "make_prospective_session_event",
    "prepare_reviewed_update",
    "projection_rows",
    "validate_event_ledger",
    "validate_normalized_ohlc",
    "verify_canonical_reviewed_calendar_v2",
    "write_canonical_reviewed_calendar_v2",
]
