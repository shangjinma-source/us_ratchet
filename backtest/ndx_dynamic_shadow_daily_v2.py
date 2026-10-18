"""Reviewed-calendar v2 evidence adapter for the research-only daily engine.

The mathematical path and benchmark engines remain in ``ndx_dynamic_shadow_daily``.
This module only replaces calendar evidence handling.  Calendar coordinates are
rebuilt from the sealed v2 event ledger; mutable vendor CSV files are never read.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from backtest import ndx_dynamic_shadow_daily as v1
from backtest.ndx_observed_session_calendar_v2 import (
    VerifiedReviewedCalendarV2,
    verify_canonical_reviewed_calendar_v2,
)
from data.versioning import file_sha256


class NdxDynamicShadowDailyV2Error(v1.NdxDynamicShadowDailyError):
    """Raised when reviewed-calendar evidence is incomplete or mutable."""


CALENDAR_RELATIVE = Path("data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json")
ALIGNMENT_TYPE = "ndx_dynamic_shadow_three_way_calendar_alignment_v2"
ALIGNMENT_STATUS = "EXACT_SELECTOR_ORIGINAL8_TARGET_REVIEWED_CALENDAR_V2_RESEARCH_ONLY"
CALENDAR_COLUMNS = [
    "session_date", "open_timestamp_utc", "close_timestamp_utc",
    "session_event_sha256",
]
ALIGNMENT_KEYS = {
    "schema_version", "manifest_type", "status", "valuation_end_date",
    "calendar_start_date", "calendar_end_date", "calendar_session_count",
    "calendar_dates_sha256", "selector_lane_count", "benchmark_control_count",
    "target_available_rows", "target_pending_rows",
    "target_first_observed_trace_complete",
    "target_resolved_outcome_benchmark_ready", "target_trace_evidence_role",
    "selector_lane_prefixes", "original_8_control_prefix", "target_012922_prefix",
    "observed_calendar_source", "calendar_artifact", "three_way_calendar_exact",
    "promotion_allowed", "live_mutation", "manifest_sha256",
}
CALENDAR_SOURCE_KEYS = {
    "canonical_path", "sha256_at_alignment", "manifest_snapshot_filename",
    "manifest_snapshot_sha256", "event_ledger_canonical_path",
    "event_prefix_rows", "event_prefix_bytes_sha256", "terminal_event_sha256",
    "event_prefix_snapshot_filename", "event_prefix_snapshot_sha256",
    "append_only_prefix_required", "current_vendor_data_used",
}


def _repository_root_from_calendar(path: Path) -> Path:
    resolved = path.resolve()
    parts = CALENDAR_RELATIVE.parts
    if len(resolved.parts) < len(parts) or tuple(resolved.parts[-len(parts):]) != parts:
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 path is not canonical")
    return resolved.parents[len(parts) - 1]


def _verified_calendar(
    path: str | Path, *, repository_root: str | Path | None,
) -> VerifiedReviewedCalendarV2:
    manifest_path = Path(path).resolve()
    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else _repository_root_from_calendar(manifest_path)
    )
    expected = (root / CALENDAR_RELATIVE).resolve()
    if manifest_path != expected:
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 path is not canonical")
    try:
        return verify_canonical_reviewed_calendar_v2(
            manifest_path, repository_root=root,
        )
    except Exception as exc:
        if isinstance(exc, NdxDynamicShadowDailyV2Error):
            raise
        raise NdxDynamicShadowDailyV2Error(
            f"reviewed calendar v2 verification failed: {exc}"
        ) from exc


def load_reviewed_calendar_projection(
    observed_calendar_manifest_path: str | Path, *,
    repository_root: str | Path | None = None,
) -> tuple[dict[str, Any], VerifiedReviewedCalendarV2, pd.DataFrame]:
    """Return a projection rebuilt exclusively from sealed v2 calendar events."""

    verified = _verified_calendar(
        observed_calendar_manifest_path, repository_root=repository_root,
    )
    projection = pd.DataFrame(list(verified.session_projection))
    if projection.empty:
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 projection is empty")
    projection["completed"] = True
    projection = v1.normalize_observed_sessions(projection)
    projection["source_price_replay_available"] = [
        bool(row["source_price_replay_available"])
        for row in verified.session_projection
    ]
    projection["session_event_sha256"] = [
        str(row["session_event_sha256"]) for row in verified.session_projection
    ]
    return dict(verified.manifest), verified, projection


def _selector_ids() -> set[str]:
    return {
        f"{track}__{role.lower()}__v1"
        for track in v1.TRACKS for role in v1.ROLES
    }


def _prefix_descriptor(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise NdxDynamicShadowDailyV2Error("calendar alignment cannot bind an empty ledger")
    return {
        "path": path.resolve().as_posix(),
        "prefix_rows": len(records),
        "terminal_record_sha256": records[-1]["record_sha256"],
    }


def _atomic_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise NdxDynamicShadowDailyV2Error(f"immutable artifact collision: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _event_prefix_bytes(path: Path, rows: int) -> bytes:
    if rows <= 0:
        raise NdxDynamicShadowDailyV2Error("reviewed calendar event prefix is empty")
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    if len(lines) < rows or any(not line.strip() for line in lines[:rows]):
        raise NdxDynamicShadowDailyV2Error("reviewed calendar event prefix is incomplete")
    return b"".join(lines[:rows])


def _supplied_sessions_match_sealed(
    supplied: pd.DataFrame, sealed: pd.DataFrame,
) -> None:
    given = v1.normalize_observed_sessions(supplied)
    columns = ["session_date", "open_timestamp_utc", "close_timestamp_utc"]
    if given[columns].reset_index(drop=True).to_dict("records") != sealed[
        columns
    ].reset_index(drop=True).to_dict("records"):
        raise NdxDynamicShadowDailyV2Error(
            "caller observed sessions differ from sealed reviewed-calendar projection"
        )


def write_three_way_calendar_manifest(
    output_dir: str | Path, *, selector_lane_ledgers: Mapping[str, str | Path],
    original_8_ledger: str | Path, target_012922_ledger: str | Path,
    observed_sessions: pd.DataFrame, observed_calendar_manifest_path: str | Path,
) -> dict[str, Any]:
    """Freeze exact 10-lane/original-8/012922 alignment against v2 events."""

    expected_selectors = _selector_ids()
    if set(selector_lane_ledgers) != expected_selectors:
        raise NdxDynamicShadowDailyV2Error(
            "calendar alignment requires the exact 10 selector lanes"
        )
    calendar_path = Path(observed_calendar_manifest_path).resolve()
    repository_root = _repository_root_from_calendar(calendar_path)
    calendar_manifest, verified, sealed = load_reviewed_calendar_projection(
        calendar_path, repository_root=repository_root,
    )
    _supplied_sessions_match_sealed(observed_sessions, sealed)

    lane_records = {
        selector_id: v1.load_lane_path_ledger(path, selector_id)
        for selector_id, path in selector_lane_ledgers.items()
    }
    original_path = Path(original_8_ledger)
    original_records = v1.load_lane_path_ledger(
        original_path, "ndx_original_8_incumbent_v0",
    )
    target_path = Path(target_012922_ledger)
    target_records = v1.load_target_012922_trace_ledger(target_path)
    calendars = [
        [str(record["date"]) for record in records]
        for records in lane_records.values()
    ]
    calendars.extend((
        [str(record["date"]) for record in original_records],
        [str(record["session_date"]) for record in target_records],
    ))
    if not calendars or any(values != calendars[0] for values in calendars[1:]):
        raise NdxDynamicShadowDailyV2Error(
            "selector/original8/012922 calendars are not identical"
        )
    dates = calendars[0]
    if not dates:
        raise NdxDynamicShadowDailyV2Error("three-way aligned calendar is empty")

    selected = sealed.loc[
        sealed["session_date"].dt.date.astype(str).isin(dates),
        ["session_date", "open_timestamp_utc", "close_timestamp_utc", "session_event_sha256"],
    ].copy()
    selected["session_date"] = selected["session_date"].dt.date.astype(str)
    selected["open_timestamp_utc"] = selected["open_timestamp_utc"].map(pd.Timestamp.isoformat)
    selected["close_timestamp_utc"] = selected["close_timestamp_utc"].map(pd.Timestamp.isoformat)
    if selected["session_date"].tolist() != dates:
        raise NdxDynamicShadowDailyV2Error(
            "aligned paths are not the sealed reviewed-calendar sessions"
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    calendar_artifact = output / "calendar_sessions.csv"
    _atomic_immutable(
        calendar_artifact,
        selected.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    manifest_snapshot = output / "observed_calendar_manifest_snapshot.json"
    manifest_bytes = calendar_path.read_bytes()
    _atomic_immutable(manifest_snapshot, manifest_bytes)

    ledger_path = Path(calendar_manifest["artifacts"]["event_ledger"]["path"]).resolve()
    event_count = len(verified.events)
    prefix_bytes = _event_prefix_bytes(ledger_path, event_count)
    event_snapshot = output / "observed_calendar_event_prefix.jsonl"
    _atomic_immutable(event_snapshot, prefix_bytes)
    manifest = {
        "schema_version": 2,
        "manifest_type": ALIGNMENT_TYPE,
        "status": ALIGNMENT_STATUS,
        "valuation_end_date": dates[-1],
        "calendar_start_date": dates[0],
        "calendar_end_date": dates[-1],
        "calendar_session_count": len(dates),
        "calendar_dates_sha256": v1.canonical_sha256(dates),
        "selector_lane_count": 10,
        "benchmark_control_count": 2,
        "target_available_rows": sum(
            record["status"] == "AVAILABLE_STALE_ASOF" for record in target_records
        ),
        "target_pending_rows": sum(
            record["status"] == "TARGET_ASOF_UNAVAILABLE_PENDING" for record in target_records
        ),
        "target_first_observed_trace_complete": len(target_records) == len(dates),
        "target_resolved_outcome_benchmark_ready": False,
        "target_trace_evidence_role": (
            "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME"
        ),
        "selector_lane_prefixes": {
            selector_id: _prefix_descriptor(
                Path(selector_lane_ledgers[selector_id]), lane_records[selector_id],
            )
            for selector_id in sorted(expected_selectors)
        },
        "original_8_control_prefix": _prefix_descriptor(original_path, original_records),
        "target_012922_prefix": _prefix_descriptor(target_path, target_records),
        "observed_calendar_source": {
            "canonical_path": calendar_path.as_posix(),
            "sha256_at_alignment": file_sha256(calendar_path),
            "manifest_snapshot_filename": manifest_snapshot.name,
            "manifest_snapshot_sha256": file_sha256(manifest_snapshot),
            "event_ledger_canonical_path": ledger_path.as_posix(),
            "event_prefix_rows": event_count,
            "event_prefix_bytes_sha256": hashlib.sha256(prefix_bytes).hexdigest(),
            "terminal_event_sha256": verified.events[-1]["event_sha256"],
            "event_prefix_snapshot_filename": event_snapshot.name,
            "event_prefix_snapshot_sha256": file_sha256(event_snapshot),
            "append_only_prefix_required": True,
            "current_vendor_data_used": False,
        },
        "calendar_artifact": {
            "filename": calendar_artifact.name,
            "rows": len(selected),
            "sha256": file_sha256(calendar_artifact),
        },
        "three_way_calendar_exact": True,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    manifest["manifest_sha256"] = v1.canonical_sha256(manifest)
    manifest_path = output / "manifest.json"
    _atomic_immutable(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    verify_three_way_calendar_manifest(manifest_path)
    return manifest


def verify_three_way_calendar_manifest(
    path: str | Path, *, require_current_calendar_manifest_hash: bool = False,
) -> dict[str, Any]:
    """Rebuild a v2 alignment and allow only append-only calendar extension."""

    del require_current_calendar_manifest_hash
    manifest_path = Path(path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowDailyV2Error(
            "three-way v2 alignment manifest is missing/invalid"
        ) from exc
    unsigned = dict(manifest)
    declared = str(unsigned.pop("manifest_sha256", ""))
    if (
        set(manifest) != ALIGNMENT_KEYS
        or v1.canonical_sha256(unsigned) != declared
        or manifest.get("schema_version") != 2
        or manifest.get("manifest_type") != ALIGNMENT_TYPE
        or manifest.get("status") != ALIGNMENT_STATUS
        or manifest.get("selector_lane_count") != 10
        or manifest.get("benchmark_control_count") != 2
        or manifest.get("target_first_observed_trace_complete") is not True
        or manifest.get("target_resolved_outcome_benchmark_ready") is not False
        or manifest.get("target_trace_evidence_role")
        != "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME"
        or manifest.get("three_way_calendar_exact") is not True
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_mutation") is not False
    ):
        raise NdxDynamicShadowDailyV2Error("three-way v2 alignment boundary changed")

    artifact = manifest.get("calendar_artifact") or {}
    calendar_path = manifest_path.parent / str(artifact.get("filename") or "")
    if (
        set(artifact) != {"filename", "rows", "sha256"}
        or calendar_path.parent != manifest_path.parent
        or not calendar_path.is_file()
        or file_sha256(calendar_path) != artifact.get("sha256")
    ):
        raise NdxDynamicShadowDailyV2Error("three-way v2 calendar artifact changed")
    calendar = pd.read_csv(calendar_path, dtype={"session_date": str})
    if list(calendar.columns) != CALENDAR_COLUMNS:
        raise NdxDynamicShadowDailyV2Error("three-way v2 calendar columns changed")
    dates = calendar["session_date"].tolist()
    if (
        len(calendar) != int(artifact.get("rows", -1))
        or len(dates) != int(manifest.get("calendar_session_count", -1))
        or not dates or dates != sorted(dates) or len(dates) != len(set(dates))
        or v1.canonical_sha256(dates) != manifest.get("calendar_dates_sha256")
        or dates[0] != manifest.get("calendar_start_date")
        or dates[-1] != manifest.get("calendar_end_date")
        or dates[-1] != manifest.get("valuation_end_date")
        or any(len(str(value)) != 64 for value in calendar["session_event_sha256"])
    ):
        raise NdxDynamicShadowDailyV2Error("three-way v2 calendar metadata changed")

    alignment_root = manifest_path.parent.parent
    daily_root = alignment_root.parent
    if (
        alignment_root.name != "three_way_calendar_alignment"
        or manifest_path.parent.name != manifest["valuation_end_date"]
    ):
        raise NdxDynamicShadowDailyV2Error("three-way v2 alignment path is not canonical")
    lane_root = (daily_root / "lane_paths").resolve()
    control_root = (daily_root / "benchmark_controls").resolve()

    def verify_prefix(
        descriptor: Mapping[str, Any], selector_id: str, *, target: bool = False,
    ) -> list[str]:
        if set(descriptor) != {"path", "prefix_rows", "terminal_record_sha256"}:
            raise NdxDynamicShadowDailyV2Error("three-way v2 prefix schema changed")
        source = Path(str(descriptor["path"])).resolve()
        expected = (
            control_root / (
                "target_012922_asof.jsonl" if target else "original_8_incumbent_v0.jsonl"
            )
            if target or selector_id == "ndx_original_8_incumbent_v0"
            else lane_root / f"{selector_id}.jsonl"
        )
        if source != expected:
            raise NdxDynamicShadowDailyV2Error("three-way v2 ledger path is not canonical")
        records = (
            v1.load_target_012922_trace_ledger(source)
            if target else v1.load_lane_path_ledger(source, selector_id)
        )
        count = int(descriptor["prefix_rows"])
        if count <= 0 or len(records) < count:
            raise NdxDynamicShadowDailyV2Error("three-way v2 ledger prefix is incomplete")
        prefix = records[:count]
        if prefix[-1]["record_sha256"] != descriptor["terminal_record_sha256"]:
            raise NdxDynamicShadowDailyV2Error("three-way v2 ledger prefix terminal changed")
        return [str(record["session_date"] if target else record["date"]) for record in prefix]

    descriptors = manifest.get("selector_lane_prefixes") or {}
    if set(descriptors) != _selector_ids():
        raise NdxDynamicShadowDailyV2Error("three-way v2 selector registry changed")
    for selector_id, descriptor in descriptors.items():
        if verify_prefix(descriptor, selector_id) != dates:
            raise NdxDynamicShadowDailyV2Error("selector lane calendar differs from v2 alignment")
    if verify_prefix(
        manifest["original_8_control_prefix"], "ndx_original_8_incumbent_v0",
    ) != dates:
        raise NdxDynamicShadowDailyV2Error("original-8 calendar differs from v2 alignment")
    if verify_prefix(
        manifest["target_012922_prefix"],
        "target_012922_dynamic_external_target", target=True,
    ) != dates:
        raise NdxDynamicShadowDailyV2Error("012922 calendar differs from v2 alignment")

    source = manifest.get("observed_calendar_source") or {}
    if set(source) != CALENDAR_SOURCE_KEYS:
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 source schema changed")
    repository_root = daily_root.parents[3]
    canonical_manifest = (repository_root / CALENDAR_RELATIVE).resolve()
    canonical_ledger = canonical_manifest.parent / "events.jsonl"
    manifest_snapshot = manifest_path.parent / str(source["manifest_snapshot_filename"])
    event_snapshot = manifest_path.parent / str(source["event_prefix_snapshot_filename"])
    if (
        Path(str(source["canonical_path"])).resolve() != canonical_manifest
        or Path(str(source["event_ledger_canonical_path"])).resolve() != canonical_ledger.resolve()
        or manifest_snapshot.parent != manifest_path.parent
        or event_snapshot.parent != manifest_path.parent
        or not manifest_snapshot.is_file() or not event_snapshot.is_file()
        or file_sha256(manifest_snapshot) != source["manifest_snapshot_sha256"]
        or source["manifest_snapshot_sha256"] != source["sha256_at_alignment"]
        or file_sha256(event_snapshot) != source["event_prefix_snapshot_sha256"]
        or source["event_prefix_snapshot_sha256"] != source["event_prefix_bytes_sha256"]
        or source["append_only_prefix_required"] is not True
        or source["current_vendor_data_used"] is not False
    ):
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 frozen source changed")
    row_count = int(source["event_prefix_rows"])
    frozen_prefix = event_snapshot.read_bytes()
    current_prefix = _event_prefix_bytes(canonical_ledger, row_count)
    if (
        current_prefix != frozen_prefix
        or hashlib.sha256(current_prefix).hexdigest() != source["event_prefix_bytes_sha256"]
    ):
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 event prefix was rewritten")
    current_manifest, verified, projection = load_reviewed_calendar_projection(
        canonical_manifest, repository_root=repository_root,
    )
    del current_manifest
    if row_count > len(verified.events) or verified.events[row_count - 1]["event_sha256"] != source[
        "terminal_event_sha256"
    ]:
        raise NdxDynamicShadowDailyV2Error("reviewed calendar v2 event prefix head changed")
    expected = projection.loc[
        projection["session_date"].dt.date.astype(str).isin(dates),
        ["session_date", "open_timestamp_utc", "close_timestamp_utc", "session_event_sha256"],
    ].copy()
    expected["session_date"] = expected["session_date"].dt.date.astype(str)
    expected["open_timestamp_utc"] = expected["open_timestamp_utc"].map(pd.Timestamp.isoformat)
    expected["close_timestamp_utc"] = expected["close_timestamp_utc"].map(pd.Timestamp.isoformat)
    if expected.reset_index(drop=True).to_dict("records") != calendar.to_dict("records"):
        raise NdxDynamicShadowDailyV2Error(
            "three-way dates/open/close differ from sealed reviewed-calendar prefix"
        )
    if int(manifest["target_available_rows"]) + int(manifest["target_pending_rows"]) != len(dates):
        raise NdxDynamicShadowDailyV2Error("012922 availability counts changed")
    return manifest


def verify_daily_run_manifest(
    path: str | Path, *, repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the existing run schema with v2 runtime and calendar provenance."""

    manifest_path = Path(path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowDailyV2Error("daily run manifest is missing/invalid") from exc
    unsigned = dict(manifest)
    declared = str(unsigned.pop("run_manifest_sha256", ""))
    if (
        set(manifest) != v1.DAILY_RUN_MANIFEST_KEYS
        or v1.canonical_sha256(unsigned) != declared
        or manifest.get("manifest_type") != "ndx_dynamic_shadow_daily_run"
        or manifest.get("status") not in {
            "RESEARCH_DAILY_COMPLETE", "RESEARCH_DAILY_COMPLETE_TARGET_TRACE_PENDING",
        }
        or int(manifest.get("independent_lane_count", -1)) not in {0, 10}
        or int(manifest.get("benchmark_control_count", -1))
        != (2 if int(manifest.get("independent_lane_count", -1)) == 10 else 0)
        or manifest.get("single_instance_lock_used") is not True
        or manifest.get("historical_candidate_replay_used") is not False
        or manifest.get("retrospective_decision_backfill_used") is not False
        or manifest.get("automation_registered") is not False
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_mutation") is not False
    ):
        raise NdxDynamicShadowDailyV2Error("daily v2 run manifest boundary changed")
    root = Path(repository_root).resolve() if repository_root is not None else None
    if root is not None:
        expected = root / "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json"
        if manifest_path != expected.resolve():
            raise NdxDynamicShadowDailyV2Error("daily v2 run manifest path is not canonical")
    artifacts = manifest.get("research_artifacts") or {}
    expected_keys = {
        "daily_contract", "daily_engine", "daily_script", "observed_calendar_manifest",
        "realized_batch_manifests", "selector_lane_ledgers",
        "original_8_control_ledger", "target_012922_trace_ledger",
        "three_way_alignment_manifest", "nominal_price_evidence_manifest",
    }
    if set(artifacts) != expected_keys:
        raise NdxDynamicShadowDailyV2Error("daily v2 artifact registry changed")

    def verify_item(value: Mapping[str, Any] | None) -> Path | None:
        if value is None:
            return None
        if set(value) not in ({"path", "sha256"}, {"path", "sha256", "rows"}):
            raise NdxDynamicShadowDailyV2Error("daily v2 artifact descriptor changed")
        source = Path(str(value.get("path") or "")).resolve()
        if not source.is_file() or file_sha256(source) != value.get("sha256"):
            raise NdxDynamicShadowDailyV2Error("daily v2 artifact path/hash changed")
        return source

    contract_path = verify_item(artifacts.get("daily_contract"))
    engine_path = verify_item(artifacts.get("daily_engine"))
    script_path = verify_item(artifacts.get("daily_script"))
    calendar_manifest_path = verify_item(artifacts.get("observed_calendar_manifest"))
    if any(path is None for path in (
        contract_path, engine_path, script_path, calendar_manifest_path,
    )):
        raise NdxDynamicShadowDailyV2Error("daily v2 core provenance is incomplete")
    if root is not None and (
        contract_path != (root / "config/ndx_dynamic_shadow_daily_v1.yaml").resolve()
        or engine_path != (root / "backtest/ndx_dynamic_shadow_daily_v2.py").resolve()
        or script_path != (root / "scripts/ndx_dynamic_shadow_daily_v3.py").resolve()
        or calendar_manifest_path != (root / CALENDAR_RELATIVE).resolve()
    ):
        raise NdxDynamicShadowDailyV2Error("daily v2 runtime provenance changed")
    v1.load_daily_contract(contract_path)
    if manifest.get("calendar_manifest_sha256") != artifacts[
        "observed_calendar_manifest"
    ]["sha256"]:
        raise NdxDynamicShadowDailyV2Error("daily v2 calendar manifest hash changed")
    if root is not None:
        _, _, projection = load_reviewed_calendar_projection(
            calendar_manifest_path, repository_root=root,
        )
        if projection.iloc[-1]["session_date"].date().isoformat() != manifest[
            "latest_observed_session"
        ]:
            raise NdxDynamicShadowDailyV2Error("daily v2 latest observed session changed")

    realized_items = artifacts.get("realized_batch_manifests") or {}
    if int(manifest["realized_decision_batches"]) != len(realized_items):
        raise NdxDynamicShadowDailyV2Error("daily v2 realized batch count changed")
    for descriptor in realized_items.values():
        verify_item(descriptor)
    selector_items = artifacts.get("selector_lane_ledgers") or {}
    if int(manifest["independent_lane_count"]) == 10:
        if set(selector_items) != _selector_ids():
            raise NdxDynamicShadowDailyV2Error("daily v2 selector registry is incomplete")
        for selector_id, descriptor in selector_items.items():
            source = verify_item(descriptor)
            records = v1.load_lane_path_ledger(source, selector_id)
            if len(records) != int(descriptor.get("rows", -1)):
                raise NdxDynamicShadowDailyV2Error("daily v2 selector ledger rows changed")
        original_descriptor = artifacts.get("original_8_control_ledger")
        original_path = verify_item(original_descriptor)
        original_records = v1.load_lane_path_ledger(
            original_path, "ndx_original_8_incumbent_v0",
        )
        if len(original_records) != int(original_descriptor.get("rows", -1)):
            raise NdxDynamicShadowDailyV2Error("daily v2 original-8 rows changed")
        if len(original_records) != int(manifest["original_8_control_rows"]):
            raise NdxDynamicShadowDailyV2Error("daily v2 original-8 run count changed")
        target_descriptor = artifacts.get("target_012922_trace_ledger")
        target_path = verify_item(target_descriptor)
        target_records = v1.load_target_012922_trace_ledger(target_path)
        if len(target_records) != int(target_descriptor.get("rows", -1)):
            raise NdxDynamicShadowDailyV2Error("daily v2 012922 rows changed")
        if len(target_records) != int(manifest["target_012922_trace_rows"]):
            raise NdxDynamicShadowDailyV2Error("daily v2 012922 run count changed")
        alignment_path = verify_item(artifacts.get("three_way_alignment_manifest"))
        alignment = verify_three_way_calendar_manifest(alignment_path)
        run_alignment = manifest.get("three_way_alignment_manifest") or {}
        if (
            set(run_alignment) != {
                "path", "sha256", "calendar_rows",
                "target_first_observed_trace_complete",
                "target_resolved_outcome_benchmark_ready",
            }
            or Path(str(run_alignment["path"])).resolve() != alignment_path
            or run_alignment["sha256"] != artifacts["three_way_alignment_manifest"]["sha256"]
            or int(run_alignment["calendar_rows"]) != int(alignment["calendar_session_count"])
            or run_alignment["target_first_observed_trace_complete"] is not True
            or run_alignment["target_resolved_outcome_benchmark_ready"] is not False
            or alignment["valuation_end_date"] != manifest["latest_observed_session"]
        ):
            raise NdxDynamicShadowDailyV2Error("daily v2 alignment/run binding changed")
        if int(alignment["target_pending_rows"]) != int(manifest["target_012922_pending_rows"]):
            raise NdxDynamicShadowDailyV2Error("daily v2 012922 pending count changed")
        verify_item(artifacts.get("nominal_price_evidence_manifest"))
    elif selector_items or any(
        artifacts.get(key) is not None for key in (
            "original_8_control_ledger", "target_012922_trace_ledger",
            "three_way_alignment_manifest", "nominal_price_evidence_manifest",
        )
    ):
        raise NdxDynamicShadowDailyV2Error("daily v2 empty run exposes partial path artifacts")
    elif (
        manifest.get("three_way_alignment_manifest") is not None
        or int(manifest["original_8_control_rows"]) != 0
        or int(manifest["target_012922_trace_rows"]) != 0
        or int(manifest["target_012922_pending_rows"]) != 0
    ):
        raise NdxDynamicShadowDailyV2Error("daily v2 empty run reports path counts")
    return manifest


__all__ = [
    "NdxDynamicShadowDailyV2Error", "load_reviewed_calendar_projection",
    "verify_daily_run_manifest", "verify_three_way_calendar_manifest",
    "write_three_way_calendar_manifest",
]
