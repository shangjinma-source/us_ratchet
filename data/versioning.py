"""Version manifests for research datasets.

The cache CSV remains the source of truth.  Its adjacent manifest records a
content hash and the evidence we actually have for source/fetch time.  Legacy
caches are backfilled from file metadata and are never presented as if their
original publication time were known.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from core.helpers import atomic_write_text


MANIFEST_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_from_file_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(
        microsecond=0
    ).isoformat()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(cache_path: str | Path) -> Path:
    path = Path(cache_path)
    return path.with_suffix(path.suffix + ".manifest.json")


def _build_manifest(
    cache_path: Path,
    *,
    dataset_type: str,
    dataset_key: str,
    source: str,
    source_locator: str | None,
    fetched_at: str,
    fetched_at_evidence: str,
    row_count: int,
    data_start: str | None,
    data_end: str | None,
    extra: dict | None,
) -> dict:
    content_hash = file_sha256(cache_path)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_type": str(dataset_type),
        "dataset_key": str(dataset_key),
        "version_id": f"{dataset_type}:{dataset_key}:{content_hash[:16]}",
        "content_sha256": content_hash,
        "content_bytes": int(cache_path.stat().st_size),
        "cache_path": cache_path.as_posix(),
        "manifest_path": manifest_path(cache_path).as_posix(),
        "source": str(source),
        "source_locator": source_locator,
        "fetched_at": str(fetched_at),
        "fetched_at_evidence": str(fetched_at_evidence),
        "row_count": int(row_count),
        "data_start": data_start,
        "data_end": data_end,
        "generated_at": utc_now_iso(),
    }
    if extra:
        overlap = set(payload).intersection(extra)
        if overlap:
            raise ValueError(f"manifest extra fields override reserved keys: {sorted(overlap)}")
        payload.update(extra)
    return payload


def write_dataset_manifest(
    cache_path: str | Path,
    *,
    dataset_type: str,
    dataset_key: str,
    source: str,
    source_locator: str | None = None,
    fetched_at: str | None = None,
    fetched_at_evidence: str = "runtime_fetch_utc",
    row_count: int = 0,
    data_start: str | None = None,
    data_end: str | None = None,
    extra: dict | None = None,
) -> dict:
    path = Path(cache_path)
    if not path.exists():
        raise FileNotFoundError(path)
    payload = _build_manifest(
        path,
        dataset_type=dataset_type,
        dataset_key=dataset_key,
        source=source,
        source_locator=source_locator,
        fetched_at=fetched_at or utc_now_iso(),
        fetched_at_evidence=fetched_at_evidence,
        row_count=row_count,
        data_start=data_start,
        data_end=data_end,
        extra=extra,
    )
    atomic_write_text(
        manifest_path(path),
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return payload


def ensure_dataset_manifest(
    cache_path: str | Path,
    *,
    dataset_type: str,
    dataset_key: str,
    row_count: int,
    data_start: str | None = None,
    data_end: str | None = None,
    legacy_source: str = "legacy_cache_unknown",
    extra: dict | None = None,
) -> dict:
    """Load a valid manifest or honestly backfill one for a legacy CSV."""
    path = Path(cache_path)
    target = manifest_path(path)
    rebuild_reason = "manifest_missing"
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            schema_matches = (
                int(payload.get("schema_version") or 0) == MANIFEST_SCHEMA_VERSION
            )
            identity_matches = (
                payload.get("dataset_type") == str(dataset_type)
                and payload.get("dataset_key") == str(dataset_key)
            )
            hash_matches = payload.get("content_sha256") == file_sha256(path)
            if schema_matches and identity_matches and hash_matches:
                return payload
            rebuild_reason = (
                "manifest_identity_mismatch"
                if schema_matches and not identity_matches
                else "manifest_hash_mismatch"
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            rebuild_reason = "manifest_invalid"

    legacy_extra = dict(extra or {})
    legacy_extra.update({
        "legacy_backfill": True,
        "manifest_rebuild_reason": rebuild_reason,
        "source_confidence": "cache_file_only",
        "publication_time_known": False,
    })
    return write_dataset_manifest(
        path,
        dataset_type=dataset_type,
        dataset_key=dataset_key,
        source=legacy_source,
        source_locator=None,
        fetched_at=_utc_from_file_mtime(path),
        fetched_at_evidence="legacy_file_mtime",
        row_count=row_count,
        data_start=data_start,
        data_end=data_end,
        extra=legacy_extra,
    )


def data_version_payload(meta, **used_fields) -> dict:
    manifest = dict(getattr(meta, "manifest", {}) or {})
    out = {
        "version_id": manifest.get("version_id"),
        "dataset_type": manifest.get("dataset_type"),
        "dataset_key": manifest.get("dataset_key"),
        "content_sha256": manifest.get("content_sha256"),
        "content_bytes": manifest.get("content_bytes"),
        "source": manifest.get("source"),
        "source_locator": manifest.get("source_locator"),
        "retrieval_source": getattr(meta, "source", None),
        "cached": bool(getattr(meta, "cached", False)),
        "fetched_at": manifest.get("fetched_at"),
        "fetched_at_evidence": manifest.get("fetched_at_evidence"),
        "manifest_path": manifest.get("manifest_path"),
        "cache_path": manifest.get("cache_path"),
        "row_count": manifest.get("row_count"),
        "data_start": manifest.get("data_start"),
        "data_end": manifest.get("data_end"),
        "legacy_backfill": bool(manifest.get("legacy_backfill", False)),
        "manifest_rebuild_reason": manifest.get("manifest_rebuild_reason"),
        "source_confidence": manifest.get("source_confidence"),
        "completeness": manifest.get("completeness"),
        "source_record_count": manifest.get("source_record_count"),
        "source_page_count": manifest.get("source_page_count"),
        "requested_years": manifest.get("requested_years"),
        "confirmed_empty_years": manifest.get("confirmed_empty_years"),
        "industry_standard": manifest.get("industry_standard"),
        "observation_frequency": manifest.get("observation_frequency"),
        "publication_time_known": manifest.get("publication_time_known"),
        "report_count": manifest.get("report_count"),
        "report_dates": manifest.get("report_dates"),
    }
    out.update({key: value for key, value in used_fields.items() if value is not None})
    return out


def modeled_availability_manifest(
    report_dates: Iterable[str], availability_delay_days: int
) -> dict:
    delay = int(availability_delay_days)
    if delay < 0:
        raise ValueError("availability_delay_days must be >= 0")
    rows = []
    for raw in sorted({str(value)[:10] for value in report_dates if str(value).strip()}):
        report_day = date.fromisoformat(raw)
        rows.append({
            "report_date": report_day.isoformat(),
            "available_date": (report_day + timedelta(days=delay)).isoformat(),
        })
    return {
        "mode": "report_date_plus_calendar_delay",
        "availability_delay_days": delay,
        "availability_date_kind": "modeled_not_source_publication_date",
        "source_publication_dates_available": False,
        "future_data_guard": "available_date <= rebalance_date",
        "zero_delay_upper_bound_only": delay == 0,
        "report_count": len(rows),
        "first_available_date": rows[0]["available_date"] if rows else None,
        "last_available_date": rows[-1]["available_date"] if rows else None,
        "reports": rows,
    }
