r"""Compress all local structures again after whole-share execution checks.

The original metric-first leaders remain immutable audit controls.  This
script selects explicit execution-compliant fallbacks from the same frozen
three-start training universe and cannot promote or mutate live strategy.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_discovery import load_discovery_spec, validate_discovery_spec
from backtest.ndx_incumbent_pit_attribution import INCUMBENT_TICKERS
from backtest.ndx_local_action_execution import (
    evaluate_local_action_execution,
    select_execution_aware_local_leaders,
)
from core.helpers import atomic_write_text
from data.versioning import file_sha256
from scripts.ndx_cardinality_frontier_attribution import parse_weight_string
from scripts.ndx_local_action_execution import _atomic_csv, _prior_close, _resolve, _verified_artifact


def _structure_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["operation"].fillna("").astype(str) + "|"
        + frame["removed"].fillna("").astype(str) + "|"
        + frame["added"].fillna("").astype(str)
    )


def run(args: argparse.Namespace) -> dict:
    stability_manifest_path = _resolve(args.local_stability_manifest)
    stability_manifest = json.loads(stability_manifest_path.read_text(encoding="utf-8"))
    if stability_manifest.get("manifest_type") != "ndx_local_challenger_cross_start_training_stability":
        raise ValueError("unexpected local stability manifest")
    if stability_manifest.get("promotion_allowed") is not False:
        raise ValueError("local stability input permits promotion")
    stability_path, stability = _verified_artifact(stability_manifest, "stability")
    latest_input = max(stability_manifest["inputs"], key=lambda item: str(item["selection_date"]))
    selection_text = str(latest_input["selection_date"])
    if selection_text != str(args.selection_date):
        raise ValueError("requested selection date is not the latest frozen local start")
    current_path = Path(str(latest_input["candidates_path"]))
    if file_sha256(current_path) != latest_input["candidates_sha256"]:
        raise ValueError("current local candidate input changed")
    current = pd.read_csv(current_path, low_memory=False).fillna("")
    current["structure_key"] = _structure_key(current)
    if current["structure_key"].duplicated().any() or set(current["structure_key"]) != set(stability["structure_key"]):
        raise ValueError("current local structures do not match stability universe")

    pit_manifest_path = _resolve(args.incumbent_pit_manifest)
    pit_manifest = json.loads(pit_manifest_path.read_text(encoding="utf-8"))
    if pit_manifest.get("manifest_type") != "ndx_incumbent_pit_execution_attribution":
        raise ValueError("unexpected incumbent PIT attribution manifest")
    if pit_manifest.get("historical_backfill_created") is not False:
        raise ValueError("incumbent PIT input created taxonomy backfill")
    pit_path, pit = _verified_artifact(pit_manifest, "projection")

    discovery_manifest_path = _resolve(args.discovery_manifest)
    discovery_manifest = json.loads(discovery_manifest_path.read_text(encoding="utf-8"))
    members_path, members = _verified_artifact(discovery_manifest, "eligible_securities")
    member_rows = members.loc[
        members["selection_date"].astype(str).eq(selection_text)
        & members["universe_track"].astype(str).eq(args.universe_track)
    ].drop_duplicates("ticker")
    metadata = member_rows.set_index("ticker")[[
        "security_id", "issuer_id", "risk_chain", "evidence_available_date",
    ]].to_dict("index")
    incumbent_rows = pit.loc[pit["selection_date"].astype(str).eq(selection_text)]
    if set(incumbent_rows["ticker"]) != set(INCUMBENT_TICKERS) or len(incumbent_rows) != 8:
        raise ValueError("incumbent PIT metadata is incomplete")
    for row in incumbent_rows.to_dict("records"):
        metadata[row["ticker"]] = {
            "security_id": row["security_id"], "issuer_id": row["issuer_id"],
            "risk_chain": row["risk_chain"], "evidence_available_date": row["evidence_available_date"],
        }

    spec_path = _resolve(args.spec)
    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    contract = spec["synthetic_smoke_contract"]
    parameters = {
        "cash": float(contract["portfolio_cash_usd"]),
        "minimum_cash_buffer": float(contract["minimum_cash_buffer_usd"]),
        "min_single_weight": 0.0,
        "max_single_weight": float(contract["max_single_weight"]),
        "top3_cap": float(contract["top_weight_cap"]),
        "minimum_effective_n_ratio": 0.0,
        "risk_chain_top1_cap": float(contract["risk_chain_top1_cap"]),
    }
    selection = date.fromisoformat(selection_text)
    price_root = _resolve(args.price_root)
    price_cache: dict[str, tuple[str, float, Path, str]] = {}
    audit_rows = []
    result_by_structure = {}
    for candidate in current.to_dict("records"):
        weights = parse_weight_string(candidate["weights"])
        prices, chains = {}, {}
        for ticker in weights:
            if ticker not in metadata:
                raise ValueError(f"PIT metadata missing: {ticker}")
            if str(metadata[ticker]["evidence_available_date"]) > selection_text:
                raise ValueError(f"future evidence in local frontier audit: {ticker}")
            if ticker not in price_cache:
                path = price_root / f"{ticker}.csv"
                prior_date, prior_close = _prior_close(path, selection)
                price_cache[ticker] = (prior_date, prior_close, path, file_sha256(path))
            prices[ticker] = price_cache[ticker][1]
            chains[ticker] = str(metadata[ticker]["risk_chain"])
        result = evaluate_local_action_execution(weights, prices, chains, **parameters)
        result_by_structure[candidate["structure_key"]] = result
        declared = str(candidate["declared_constraints_passed"]).strip().lower() == "true"
        audit_rows.append({
            "structure_key": candidate["structure_key"], "challenger_id": candidate["challenger_id"],
            "operation": candidate["operation"], "removed": candidate["removed"], "added": candidate["added"],
            "holding_count": int(candidate["holding_count"]), "tickers": candidate["tickers"],
            "weights": candidate["weights"], "declared_constraints_passed": declared,
            "execution_constraints_passed": result["constraints_passed"],
            "execution_eligible": declared and result["constraints_passed"],
            "execution_constraint_failures": result["constraint_failures"],
            "whole_lot_shares": ";".join(f"{ticker}:{result['shares'][ticker]}" for ticker in sorted(weights)),
            "execution_invested_usd": result["invested_usd"],
            "execution_residual_cash_usd": result["residual_cash_usd"],
            "execution_deployment_ratio": result["deployment_ratio"],
            "execution_actual_top1_weight": result["actual_top1_weight"],
            "execution_actual_top3_weight": result["actual_top3_weight"],
            "execution_actual_effective_n": result["actual_effective_n"],
            "execution_actual_risk_chain_top1_weight": result["actual_risk_chain_top1_weight"],
        })
    audit = pd.DataFrame(audit_rows)
    execution_leaders = select_execution_aware_local_leaders(stability, audit)
    leader_keys = set(execution_leaders["structure_key"])
    across_starts = []
    for source in stability_manifest["inputs"]:
        path = Path(str(source["candidates_path"]))
        if file_sha256(path) != source["candidates_sha256"]:
            raise ValueError(f"cross-start local candidate input changed: {path}")
        frame = pd.read_csv(path, low_memory=False).fillna("")
        frame["structure_key"] = _structure_key(frame)
        frame = frame.loc[frame["structure_key"].isin(leader_keys)].copy()
        frame["source_selection_date"] = str(source["selection_date"])
        across_starts.append(frame)
    leader_history = pd.concat(across_starts, ignore_index=True)
    if leader_history.groupby("structure_key").size().ne(len(stability_manifest["selection_dates"])).any():
        raise ValueError("execution-aware leader cross-start coverage is incomplete")
    conservative = leader_history.groupby("structure_key", as_index=False).agg(
        absolute_return_p50_conservative=("return_p50", "min"),
        absolute_return_p10_conservative=("return_p10", "min"),
        absolute_max_drawdown_p50_conservative=("max_drawdown_p50", "max"),
        absolute_max_drawdown_p90_conservative=("max_drawdown_p90", "max"),
    )
    execution_leaders = execution_leaders.merge(
        conservative, on="structure_key", how="left", validate="many_to_one",
    )
    current_index = current.set_index("structure_key")
    enriched_rows = []
    position_rows = []
    for leader in execution_leaders.to_dict("records"):
        detail = current_index.loc[leader["structure_key"]]
        result = result_by_structure[leader["structure_key"]]
        leader.update({
            "tickers": detail["tickers"], "weights": detail["weights"],
            "absolute_return_p50": detail["return_p50"], "absolute_return_p10": detail["return_p10"],
            "absolute_max_drawdown_p50": detail["max_drawdown_p50"],
            "absolute_max_drawdown_p90": detail["max_drawdown_p90"],
            "whole_lot_shares": ";".join(f"{ticker}:{result['shares'][ticker]}" for ticker in sorted(result["shares"])),
            "execution_deployment_ratio": result["deployment_ratio"],
            "execution_invested_usd": result["invested_usd"],
            "execution_residual_cash_usd": result["residual_cash_usd"],
            "execution_risky_weight_l1_drift": result["risky_weight_l1_drift"],
            "execution_risky_weight_max_abs_drift": result["risky_weight_max_abs_drift"],
            "execution_actual_top1_weight": result["actual_top1_weight"],
            "execution_actual_top3_weight": result["actual_top3_weight"],
            "execution_actual_effective_n": result["actual_effective_n"],
            "execution_actual_risk_chain_top1_weight": result["actual_risk_chain_top1_weight"],
            "risk_chain_weights": ";".join(
                f"{chain}:{weight:.10f}" for chain, weight in sorted(result["risk_chain_weights"].items())
            ),
            "current_transaction_cost": detail["transaction_cost"],
            "current_effective_n": detail["effective_n"],
            "current_weight_top1": detail["weight_top1"],
            "current_weight_top3": detail["weight_top3"],
        })
        enriched_rows.append(leader)
        weights = parse_weight_string(detail["weights"])
        for ticker in sorted(weights):
            prior_date, prior_close, _, _ = price_cache[ticker]
            position_rows.append({
                "candidate_id": leader["candidate_id"], "action_family": leader["action_family"],
                "selection_role": leader["selection_role"], "selection_status": leader["selection_status"],
                "ticker": ticker, "security_id": metadata[ticker]["security_id"],
                "issuer_id": metadata[ticker]["issuer_id"], "risk_chain": metadata[ticker]["risk_chain"],
                "target_weight": weights[ticker], "prior_close_date": prior_date,
                "prior_close": prior_close, "whole_shares": result["shares"][ticker],
                "whole_lot_notional_usd": result["notionals"][ticker],
                "actual_risky_weight": result["actual_risky_weights"][ticker],
            })
    leaders = pd.DataFrame(enriched_rows)
    positions = pd.DataFrame(position_rows)

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "all_local_execution_audit.csv"
    leader_path = output / "execution_aware_role_rankings.csv"
    position_path = output / "execution_aware_positions.csv"
    _atomic_csv(audit, audit_path); _atomic_csv(leaders, leader_path); _atomic_csv(positions, position_path)
    price_inputs = [{"ticker": ticker, "path": item[2].as_posix(), "sha256": item[3]} for ticker, item in sorted(price_cache.items())]
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_local_execution_aware_training_frontiers",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_EXECUTION_FALLBACKS_ONLY_NOT_ADMISSION",
        "selection_date": selection_text,
        "structure_count": len(audit),
        "execution_eligible_count": int(audit["execution_eligible"].sum()),
        "role_count": len(leaders),
        "fallback_count": int(leaders["fallback_used"].sum()),
        "metric_first_control_preserved": True,
        "historical_taxonomy_backfill_used": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "inputs": {
            "stability_manifest": {"path": stability_manifest_path.as_posix(), "sha256": file_sha256(stability_manifest_path)},
            "stability": {"path": stability_path.as_posix(), "sha256": file_sha256(stability_path)},
            "current_candidates": {"path": current_path.as_posix(), "sha256": file_sha256(current_path)},
            "incumbent_pit_manifest": {"path": pit_manifest_path.as_posix(), "sha256": file_sha256(pit_manifest_path)},
            "incumbent_pit": {"path": pit_path.as_posix(), "sha256": file_sha256(pit_path)},
            "discovery_manifest": {"path": discovery_manifest_path.as_posix(), "sha256": file_sha256(discovery_manifest_path)},
            "members": {"path": members_path.as_posix(), "sha256": file_sha256(members_path)},
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "prices": price_inputs,
        },
        "artifacts": {
            "audit": {"path": audit_path.as_posix(), "rows": len(audit), "sha256": file_sha256(audit_path)},
            "leaders": {"path": leader_path.as_posix(), "rows": len(leaders), "sha256": file_sha256(leader_path)},
            "positions": {"path": position_path.as_posix(), "rows": len(positions), "sha256": file_sha256(position_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="全部局部结构的执行感知训练前沿")
    parser.add_argument("--local-stability-manifest", default="data/cache/research/ndx_local_challenger_stability_v1/manifest.json")
    parser.add_argument("--incumbent-pit-manifest", default="data/cache/research/ndx_incumbent_pit_attribution_v1/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--selection-date", default="2024-06-03")
    parser.add_argument("--universe-track", default="strict_technology")
    parser.add_argument("--price-root", default="data/cache")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_local_execution_frontier_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"局部执行感知前沿失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"局部执行感知前沿完成 | structures={payload['structure_count']} | "
        f"eligible={payload['execution_eligible_count']} | fallbacks={payload['fallback_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
