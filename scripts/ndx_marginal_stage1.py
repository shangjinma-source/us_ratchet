"""Build the hash-locked current-security readiness bundle for v11 stage 1."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_marginal_allocation import load_plan
from backtest.ndx_marginal_stage1 import NdxMarginalStage1Error, allocation_rows, attach_current_competition, build_candidate_readiness, load_current_inputs, verify_sidecar
from core.helpers import atomic_write_text
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "sha256": file_sha256(path), "bytes": path.stat().st_size}


def build_bundle(args) -> dict:
    paths = {name: _resolve(getattr(args, name)) for name in ("spec", "config", "taxonomy", "overlay", "quality", "valuation", "registry", "exact_events", "event_gaps", "competition", "shortlist", "output_dir")}
    config = yaml.safe_load(paths["config"].read_text(encoding="utf-8")) or {}
    plan = load_plan(paths["spec"], config=config)
    frame, versions = load_current_inputs(paths["taxonomy"], paths["quality"], paths["valuation"], paths["registry"])
    versions["incumbent_overlay"] = verify_sidecar(paths["overlay"])
    exact_events = json.loads(paths["exact_events"].read_text(encoding="utf-8"))
    event_gaps = json.loads(paths["event_gaps"].read_text(encoding="utf-8"))
    if exact_events.get("historical_backtest_allowed") is not False:
        raise NdxMarginalStage1Error("exact-event manifest must retain historical_backtest_allowed=false")
    if not (
        event_gaps.get("scope_lock_complete") is True
        and event_gaps.get("v11_execution_allowed") is False
        and event_gaps.get("exact_event_manifest_sha256") == file_sha256(paths["exact_events"])
    ):
        raise NdxMarginalStage1Error("CEG/GRAL event-gap scope or exact-event hash audit failed")
    versions["exact_events"] = {"path": paths["exact_events"].as_posix(), "sha256": file_sha256(paths["exact_events"]), "historical_backtest_allowed": False}
    versions["event_gap_disposition"] = {"path": paths["event_gaps"].as_posix(), "sha256": file_sha256(paths["event_gaps"]), "scope_lock_complete": True, "v11_execution_allowed": False}
    readiness = build_candidate_readiness(frame, config=config)
    versions["competition"] = verify_sidecar(
        paths["competition"], expected_return_data_read=True
    )
    versions["shortlist"] = verify_sidecar(
        paths["shortlist"], expected_return_data_read=True
    )
    readiness = attach_current_competition(
        readiness,
        pd.read_csv(paths["competition"], low_memory=False),
        pd.read_csv(paths["shortlist"], low_memory=False),
    )
    overlay = pd.read_csv(paths["overlay"])
    incumbent_risk_chains = dict(zip(overlay["ticker"].astype(str), overlay["risk_chain"].astype(str)))
    execution = plan["stage_1_marginal"]["execution_model"]
    allocations = allocation_rows(
        readiness,
        new_money=args.new_money,
        lot_size=float(config["execution"]["lot_size"]),
        fee_bps=float(execution["modeled_transaction_cost_bps"]),
        minimum_fee=float(execution["minimum_fee"]),
        config=config,
        incumbent_risk_chains=incumbent_risk_chains,
    )
    metrics = pd.DataFrame([{
        "metric": name, "value": None, "status": "NOT_AVAILABLE_UNTIL_FRESH_OOS",
        "reason": "当前包不读取收益；2024-07后历史已消费，不能计算或宣称通过守门",
    } for name in plan["objective_contract"]["gate_metrics"]] + [
        {"metric": "correlation_clusters", "value": None, "status": "NOT_EVALUATED", "reason": "未读取收益/相关性序列"},
        {"metric": "012922_risk_envelope", "value": None, "status": "NOT_EVALUATED", "reason": "未消费fresh OOS"},
        {"metric": "qqq_auxiliary_reference", "value": None, "status": "NOT_EVALUATED", "reason": "QQQ仅参照且本包不读取收益"},
    ])
    summary = pd.DataFrame([
        {"项目": "状态", "值": "PLAN_ONLY_PRE_REGISTERED_BLOCKED_UNTIL_FRESH_OOS"},
        {"项目": "NDX证券数", "值": len(readiness)},
        {"项目": "当前NDX内冻结incumbent数", "值": int(readiness["role"].eq("incumbent_frozen").sum())},
        {"项目": "NDX外单独overlay冻结incumbent", "值": "TSM"},
        {"项目": "冻结incumbent总数", "值": 8},
        {"项目": "真实挑战证券数", "值": int(readiness["role"].eq("challenger").sum())},
        {"项目": "已接受risk-chain证券数", "值": int(readiness["taxonomy_status"].eq("accepted").sum())},
        {"项目": "未分类证券数", "值": int((~readiness["taxonomy_status"].eq("accepted")).sum())},
        {"项目": "候选准入数", "值": 0},
        {"项目": "风险链冠军候选数", "值": int(readiness["component_shortlisted"].sum())},
        {"项目": "显式新增资金", "值": args.new_money},
        {"项目": "收益数据读取", "值": False},
        {"项目": "配置/state/今日建议改变", "值": False},
    ])
    output = paths["output_dir"]
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "candidate_readiness": output / "candidate_readiness.csv",
        "allocation_actions": output / "allocation_actions.csv",
        "metric_readiness": output / "metric_readiness.csv",
        "summary": output / "summary.csv",
        "workbook": output / "ndx_marginal_stage1.xlsx",
    }
    readiness.to_csv(artifacts["candidate_readiness"], index=False, encoding="utf-8-sig")
    allocations.to_csv(artifacts["allocation_actions"], index=False, encoding="utf-8-sig")
    metrics.to_csv(artifacts["metric_readiness"], index=False, encoding="utf-8-sig")
    summary.to_csv(artifacts["summary"], index=False, encoding="utf-8-sig")
    for name, frame_value in {
        "candidate_readiness": readiness,
        "allocation_actions": allocations,
        "metric_readiness": metrics,
        "summary": summary,
    }.items():
        write_dataset_manifest(
            artifacts[name],
            dataset_type="ndx_marginal_stage1",
            dataset_key=name,
            source="derived_from_hash_locked_stage1_inputs",
            fetched_at=utc_now_iso(),
            fetched_at_evidence="bundle_generation_utc",
            row_count=len(frame_value),
            data_start="2026-07-13",
            data_end="2026-07-13",
            extra={
                "return_data_read": False,
                "upstream_component_ranking_return_data_read": True,
                "fresh_oos_consumed": False,
                "candidate_admission_count": 0,
                "live_config_changed": False,
                "state_changed": False,
                "today_advice_changed": False,
            },
        )
    temporary = artifacts["workbook"].with_name(artifacts["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="摘要", index=False)
            readiness.to_excel(writer, sheet_name="候选证券与未晋级原因", index=False)
            allocations.to_excel(writer, sheet_name="边际比例与整股", index=False)
            metrics.to_excel(writer, sheet_name="指标就绪", index=False)
        os.replace(temporary, artifacts["workbook"])
    finally:
        if temporary.exists(): temporary.unlink()
    manifest = {
        "schema_version": 1, "manifest_type": "ndx_marginal_stage1_readiness",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "PLAN_ONLY_PRE_REGISTERED_BLOCKED_UNTIL_FRESH_OOS",
        "new_money": args.new_money, "return_data_read": False, "price_return_series_read": False,
        "upstream_component_ranking_return_data_read": True,
        "upstream_return_data_role": "signal_formation_only_not_oos_evaluation",
        "qqq_candidate_allowed": False, "fresh_oos_consumed": False, "historical_interval_consumed_as_oos": False,
        "candidate_admission_count": 0, "component_improvement_evaluated": False,
        "incumbent_gate_evaluated": False, "live_eligible_count": 0,
        "live_config_changed": False, "state_changed": False, "today_advice_changed": False,
        "input_versions": versions,
        "spec_sha256": file_sha256(paths["spec"]), "config_sha256": file_sha256(paths["config"]),
        "artifacts": {name: _artifact(path, None if name == "workbook" else len({"candidate_readiness":readiness,"allocation_actions":allocations,"metric_readiness":metrics,"summary":summary}[name])) for name, path in artifacts.items()},
    }
    atomic_write_text(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX v11阶段1当前证券/整股边际配置（只读）")
    parser.add_argument("--spec", default="config/ndx_marginal_allocation_v11_plan.yaml")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--taxonomy", default="data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/evidence_reviewed.csv")
    parser.add_argument("--overlay", default="data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/evidence_reviewed.csv")
    parser.add_argument("--quality", default="data/cache/research/ndx_v11_current_fundamental_evidence_v1/quality_input_readiness.csv")
    parser.add_argument("--valuation", default="data/cache/research/ndx_v11_current_valuation_guard_v1/valuation_gate.csv")
    parser.add_argument("--registry", default="data/cache/candidate_pools/security_candidate_registry_current.json")
    parser.add_argument("--exact-events", default="data/cache/candidate_pools/ndx_history/exact_events/manifest.json")
    parser.add_argument("--event-gaps", default="data/cache/candidate_pools/ndx_history/event_gap_disposition/manifest.json")
    parser.add_argument("--competition", default="data/cache/research/ndx_v11_current_competition_v1/candidate_competition.csv")
    parser.add_argument("--shortlist", default="data/cache/research/ndx_v11_current_competition_v1/risk_chain_shortlist.csv")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_marginal_stage1_v1")
    parser.add_argument("--new-money", type=float, default=None, help="显式新增资金USD；不提供则金额/整股保持空白")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not args.plan_only:
        parser.error("add --plan-only; fresh OOS and execution guards are still blocked")
    if args.new_money is not None and args.new_money <= 0:
        parser.error("--new-money must be positive")
    try:
        manifest = build_bundle(args)
    except (NdxMarginalStage1Error, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"NDX v11阶段1失败: {exc}", file=sys.stderr)
        return 2
    print(f"NDX v11阶段1证据包完成 | status={manifest['status']} | new_money={manifest['new_money']} | candidates_admitted=0 | return_data_read=False")
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
