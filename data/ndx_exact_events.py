"""Validation helpers for the point-in-time Nasdaq-100 event registry.

The registry is deliberately separate from the QQQ N-PORT proxy.  It records
official Nasdaq announcements and their effective dates; it does not infer
membership from prices, returns, fund holdings, or a ticker's recent behavior.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml


REGISTRY_SCHEMA_VERSION = 1
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
ALLOWED_HOSTS = {"www.nasdaq.com", "nasdaq.com", "ir.nasdaq.com"}
EVENT_STATUSES = {"effective", "superseded_reference"}
EVENT_TYPES = {
    "annual_reconstitution",
    "annual_reconstitution_update",
    "interim_replacement",
    "corporate_action_replacement",
    "special_rebalance_weight_only",
}

SOURCE_AUDIT_COLUMNS = [
    "event_id",
    "event_type",
    "event_status",
    "announcement_date",
    "effective_date",
    "source_available_date",
    "source_locator",
    "fetch_status",
    "http_status",
    "raw_path",
    "content_sha256",
    "raw_manifest_verified",
    "required_tickers",
    "missing_tickers",
    "required_phrases",
    "missing_phrases",
    "source_verified",
    "future_data_guard",
    "base_event_id",
    "base_source_verified",
    "notes",
]

EVENT_COLUMNS = [
    "event_id",
    "action_source_event_id",
    "event_type",
    "event_status",
    "announcement_date",
    "effective_date",
    "action",
    "ticker",
    "source_locator",
    "raw_path",
    "content_sha256",
    "source_manifest_verified",
    "source_available_date",
    "future_data_guard",
    "source_verified",
    "inherited_from_event_id",
    "notes",
]

FETCH_COLUMNS = [
    "event_id",
    "event_type",
    "event_status",
    "source_locator",
    "raw_path",
    "status",
    "http_status",
    "attempted_at",
    "content_sha256",
    "error",
]

GAP_COLUMNS = ["gap_type", "event_id", "details"]


class NdxExactEventsError(ValueError):
    """Raised when the official event registry cannot be audited safely."""


def _iso_date(value: object, field: str) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise NdxExactEventsError(f"{field} must be YYYY-MM-DD: {value!r}") from exc


def _ticker(value: object, field: str) -> str:
    text = str(value or "").strip().upper()
    if not TICKER_PATTERN.fullmatch(text):
        raise NdxExactEventsError(f"{field} is not a valid ticker: {value!r}")
    if text in {"NDX", "QQQ"}:
        raise NdxExactEventsError(f"{field} cannot contain NDX or QQQ")
    return text


def _ticker_list(value: object, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise NdxExactEventsError(f"{field} must be a list")
    result = [_ticker(item, f"{field}[]") for item in value]
    if len(result) != len(set(result)):
        raise NdxExactEventsError(f"{field} contains duplicate tickers")
    return result


def _source_url(value: object, field: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise NdxExactEventsError(
            f"{field} must be an HTTPS Nasdaq source: {value!r}"
        )
    if not parsed.path or parsed.path == "/404":
        raise NdxExactEventsError(f"{field} has no usable Nasdaq page path")
    return text


def load_event_registry(path: str | Path) -> dict:
    """Load and strictly validate the versioned official-source registry."""

    source_path = Path(path)
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise NdxExactEventsError(f"cannot read event registry: {source_path}") from exc
    if not isinstance(payload, dict):
        raise NdxExactEventsError("event registry root must be a mapping")
    if int(payload.get("schema_version") or 0) != REGISTRY_SCHEMA_VERSION:
        raise NdxExactEventsError("unsupported event registry schema_version")
    if str(payload.get("index") or "").upper() != "NDX":
        raise NdxExactEventsError("event registry index must be NDX")
    scope = payload.get("scope") or {}
    if not isinstance(scope, dict):
        raise NdxExactEventsError("event registry scope must be a mapping")
    scope_start = _iso_date(scope.get("start"), "scope.start")
    scope_end = _iso_date(scope.get("end"), "scope.end")
    if scope_start > scope_end:
        raise NdxExactEventsError("event registry scope is reversed")
    events = payload.get("events") or []
    if not isinstance(events, list) or not events:
        raise NdxExactEventsError("event registry events must be a non-empty list")

    normalized = []
    seen_ids: set[str] = set()
    for raw in events:
        if not isinstance(raw, dict):
            raise NdxExactEventsError("each event registry item must be a mapping")
        event = dict(raw)
        event_id = str(event.get("event_id") or "").strip()
        if not event_id or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,100}", event_id):
            raise NdxExactEventsError(f"invalid event_id: {event_id!r}")
        if event_id in seen_ids:
            raise NdxExactEventsError(f"duplicate event_id: {event_id}")
        seen_ids.add(event_id)
        event_type = str(event.get("event_type") or "").strip()
        if event_type not in EVENT_TYPES:
            raise NdxExactEventsError(f"{event_id}: unsupported event_type {event_type!r}")
        event_status = str(event.get("event_status") or "").strip()
        if event_status not in EVENT_STATUSES:
            raise NdxExactEventsError(f"{event_id}: unsupported event_status {event_status!r}")
        announcement_date = _iso_date(event.get("announcement_date"), f"{event_id}.announcement_date")
        effective_date = _iso_date(event.get("effective_date"), f"{event_id}.effective_date")
        source_available_date = _iso_date(
            event.get("source_available_date", announcement_date),
            f"{event_id}.source_available_date",
        )
        if source_available_date < announcement_date:
            raise NdxExactEventsError(
                f"{event_id}: source_available_date is before announcement_date"
            )
        if not scope_start <= effective_date <= scope_end:
            raise NdxExactEventsError(
                f"{event_id}: effective date {effective_date} outside registry scope"
            )
        source_locator = _source_url(event.get("source_locator"), f"{event_id}.source_locator")
        added = _ticker_list(event.get("added_tickers"), f"{event_id}.added_tickers")
        removed = _ticker_list(event.get("removed_tickers"), f"{event_id}.removed_tickers")
        if set(added) & set(removed):
            raise NdxExactEventsError(f"{event_id}: ticker both added and removed")
        required_tickers = _ticker_list(
            event.get("required_tickers", added + removed),
            f"{event_id}.required_tickers",
        )
        phrases = event.get("required_phrases") or []
        if not isinstance(phrases, list) or not all(str(item).strip() for item in phrases):
            raise NdxExactEventsError(f"{event_id}.required_phrases must be a non-empty-text list")
        event["event_id"] = event_id
        event["event_type"] = event_type
        event["event_status"] = event_status
        event["announcement_date"] = announcement_date
        event["effective_date"] = effective_date
        event["source_available_date"] = source_available_date
        event["source_locator"] = source_locator
        event["added_tickers"] = added
        event["removed_tickers"] = removed
        event["required_tickers"] = required_tickers
        event["required_phrases"] = [str(item).strip() for item in phrases]
        event["base_event_id"] = str(event.get("base_event_id") or "").strip()
        event["remove_from_base"] = _ticker_list(
            event.get("remove_from_base"), f"{event_id}.remove_from_base"
        )
        notes = event.get("notes") or ""
        event["notes"] = str(notes).strip()
        if event_type == "special_rebalance_weight_only":
            if added or removed or event["base_event_id"]:
                raise NdxExactEventsError(
                    f"{event_id}: special rebalance cannot contain membership actions"
                )
        elif event_status == "effective" and not (added or removed or event["base_event_id"]):
            raise NdxExactEventsError(f"{event_id}: effective event has no membership action")
        if event["base_event_id"] and event["base_event_id"] == event_id:
            raise NdxExactEventsError(f"{event_id}: base_event_id cannot reference itself")
        normalized.append(event)

    by_id = {event["event_id"]: event for event in normalized}
    for event in normalized:
        base_id = event["base_event_id"]
        if not base_id:
            continue
        if base_id not in by_id:
            raise NdxExactEventsError(f"{event['event_id']}: unknown base_event_id {base_id}")
        base = by_id[base_id]
        if base["event_type"] == "special_rebalance_weight_only":
            raise NdxExactEventsError(f"{event['event_id']}: cannot inherit a weight-only event")
        if set(event["remove_from_base"]) - set(base["added_tickers"] + base["removed_tickers"]):
            raise NdxExactEventsError(
                f"{event['event_id']}: remove_from_base is not present in base event"
            )

    metadata = dict(payload)
    metadata["schema_version"] = REGISTRY_SCHEMA_VERSION
    metadata["index"] = "NDX"
    metadata["scope"] = {"start": scope_start, "end": scope_end}
    metadata["events"] = normalized
    metadata["registry_path"] = source_path.as_posix()
    return metadata


def html_to_text(content: bytes) -> str:
    """Turn an HTML response into normalized searchable text."""

    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def _contains_ticker(text: str, ticker: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])",
            text,
            flags=re.I,
        )
    )


def verify_source_content(event: dict, content: bytes) -> dict:
    """Verify the declared source markers without interpreting returns."""

    text = html_to_text(content)
    missing_tickers = [
        ticker for ticker in event.get("required_tickers", [])
        if not _contains_ticker(text, ticker)
    ]
    normalized_text = text.casefold()
    missing_phrases = [
        phrase for phrase in event.get("required_phrases", [])
        if " ".join(str(phrase).split()).casefold() not in normalized_text
    ]
    return {
        "source_verified": not missing_tickers and not missing_phrases and bool(text),
        "missing_tickers": missing_tickers,
        "missing_phrases": missing_phrases,
        "text_length": len(text),
    }


def _direct_actions(event: dict) -> list[dict]:
    rows = [
        {"action": "add", "ticker": ticker, "action_source_event_id": event["event_id"]}
        for ticker in event.get("added_tickers", [])
    ]
    rows.extend(
        {
            "action": "remove",
            "ticker": ticker,
            "action_source_event_id": event["event_id"],
        }
        for ticker in event.get("removed_tickers", [])
    )
    if event["event_type"] == "special_rebalance_weight_only":
        rows.append(
            {
                "action": "weight_only",
                "ticker": "",
                "action_source_event_id": event["event_id"],
            }
        )
    return rows


def _expanded_actions(event_id: str, by_id: dict[str, dict], seen: set[str] | None = None) -> list[dict]:
    seen = set(seen or set())
    if event_id in seen:
        raise NdxExactEventsError(f"event inheritance cycle detected at {event_id}")
    seen.add(event_id)
    event = by_id[event_id]
    base_id = event.get("base_event_id") or ""
    if not base_id:
        return _direct_actions(event)
    base_rows = _expanded_actions(base_id, by_id, seen)
    remove_from_base = set(event.get("remove_from_base") or [])
    rows = [
        row for row in base_rows
        if not (row["action"] in {"add", "remove"} and row["ticker"] in remove_from_base)
    ]
    rows.extend(_direct_actions(event))
    unique = {}
    for row in rows:
        key = (row["action"], row["ticker"])
        unique[key] = row
    return list(unique.values())


def build_effective_event_rows(
    registry: dict,
    source_audit: pd.DataFrame,
    *,
    raw_path_by_event: dict[str, str] | None = None,
    hash_by_event: dict[str, str] | None = None,
    manifest_verified_by_event: dict[str, bool] | None = None,
) -> pd.DataFrame:
    """Expand effective events, including an amended event's inherited actions."""

    raw_path_by_event = raw_path_by_event or {}
    hash_by_event = hash_by_event or {}
    manifest_verified_by_event = manifest_verified_by_event or {}
    audit_by_id = {
        str(row["event_id"]): row
        for row in source_audit.to_dict(orient="records")
    }
    by_id = {event["event_id"]: event for event in registry["events"]}
    rows: list[dict] = []
    for event in registry["events"]:
        if event["event_status"] != "effective":
            continue
        current_audit = audit_by_id.get(event["event_id"], {})
        base_id = event.get("base_event_id") or ""
        base_audit = audit_by_id.get(base_id, {}) if base_id else {}
        current_verified = bool(current_audit.get("source_verified"))
        base_verified = bool(base_audit.get("source_verified")) if base_id else True
        source_verified = current_verified and base_verified
        future_guard = event["source_available_date"] <= event["effective_date"]
        for action_row in _expanded_actions(event["event_id"], by_id):
            action_source_id = action_row["action_source_event_id"]
            inherited = action_source_id if action_source_id != event["event_id"] else ""
            rows.append({
                "event_id": event["event_id"],
                "action_source_event_id": action_source_id,
                "event_type": event["event_type"],
                "event_status": event["event_status"],
                "announcement_date": event["announcement_date"],
                "effective_date": event["effective_date"],
                "action": action_row["action"],
                "ticker": action_row["ticker"],
                "source_locator": event["source_locator"],
                "raw_path": raw_path_by_event.get(event["event_id"], ""),
                "content_sha256": hash_by_event.get(event["event_id"], ""),
                "source_manifest_verified": bool(
                    manifest_verified_by_event.get(event["event_id"], False)
                ),
                "source_available_date": event["source_available_date"],
                "future_data_guard": future_guard,
                "source_verified": source_verified,
                "inherited_from_event_id": inherited,
                "notes": event.get("notes", ""),
            })
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def empty_fetch_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=FETCH_COLUMNS)


def empty_source_audit_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=SOURCE_AUDIT_COLUMNS)


def empty_gap_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=GAP_COLUMNS)


def json_safe(value: object) -> object:
    """Convert pandas/numpy scalar values for manifest JSON construction."""

    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


__all__ = [
    "EVENT_COLUMNS",
    "EVENT_STATUSES",
    "EVENT_TYPES",
    "FETCH_COLUMNS",
    "GAP_COLUMNS",
    "NdxExactEventsError",
    "REGISTRY_SCHEMA_VERSION",
    "SOURCE_AUDIT_COLUMNS",
    "build_effective_event_rows",
    "empty_fetch_frame",
    "empty_gap_frame",
    "empty_source_audit_frame",
    "html_to_text",
    "load_event_registry",
    "verify_source_content",
]
