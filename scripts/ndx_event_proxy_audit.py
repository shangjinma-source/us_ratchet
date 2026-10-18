"""Quantify quarterly QQQ N-PORT proxy lag against exact Nasdaq events.

Examples for a PyCharm/PowerShell terminal::

    python -B scripts\\ndx_event_proxy_audit.py --plan-only
    python -B scripts\\ndx_event_proxy_audit.py

This is a constituent/disclosure audit only.  It never reads OHLC, returns or
backtest output, and it cannot make QQQ an NDX candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from data.ndx_event_proxy_audit import (  # noqa: E402
    ACTION_AUDIT_COLUMNS,
    EVENT_SUMMARY_COLUMNS,
    REPORT_AUDIT_COLUMNS,
    NdxEventProxyAuditError,
    audit_event_actions,
    audit_metrics,
    build_unresolved_proxy_gaps,
    load_alias_registry,
    load_verified_proxy,
)
from data.versioning import file_sha256, manifest_path, utc_now_iso, write_dataset_manifest  # noqa: E402


DEFAULT_EXACT_DIR = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "exact_events"
DEFAULT_PROXY = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "qqq_nport_constituents.csv"
DEFAULT_ALIAS_REGISTRY = ROOT / "config" / "ndx_event_proxy_aliases.yaml"
DEFAULT_OUTPUT = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "event_proxy_audit"
AUDIT_DATASET_KEY = "ndx_official_events_vs_qqq_nport_v2"


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
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _read_exact_events(exact_dir: Path) -> tuple[pd.DataFrame, dict, Path]:
    manifest_path_value = exact_dir / "manifest.json"
    if not manifest_path_value.exists():
        raise NdxEventProxyAuditError(f"exact event manifest missing: {manifest_path_value}")
    try:
        manifest = json.loads(manifest_path_value.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxEventProxyAuditError("exact event manifest is invalid") from exc
    if manifest.get("exact_index_event_timing") is not True:
        raise NdxEventProxyAuditError("exact event timing is not complete")
    file_meta = (manifest.get("files") or {}).get("exact_events") or {}
    path = exact_dir / str(file_meta.get("filename") or "exact_events.csv")
    if not path.exists() or not file_meta.get("sha256") or file_sha256(path) != file_meta["sha256"]:
        raise NdxEventProxyAuditError("exact event table hash is missing or mismatched")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "source_verified" not in frame.columns:
        raise NdxEventProxyAuditError("exact event table lacks source_verified")
    verified = frame["source_verified"].astype(str).str.lower().isin({"true", "1"})
    if not bool(verified.all()):
        raise NdxEventProxyAuditError("exact event table still contains unverified actions")
    return frame, manifest, path


def _write_workbook(
    path: Path,
    action_audit: pd.DataFrame,
    event_summary: pd.DataFrame,
    report_audit: pd.DataFrame,
    unresolved: pd.DataFrame,
    coverage: pd.DataFrame,
    version_audit: pd.DataFrame,
) -> None:
    translations = {
        "event_id": "事件编号",
        "event_type": "事件类型",
        "effective_date": "生效日期",
        "source_available_date": "事件证据可用日期",
        "action": "动作",
        "ticker": "证券代码",
        "comparison_tickers": "比较代码集合",
        "first_post_event_report_date": "事件后首个报告期",
        "first_post_event_available_date": "事件后首个报告可用日",
        "first_post_event_state": "首个报告状态",
        "first_post_event_expected_state": "首个报告应有状态",
        "first_post_event_correct": "首个报告是否正确",
        "first_correct_report_date": "首次正确报告期",
        "first_correct_available_date": "首次正确可用日",
        "report_lag_days": "报告期滞后天数",
        "availability_lag_days": "首个代理可用滞后天数",
        "corrected_lag_days": "修正后滞后天数",
        "proxy_status": "代理状态",
        "source_future_data_guard": "事件来源生效日守门",
        "notes": "备注",
        "action_count": "动作数",
        "first_report_correct_action_count": "首个报告正确动作数",
        "first_report_mismatch_action_count": "首个报告错动作数",
        "unresolved_action_count": "未解决动作数",
        "max_corrected_lag_days": "最大修正滞后天数",
        "event_proxy_status": "事件代理状态",
        "report_date": "报告期",
        "available_date": "报告可用日",
        "expected_member_count": "重建预期成分数",
        "proxy_member_count": "代理成分数",
        "expected_missing_from_proxy_count": "预期但代理缺失数",
        "proxy_extra_count": "代理多余数",
        "expected_missing_from_proxy": "预期但代理缺失代码",
        "proxy_extra": "代理多余代码",
        "proxy_extra_details": "代理多余明细",
        "membership_state_comparison": "成分状态比较",
        "baseline_source_report_date": "基准报告期",
        "gap_type": "缺口类型",
        "evidence_status": "证据状态",
        "details": "详情",
        "proxy_weight": "代理权重",
        "proxy_value_usd": "代理市值美元",
        "proxy_name": "代理证券名称",
        "proxy_cusip": "代理CUSIP",
        "proxy_mapping_method": "代理映射方式",
        "metric": "审计指标",
        "value": "指标值",
    }

    def localize(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.rename(columns={key: value for key, value in translations.items()})

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            localize(action_audit).to_excel(writer, sheet_name="动作滞后", index=False)
            localize(event_summary).to_excel(writer, sheet_name="事件汇总", index=False)
            localize(report_audit).to_excel(writer, sheet_name="季度状态", index=False)
            localize(unresolved).to_excel(writer, sheet_name="未解决代理缺口", index=False)
            localize(coverage).to_excel(writer, sheet_name="覆盖摘要", index=False)
            localize(version_audit).to_excel(writer, sheet_name="版本与审计", index=False)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _update_exact_manifest(exact_manifest_path: Path, audit_manifest_path: Path, proxy_manifest: dict, metrics: dict) -> None:
    try:
        payload = json.loads(exact_manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxEventProxyAuditError("cannot update exact event manifest") from exc
    payload["nport_comparison_complete"] = True
    payload.pop("nport_comparison_manifest", None)
    payload["nport_comparison_audit_path"] = audit_manifest_path.as_posix()
    payload["qqq_nport_manifest_sha256"] = file_sha256(
        Path(str(proxy_manifest["manifest_path"]))
    )
    payload["proxy_error_metrics"] = metrics
    atomic_write_text(exact_manifest_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit QQQ N-PORT quarterly proxy lag against exact NDX events.")
    parser.add_argument("--exact-events-dir", default=str(DEFAULT_EXACT_DIR))
    parser.add_argument("--proxy-path", default=str(DEFAULT_PROXY))
    parser.add_argument("--alias-registry", default=str(DEFAULT_ALIAS_REGISTRY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    exact_dir = _resolve(args.exact_events_dir)
    proxy_path = _resolve(args.proxy_path)
    alias_path = _resolve(args.alias_registry)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    events, exact_manifest, exact_events_path = _read_exact_events(exact_dir)
    proxy, proxy_manifest = load_verified_proxy(proxy_path)
    aliases = load_alias_registry(alias_path)

    if args.plan_only:
        print(
            "NDX QQQ proxy audit plan ready | "
            f"exact_actions={int(events['action'].isin(['add', 'remove']).sum())} | "
            f"proxy_reports={proxy['report_date'].nunique()} | "
            "return_data_read=False"
        )
        print(f"Output: {output}")
        return 0

    action_audit, event_summary, report_audit = audit_event_actions(events, proxy, aliases)
    unresolved = build_unresolved_proxy_gaps(report_audit)
    metrics = audit_metrics(action_audit, event_summary, report_audit)
    _update_exact_manifest(
        exact_dir / "manifest.json",
        output / "manifest.json",
        proxy_manifest,
        metrics,
    )
    coverage = pd.DataFrame(
        [{"metric": key, "value": value} for key, value in metrics.items()]
    )
    version_audit = pd.DataFrame([
        {"metric": "exact_event_manifest_sha256", "value": file_sha256(exact_dir / "manifest.json")},
        {"metric": "exact_event_table_sha256", "value": file_sha256(exact_events_path)},
        {"metric": "qqq_nport_proxy_manifest_sha256", "value": file_sha256(proxy_path.with_suffix(proxy_path.suffix + ".manifest.json"))},
        {"metric": "qqq_nport_proxy_content_sha256", "value": proxy_manifest.get("content_sha256")},
        {"metric": "alias_registry_sha256", "value": file_sha256(alias_path)},
        {"metric": "research_only", "value": True},
        {"metric": "return_data_read", "value": False},
        {"metric": "price_data_used", "value": False},
        {"metric": "backtest_results_used", "value": False},
        {"metric": "qqq_is_candidate", "value": False},
    ])
    frames = {
        "action_audit": action_audit,
        "event_summary": event_summary,
        "report_audit": report_audit,
        "unresolved_proxy_gaps": unresolved,
        "coverage": coverage,
    }
    evidence_files = {}
    for name, frame in frames.items():
        path = output / f"{name}.csv"
        _atomic_csv(frame, path)
        manifest = write_dataset_manifest(
            path,
            dataset_type=f"ndx_event_proxy_audit_{name}",
            dataset_key=AUDIT_DATASET_KEY,
            source="local_exact_nasdaq_events_and_sec_qqq_nport",
            source_locator=(exact_dir / "manifest.json").as_posix(),
            fetched_at=utc_now_iso(),
            fetched_at_evidence="derived_from_hash_locked_local_sources",
            row_count=len(frame),
            data_start=str(proxy["report_date"].min()),
            data_end=str(proxy["report_date"].max()),
            extra={
                "research_only": True,
                "return_data_read": False,
                "price_data_used": False,
                "backtest_results_used": False,
                "qqq_is_candidate": False,
                "exact_index_event_timing": True,
                "qqq_proxy_is_exact_index": False,
            },
        )
        evidence_files[name] = {
            "filename": path.name,
            "sha256": manifest["content_sha256"],
            "manifest_filename": manifest_path(path).name,
            "manifest_sha256": file_sha256(manifest_path(path)),
            "rows": len(frame),
        }

    workbook = output / "ndx_event_proxy_audit.xlsx"
    _write_workbook(workbook, action_audit, event_summary, report_audit, unresolved, coverage, version_audit)
    workbook_manifest = write_dataset_manifest(
        workbook,
        dataset_type="ndx_event_proxy_audit_workbook",
        dataset_key=AUDIT_DATASET_KEY,
        source="local_exact_nasdaq_events_and_sec_qqq_nport",
        source_locator=(exact_dir / "manifest.json").as_posix(),
        fetched_at=utc_now_iso(),
        fetched_at_evidence="derived_from_hash_locked_local_sources",
        row_count=len(action_audit),
        data_start=str(proxy["report_date"].min()),
        data_end=str(proxy["report_date"].max()),
        extra={
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "qqq_is_candidate": False,
            "qqq_proxy_is_exact_index": False,
        },
    )
    evidence_files["workbook"] = {
        "filename": workbook.name,
        "sha256": workbook_manifest["content_sha256"],
        "manifest_filename": manifest_path(workbook).name,
        "manifest_sha256": file_sha256(manifest_path(workbook)),
        "rows": len(action_audit),
    }
    alias_snapshot = output / "alias_registry_snapshot.yaml"
    atomic_write_text(alias_snapshot, alias_path.read_text(encoding="utf-8"))
    alias_manifest = write_dataset_manifest(
        alias_snapshot,
        dataset_type="ndx_event_proxy_alias_registry",
        dataset_key=str(aliases.get("alias_registry_id") or "ndx_event_proxy_aliases_v1"),
        source="local_versioned_identity_lifecycle_registry",
        source_locator=alias_path.as_posix(),
        fetched_at=utc_now_iso(),
        fetched_at_evidence="local_registry_read",
        row_count=len(aliases["groups"]),
        extra={"research_only": True, "return_data_read": False},
    )
    evidence_files["alias_registry"] = {
        "filename": alias_snapshot.name,
        "sha256": alias_manifest["content_sha256"],
        "manifest_filename": manifest_path(alias_snapshot).name,
        "manifest_sha256": file_sha256(manifest_path(alias_snapshot)),
        "rows": len(aliases["groups"]),
    }
    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "dataset_type": "ndx_event_proxy_error_audit",
        "dataset_key": AUDIT_DATASET_KEY,
        "scope": {
            "exact_event_scope": exact_manifest.get("scope"),
            "qqq_report_start": str(proxy["report_date"].min()),
            "qqq_report_end": str(proxy["report_date"].max()),
        },
        "exact_index_event_timing": True,
        "event_proxy_audit_complete": True,
        "qqq_proxy_is_exact_index": False,
        "historical_backtest_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "qqq_is_candidate": False,
        "exact_event_manifest_sha256": file_sha256(exact_dir / "manifest.json"),
        "exact_event_table_sha256": file_sha256(exact_events_path),
        "qqq_nport_manifest_sha256": file_sha256(proxy_path.with_suffix(proxy_path.suffix + ".manifest.json")),
        "alias_registry_sha256": file_sha256(alias_path),
        "metrics": metrics,
        "unresolved_proxy_gap_count": len(unresolved),
        "files": evidence_files,
    }
    manifest_path_value = output / "manifest.json"
    _write_json(manifest_path_value, payload)
    print(
        "NDX QQQ proxy audit complete | "
        f"actions={metrics['membership_action_count']} | "
        f"first_snapshot_correct={metrics['first_post_event_correct_count']} | "
        f"mismatches={metrics['first_post_event_mismatch_count']} | "
        f"report_state_mismatches={metrics['report_state_mismatch_count']} | "
        f"lag_p50={metrics['corrected_lag_days_p50']}d | "
        f"lag_p90={metrics['corrected_lag_days_p90']}d"
    )
    print(f"Output: {output}")
    print(f"Manifest: {manifest_path_value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
