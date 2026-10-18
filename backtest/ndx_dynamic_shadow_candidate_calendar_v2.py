"""Immutable reviewed-calendar-v2 prefix evidence for one candidate seal.

The canonical v2 calendar is append-only, so its whole-file digest changes on a
normal later session.  A candidate decision must therefore bind a verified
prefix (row count, exact prefix bytes and terminal event hash), not the future
whole-file digest.  The small frozen session projection in this evidence bundle
is sufficient to reproduce the decision coordinate after later appends.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

import pandas as pd

from data.versioning import file_sha256


class NdxDynamicShadowCandidateCalendarV2Error(ValueError):
    """Raised when a reviewed-calendar prefix is non-canonical or mutable."""


CALENDAR_RELATIVE = Path(
    "data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json"
)
EVENT_LEDGER_RELATIVE = Path(
    "data/cache/research/ndx_observed_us_session_calendar_v2/events.jsonl"
)
SESSION_PROJECTION_RELATIVE = Path(
    "data/cache/research/ndx_observed_us_session_calendar_v2/sessions.csv"
)
EVIDENCE_ROOT_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1/calendar_evidence_v2"
)
ENGINE_RELATIVE = Path("backtest/ndx_observed_session_calendar_v2.py")
CALENDAR_SCRIPT_RELATIVE = Path("scripts/ndx_observed_session_calendar_v2.py")
ADAPTER_RELATIVE = Path("backtest/ndx_dynamic_shadow_candidate_calendar_v2.py")
MANIFEST_TYPE = "ndx_dynamic_shadow_candidate_calendar_v2_prefix"
MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "status", "decision_date",
    "calendar_manifest", "event_ledger_prefix", "session_projection_prefix",
    "source_code", "evidence_boundary", "manifest_sha256",
}
CALENDAR_MANIFEST_FIELDS = {
    "canonical_path", "sha256_at_capture", "frozen_filename",
    "committed_transaction_id", "committed_receipt_canonical_path",
    "committed_receipt_filename", "committed_receipt_sha256",
}
EVENT_PREFIX_FIELDS = {
    "canonical_path", "prefix_rows", "prefix_bytes_sha256",
    "terminal_event_sha256",
}
SESSION_PREFIX_FIELDS = {"filename", "rows", "sha256"}
SOURCE_CODE_FIELDS = {"calendar_engine", "calendar_script", "candidate_calendar_adapter"}
SOURCE_CODE_ITEM_FIELDS = {"path", "sha256_at_capture"}
DECISION_SESSION_FIELDS = [
    "session_date", "open_timestamp_utc", "close_timestamp_utc",
    "is_first_observed_session_of_month", "origin", "decision_eligible",
    "source_price_replay_available", "session_event_sha256",
]


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    return hashlib.sha256(json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _exact_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise NdxDynamicShadowCandidateCalendarV2Error(f"{label} schema changed")
    return value


def _atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _public_calendar_verifier(path: Path, root: Path) -> Any:
    from backtest.ndx_observed_session_calendar_v2 import (
        verify_canonical_reviewed_calendar_v2,
    )

    return verify_canonical_reviewed_calendar_v2(path, repository_root=root)


def _public_decision_sessions(path: Path, root: Path) -> pd.DataFrame:
    from backtest.ndx_observed_session_calendar_v2 import (
        load_verified_decision_sessions_v2,
    )

    result = load_verified_decision_sessions_v2(path, repository_root=root)
    if not isinstance(result, pd.DataFrame):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 decision-session loader did not return a data frame"
        )
    return result


def _strict_decision_sessions(
    frame: pd.DataFrame, decision_date: str, *, allow_later_sessions: bool = False,
) -> pd.DataFrame:
    required = set(DECISION_SESSION_FIELDS)
    if not required.issubset(frame.columns):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 decision-session projection is incomplete"
        )
    sessions = frame.copy()
    raw_dates = sessions["session_date"].astype(str)
    if not raw_dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 session dates must be YYYY-MM-DD"
        )
    sessions["session_date"] = pd.to_datetime(raw_dates, errors="raise")
    sessions["open_timestamp_utc"] = pd.to_datetime(
        sessions["open_timestamp_utc"], utc=True, errors="raise",
    )
    sessions["close_timestamp_utc"] = pd.to_datetime(
        sessions["close_timestamp_utc"], utc=True, errors="raise",
    )
    for column in ("is_first_observed_session_of_month", "decision_eligible", "source_price_replay_available"):
        values = sessions[column].map(
            lambda value: value if isinstance(value, bool)
            else str(value).strip().lower() == "true"
            if str(value).strip().lower() in {"true", "false"}
            else None
        )
        if values.isna().any():
            raise NdxDynamicShadowCandidateCalendarV2Error(
                f"calendar-v2 decision session has invalid boolean: {column}"
            )
        sessions[column] = values.astype(bool)
    if (
        sessions["origin"].astype(str).str.strip().eq("").any()
        or sessions["session_event_sha256"].map(_is_sha256).eq(False).any()
        or not sessions["decision_eligible"].all()
        or not sessions["source_price_replay_available"].all()
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 decision-session identity is incomplete"
        )
    if (
        sessions.empty or sessions["session_date"].duplicated().any()
        or not sessions["session_date"].is_monotonic_increasing
        or sessions["open_timestamp_utc"].ge(sessions["close_timestamp_utc"]).any()
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 decision sessions are empty, duplicated, or misordered"
        )
    decision = pd.Timestamp(decision_date).normalize()
    if decision < pd.Timestamp("2026-10-01"):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate-v2 decision precedes the prospective calendar boundary"
        )
    prefix = sessions.loc[sessions["session_date"].le(decision)].copy()
    if prefix.empty or prefix["session_date"].iloc[-1] != decision:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate decision is not a verified decision-eligible v2 session"
        )
    if not allow_later_sessions and sessions["session_date"].gt(decision).any():
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "later decision-eligible sessions already exist; late seal/backfill is forbidden"
        )
    prefix["session_date"] = prefix["session_date"].dt.strftime("%Y-%m-%d")
    prefix["open_timestamp_utc"] = prefix["open_timestamp_utc"].map(pd.Timestamp.isoformat)
    prefix["close_timestamp_utc"] = prefix["close_timestamp_utc"].map(pd.Timestamp.isoformat)
    return prefix[DECISION_SESSION_FIELDS]


def _event_prefix(raw: bytes) -> tuple[int, str, str]:
    lines = raw.splitlines(keepends=True)
    if not lines or any(not line.strip() for line in lines) or not raw.endswith(b"\n"):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 event ledger is empty or not canonical JSONL"
        )
    try:
        events = [json.loads(line.decode("utf-8")) for line in lines]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 event ledger cannot be parsed"
        ) from exc
    if any(not isinstance(event, dict) for event in events):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 event ledger row is not a mapping"
        )
    terminal = str(events[-1].get("event_sha256") or "")
    if len(terminal) != 64:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 terminal event hash is missing"
        )
    return len(lines), terminal, hashlib.sha256(raw).hexdigest()


def _stable_verified_capture(
    manifest_path: Path, root: Path,
) -> tuple[bytes, bytes, bytes, bytes, Path, pd.DataFrame]:
    event_path = root / EVENT_LEDGER_RELATIVE
    projection_path = root / SESSION_PROJECTION_RELATIVE
    _public_calendar_verifier(manifest_path, root)
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 canonical manifest cannot be frozen"
        ) from exc
    transaction_id = str(manifest.get("commit_transaction_id") or "")
    if not _is_sha256(transaction_id):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 canonical manifest lacks a committed transaction"
        )
    receipt_path = (
        manifest_path.parent / "committed_transactions" / f"{transaction_id}.json"
    ).resolve()
    before = (
        manifest_bytes, event_path.read_bytes(), projection_path.read_bytes(),
        receipt_path.read_bytes(),
    )
    sessions = _public_decision_sessions(manifest_path, root)
    after = (
        manifest_path.read_bytes(), event_path.read_bytes(), projection_path.read_bytes(),
        receipt_path.read_bytes(),
    )
    if before != after:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 changed while candidate evidence was captured"
        )
    return before[0], before[1], before[2], before[3], receipt_path, sessions


def candidate_calendar_evidence_path(
    decision_date: str, *, repository_root: str | Path,
) -> Path:
    if not pd.Series([decision_date]).astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise NdxDynamicShadowCandidateCalendarV2Error("invalid candidate decision date")
    return (
        Path(repository_root).resolve() / EVIDENCE_ROOT_RELATIVE
        / decision_date / "manifest.json"
    )


def capture_candidate_calendar_evidence_v2(
    calendar_manifest_path: str | Path, *, decision_date: str,
    repository_root: str | Path,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    """Seal one verified append-only prefix without blocking later appends."""

    root = Path(repository_root).resolve()
    calendar_path = Path(calendar_manifest_path).resolve()
    if calendar_path != (root / CALENDAR_RELATIVE).resolve():
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate-v2 requires the canonical reviewed calendar-v2 manifest"
        )
    destination = candidate_calendar_evidence_path(
        decision_date, repository_root=root,
    )
    if destination.is_file():
        sessions = verify_candidate_calendar_evidence_v2(
            destination, repository_root=root,
        )
        return sessions, *_source_registry(destination, root)
    if destination.parent.exists():
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "partial immutable calendar-v2 candidate evidence exists"
        )
    manifest_bytes, event_bytes, _, receipt_bytes, receipt_path, sessions = _stable_verified_capture(
        calendar_path, root,
    )
    prefix = _strict_decision_sessions(sessions, decision_date)
    event_rows, terminal_hash, prefix_hash = _event_prefix(event_bytes)
    try:
        frozen_manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
        receipt_payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 committed evidence cannot be parsed"
        ) from exc
    transaction_id = str(frozen_manifest_payload.get("commit_transaction_id") or "")
    if (
        receipt_payload.get("transaction_id") != transaction_id
        or receipt_payload.get("planned_manifest") != frozen_manifest_payload
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 committed receipt does not bind the captured manifest"
        )
    ledger_item = ((frozen_manifest_payload.get("artifacts") or {}).get("event_ledger") or {})
    if (
        int(ledger_item.get("rows", -1)) != event_rows
        or ledger_item.get("sha256") != prefix_hash
        or ledger_item.get("latest_event_sha256") != terminal_hash
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 captured manifest does not bind its event prefix"
        )
    evidence_root = destination.parent.parent
    evidence_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{decision_date}.", dir=evidence_root))
    projection_path = temporary / "decision_sessions_prefix.csv"
    frozen_manifest_path = temporary / "calendar_manifest_at_capture.json"
    frozen_receipt_path = temporary / "committed_transaction_receipt.json"
    projection_content = prefix.to_csv(index=False, lineterminator="\n")
    _atomic_text(projection_path, projection_content)
    frozen_manifest_path.write_bytes(manifest_bytes)
    frozen_receipt_path.write_bytes(receipt_bytes)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "status": "IMMUTABLE_VERIFIED_CALENDAR_V2_PREFIX_RESEARCH_ONLY",
        "decision_date": decision_date,
        "calendar_manifest": {
            "canonical_path": calendar_path.as_posix(),
            "sha256_at_capture": hashlib.sha256(manifest_bytes).hexdigest(),
            "frozen_filename": frozen_manifest_path.name,
            "committed_transaction_id": transaction_id,
            "committed_receipt_canonical_path": receipt_path.as_posix(),
            "committed_receipt_filename": frozen_receipt_path.name,
            "committed_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        },
        "event_ledger_prefix": {
            "canonical_path": (root / EVENT_LEDGER_RELATIVE).as_posix(),
            "prefix_rows": event_rows,
            "prefix_bytes_sha256": prefix_hash,
            "terminal_event_sha256": terminal_hash,
        },
        "session_projection_prefix": {
            "filename": projection_path.name,
            "rows": len(prefix),
            "sha256": file_sha256(projection_path),
        },
        "source_code": {
            "calendar_engine": {
                "path": (root / ENGINE_RELATIVE).as_posix(),
                "sha256_at_capture": file_sha256(root / ENGINE_RELATIVE),
            },
            "calendar_script": {
                "path": (root / CALENDAR_SCRIPT_RELATIVE).as_posix(),
                "sha256_at_capture": file_sha256(root / CALENDAR_SCRIPT_RELATIVE),
            },
            "candidate_calendar_adapter": {
                "path": (root / ADAPTER_RELATIVE).as_posix(),
                "sha256_at_capture": file_sha256(root / ADAPTER_RELATIVE),
            },
        },
        "evidence_boundary": {
            "legacy_hash_only_session_used_for_decision": False,
            "source_revision_event_used_for_decision": False,
            "later_calendar_append_allowed": True,
            "retrospective_backfill_allowed": False,
            "promotion_allowed": False,
            "live_mutation": False,
        },
    }
    payload["manifest_sha256"] = _canonical_sha256(payload)
    temporary_manifest = temporary / "manifest.json"
    try:
        _atomic_text(
            temporary_manifest,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        try:
            os.replace(temporary, destination.parent)
        except OSError:
            if destination.is_file():
                shutil.rmtree(temporary)
            else:
                raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    verified = verify_candidate_calendar_evidence_v2(
        destination, repository_root=root,
    )
    return verified, *_source_registry(destination, root)


def _source_registry(
    evidence_manifest: Path, root: Path,
) -> tuple[dict[str, str], dict[str, str]]:
    evidence = json.loads(evidence_manifest.read_text(encoding="utf-8"))
    prefix = evidence["event_ledger_prefix"]
    projection = evidence_manifest.parent / evidence["session_projection_prefix"]["filename"]
    versions = {
        "session_calendar_manifest_sha256": evidence["calendar_manifest"]["sha256_at_capture"],
        "session_calendar_projection_sha256": file_sha256(projection),
        "session_calendar_ledger_sha256": prefix["prefix_bytes_sha256"],
        "session_calendar_verifier_sha256": evidence["source_code"]["calendar_script"]["sha256_at_capture"],
        "session_calendar_engine_sha256": evidence["source_code"]["calendar_engine"]["sha256_at_capture"],
        "session_calendar_v2_prefix_evidence_sha256": file_sha256(evidence_manifest),
        "candidate_calendar_v2_adapter_sha256": file_sha256(root / ADAPTER_RELATIVE),
    }
    paths = {
        "session_calendar_manifest_sha256": evidence["calendar_manifest"]["canonical_path"],
        "session_calendar_projection_sha256": projection.resolve().as_posix(),
        "session_calendar_ledger_sha256": prefix["canonical_path"],
        "session_calendar_verifier_sha256": evidence["source_code"]["calendar_script"]["path"],
        "session_calendar_engine_sha256": evidence["source_code"]["calendar_engine"]["path"],
        "session_calendar_v2_prefix_evidence_sha256": evidence_manifest.resolve().as_posix(),
        "candidate_calendar_v2_adapter_sha256": (root / ADAPTER_RELATIVE).resolve().as_posix(),
    }
    return versions, paths


def verify_candidate_calendar_evidence_v2(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> pd.DataFrame:
    """Verify the frozen prefix against the still-append-only canonical ledger."""

    root = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "cannot read candidate calendar-v2 prefix evidence"
        ) from exc
    decision_date = str(payload.get("decision_date") or "")
    if (
        path != candidate_calendar_evidence_path(decision_date, repository_root=root)
        or set(payload) != MANIFEST_FIELDS
        or payload.get("schema_version") != 1
        or payload.get("manifest_type") != MANIFEST_TYPE
        or payload.get("status")
        != "IMMUTABLE_VERIFIED_CALENDAR_V2_PREFIX_RESEARCH_ONLY"
        or payload.get("manifest_sha256") != _canonical_sha256(payload)
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate calendar-v2 evidence identity changed"
        )
    calendar_item = _exact_mapping(
        payload.get("calendar_manifest"), CALENDAR_MANIFEST_FIELDS,
        "candidate calendar-v2 calendar manifest",
    )
    prefix = _exact_mapping(
        payload.get("event_ledger_prefix"), EVENT_PREFIX_FIELDS,
        "candidate calendar-v2 event prefix",
    )
    projection = _exact_mapping(
        payload.get("session_projection_prefix"), SESSION_PREFIX_FIELDS,
        "candidate calendar-v2 session prefix",
    )
    source_code = _exact_mapping(
        payload.get("source_code"), SOURCE_CODE_FIELDS,
        "candidate calendar-v2 source code",
    )
    expected_code_paths = {
        "calendar_engine": (root / ENGINE_RELATIVE).resolve(),
        "calendar_script": (root / CALENDAR_SCRIPT_RELATIVE).resolve(),
        "candidate_calendar_adapter": (root / ADAPTER_RELATIVE).resolve(),
    }
    for key, expected_path in expected_code_paths.items():
        item = _exact_mapping(
            source_code.get(key), SOURCE_CODE_ITEM_FIELDS,
            f"candidate calendar-v2 source code {key}",
        )
        if (
            Path(str(item.get("path") or "")).resolve() != expected_path
            or not _is_sha256(item.get("sha256_at_capture"))
            or not expected_path.is_file()
            or file_sha256(expected_path) != item.get("sha256_at_capture")
        ):
            raise NdxDynamicShadowCandidateCalendarV2Error(
                f"candidate calendar-v2 source code binding changed: {key}"
            )
    boundary = payload.get("evidence_boundary") or {}
    if boundary != {
        "legacy_hash_only_session_used_for_decision": False,
        "source_revision_event_used_for_decision": False,
        "later_calendar_append_allowed": True,
        "retrospective_backfill_allowed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate calendar-v2 evidence boundary changed"
        )
    calendar_path = (root / CALENDAR_RELATIVE).resolve()
    event_path = (root / EVENT_LEDGER_RELATIVE).resolve()
    if (
        Path(str(calendar_item.get("canonical_path") or "")).resolve() != calendar_path
        or not _is_sha256(calendar_item.get("sha256_at_capture"))
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error("calendar-v2 manifest path changed")
    frozen_manifest_path = path.parent / str(calendar_item.get("frozen_filename") or "")
    transaction_id = str(calendar_item.get("committed_transaction_id") or "")
    receipt_path = (
        calendar_path.parent / "committed_transactions" / f"{transaction_id}.json"
    ).resolve()
    frozen_receipt_path = path.parent / str(
        calendar_item.get("committed_receipt_filename") or ""
    )
    if (
        frozen_manifest_path.parent != path.parent
        or frozen_manifest_path.name != "calendar_manifest_at_capture.json"
        or not frozen_manifest_path.is_file()
        or hashlib.sha256(frozen_manifest_path.read_bytes()).hexdigest()
        != calendar_item.get("sha256_at_capture")
        or not _is_sha256(transaction_id)
        or Path(str(calendar_item.get("committed_receipt_canonical_path") or "")).resolve()
        != receipt_path
        or frozen_receipt_path.parent != path.parent
        or frozen_receipt_path.name != "committed_transaction_receipt.json"
        or not frozen_receipt_path.is_file()
        or hashlib.sha256(frozen_receipt_path.read_bytes()).hexdigest()
        != calendar_item.get("committed_receipt_sha256")
        or not receipt_path.is_file()
        or receipt_path.read_bytes() != frozen_receipt_path.read_bytes()
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 frozen committed transaction binding changed"
        )
    try:
        frozen_manifest = json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
        receipt = json.loads(frozen_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 frozen committed evidence is unreadable"
        ) from exc
    from backtest.ndx_observed_session_calendar_v2 import (
        _event_ledger_bytes,
        _validate_transaction_receipt,
    )
    try:
        _validate_transaction_receipt(receipt, expected_manifest=frozen_manifest)
    except Exception as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 historical committed receipt is invalid"
        ) from exc
    if (
        frozen_manifest.get("commit_transaction_id") != transaction_id
        or receipt.get("transaction_id") != transaction_id
        or receipt.get("planned_manifest") != frozen_manifest
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 frozen receipt does not bind the captured manifest"
        )
    if Path(str(prefix.get("canonical_path") or "")).resolve() != event_path:
        raise NdxDynamicShadowCandidateCalendarV2Error("calendar-v2 event-ledger path changed")
    if not all(_is_sha256(prefix.get(key)) for key in (
        "prefix_bytes_sha256", "terminal_event_sha256",
    )):
        raise NdxDynamicShadowCandidateCalendarV2Error("calendar-v2 event-prefix hash is invalid")
    try:
        current_event_bytes = event_path.read_bytes()
    except OSError as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error("calendar-v2 event ledger is missing") from exc
    lines = current_event_bytes.splitlines(keepends=True)
    count = int(prefix.get("prefix_rows", -1))
    if count <= 0 or len(lines) < count:
        raise NdxDynamicShadowCandidateCalendarV2Error("calendar-v2 event prefix is incomplete")
    prefix_bytes = b"".join(lines[:count])
    rows, terminal, digest = _event_prefix(prefix_bytes)
    if (
        rows != count or terminal != prefix.get("terminal_event_sha256")
        or digest != prefix.get("prefix_bytes_sha256")
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error("calendar-v2 event prefix changed")
    frozen_ledger_item = ((frozen_manifest.get("artifacts") or {}).get("event_ledger") or {})
    if (
        int(frozen_ledger_item.get("rows", -1)) != count
        or frozen_ledger_item.get("sha256") != digest
        or frozen_ledger_item.get("latest_event_sha256") != terminal
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 frozen manifest does not bind the event prefix"
        )
    try:
        old_size = int(receipt["old_ledger_size"])
        old_prefix = prefix_bytes[:old_size]
        old_events = [
            json.loads(line.decode("utf-8"))
            for line in old_prefix.splitlines(keepends=True)
        ]
    except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 historical transaction prefix is invalid"
        ) from exc
    if (
        old_size < 0
        or len(prefix_bytes) < old_size
        or hashlib.sha256(old_prefix).hexdigest() != receipt["old_ledger_sha256"]
        or len(old_events) != int(receipt["old_event_count"])
        or (old_events[-1].get("event_sha256") if old_events else None)
        != receipt["old_event_head_sha256"]
        or old_prefix + _event_ledger_bytes(receipt["additions"]) != prefix_bytes
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "calendar-v2 historical committed transaction does not reconstruct the event prefix"
        )
    _public_calendar_verifier(calendar_path, root)
    current_sessions = _public_decision_sessions(calendar_path, root)
    expected_sessions = _strict_decision_sessions(
        current_sessions, decision_date, allow_later_sessions=True,
    )
    projection_path = path.parent / str(projection.get("filename") or "")
    if (
        projection_path.parent != path.parent
        or projection_path.name != "decision_sessions_prefix.csv"
        or not projection_path.is_file()
        or not _is_sha256(projection.get("sha256"))
        or file_sha256(projection_path) != projection.get("sha256")
    ):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate calendar-v2 session prefix artifact changed"
        )
    frozen_sessions = _strict_decision_sessions(
        pd.read_csv(projection_path, low_memory=False), decision_date,
        allow_later_sessions=True,
    )
    if len(frozen_sessions) != int(projection.get("rows", -1)):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate calendar-v2 session prefix row count changed"
        )
    columns = DECISION_SESSION_FIELDS
    if frozen_sessions[columns].to_dict("records") != expected_sessions[columns].to_dict("records"):
        raise NdxDynamicShadowCandidateCalendarV2Error(
            "candidate calendar-v2 frozen sessions differ from the canonical prefix"
        )
    return frozen_sessions


__all__ = [
    "NdxDynamicShadowCandidateCalendarV2Error",
    "candidate_calendar_evidence_path",
    "capture_candidate_calendar_evidence_v2",
    "verify_candidate_calendar_evidence_v2",
]
