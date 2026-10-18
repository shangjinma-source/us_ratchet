"""Fetch and audit official point-in-time Nasdaq-100 event evidence.

Examples for a PyCharm/PowerShell terminal::

    python -B scripts\\ndx_exact_events.py --plan-only
    python -B scripts\\ndx_exact_events.py --fetch-nasdaq --resume --max-jobs 1
    python -B scripts\\ndx_exact_events.py --fetch-nasdaq --resume

The command is research-only.  It does not read prices, returns, QQQ N-PORT
holdings, live state, config.yaml, or today's executable advice.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from data.ndx_exact_events import (  # noqa: E402
    EVENT_COLUMNS,
    FETCH_COLUMNS,
    GAP_COLUMNS,
    SOURCE_AUDIT_COLUMNS,
    NdxExactEventsError,
    build_effective_event_rows,
    empty_fetch_frame,
    load_event_registry,
    verify_source_content,
)
from data.versioning import (  # noqa: E402
    file_sha256,
    manifest_path,
    utc_now_iso,
    write_dataset_manifest,
)


OUTPUT_SCHEMA_VERSION = 1
DEFAULT_REGISTRY = ROOT / "config" / "ndx_exact_event_sources.yaml"
DEFAULT_OUTPUT = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "exact_events"


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, payload: dict) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )


def _write_raw(path: Path, content: bytes, *, event: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return write_dataset_manifest(
        path,
        dataset_type="ndx_official_event_raw_html",
        dataset_key=event["event_id"],
        source="official_nasdaq_press_release",
        source_locator=event["source_locator"],
        fetched_at=utc_now_iso(),
        fetched_at_evidence="nasdaq_public_html_http_200",
        row_count=1,
        extra={
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "announcement_date": event["announcement_date"],
            "effective_date": event["effective_date"],
            "source_available_date": event["source_available_date"],
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "qqq_nport_used": False,
        },
    )


def _raw_valid(path: Path, *, event: dict) -> bool:
    sidecar = manifest_path(path)
    if not path.exists() or not sidecar.exists():
        return False
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return bool(
        payload.get("content_sha256") == file_sha256(path)
        and payload.get("source_locator") == event["source_locator"]
        and payload.get("event_id") == event["event_id"]
    )


def _load_fetch_attempts(path: Path) -> pd.DataFrame:
    if not path.exists():
        return empty_fetch_frame()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in FETCH_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[FETCH_COLUMNS].drop_duplicates("event_id", keep="last")


def _upsert_attempt(frame: pd.DataFrame, row: dict) -> pd.DataFrame:
    remaining = frame[~frame["event_id"].eq(str(row["event_id"]))].copy()
    updated = pd.concat([remaining, pd.DataFrame([row])], ignore_index=True)
    return updated[FETCH_COLUMNS].sort_values("event_id", kind="stable").reset_index(drop=True)


def _fetch_one(session: requests.Session, url: str, *, timeout: float) -> tuple[int, bytes, str]:
    last_error = ""
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            if response.status_code != 200:
                raise NdxExactEventsError(f"unexpected HTTP status {response.status_code}")
            if urlparse(response.url).path == "/404":
                raise NdxExactEventsError("Nasdaq redirected the source to /404")
            if not response.content:
                raise NdxExactEventsError("Nasdaq source returned an empty body")
            return int(response.status_code), response.content, ""
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt >= 3:
                break
            time.sleep(float(2 ** (attempt - 1)))
    return 0, b"", last_error


def _fetch_sources(
    registry: dict,
    *,
    output: Path,
    user_agent: str,
    timeout: float,
    request_delay: float,
    max_jobs: int,
    resume: bool,
    refresh: bool,
) -> pd.DataFrame:
    raw_dir = output / "raw_nasdaq"
    attempts_path = output / "fetch_attempts.csv"
    attempts = _load_fetch_attempts(attempts_path)
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip, deflate",
    })
    attempted = 0
    for event in registry["events"]:
        event_id = event["event_id"]
        raw_path = raw_dir / f"{event_id}.html"
        previous = attempts[attempts["event_id"].eq(event_id)]
        previous_status = str(previous.iloc[-1]["status"]) if not previous.empty else ""
        if raw_path.exists() and _raw_valid(raw_path, event=event) and not refresh:
            row = {
                "event_id": event_id,
                "event_type": event["event_type"],
                "event_status": event["event_status"],
                "source_locator": event["source_locator"],
                "raw_path": raw_path.relative_to(output).as_posix(),
                "status": "fetched" if previous_status != "failed" else previous_status,
                "http_status": "200",
                "attempted_at": str(previous.iloc[-1]["attempted_at"]) if not previous.empty else "",
                "content_sha256": file_sha256(raw_path),
                "error": "" if previous_status != "failed" else str(previous.iloc[-1]["error"]),
            }
            if previous_status == "failed" and not resume:
                row["status"] = "fetched"
                row["error"] = ""
            attempts = _upsert_attempt(attempts, row)
            continue
        if resume and not refresh and previous_status == "fetched" and _raw_valid(raw_path, event=event):
            continue
        if max_jobs and attempted >= max_jobs:
            pending = {
                "event_id": event_id,
                "event_type": event["event_type"],
                "event_status": event["event_status"],
                "source_locator": event["source_locator"],
                "raw_path": raw_path.relative_to(output).as_posix(),
                "status": "pending_limit",
                "http_status": "",
                "attempted_at": "",
                "content_sha256": "",
                "error": "max_jobs limit reached",
            }
            attempts = _upsert_attempt(attempts, pending)
            continue
        attempted += 1
        status_code, content, error = _fetch_one(
            session,
            event["source_locator"],
            timeout=timeout,
        )
        row = {
            "event_id": event_id,
            "event_type": event["event_type"],
            "event_status": event["event_status"],
            "source_locator": event["source_locator"],
            "raw_path": raw_path.relative_to(output).as_posix(),
            "status": "failed" if error else "fetched",
            "http_status": str(status_code) if status_code else "",
            "attempted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "content_sha256": "",
            "error": error,
        }
        if not error:
            _write_raw(raw_path, content, event=event)
            row["content_sha256"] = file_sha256(raw_path)
        attempts = _upsert_attempt(attempts, row)
        _atomic_csv(attempts, attempts_path)
        if request_delay > 0:
            time.sleep(request_delay)
    _atomic_csv(attempts, attempts_path)
    return attempts


def _audit_sources(registry: dict, output: Path, attempts: pd.DataFrame) -> pd.DataFrame:
    raw_dir = output / "raw_nasdaq"
    attempts_by_id = {
        str(row["event_id"]): row
        for row in attempts.to_dict(orient="records")
    }
    rows = []
    for event in registry["events"]:
        event_id = event["event_id"]
        raw_path = raw_dir / f"{event_id}.html"
        attempt = attempts_by_id.get(event_id, {})
        raw_manifest_verified = _raw_valid(raw_path, event=event)
        content_hash = file_sha256(raw_path) if raw_path.exists() else ""
        verification = verify_source_content(
            event,
            raw_path.read_bytes() if raw_manifest_verified else b"",
        )
        source_verified = bool(raw_manifest_verified and verification["source_verified"])
        future_guard = event["source_available_date"] <= event["effective_date"]
        rows.append({
            "event_id": event_id,
            "event_type": event["event_type"],
            "event_status": event["event_status"],
            "announcement_date": event["announcement_date"],
            "effective_date": event["effective_date"],
            "source_available_date": event["source_available_date"],
            "source_locator": event["source_locator"],
            "fetch_status": str(attempt.get("status") or ("fetched" if raw_manifest_verified else "pending")),
            "http_status": str(attempt.get("http_status") or ""),
            "raw_path": raw_path.relative_to(output).as_posix() if raw_path.exists() else "",
            "content_sha256": content_hash,
            "raw_manifest_verified": raw_manifest_verified,
            "required_tickers": json.dumps(event["required_tickers"], ensure_ascii=False),
            "missing_tickers": json.dumps(verification["missing_tickers"], ensure_ascii=False),
            "required_phrases": json.dumps(event["required_phrases"], ensure_ascii=False),
            "missing_phrases": json.dumps(verification["missing_phrases"], ensure_ascii=False),
            "source_verified": source_verified,
            "future_data_guard": future_guard,
            "base_event_id": event.get("base_event_id", ""),
            "base_source_verified": True,
            "notes": event.get("notes", ""),
        })
    frame = pd.DataFrame(rows, columns=SOURCE_AUDIT_COLUMNS)
    verified = dict(zip(frame["event_id"], frame["source_verified"]))
    frame["base_source_verified"] = frame.apply(
        lambda row: bool(verified.get(row["base_event_id"], True))
        if str(row["base_event_id"] or "") else True,
        axis=1,
    )
    frame["source_verified"] = frame["source_verified"].astype(bool) & frame["base_source_verified"].astype(bool)
    return frame


def _gaps(registry: dict, source_audit: pd.DataFrame) -> pd.DataFrame:
    gaps = []
    for row in source_audit.to_dict(orient="records"):
        if not bool(row["source_verified"]):
            details = {
                "fetch_status": row["fetch_status"],
                "missing_tickers": row["missing_tickers"],
                "missing_phrases": row["missing_phrases"],
                "raw_manifest_verified": bool(row["raw_manifest_verified"]),
            }
            gaps.append({
                "gap_type": "source_not_verified",
                "event_id": row["event_id"],
                "details": json.dumps(details, ensure_ascii=False, sort_keys=True),
            })
        if not bool(row["future_data_guard"]):
            gaps.append({
                "gap_type": "source_available_after_effective_date",
                "event_id": row["event_id"],
                "details": (
                    f"source_available_date={row.get('source_available_date') or row['announcement_date']} > "
                    f"effective_date={row['effective_date']}; downstream selection date "
                    "must be on or after the source availability date"
                ),
            })
    return pd.DataFrame(gaps, columns=GAP_COLUMNS)


def _write_workbook(
    path: Path,
    events: pd.DataFrame,
    source_audit: pd.DataFrame,
    gaps: pd.DataFrame,
    coverage: pd.DataFrame,
    version_audit: pd.DataFrame,
) -> None:
    translations = {
        "event_id": "事件编号",
        "action_source_event_id": "动作证据事件编号",
        "event_type": "事件类型",
        "event_status": "事件状态",
        "announcement_date": "公告日期",
        "effective_date": "生效日期",
        "source_available_date": "证据可用日期",
        "action": "动作",
        "ticker": "证券代码",
        "source_locator": "官方来源",
        "raw_path": "原始文件路径",
        "content_sha256": "内容哈希",
        "source_manifest_verified": "原始文件Manifest校验",
        "source_available_date": "证据可用日期",
        "future_data_guard": "生效日未来数据守门",
        "source_verified": "来源验证通过",
        "inherited_from_event_id": "继承自事件编号",
        "notes": "备注",
        "fetch_status": "抓取状态",
        "http_status": "HTTP状态",
        "required_tickers": "要求出现的代码",
        "missing_tickers": "缺失代码",
        "required_phrases": "要求出现的短语",
        "missing_phrases": "缺失短语",
        "base_event_id": "基础事件编号",
        "base_source_verified": "基础来源验证通过",
        "gap_type": "缺口类型",
        "details": "详情",
        "metric": "审计指标",
        "value": "指标值",
    }

    def localize(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.rename(columns={key: value for key, value in translations.items()})

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            localize(events).to_excel(writer, sheet_name="有效事件", index=False)
            localize(source_audit).to_excel(writer, sheet_name="来源审计", index=False)
            localize(gaps).to_excel(writer, sheet_name="未解决缺口", index=False)
            localize(coverage).to_excel(writer, sheet_name="覆盖摘要", index=False)
            localize(version_audit).to_excel(writer, sheet_name="版本与审计", index=False)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_artifacts(
    registry: dict,
    registry_path: Path,
    output: Path,
    attempts: pd.DataFrame,
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    registry_snapshot = output / "source_registry_snapshot.yaml"
    atomic_write_text(registry_snapshot, registry_path.read_text(encoding="utf-8"))
    registry_snapshot_manifest = write_dataset_manifest(
        registry_snapshot,
        dataset_type="ndx_exact_event_source_registry_snapshot",
        dataset_key=str(registry.get("registry_id") or "ndx_official_nasdaq_events_v1"),
        source="local_versioned_source_registry",
        source_locator=registry_path.as_posix(),
        fetched_at=utc_now_iso(),
        fetched_at_evidence="local_registry_snapshot",
        row_count=len(registry["events"]),
        data_start=registry["scope"]["start"],
        data_end=registry["scope"]["end"],
        extra={
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "qqq_nport_used": False,
        },
    )
    source_audit = _audit_sources(registry, output, attempts)
    gaps = _gaps(registry, source_audit)
    raw_paths = {
        str(row["event_id"]): str(row["raw_path"] or "")
        for row in source_audit.to_dict(orient="records")
    }
    hashes = {
        str(row["event_id"]): str(row["content_sha256"] or "")
        for row in source_audit.to_dict(orient="records")
    }
    manifest_verified = {
        str(row["event_id"]): bool(row["raw_manifest_verified"])
        for row in source_audit.to_dict(orient="records")
    }
    events = build_effective_event_rows(
        registry,
        source_audit,
        raw_path_by_event=raw_paths,
        hash_by_event=hashes,
        manifest_verified_by_event=manifest_verified,
    )
    coverage = pd.DataFrame([
        {
            "metric": "scope_start",
            "value": registry["scope"]["start"],
        },
        {
            "metric": "scope_end",
            "value": registry["scope"]["end"],
        },
        {
            "metric": "configured_source_count",
            "value": len(registry["events"]),
        },
        {
            "metric": "effective_source_count",
            "value": int((source_audit["event_status"] == "effective").sum()),
        },
        {
            "metric": "superseded_reference_count",
            "value": int((source_audit["event_status"] == "superseded_reference").sum()),
        },
        {
            "metric": "effective_event_action_rows",
            "value": len(events),
        },
        {
            "metric": "verified_source_count",
            "value": int(source_audit["source_verified"].sum()),
        },
        {
            "metric": "source_verification_complete",
            "value": bool(source_audit["source_verified"].all()) if not source_audit.empty else False,
        },
        {
            "metric": "future_data_guard_passed_at_effective_date",
            "value": bool(source_audit["future_data_guard"].all()) if not source_audit.empty else False,
        },
        {
            "metric": "unresolved_gap_count",
            "value": len(gaps),
        },
    ])
    version_audit = pd.DataFrame([
        {"metric": "registry_id", "value": registry.get("registry_id", "")},
        {"metric": "registry_sha256", "value": file_sha256(registry_path)},
        {"metric": "registry_snapshot_sha256", "value": registry_snapshot_manifest["content_sha256"]},
        {"metric": "research_only", "value": True},
        {"metric": "return_data_read", "value": False},
        {"metric": "price_data_used", "value": False},
        {"metric": "backtest_results_used", "value": False},
        {"metric": "qqq_nport_used", "value": False},
    ])

    frames = {
        "fetch_attempts": attempts,
        "source_audit": source_audit,
        "exact_events": events,
        "unresolved_gaps": gaps,
        "coverage": coverage,
    }
    evidence_files = {}
    for name, frame in frames.items():
        path = output / f"{name}.csv"
        _atomic_csv(frame, path)
        manifest = write_dataset_manifest(
            path,
            dataset_type=f"ndx_exact_event_{name}",
            dataset_key=str(registry.get("registry_id") or "ndx_official_nasdaq_events_v1"),
            source="official_nasdaq_event_registry_audit",
            source_locator=registry_path.as_posix(),
            fetched_at=utc_now_iso(),
            fetched_at_evidence="derived_from_hash_locked_registry_and_raw_sources",
            row_count=len(frame),
            data_start=registry["scope"]["start"],
            data_end=registry["scope"]["end"],
            extra={
                "research_only": True,
                "return_data_read": False,
                "price_data_used": False,
                "backtest_results_used": False,
                "qqq_nport_used": False,
            },
        )
        evidence_files[name] = {
            "filename": path.name,
            "sha256": manifest["content_sha256"],
            "manifest_filename": manifest_path(path).name,
            "manifest_sha256": file_sha256(manifest_path(path)),
            "rows": len(frame),
        }

    workbook = output / "ndx_exact_events.xlsx"
    _write_workbook(workbook, events, source_audit, gaps, coverage, version_audit)
    workbook_manifest = write_dataset_manifest(
        workbook,
        dataset_type="ndx_exact_event_workbook",
        dataset_key=str(registry.get("registry_id") or "ndx_official_nasdaq_events_v1"),
        source="official_nasdaq_event_registry_audit",
        source_locator=registry_path.as_posix(),
        fetched_at=utc_now_iso(),
        fetched_at_evidence="derived_from_hash_locked_event_audit",
        row_count=len(events),
        data_start=registry["scope"]["start"],
        data_end=registry["scope"]["end"],
        extra={
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "qqq_nport_used": False,
        },
    )
    evidence_files["workbook"] = {
        "filename": workbook.name,
        "sha256": workbook_manifest["content_sha256"],
        "manifest_filename": manifest_path(workbook).name,
        "manifest_sha256": file_sha256(manifest_path(workbook)),
        "rows": len(events),
    }
    evidence_files["source_registry_snapshot"] = {
        "filename": registry_snapshot.name,
        "sha256": registry_snapshot_manifest["content_sha256"],
        "manifest_filename": manifest_path(registry_snapshot).name,
        "manifest_sha256": file_sha256(manifest_path(registry_snapshot)),
        "rows": len(registry["events"]),
    }

    sources_complete = bool(source_audit["source_verified"].all()) if not source_audit.empty else False
    future_guard = bool(source_audit["future_data_guard"].all()) if not source_audit.empty else False
    exact_timing = bool(sources_complete and len(gaps[gaps["gap_type"] == "source_not_verified"]) == 0)
    historical_allowed = bool(exact_timing and future_guard and gaps.empty)
    raw_source_manifests = {}
    for row in source_audit.to_dict(orient="records"):
        raw = output / str(row["raw_path"] or "")
        sidecar = manifest_path(raw)
        if sidecar.exists():
            raw_source_manifests[row["event_id"]] = {
                "filename": row["raw_path"],
                "sha256": row["content_sha256"],
                "manifest_sha256": file_sha256(sidecar),
            }
    payload = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "dataset_type": "ndx_exact_index_events",
        "dataset_key": str(registry.get("registry_id") or "ndx_official_nasdaq_events_v1"),
        "index": "NDX",
        "scope": registry["scope"],
        "registry_id": registry.get("registry_id"),
        "registry_sha256": file_sha256(registry_path),
        "event_count_configured": len(registry["events"]),
        "event_count_effective_sources": int((source_audit["event_status"] == "effective").sum()),
        "event_count_superseded_references": int((source_audit["event_status"] == "superseded_reference").sum()),
        "event_action_row_count": len(events),
        "source_verified_count": int(source_audit["source_verified"].sum()),
        "source_verification_complete": sources_complete,
        "exact_index_event_timing": exact_timing,
        "future_data_guard_passed_at_effective_date": future_guard,
        "historical_backtest_allowed": historical_allowed,
        "unresolved_gap_count": len(gaps),
        "availability_lag_event_count": int((~source_audit["future_data_guard"]).sum()),
        "nport_comparison_complete": False,
        "nport_comparison_manifest": None,
        "research_only": True,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "qqq_nport_used": False,
        "files": evidence_files,
        "raw_source_manifests": raw_source_manifests,
    }
    _write_json(output / "manifest.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and audit official Nasdaq-100 membership event sources."
    )
    parser.add_argument("--source-registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fetch-nasdaq", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("NDX_USER_AGENT", "us_ratchet/1.0"),
    )
    args = parser.parse_args()
    if args.max_jobs < 0:
        raise SystemExit("--max-jobs must be >= 0")
    if args.refresh and not args.fetch_nasdaq:
        raise SystemExit("--refresh requires --fetch-nasdaq")
    registry_path = _resolve(args.source_registry)
    output = _resolve(args.output_dir)
    registry = load_event_registry(registry_path)
    output.mkdir(parents=True, exist_ok=True)
    if args.fetch_nasdaq and not args.plan_only:
        attempts = _fetch_sources(
            registry,
            output=output,
            user_agent=str(args.user_agent),
            timeout=max(float(args.timeout), 1.0),
            request_delay=max(float(args.request_delay), 0.0),
            max_jobs=int(args.max_jobs),
            resume=bool(args.resume),
            refresh=bool(args.refresh),
        )
    else:
        attempts = _load_fetch_attempts(output / "fetch_attempts.csv")
    payload = _write_artifacts(registry, registry_path, output, attempts)
    print(
        "NDX exact event audit complete | "
        f"configured={payload['event_count_configured']} | "
        f"effective_sources={payload['event_count_effective_sources']} | "
        f"actions={payload['event_action_row_count']} | "
        f"verified={payload['source_verified_count']} | "
        f"gaps={payload['unresolved_gap_count']} | "
        f"exact_timing={payload['exact_index_event_timing']} | "
        f"historical_allowed={payload['historical_backtest_allowed']}"
    )
    print(f"Output: {output}")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
