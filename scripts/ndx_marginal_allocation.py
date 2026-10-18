"""Create the read-only v11 incumbent-first marginal allocation plan.

PowerShell / PyCharm terminal:
    python -B scripts/ndx_marginal_allocation.py --plan-only
    python -B scripts/ndx_marginal_allocation.py --smoke

This command intentionally does not read returns or start a backtest. It
audits the action space before the exact NDX event table and current-incumbent
taxonomy overlay are ready.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_marginal_allocation import (  # noqa: E402
    NdxMarginalAllocationError,
    PLAN_COLUMN_LABELS,
    build_plan_rows,
    current_incumbent_snapshot,
    file_sha256,
    load_plan,
    local_manifest_entry,
)


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _load_config(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise NdxMarginalAllocationError("config root must be a mapping")
    return raw


def _prerequisite_audit(spec: dict, *, taxonomy_manifest: Path) -> list[dict]:
    config_snapshot = spec["_config_snapshot"]
    overlay_manifest = _resolve(
        spec["prerequisites"]["incumbent_taxonomy_overlay_manifest"]
    )
    event_manifest = _resolve(spec["prerequisites"]["exact_ndx_event_manifest"])
    gap_disposition_manifest = _resolve(
        spec["prerequisites"]["event_gap_disposition_manifest"]
    )
    required = [
        {
            "id": "taxonomy_v2_manifest",
            "path": str(taxonomy_manifest),
            "available": taxonomy_manifest.exists(),
            "reason": "需要版本化 taxonomy v2 输出",
        },
        {
            "id": "current_incumbents_taxonomy",
            "path": str(taxonomy_manifest.parent / "coverage_by_security.csv"),
            "available": False,
            "reason": "当前8只仍需全部一手业务证据；TSM 使用单独 incumbent overlay",
        },
        {
            "id": "incumbent_taxonomy_overlay_manifest",
            "path": str(overlay_manifest),
            "available": False,
            "reason": "当前8只 SEC 业务证据 overlay 尚未完成审核决定",
        },
        {
            "id": "exact_ndx_event_manifest",
            "path": str(event_manifest),
            "available": event_manifest.exists(),
            "reason": "精确年度重构/临时调入调出事件表尚未完成",
        },
        {
            "id": "fresh_oos",
            "path": "2026-07-13 onward",
            "available": False,
            "reason": "计划包只登记方法，不伪造未发生的前向观察",
        },
        {
            "id": "event_gap_scope_lock",
            "path": str(gap_disposition_manifest),
            "available": False,
            "reason": "CEG/GRAL 事件缺口必须显式锁定范围；锁定后仍不得执行历史回测",
        },
    ]
    if event_manifest.exists():
        try:
            event_payload = json.loads(event_manifest.read_text(encoding="utf-8"))
            event_exact = event_payload.get("exact_index_event_timing") is True
            event_backtest_ready = event_payload.get("historical_backtest_allowed") is True
            required[3]["available"] = bool(event_exact)
            required[3]["exact_index_event_timing"] = event_exact
            required[3]["historical_backtest_allowed"] = event_backtest_ready
            required[3]["unresolved_gap_count"] = int(
                event_payload.get("unresolved_gap_count") or 0
            )
            if event_exact and event_backtest_ready:
                required[3]["reason"] = "exact NDX event manifest is verified and backtest-ready"
            elif event_exact:
                required[3]["reason"] = (
                    "exact event sources are verified, but the availability-date "
                    "guard still has unresolved event timing gaps"
                )
            else:
                required[3]["reason"] = "exact NDX event timing audit is not complete"
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            required[3]["reason"] = f"event manifest audit failed: {exc}"
    if gap_disposition_manifest.exists():
        try:
            gap_payload = json.loads(
                gap_disposition_manifest.read_text(encoding="utf-8")
            )
            exact_hash_matches = (
                event_manifest.exists()
                and gap_payload.get("exact_event_manifest_sha256")
                == file_sha256(event_manifest)
            )
            gap_ready = (
                gap_payload.get("dataset_key") == "ndx_event_gap_disposition_v1"
                and gap_payload.get("scope_lock_complete") is True
                and gap_payload.get("historical_backtest_allowed") is False
                and gap_payload.get("v11_execution_allowed") is False
                and exact_hash_matches
            )
            required[5]["available"] = bool(gap_ready)
            required[5]["scope_lock_complete"] = bool(
                gap_payload.get("scope_lock_complete") is True
            )
            required[5]["historical_backtest_allowed"] = bool(
                gap_payload.get("historical_backtest_allowed") is True
            )
            required[5]["exact_event_manifest_hash_matches"] = bool(
                exact_hash_matches
            )
            required[5]["reason"] = (
                "CEG/GRAL blocker scope is hash-locked; v11 registration only, execution remains blocked"
                if gap_ready
                else "event-gap disposition exists but dataset, scope, or input-hash audit failed"
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            required[5]["reason"] = f"event-gap disposition audit failed: {exc}"
    coverage_path = taxonomy_manifest.parent / "coverage_by_security.csv"
    overlay_ready = False
    if overlay_manifest.exists():
        try:
            overlay_payload = json.loads(overlay_manifest.read_text(encoding="utf-8"))
            overlay_summary = overlay_payload.get("summary") or {}
            overlay_ready = (
                overlay_payload.get("classification_status") == "accepted_evidence_applied"
                and int(overlay_summary.get("classification_decisions") or 0) >= len(config_snapshot["tickers"])
                and int(overlay_summary.get("raw_fetched_count") or 0) >= len(config_snapshot["tickers"])
            )
            required[2]["available"] = overlay_ready
            if overlay_ready:
                required[2]["reason"] = "incumbent overlay accepted evidence is available"
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            required[2]["reason"] = f"overlay manifest audit failed: {exc}"
    if taxonomy_manifest.exists() and coverage_path.exists():
        try:
            coverage = pd.read_csv(coverage_path)
            classified = set(
                coverage.loc[
                    pd.to_numeric(
                        coverage["classified_observations"], errors="coerce"
                    ).fillna(0) > 0,
                    "ticker",
                ].astype(str).str.upper()
            )
            missing = sorted(set(config_snapshot["tickers"]) - classified)
            # The current eight are intentionally covered by the separate
            # incumbent overlay because TSM is absent from the historical NDX
            # identity universe and the remaining incumbents may have no
            # accepted historical observations yet.  Do not require a false
            # historical backfill merely to unlock the overlay prerequisite.
            required[1]["available"] = overlay_ready
            required[1]["missing_tickers"] = missing
            required[1]["overlay_ready"] = overlay_ready
            if overlay_ready:
                required[1]["reason"] = (
                    "current eight incumbent risk-chain evidence is supplied by "
                    "the accepted point-in-time overlay; historical coverage "
                    "remains separately audited"
                )
        except (OSError, ValueError, KeyError) as exc:
            required[1]["reason"] = f"coverage audit failed: {exc}"
    return required


def _write_workbook(
    path: Path,
    plan_rows: pd.DataFrame,
    summary: pd.DataFrame,
    prerequisites: pd.DataFrame,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.xlsx")
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        plan_rows.rename(columns=PLAN_COLUMN_LABELS).to_excel(
            writer, sheet_name="动作计划", index=False
        )
        summary.to_excel(writer, sheet_name="当前基准", index=False)
        prerequisites.to_excel(writer, sheet_name="前置审计", index=False)
    temporary.replace(path)


def build_bundle(
    *,
    spec_path: Path,
    config_path: Path,
    taxonomy_manifest: Path,
    output_dir: Path,
) -> dict:
    config = _load_config(config_path)
    spec = load_plan(spec_path, config=config)
    plan_rows = build_plan_rows(spec, config=config)
    prerequisites = _prerequisite_audit(spec, taxonomy_manifest=taxonomy_manifest)
    prerequisite_frame = pd.DataFrame(prerequisites)
    exact_ready = bool(
        prerequisite_frame.loc[
            prerequisite_frame["id"].eq("exact_ndx_event_manifest"), "available"
        ].astype(bool).any()
    )
    overlay_ready = bool(
        prerequisite_frame.loc[
            prerequisite_frame["id"].eq("incumbent_taxonomy_overlay_manifest"), "available"
        ].astype(bool).any()
    )
    scope_locked = bool(
        prerequisite_frame.loc[
            prerequisite_frame["id"].eq("event_gap_scope_lock"), "available"
        ].astype(bool).any()
    )
    status = (
        "PLAN_ONLY_PRE_REGISTERED_BLOCKED_UNTIL_FRESH_OOS"
        if exact_ready and overlay_ready and scope_locked
        else "PLAN_ONLY_BLOCKED_UNTIL_PREREQUISITES"
    )
    snapshot = current_incumbent_snapshot(config)
    summary = pd.DataFrame([
        {"项目": "研究状态", "内容": status},
        {"项目": "当前持仓数量", "内容": snapshot["holding_count"]},
        {"项目": "当前Top1", "内容": snapshot["top1"]},
        {"项目": "当前Top3", "内容": snapshot["top3"]},
        {"项目": "当前effective-N", "内容": snapshot["effective_n"]},
        {"项目": "旧仓卖出允许", "内容": False},
        {"项目": "收益数据读取", "内容": False},
        {"项目": "实盘配置改变", "内容": False},
        {"项目": "今日建议改变", "内容": False},
    ])
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_csv = output_dir / "marginal_allocation_plan.csv"
    summary_csv = output_dir / "marginal_allocation_summary.csv"
    prerequisite_csv = output_dir / "prerequisites.csv"
    workbook = output_dir / "ndx_marginal_allocation_plan.xlsx"
    plan_rows.to_csv(plan_csv, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    prerequisite_frame.to_csv(prerequisite_csv, index=False, encoding="utf-8-sig")
    workbook_error = None
    try:
        _write_workbook(workbook, plan_rows, summary, prerequisite_frame)
    except Exception as exc:  # pragma: no cover - depends on local Excel runtime
        workbook_error = f"{type(exc).__name__}: {exc}"

    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_marginal_allocation_plan",
        "generated_at": _utc_now(),
        "experiment_id": spec["experiment_id"],
        "research_only": True,
        "status": status,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "live_config_changed": False,
        "today_advice_changed": False,
        "old_holding_sale_allowed": False,
        "spec_sha256": spec["_spec_sha256"],
        "config_sha256": file_sha256(config_path),
        "taxonomy_manifest_sha256": (
            file_sha256(taxonomy_manifest) if taxonomy_manifest.exists() else None
        ),
        "prerequisites": prerequisites,
        "incumbent_snapshot": snapshot,
        "artifacts": {
            "plan": local_manifest_entry(plan_csv, rows=len(plan_rows)),
            "summary": local_manifest_entry(summary_csv, rows=len(summary)),
            "prerequisites": local_manifest_entry(
                prerequisite_csv, rows=len(prerequisites)
            ),
        },
    }
    if workbook.exists():
        manifest["artifacts"]["workbook"] = local_manifest_entry(
            workbook, rows=len(plan_rows)
        )
    if workbook_error:
        manifest["workbook_error"] = workbook_error
    _atomic_text(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX v11新增资金边际配置计划（只读）")
    parser.add_argument("--spec", default="config/ndx_marginal_allocation_v11_plan.yaml")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--taxonomy-manifest",
        default="data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        default="data/cache/research/ndx_marginal_allocation_v11_plan",
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if not args.plan_only and not args.smoke:
        parser.error("this first entrypoint is plan-only; add --plan-only or --smoke")
    try:
        manifest = build_bundle(
            spec_path=_resolve(args.spec),
            config_path=_resolve(args.config),
            taxonomy_manifest=_resolve(args.taxonomy_manifest),
            output_dir=_resolve(args.output_dir),
        )
    except (NdxMarginalAllocationError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"NDX v11边际配置计划失败: {exc}", file=sys.stderr)
        return 2
    print(
        "NDX v11新增资金边际配置计划完成 | "
        f"status={manifest['status']} | "
        f"old_sell={manifest['old_holding_sale_allowed']} | "
        f"return_data_read={manifest['return_data_read']}"
    )
    print(f"输出: {_resolve(args.output_dir)}")
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
