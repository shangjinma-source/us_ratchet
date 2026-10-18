r"""Build a transparent pure-stock challenger shortlist from reused training evidence."""
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

from backtest.ndx_cardinality_aggressive import (
    compress_aggressive_shortlist,
    mark_incumbent_risk_reward_pareto,
    ticker_set,
)
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


def _artifact_frame(manifest: dict, key: str) -> tuple[Path, pd.DataFrame]:
    artifact = (manifest.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or not path.exists() or file_sha256(path) != artifact.get("sha256"):
        raise ValueError(f"artifact mismatch: {key}")
    frame = pd.read_csv(path, low_memory=False)
    if artifact.get("rows") is not None and len(frame) != int(artifact["rows"]):
        raise ValueError(f"artifact row count changed: {key}")
    return path, frame


def _parse_shares(value: str) -> dict[str, int]:
    result = {}
    for item in str(value).split(";"):
        if not item:
            continue
        ticker, shares = item.split(":", 1)
        result[ticker] = int(shares)
    return result


def run(args: argparse.Namespace) -> dict:
    common_manifest_path = _resolve(args.common_manifest)
    common = json.loads(common_manifest_path.read_text(encoding="utf-8"))
    if common.get("manifest_type") != "ndx_cardinality_common_structure_stability":
        raise ValueError("unexpected common-structure manifest")
    if common.get("promotion_allowed") is not False:
        raise ValueError("common-structure evidence unexpectedly permits promotion")
    if common.get("strategy_baseline") != "ORIGINAL_8_CAP_TOTAL_NORMALIZED":
        raise ValueError("strategy baseline changed")
    if common.get("personal_off_strategy_positions_included") is not False:
        raise ValueError("off-strategy positions contaminated the baseline")
    structures_path, structures = _artifact_frame(common, "structures")
    per_start_path, per_start = _artifact_frame(common, "per_date")

    execution_manifest_path = _resolve(args.execution_manifest)
    execution_manifest = json.loads(execution_manifest_path.read_text(encoding="utf-8"))
    if execution_manifest.get("manifest_type") != "ndx_cardinality_execution_aware_frontiers":
        raise ValueError("unexpected execution manifest")
    if execution_manifest.get("promotion_allowed") is not False:
        raise ValueError("execution evidence unexpectedly permits promotion")
    if execution_manifest.get("strategy_baseline") != "ORIGINAL_8_CAP_TOTAL_NORMALIZED":
        raise ValueError("execution strategy baseline changed")
    execution_path, execution = _artifact_frame(execution_manifest, "audit")
    members_artifact = ((execution_manifest.get("inputs") or {}).get("members") or {})
    members_path = Path(str(members_artifact.get("path") or ""))
    if not members_path.is_absolute() or file_sha256(members_path) != members_artifact.get("sha256"):
        raise ValueError("execution member metadata mismatch")
    members = pd.read_csv(members_path, low_memory=False)

    latest_date = str(execution["selection_date"].astype(str).max())
    execution_equal = execution.loc[
        execution["selection_date"].astype(str).eq(latest_date)
        & execution["weight_spec"].eq("equal_weight")
        & execution["execution_constraints_passed"].astype(bool)
    ].copy()
    executable_tickers = set(execution_equal["tickers"].astype(str))
    executable_structures = structures.loc[
        structures["canonical_tickers"].astype(str).isin(executable_tickers)
    ].copy()
    if executable_structures.empty:
        raise ValueError("no common structure has a compliant whole-lot replay")
    preference = [part.strip().upper() for part in args.preference_tickers.split(",") if part.strip()]
    shortlist = compress_aggressive_shortlist(
        executable_structures, preference_tickers=preference, per_role=args.per_role,
    )
    execution_columns = [
        "tickers", "weights", "execution_whole_shares", "execution_invested_usd",
        "execution_residual_cash_usd", "execution_deployment_ratio",
        "execution_actual_top1_weight", "execution_actual_top3_weight",
        "execution_actual_effective_n", "execution_actual_risk_chain_top1_weight",
        "portfolio_min_median_dollar_volume_usd", "initial_turnover",
        "initial_transaction_cost", "ongoing_rebalance_turnover_p50",
    ]
    execution_equal = execution_equal[execution_columns].drop_duplicates("tickers")
    shortlist = shortlist.merge(
        execution_equal, left_on="canonical_tickers", right_on="tickers", how="left",
        validate="many_to_one", suffixes=("", "_execution"),
    )
    shortlist["execution_selection_date"] = latest_date
    shortlist["whole_lot_execution_available"] = shortlist["execution_whole_shares"].notna()
    if not shortlist["whole_lot_execution_available"].all():
        missing = shortlist.loc[~shortlist["whole_lot_execution_available"], "canonical_tickers"].tolist()
        raise ValueError(f"whole-lot replay missing for shortlisted structures: {missing}")

    unique = shortlist.drop_duplicates("candidate_id").copy()
    roles = shortlist.groupby("candidate_id")["selection_role"].agg(
        lambda values: ";".join(dict.fromkeys(values))
    )
    unique["selection_roles"] = unique["candidate_id"].map(roles)
    unique["target_equal_weight"] = 1.0 / unique["holding_count"].astype(int)

    selected_issuers = set(unique["issuer_structure"].astype(str))
    selected_per_start = per_start.loc[per_start["issuer_structure"].astype(str).isin(selected_issuers)].copy()
    candidate_ids = unique.set_index("issuer_structure")["candidate_id"]
    selected_per_start.insert(
        0, "candidate_id", selected_per_start["issuer_structure"].map(candidate_ids),
    )

    latest_members = members.loc[
        members["universe_track"].eq("strict_technology")
        & members["selection_date"].astype(str).eq(latest_date)
    ].drop_duplicates("ticker").set_index("ticker")
    holding_rows = []
    for row in unique.itertuples():
        tickers = sorted(ticker_set(row.canonical_tickers))
        shares = _parse_shares(row.execution_whole_shares)
        for ticker in tickers:
            if ticker not in latest_members.index:
                raise ValueError(f"latest point-in-time metadata missing: {ticker}")
            meta = latest_members.loc[ticker]
            holding_rows.append({
                "candidate_id": row.candidate_id,
                "selection_roles": row.selection_roles,
                "ticker": ticker,
                "issuer_id": meta["issuer_id"],
                "risk_chain": meta["risk_chain"],
                "risk_chain_label": meta["risk_chain_label"],
                "target_weight": 1.0 / len(tickers),
                "whole_shares_at_5000_usd": shares[ticker],
                "execution_selection_date": latest_date,
            })
    holdings = pd.DataFrame(holding_rows)

    display_columns = [
        "candidate_id", "selection_roles", "holding_count", "canonical_tickers",
        "worst_return_p50", "worst_return_p10", "worst_max_drawdown_p50", "worst_max_drawdown_p90",
        "worst_paired_return_p50_vs_incumbent", "worst_paired_return_p10_vs_incumbent",
        "worst_paired_drawdown_cost_p50_vs_incumbent", "worst_paired_drawdown_cost_p90_vs_incumbent",
        "worst_target_012922_distance", "incumbent_risk_reward_pareto", "weights",
        "execution_whole_shares", "execution_invested_usd", "execution_residual_cash_usd",
        "execution_deployment_ratio", "execution_actual_top1_weight", "execution_actual_top3_weight",
        "execution_actual_effective_n", "execution_actual_risk_chain_top1_weight",
        "portfolio_min_median_dollar_volume_usd", "initial_turnover", "initial_transaction_cost",
        "ongoing_rebalance_turnover_p50", "portfolio_scope", "safe_leg_included",
        "external_index_included", "promotion_allowed", "result_status",
    ]
    candidates = unique[display_columns].sort_values(
        ["selection_roles", "holding_count", "canonical_tickers"], kind="stable"
    ).reset_index(drop=True)

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    candidates_path = output / "aggressive_shortlist.csv"
    per_start_output = output / "aggressive_shortlist_per_start.csv"
    holdings_path = output / "aggressive_shortlist_holdings.csv"
    role_rows_path = output / "aggressive_role_rankings.csv"
    _atomic_csv(candidates, candidates_path)
    _atomic_csv(selected_per_start, per_start_output)
    _atomic_csv(holdings, holdings_path)
    _atomic_csv(shortlist, role_rows_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_pure_equity_aggressive_shortlist",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "REUSED_TRAINING_SHORTLIST_ONLY_NOT_ADMISSION",
        "portfolio_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
        "safe_leg_included": False,
        "external_index_included": False,
        "external_index_context": "USER_MANAGED_QDII_APPROXIMATELY_HALF_OF_TOTAL_ASSETS",
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "personal_off_strategy_positions_included": False,
        "selection_roles": ["RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE", "USER_PREFERENCE"],
        "role_rank_limit": args.per_role,
        "composite_score_used": False,
        "preference_tickers": preference,
        "common_structure_count": len(structures),
        "whole_lot_replayable_common_structure_count": len(executable_structures),
        "risk_reward_pareto_count": int(mark_incumbent_risk_reward_pareto(executable_structures).sum()),
        "shortlist_candidate_count": len(candidates),
        "selection_dates": sorted(selected_per_start["selection_date"].astype(str).unique()),
        "execution_selection_date": latest_date,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "inputs": {
            "common_manifest": {"path": common_manifest_path.as_posix(), "sha256": file_sha256(common_manifest_path)},
            "structures": {"path": structures_path.as_posix(), "sha256": file_sha256(structures_path)},
            "per_start": {"path": per_start_path.as_posix(), "sha256": file_sha256(per_start_path)},
            "execution_manifest": {"path": execution_manifest_path.as_posix(), "sha256": file_sha256(execution_manifest_path)},
            "execution_audit": {"path": execution_path.as_posix(), "sha256": file_sha256(execution_path)},
            "members": {"path": members_path.as_posix(), "sha256": file_sha256(members_path)},
        },
        "artifacts": {
            "candidates": {"path": candidates_path.as_posix(), "rows": len(candidates), "sha256": file_sha256(candidates_path)},
            "per_start": {"path": per_start_output.as_posix(), "rows": len(selected_per_start), "sha256": file_sha256(per_start_output)},
            "holdings": {"path": holdings_path.as_posix(), "rows": len(holdings), "sha256": file_sha256(holdings_path)},
            "role_rankings": {"path": role_rows_path.as_posix(), "rows": len(shortlist), "sha256": file_sha256(role_rows_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纯美股股票风险仓跨起点候选压缩")
    parser.add_argument("--common-manifest", default="data/cache/research/ndx_cardinality_common_structure_stability_v1/manifest.json")
    parser.add_argument("--execution-manifest", default="data/cache/research/ndx_cardinality_execution_frontiers_v1/manifest.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_aggressive_shortlist_v1")
    parser.add_argument("--preference-tickers", default="AMAT,AVGO,CDNS,GOOG")
    parser.add_argument("--per-role", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"纯股票候选压缩失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"纯股票候选压缩完成 | candidates={payload['shortlist_candidate_count']} | "
        f"roles={len(payload['selection_roles'])} | SGOV=False | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
