r"""Build the variable-cardinality technology portfolio search plan bundle.

PowerShell/PyCharm:
    python -B scripts\ndx_cardinality_search_plan.py --plan-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_search import (
    NdxCardinalitySearchError,
    build_search_universe,
    cardinality_space,
    load_search_plan,
    metric_contract_rows,
    search_family_rows,
    validate_search_plan,
)
from core.helpers import atomic_write_text
from data.versioning import file_sha256


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {
        "path": path.as_posix(), "rows": rows,
        "sha256": file_sha256(path), "bytes": path.stat().st_size,
    }


def _verify_stage1(readiness_path: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "ndx_marginal_stage1_readiness":
        raise NdxCardinalitySearchError("unexpected stage-1 manifest type")
    artifact = (manifest.get("artifacts") or {}).get("candidate_readiness") or {}
    if artifact.get("sha256") != file_sha256(readiness_path):
        raise NdxCardinalitySearchError("stage-1 candidate readiness hash mismatch")
    if manifest.get("fresh_oos_consumed") is not False:
        raise NdxCardinalitySearchError("stage-1 manifest unexpectedly consumed fresh OOS")
    return manifest


def build_bundle(args) -> dict:
    paths = {
        name: _resolve(getattr(args, name))
        for name in ("spec", "readiness", "stage1_manifest", "overlay", "config", "state", "output_dir")
    }
    protected_before = {
        "config": file_sha256(paths["config"]),
        "state": file_sha256(paths["state"]),
    }
    plan = load_search_plan(paths["spec"])
    plan_audit = validate_search_plan(plan)
    stage1 = _verify_stage1(paths["readiness"], paths["stage1_manifest"])
    readiness = pd.read_csv(paths["readiness"], low_memory=False)
    overlay = pd.read_csv(paths["overlay"], low_memory=False)
    universe = build_search_universe(readiness, overlay, plan)
    exact_limit = int(plan["search_contract"]["exact_enumeration_max_feasible_combinations"])
    spaces = pd.concat([
        cardinality_space(universe, track=track, exact_limit=exact_limit)
        for track in ("strict_technology", "technology_plus_adjacent")
    ], ignore_index=True)
    families = search_family_rows(plan)
    metrics = metric_contract_rows(plan)
    summary = pd.DataFrame([
        {"项目": "状态", "值": "PLAN_ONLY_SEARCH_DEVELOPMENT"},
        {"项目": "严格科技证券数", "值": int(universe["strict_technology_eligible"].sum())},
        {"项目": "严格科技issuer数", "值": int(universe.loc[universe["strict_technology_eligible"], "issuer_id"].nunique())},
        {"项目": "科技及邻接证券数", "值": int(universe["technology_plus_adjacent_eligible"].sum())},
        {"项目": "科技及邻接issuer数", "值": int(universe.loc[universe["technology_plus_adjacent_eligible"], "issuer_id"].nunique())},
        {"项目": "持仓数量范围", "值": "1..各轨合格issuer数"},
        {"项目": "当前8只角色", "值": "迭代起点与守门，不假设最优"},
        {"项目": "组合计算范围", "值": "汇丰100%美股股票风险仓"},
        {"项目": "SGOV处理", "值": "排除出目标函数、候选权重和绩效比较"},
        {"项目": "外部指数底仓", "值": "约占全资产一半，仅作架构背景，不并入回测"},
        {"项目": "012922角色", "值": "核心收益-回撤目标包络"},
        {"项目": "收益数据读取", "值": False},
        {"项目": "fresh OOS消费", "值": False},
        {"项目": "配置/state/今日建议改变", "值": False},
    ])

    output = paths["output_dir"]
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "universe": output / "technology_search_universe.csv",
        "cardinality": output / "cardinality_space.csv",
        "families": output / "search_families.csv",
        "metrics": output / "metric_contract.csv",
        "summary": output / "summary.csv",
        "workbook": output / "ndx_variable_cardinality_search_plan.xlsx",
    }
    frames = {
        "universe": universe, "cardinality": spaces, "families": families,
        "metrics": metrics, "summary": summary,
    }
    for name, frame in frames.items():
        frame.to_csv(artifacts[name], index=False, encoding="utf-8-sig")
    temporary = artifacts["workbook"].with_name(artifacts["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="摘要", index=False)
            universe.to_excel(writer, sheet_name="科技候选与排除", index=False)
            spaces.to_excel(writer, sheet_name="持仓数量与组合空间", index=False)
            families.to_excel(writer, sheet_name="搜索路径", index=False)
            metrics.to_excel(writer, sheet_name="后续指标契约", index=False)
        os.replace(temporary, artifacts["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()

    protected_after = {
        "config": file_sha256(paths["config"]),
        "state": file_sha256(paths["state"]),
    }
    if protected_after != protected_before:
        raise NdxCardinalitySearchError("protected config/state hash changed")
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_variable_cardinality_search_plan",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "PLAN_ONLY_SEARCH_DEVELOPMENT",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_audit["plan_sha256"],
        "return_data_read": False,
        "price_return_series_read": False,
        "fresh_oos_consumed": False,
        "historical_discovery_executed": False,
        "candidate_promotion_count": 0,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "protected_hashes_unchanged": True,
        "holding_count_fixed": False,
        "holding_count_policy": "1..eligible_issuer_count",
        "incumbent_is_assumed_optimal": False,
        "portfolio_scope": plan["objective_contract"]["portfolio_scope"],
        "safe_leg_role": plan["objective_contract"]["safe_leg_role"],
        "external_index_context": plan["objective_contract"]["external_index_context"],
        "target_012922_role": "core_return_drawdown_envelope",
        "input_files": {
            "spec": {"path": paths["spec"].as_posix(), "sha256": file_sha256(paths["spec"])},
            "stage1_manifest": {"path": paths["stage1_manifest"].as_posix(), "sha256": file_sha256(paths["stage1_manifest"]), "status": stage1["status"]},
            "readiness": {"path": paths["readiness"].as_posix(), "sha256": file_sha256(paths["readiness"])},
            "overlay": {"path": paths["overlay"].as_posix(), "sha256": file_sha256(paths["overlay"])},
            "config": {"path": paths["config"].as_posix(), "sha256": protected_before["config"]},
            "state": {"path": paths["state"].as_posix(), "sha256": protected_before["state"]},
        },
        "artifacts": {
            name: _artifact(path, None if name == "workbook" else len(frames[name]))
            for name, path in artifacts.items()
        },
    }
    atomic_write_text(
        output / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX科技组合不固定持仓数搜索计划（只读）")
    parser.add_argument("--spec", default="config/ndx_cardinality_search_v1_plan.yaml")
    parser.add_argument("--readiness", default="data/cache/research/ndx_marginal_stage1_v1/candidate_readiness.csv")
    parser.add_argument("--stage1-manifest", dest="stage1_manifest", default="data/cache/research/ndx_marginal_stage1_v1/manifest.json")
    parser.add_argument("--overlay", default="data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/evidence_reviewed.csv")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_variable_cardinality_search_plan_v1")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not args.plan_only:
        parser.error("add --plan-only; this command only builds the search contract")
    try:
        manifest = build_bundle(args)
    except (NdxCardinalitySearchError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"NDX不固定持仓数搜索计划失败: {exc}", file=sys.stderr)
        return 2
    print(
        "NDX不固定持仓数搜索计划完成 | holding_count=dynamic | "
        "target=012922 | return_data_read=False | live_changed=False"
    )
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
