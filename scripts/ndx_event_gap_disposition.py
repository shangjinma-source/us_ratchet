"""Build the hash-locked NDX event-gap disposition package.

PowerShell / PyCharm terminal:
    python -B scripts/ndx_event_gap_disposition.py --plan-only

The package locks the affected scope for CEG and GRAL.  It does not alter the
exact event registry, does not promote QQQ-only evidence, and does not read
prices, returns, or backtest results.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.ndx_event_gap_disposition import (  # noqa: E402
    NdxEventGapDispositionError,
    SCOPE_COLUMNS,
    build_scope_rows,
    disposition_summary,
    validate_config,
)
from data.versioning import file_sha256, manifest_path, utc_now_iso, write_dataset_manifest  # noqa: E402


DEFAULT_CONFIG = ROOT / "config" / "ndx_event_gap_dispositions.yaml"
DEFAULT_EXACT_MANIFEST = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "exact_events" / "manifest.json"
DEFAULT_PROXY_MANIFEST = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "event_proxy_audit" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "event_gap_disposition"


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxEventGapDispositionError(f"invalid JSON manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxEventGapDispositionError(f"manifest root must be a mapping: {path}")
    return payload


def _read_config(path: Path) -> dict:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise NdxEventGapDispositionError(f"cannot read disposition config: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxEventGapDispositionError("disposition config root must be a mapping")
    return validate_config(payload)


def _read_verified_child(parent_manifest_path: Path, key: str) -> tuple[pd.DataFrame, dict, Path]:
    parent = _read_json(parent_manifest_path)
    entry = (parent.get("files") or {}).get(key)
    if not isinstance(entry, dict):
        raise NdxEventGapDispositionError(
            f"manifest child entry is missing: {parent_manifest_path} / {key}"
        )
    path = parent_manifest_path.parent / str(entry.get("filename") or "")
    sidecar = parent_manifest_path.parent / str(entry.get("manifest_filename") or "")
    if not path.exists() or not sidecar.exists():
        raise NdxEventGapDispositionError(f"manifest child file is missing: {path}")
    content_hash = file_sha256(path)
    if content_hash != str(entry.get("sha256") or ""):
        raise NdxEventGapDispositionError(f"child content hash mismatch: {path}")
    sidecar_hash = file_sha256(sidecar)
    if sidecar_hash != str(entry.get("manifest_sha256") or ""):
        raise NdxEventGapDispositionError(f"child manifest hash mismatch: {sidecar}")
    child_manifest = _read_json(sidecar)
    if child_manifest.get("content_sha256") != content_hash:
        raise NdxEventGapDispositionError(f"child manifest content hash mismatch: {sidecar}")
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise NdxEventGapDispositionError(f"cannot read verified child CSV: {path}") from exc
    return frame, parent, path


def _verify_input_manifests(exact_manifest: dict, proxy_manifest: dict) -> None:
    if exact_manifest.get("dataset_key") != "ndx_official_nasdaq_events_v1":
        raise NdxEventGapDispositionError("exact event manifest key mismatch")
    if exact_manifest.get("historical_backtest_allowed") is not False:
        raise NdxEventGapDispositionError("exact event manifest must remain backtest-blocked")
    if proxy_manifest.get("dataset_key") != "ndx_official_events_vs_qqq_nport_v2":
        raise NdxEventGapDispositionError("proxy audit manifest key mismatch")
    if proxy_manifest.get("historical_backtest_allowed") is not False:
        raise NdxEventGapDispositionError("proxy audit must remain backtest-blocked")
    if proxy_manifest.get("event_proxy_audit_complete") is not True:
        raise NdxEventGapDispositionError("proxy audit is not complete")


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_workbook(path: Path, scope: pd.DataFrame, inputs: pd.DataFrame, summary: pd.DataFrame) -> None:
    labels = {
        "case_id": "处置案例",
        "issue_type": "问题类型",
        "ticker": "证券代码",
        "source_event_id": "来源事件编号",
        "effective_date": "生效日期",
        "proxy_report_date": "代理报告日期",
        "evidence_available_date": "证据可用日期",
        "proxy_available_date": "代理可用日期",
        "blocked_selection_start": "阻断选择起始日",
        "blocked_selection_end": "阻断选择结束日",
        "scope_lock": "范围锁定规则",
        "status": "处置状态",
        "promotion_allowed": "允许晋升",
        "evidence_match": "证据匹配",
        "observed_weight": "观测代理权重",
        "observed_value_usd": "观测代理金额美元",
        "observed_cusip": "观测CUSIP",
        "spin_off_parent_ticker": "分拆母公司代码",
        "distribution_date": "分拆分配日",
        "regular_way_start_date": "普通交易起始日",
        "exact_addition_supported": "精确加入已有证据",
        "exact_removal_date_supported": "精确移除日已有证据",
        "evidence_status": "证据状态",
        "source_locator": "事实来源",
        "rule_source_locator": "公司行动规则来源",
        "ndx_policy_source_locator": "NDX分拆政策来源",
        "trading_source_locator": "交易公告来源",
        "resolution_required": "解除条件",
        "input_id": "输入编号",
        "path": "文件路径",
        "dataset_key": "数据集编号",
        "content_sha256": "内容哈希",
        "manifest_sha256": "Manifest哈希",
        "rows": "行数",
        "metric": "审计指标",
        "value": "指标值",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            scope.rename(columns=labels).to_excel(writer, sheet_name="阻断范围", index=False)
            inputs.rename(columns=labels).to_excel(writer, sheet_name="证据输入", index=False)
            summary.rename(columns=labels).to_excel(writer, sheet_name="审计摘要", index=False)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _child_manifest_entry(path: Path, *, rows: int) -> dict:
    sidecar = manifest_path(path)
    payload = _read_json(sidecar)
    return {
        "filename": path.name,
        "sha256": file_sha256(path),
        "manifest_filename": sidecar.name,
        "manifest_sha256": file_sha256(sidecar),
        "rows": int(rows),
        "dataset_key": payload.get("dataset_key"),
    }


def build_bundle(
    *,
    config_path: Path,
    exact_manifest_path: Path,
    proxy_manifest_path: Path,
    output_dir: Path,
) -> dict:
    config = _read_config(config_path)
    exact_gaps, exact_manifest, exact_gaps_path = _read_verified_child(
        exact_manifest_path, "unresolved_gaps"
    )
    exact_source, _, exact_source_path = _read_verified_child(
        exact_manifest_path, "source_audit"
    )
    proxy_gaps, proxy_manifest, proxy_gaps_path = _read_verified_child(
        proxy_manifest_path, "unresolved_proxy_gaps"
    )
    _verify_input_manifests(exact_manifest, proxy_manifest)
    scope = build_scope_rows(
        config,
        exact_gaps=exact_gaps,
        exact_source_audit=exact_source,
        proxy_gaps=proxy_gaps,
    )
    summary_payload = disposition_summary(scope)
    if not summary_payload["scope_lock_complete"]:
        raise NdxEventGapDispositionError("event-gap scope lock did not pass")

    input_rows = []
    for input_id, manifest_path_value, frame, data_path in (
        ("exact_unresolved_gaps", exact_manifest_path, exact_gaps, exact_gaps_path),
        ("exact_source_audit", exact_manifest_path, exact_source, exact_source_path),
        ("proxy_unresolved_gaps", proxy_manifest_path, proxy_gaps, proxy_gaps_path),
    ):
        root_manifest = exact_manifest if manifest_path_value == exact_manifest_path else proxy_manifest
        sidecar = manifest_path(data_path)
        input_rows.append({
            "input_id": input_id,
            "path": data_path.as_posix(),
            "dataset_key": root_manifest.get("dataset_key"),
            "content_sha256": file_sha256(data_path),
            "manifest_sha256": file_sha256(sidecar),
            "rows": int(len(frame)),
        })
    inputs = pd.DataFrame(input_rows)
    summary = pd.DataFrame([
        {"metric": key, "value": value}
        for key, value in summary_payload.items()
    ])
    output_dir.mkdir(parents=True, exist_ok=True)
    scope_path = output_dir / "blocking_scope.csv"
    inputs_path = output_dir / "evidence_inputs.csv"
    summary_path = output_dir / "audit_summary.csv"
    workbook_path = output_dir / "ndx_event_gap_disposition.xlsx"
    _atomic_csv(scope, scope_path)
    _atomic_csv(inputs, inputs_path)
    _atomic_csv(summary, summary_path)
    _write_workbook(workbook_path, scope, inputs, summary)
    artifacts = {}
    for name, path, rows in (
        ("blocking_scope", scope_path, len(scope)),
        ("evidence_inputs", inputs_path, len(inputs)),
        ("audit_summary", summary_path, len(summary)),
        ("workbook", workbook_path, len(scope)),
    ):
        dataset_type = (
            "ndx_event_gap_disposition_workbook"
            if name == "workbook"
            else f"ndx_event_gap_disposition_{name}"
        )
        write_dataset_manifest(
            path,
            dataset_type=dataset_type,
            dataset_key="ndx_event_gap_disposition_v1",
            source="hash_locked_ndx_event_and_proxy_audits",
            source_locator=config_path.as_posix(),
            fetched_at=utc_now_iso(),
            fetched_at_evidence="derived_from_hash_locked_local_audits",
            row_count=rows,
            data_start="2019-09-30",
            data_end="2026-03-31",
            extra={
                "research_only": True,
                "historical_backtest_allowed": False,
                "v11_plan_registration_allowed": True,
                "v11_execution_allowed": False,
                "return_data_read": False,
                "price_data_used": False,
                "backtest_results_used": False,
            },
        )
        artifacts[name] = _child_manifest_entry(path, rows=rows)
    manifest = {
        "schema_version": 1,
        "dataset_type": "ndx_event_gap_disposition",
        "dataset_key": "ndx_event_gap_disposition_v1",
        "generated_at": utc_now_iso(),
        "research_only": True,
        "scope_lock_complete": bool(summary_payload["scope_lock_complete"]),
        "historical_backtest_allowed": False,
        "v11_plan_registration_allowed": True,
        "v11_execution_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "config_sha256": file_sha256(config_path),
        "exact_event_manifest_sha256": file_sha256(exact_manifest_path),
        "proxy_audit_manifest_sha256": file_sha256(proxy_manifest_path),
        "summary": summary_payload,
        "artifacts": artifacts,
    }
    _atomic_text(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build explicit NDX event-gap blocker scope.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--exact-manifest", default=str(DEFAULT_EXACT_MANIFEST))
    parser.add_argument("--proxy-manifest", default=str(DEFAULT_PROXY_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if not args.plan_only and not args.smoke:
        parser.error("add --plan-only or --smoke; this command never runs a backtest")
    try:
        manifest = build_bundle(
            config_path=_resolve(args.config),
            exact_manifest_path=_resolve(args.exact_manifest),
            proxy_manifest_path=_resolve(args.proxy_manifest),
            output_dir=_resolve(args.output_dir),
        )
    except (NdxEventGapDispositionError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"NDX 事件缺口处置包失败: {exc}", file=sys.stderr)
        return 2
    print(
        "NDX 事件缺口处置包完成 | "
        f"scope_lock={manifest['scope_lock_complete']} | "
        f"historical_backtest_allowed={manifest['historical_backtest_allowed']} | "
        f"v11_plan_registration_allowed={manifest['v11_plan_registration_allowed']} | "
        f"v11_execution_allowed={manifest['v11_execution_allowed']}"
    )
    print(f"输出: {_resolve(args.output_dir)}")
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
