r"""Unify local actions and variable-cardinality challengers under a pure-stock schema."""
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

from backtest.ndx_cardinality_aggressive import compress_local_action_families
from core.helpers import atomic_write_text
from data.versioning import file_sha256


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_manifest(path: Path, expected_type: str) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != expected_type:
        raise ValueError(f"unexpected manifest type: {path}")
    if manifest.get("promotion_allowed") is not False:
        raise ValueError(f"input unexpectedly permits promotion: {path}")
    return manifest


def _artifact(manifest: dict, key: str) -> tuple[Path, pd.DataFrame]:
    artifact = (manifest.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or file_sha256(path) != artifact.get("sha256"):
        raise ValueError(f"artifact mismatch: {key}")
    frame = pd.read_csv(path, low_memory=False)
    if artifact.get("rows") is not None and len(frame) != int(artifact["rows"]):
        raise ValueError(f"artifact row count changed: {key}")
    return path, frame


def _local_structure_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["operation"].fillna("").astype(str) + "|"
        + frame["removed"].fillna("").astype(str) + "|"
        + frame["added"].fillna("").astype(str)
    )


def build_local_master_rows(local_manifest_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, Path, list[dict]]:
    """Rebuild frozen local role selections directly from the stability bundle."""
    local_manifest = _load_manifest(
        local_manifest_path, "ndx_local_challenger_cross_start_training_stability",
    )
    stability_path, stability = _artifact(local_manifest, "stability")
    local_rankings = compress_local_action_families(stability)
    selected_keys = set(local_rankings["structure_key"].astype(str))

    local_details = []
    local_inputs = []
    for source in local_manifest["inputs"]:
        path = Path(source["candidates_path"])
        if file_sha256(path) != source["candidates_sha256"]:
            raise ValueError(f"local candidate input changed: {path}")
        frame = pd.read_csv(path, low_memory=False)
        frame["structure_key"] = _local_structure_key(frame)
        frame = frame.loc[frame["structure_key"].isin(selected_keys)].copy()
        local_details.append(frame)
        local_inputs.append({"path": path.as_posix(), "sha256": file_sha256(path)})
    detail = pd.concat(local_details, ignore_index=True)
    if detail["selection_date"].nunique() != len(local_manifest["selection_dates"]):
        raise ValueError("selected local action coverage is incomplete")

    aggregate_rows = []
    latest_date = str(detail["selection_date"].astype(str).max())
    for key, group in detail.groupby("structure_key", sort=True):
        current = group.loc[group["selection_date"].astype(str).eq(latest_date)]
        if len(current) != 1:
            raise ValueError(f"current local structure is ambiguous: {key}")
        current_row = current.iloc[0]
        aggregate_rows.append({
            "structure_key": key,
            "absolute_return_p50_conservative": group["return_p50"].min(),
            "absolute_return_p10_conservative": group["return_p10"].min(),
            "absolute_max_drawdown_p50_conservative": group["max_drawdown_p50"].max(),
            "absolute_max_drawdown_p90_conservative": group["max_drawdown_p90"].max(),
            "tickers": current_row["tickers"],
            "weights": current_row["weights"],
            "current_transaction_cost": current_row["transaction_cost"],
            "current_effective_n": current_row["effective_n"],
            "current_weight_top1": current_row["weight_top1"],
            "current_weight_top3": current_row["weight_top3"],
        })
    local_aggregates = pd.DataFrame(aggregate_rows)
    local = local_rankings.merge(local_aggregates, on="structure_key", how="left", validate="many_to_one")
    local["action_scope"] = local["action_family"]
    local["candidate_tickers"] = local["tickers"]
    local["candidate_weights"] = local["weights"]
    local["absolute_return_p50"] = local["absolute_return_p50_conservative"]
    local["absolute_return_p10"] = local["absolute_return_p10_conservative"]
    local["absolute_max_drawdown_p50"] = local["absolute_max_drawdown_p50_conservative"]
    local["absolute_max_drawdown_p90"] = local["absolute_max_drawdown_p90_conservative"]
    local["paired_return_p50"] = local["worst_paired_return_p50"]
    local["paired_return_p10"] = local["worst_paired_return_p10"]
    local["paired_drawdown_cost_p50"] = local["worst_paired_drawdown_cost_p50"]
    local["paired_drawdown_cost_p90"] = local["worst_paired_drawdown_cost_p90"]
    local["target_012922_distance"] = local["median_target_012922_distance"]
    local["whole_lot_shares"] = ""
    local["execution_status"] = "NOT_REPLAYED_LOCAL_ACTION_RISK_CHAIN_HISTORY_INCOMPLETE"
    local["evidence_status"] = "REUSED_THREE_START_TRAINING_ONLY"
    return local, detail, stability_path, local_inputs


def run(args: argparse.Namespace) -> dict:
    local_manifest_path = _resolve(args.local_stability_manifest)
    local, detail, stability_path, local_inputs = build_local_master_rows(local_manifest_path)

    execution_manifest_path = _resolve(args.local_execution_manifest)
    execution_manifest = _load_manifest(
        execution_manifest_path, "ndx_local_action_whole_lot_execution_audit",
    )
    if execution_manifest.get("candidate_selection_changed") is not False:
        raise ValueError("local execution audit changed frozen candidate selection")
    execution_path, execution = _artifact(execution_manifest, "summary")
    execution_columns = [
        "candidate_id", "selection_role", "whole_lot_shares", "execution_status",
        "execution_constraint_failures", "execution_invested_usd",
        "execution_residual_cash_usd", "execution_deployment_ratio",
        "execution_risky_weight_l1_drift", "execution_risky_weight_max_abs_drift",
        "execution_actual_top1_weight", "execution_actual_top3_weight",
        "execution_actual_effective_n", "execution_actual_risk_chain_top1_weight",
        "risk_chain_weights",
    ]
    if not set(execution_columns).issubset(execution.columns):
        raise ValueError("local execution audit columns are incomplete")
    local = local.drop(columns=["whole_lot_shares", "execution_status"]).merge(
        execution[execution_columns], on=["candidate_id", "selection_role"],
        how="left", validate="one_to_one",
    )
    if local["execution_status"].isna().any():
        raise ValueError("local execution audit coverage is incomplete")

    execution_frontier_manifest_path = _resolve(args.local_execution_frontier_manifest)
    execution_frontier_manifest = _load_manifest(
        execution_frontier_manifest_path, "ndx_local_execution_aware_training_frontiers",
    )
    if execution_frontier_manifest.get("metric_first_control_preserved") is not True:
        raise ValueError("execution-aware frontier did not preserve metric-first controls")
    execution_frontier_path, execution_frontiers = _artifact(
        execution_frontier_manifest, "leaders",
    )
    fallback = execution_frontiers.loc[execution_frontiers["fallback_used"].astype(bool)].copy()
    fallback["selection_role"] = fallback["selection_role"].astype(str) + "_EXECUTION_FALLBACK"
    fallback["action_scope"] = fallback["action_family"]
    fallback["candidate_tickers"] = fallback["tickers"]
    fallback["candidate_weights"] = fallback["weights"]
    fallback["absolute_return_p50"] = fallback["absolute_return_p50_conservative"]
    fallback["absolute_return_p10"] = fallback["absolute_return_p10_conservative"]
    fallback["absolute_max_drawdown_p50"] = fallback["absolute_max_drawdown_p50_conservative"]
    fallback["absolute_max_drawdown_p90"] = fallback["absolute_max_drawdown_p90_conservative"]
    fallback["paired_return_p50"] = fallback["worst_paired_return_p50"]
    fallback["paired_return_p10"] = fallback["worst_paired_return_p10"]
    fallback["paired_drawdown_cost_p50"] = fallback["worst_paired_drawdown_cost_p50"]
    fallback["paired_drawdown_cost_p90"] = fallback["worst_paired_drawdown_cost_p90"]
    fallback["target_012922_distance"] = fallback["median_target_012922_distance"]
    fallback["execution_constraint_failures"] = ""
    fallback["execution_status"] = "WHOLE_LOT_REPLAY_COMPLIANT"
    fallback["evidence_status"] = "REUSED_THREE_START_TRAINING_EXECUTION_FALLBACK_ONLY"

    dynamic_manifest_path = _resolve(args.dynamic_manifest)
    dynamic_manifest = _load_manifest(
        dynamic_manifest_path, "ndx_cardinality_pure_equity_aggressive_shortlist",
    )
    if dynamic_manifest.get("safe_leg_included") is not False:
        raise ValueError("dynamic shortlist scope includes safe leg")
    dynamic_path, dynamic = _artifact(dynamic_manifest, "candidates")
    dynamic["selection_role"] = dynamic["selection_roles"]
    dynamic["action_scope"] = "VARIABLE_CARDINALITY"
    dynamic["candidate_tickers"] = dynamic["canonical_tickers"]
    dynamic["candidate_weights"] = dynamic["weights"]
    dynamic["absolute_return_p50"] = dynamic["worst_return_p50"]
    dynamic["absolute_return_p10"] = dynamic["worst_return_p10"]
    dynamic["absolute_max_drawdown_p50"] = dynamic["worst_max_drawdown_p50"]
    dynamic["absolute_max_drawdown_p90"] = dynamic["worst_max_drawdown_p90"]
    dynamic["paired_return_p50"] = dynamic["worst_paired_return_p50_vs_incumbent"]
    dynamic["paired_return_p10"] = dynamic["worst_paired_return_p10_vs_incumbent"]
    dynamic["paired_drawdown_cost_p50"] = dynamic["worst_paired_drawdown_cost_p50_vs_incumbent"]
    dynamic["paired_drawdown_cost_p90"] = dynamic["worst_paired_drawdown_cost_p90_vs_incumbent"]
    dynamic["target_012922_distance"] = dynamic["worst_target_012922_distance"]
    dynamic["whole_lot_shares"] = dynamic["execution_whole_shares"]
    dynamic["execution_status"] = "WHOLE_LOT_REPLAY_COMPLIANT"
    dynamic["execution_constraint_failures"] = ""
    dynamic["execution_invested_usd"] = dynamic["execution_invested_usd"]
    dynamic["execution_residual_cash_usd"] = dynamic["execution_residual_cash_usd"]
    dynamic["execution_deployment_ratio"] = dynamic["execution_deployment_ratio"]
    dynamic["execution_risky_weight_l1_drift"] = pd.NA
    dynamic["execution_risky_weight_max_abs_drift"] = pd.NA
    dynamic["execution_actual_risk_chain_top1_weight"] = dynamic["execution_actual_risk_chain_top1_weight"]
    dynamic["risk_chain_weights"] = ""
    dynamic["evidence_status"] = "REUSED_THREE_START_TRAINING_ONLY"
    dynamic["turnover"] = dynamic["initial_turnover"]
    dynamic["current_transaction_cost"] = dynamic["initial_transaction_cost"]
    dynamic["current_effective_n"] = dynamic["execution_actual_effective_n"]
    dynamic["current_weight_top1"] = dynamic["execution_actual_top1_weight"]
    dynamic["current_weight_top3"] = dynamic["execution_actual_top3_weight"]

    columns = [
        "candidate_id", "action_scope", "selection_role", "holding_count",
        "candidate_tickers", "candidate_weights", "absolute_return_p50", "absolute_return_p10",
        "absolute_max_drawdown_p50", "absolute_max_drawdown_p90", "paired_return_p50",
        "paired_return_p10", "paired_drawdown_cost_p50", "paired_drawdown_cost_p90",
        "target_012922_distance", "turnover", "current_transaction_cost", "current_effective_n",
        "current_weight_top1", "current_weight_top3", "whole_lot_shares", "execution_status",
        "execution_constraint_failures", "execution_invested_usd", "execution_residual_cash_usd",
        "execution_deployment_ratio", "execution_risky_weight_l1_drift",
        "execution_risky_weight_max_abs_drift", "execution_actual_top1_weight",
        "execution_actual_top3_weight", "execution_actual_effective_n",
        "execution_actual_risk_chain_top1_weight", "risk_chain_weights",
        "evidence_status", "portfolio_scope", "safe_leg_included", "external_index_included",
        "promotion_allowed",
    ]
    master = pd.DataFrame.from_records(
        local[columns].to_dict("records") + fallback[columns].to_dict("records")
        + dynamic[columns].to_dict("records"),
        columns=columns,
    )
    master = master.sort_values(
        ["action_scope", "selection_role", "holding_count", "candidate_tickers"], kind="stable",
    ).reset_index(drop=True)

    marginal_manifest_path = _resolve(args.marginal_forward_manifest)
    marginal = json.loads(marginal_manifest_path.read_text(encoding="utf-8"))
    if marginal.get("manifest_type") != "ndx_marginal_forward_evaluation":
        raise ValueError("unexpected marginal forward manifest")
    if int(marginal.get("fresh_oos_cohorts") or 0) != 0:
        raise ValueError("fresh marginal evidence appeared; master table needs a new version")

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    master_path = output / "challenger_master_table.csv"
    local_rankings_path = output / "local_action_role_rankings.csv"
    local_detail_path = output / "local_action_per_start.csv"
    _atomic_csv(master, master_path)
    _atomic_csv(local, local_rankings_path)
    _atomic_csv(detail, local_detail_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_pure_equity_challenger_master_table",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "REUSED_TRAINING_MASTER_TABLE_ONLY_NOT_ADMISSION",
        "portfolio_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
        "safe_leg_included": False,
        "external_index_included": False,
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "composite_score_used": False,
        "action_scopes": sorted(master["action_scope"].unique()),
        "row_count": len(master),
        "fresh_marginal_oos_cohorts": 0,
        "local_action_execution_status": "REPLAYED_WITH_INDEPENDENT_PIT_ATTRIBUTION",
        "local_action_execution_compliant_count": int(local["execution_status"].eq("WHOLE_LOT_REPLAY_COMPLIANT").sum()),
        "local_action_execution_noncompliant_count": int(local["execution_status"].ne("WHOLE_LOT_REPLAY_COMPLIANT").sum()),
        "execution_compliant_fallback_count": len(fallback),
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "inputs": {
            "local_stability_manifest": {"path": local_manifest_path.as_posix(), "sha256": file_sha256(local_manifest_path)},
            "local_stability": {"path": stability_path.as_posix(), "sha256": file_sha256(stability_path)},
            "local_candidates": local_inputs,
            "local_execution_manifest": {"path": execution_manifest_path.as_posix(), "sha256": file_sha256(execution_manifest_path)},
            "local_execution": {"path": execution_path.as_posix(), "sha256": file_sha256(execution_path)},
            "local_execution_frontier_manifest": {"path": execution_frontier_manifest_path.as_posix(), "sha256": file_sha256(execution_frontier_manifest_path)},
            "local_execution_frontiers": {"path": execution_frontier_path.as_posix(), "sha256": file_sha256(execution_frontier_path)},
            "dynamic_manifest": {"path": dynamic_manifest_path.as_posix(), "sha256": file_sha256(dynamic_manifest_path)},
            "dynamic_candidates": {"path": dynamic_path.as_posix(), "sha256": file_sha256(dynamic_path)},
            "marginal_forward_manifest": {"path": marginal_manifest_path.as_posix(), "sha256": file_sha256(marginal_manifest_path)},
        },
        "artifacts": {
            "master": {"path": master_path.as_posix(), "rows": len(master), "sha256": file_sha256(master_path)},
            "local_rankings": {"path": local_rankings_path.as_posix(), "rows": len(local), "sha256": file_sha256(local_rankings_path)},
            "local_per_start": {"path": local_detail_path.as_posix(), "rows": len(detail), "sha256": file_sha256(local_detail_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纯美股持仓四类 challenger 统一总表")
    parser.add_argument("--local-stability-manifest", default="data/cache/research/ndx_local_challenger_stability_v1/manifest.json")
    parser.add_argument("--local-execution-manifest", default="data/cache/research/ndx_local_action_execution_v1/manifest.json")
    parser.add_argument("--local-execution-frontier-manifest", default="data/cache/research/ndx_local_execution_frontier_v1/manifest.json")
    parser.add_argument("--dynamic-manifest", default="data/cache/research/ndx_cardinality_aggressive_shortlist_v1/manifest.json")
    parser.add_argument("--marginal-forward-manifest", default="data/cache/research/ndx_marginal_forward_v1/latest_evaluation/manifest.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_challenger_master_table_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"challenger总表失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"challenger总表完成 | rows={payload['row_count']} | scopes={len(payload['action_scopes'])} | "
        "SGOV=False | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
