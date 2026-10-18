r"""Attribute cross-cardinality training representatives to securities and risk chains."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text
from backtest.ndx_cardinality_discovery import load_discovery_spec, validate_discovery_spec
from data.versioning import file_sha256
from scripts.ndx_cardinality_real_smoke import _load_bars


INCUMBENT = ["NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG"]


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


def parse_weight_string(value: str) -> dict[str, float]:
    result = {}
    for item in str(value).split(";"):
        ticker, separator, weight = item.partition(":")
        if not separator or not ticker.strip():
            raise ValueError(f"invalid weight item: {item}")
        ticker = ticker.strip().upper()
        if ticker in result:
            raise ValueError(f"duplicate weight ticker: {ticker}")
        result[ticker] = float(weight)
    if not result or any(weight <= 0 for weight in result.values()):
        raise ValueError("weights must be positive")
    if abs(sum(result.values()) - 1.0) > 1e-6:
        raise ValueError("weights must sum to one")
    return result


def concentration_metrics(weights: dict[str, float]) -> dict[str, float]:
    values = sorted((float(value) for value in weights.values() if value > 0), reverse=True)
    if not values:
        raise ValueError("concentration weights are empty")
    total = sum(values)
    normalized = [value / total for value in values]
    return {
        "top1_weight": normalized[0],
        "top3_weight": sum(normalized[:3]),
        "effective_n": 1.0 / sum(value * value for value in normalized),
    }


def whole_lot_weight_drift(target: dict[str, float], notionals: dict[str, float], cash: float) -> dict:
    invested = sum(notionals.values())
    if invested <= 0 or cash <= 0:
        raise ValueError("whole-lot drift requires positive invested notional and cash")
    actual_risky = {ticker: notionals.get(ticker, 0.0) / invested for ticker in target}
    differences = {ticker: actual_risky[ticker] - weight for ticker, weight in target.items()}
    return {
        "actual_risky_weights": actual_risky,
        "actual_total_cash_weights": {ticker: notionals.get(ticker, 0.0) / cash for ticker in target},
        "risky_weight_l1_drift": sum(abs(value) for value in differences.values()),
        "risky_weight_max_abs_drift": max(abs(value) for value in differences.values()),
        "risky_weight_max_abs_drift_ticker": max(differences, key=lambda ticker: abs(differences[ticker])),
        "cash_weight": (cash - invested) / cash,
        "deployment_ratio": invested / cash,
    }


def repair_whole_lot_allocation(
    target: dict[str, float], prices: dict[str, float], risk_chains: dict[str, str],
    *, cash: float, minimum_cash_buffer: float, risk_chain_top1_cap: float,
    min_single_weight: float = 0.0, max_single_weight: float = 1.0,
    top3_cap: float = 1.0, minimum_effective_n_ratio: float = 0.0,
) -> dict[str, int]:
    """Greedily repair floor lots with a deterministic constraint-first objective."""
    investable = cash - minimum_cash_buffer
    shares = {ticker: int(math.floor(investable * weight / prices[ticker])) for ticker, weight in target.items()}

    def score(candidate: dict[str, int]) -> tuple[float, float, float, float]:
        notionals = {ticker: candidate[ticker] * prices[ticker] for ticker in target}
        invested = sum(notionals.values())
        if invested <= 0:
            return (1.0, float("inf"), float("inf"), 1.0)
        actual = {ticker: notional / invested for ticker, notional in notionals.items()}
        chains: dict[str, float] = {}
        for ticker, weight in actual.items():
            chain = risk_chains[ticker]
            chains[chain] = chains.get(chain, 0.0) + weight
        concentration = concentration_metrics(actual)
        constraint_violation = (
            max(0.0, min_single_weight - min(actual.values()))
            + max(0.0, concentration["top1_weight"] - max_single_weight)
            + max(0.0, concentration["top3_weight"] - top3_cap)
            + max(0.0, len(target) * minimum_effective_n_ratio - concentration["effective_n"]) / len(target)
            + max(0.0, max(chains.values()) - risk_chain_top1_cap)
            + sum(1 for value in candidate.values() if value < 1)
        )
        differences = [abs(actual[ticker] - target[ticker]) for ticker in target]
        return (constraint_violation, sum(differences), max(differences), (cash - invested) / cash)

    current_score = score(shares)
    while True:
        invested = sum(shares[ticker] * prices[ticker] for ticker in target)
        affordable = [
            ticker for ticker in sorted(target)
            if invested + prices[ticker] <= investable + 1e-9
        ]
        proposals = []
        for ticker in affordable:
            candidate = dict(shares)
            candidate[ticker] += 1
            proposals.append((score(candidate), ticker, candidate))
        if not proposals:
            break
        best_score, _, best = min(proposals, key=lambda item: (item[0], item[1]))
        if best_score >= current_score:
            break
        shares, current_score = best, best_score
    return shares


def run(args: argparse.Namespace) -> dict:
    frontier_manifest_path = _resolve(args.frontier_manifest)
    discovery_manifest_path = _resolve(args.discovery_manifest)
    spec_path = _resolve(args.spec)
    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    risk_chain_top1_cap = (
        float(args.risk_chain_top1_cap)
        if args.risk_chain_top1_cap is not None
        else float(spec["synthetic_smoke_contract"]["risk_chain_top1_cap"])
    )
    smoke_contract = spec["synthetic_smoke_contract"]
    max_single_weight = float(smoke_contract["max_single_weight"])
    min_single_weight = float(smoke_contract["min_single_weight"])
    top3_cap = float(smoke_contract["top_weight_cap"])
    minimum_effective_n_ratio = float(smoke_contract["minimum_effective_n_ratio"])
    frontier_manifest = json.loads(frontier_manifest_path.read_text(encoding="utf-8"))
    if frontier_manifest.get("manifest_type") != "ndx_cross_cardinality_real_training_frontiers":
        raise ValueError("unexpected cross-cardinality frontier manifest")
    frontier_artifact = (frontier_manifest.get("artifacts") or {}).get("cross_cardinality_frontiers") or {}
    frontier_path = Path(str(frontier_artifact.get("path") or ""))
    if not frontier_path.is_absolute() or file_sha256(frontier_path) != frontier_artifact.get("sha256"):
        raise ValueError("cross-cardinality frontier artifact mismatch")
    frontiers = pd.read_csv(frontier_path, low_memory=False)
    if len(frontiers) != int(frontier_artifact.get("rows") or -1):
        raise ValueError("cross-cardinality frontier row count changed")

    discovery = json.loads(discovery_manifest_path.read_text(encoding="utf-8"))
    members_artifact = (discovery.get("artifacts") or {}).get("eligible_securities") or {}
    members_path = Path(str(members_artifact.get("path") or ""))
    if not members_path.is_absolute() or file_sha256(members_path) != members_artifact.get("sha256"):
        raise ValueError("point-in-time membership artifact mismatch")
    members = pd.read_csv(members_path, low_memory=False)
    identity = frontier_manifest["comparison_identity"]
    selection = pd.Timestamp(identity["selection_date"]).normalize()
    metadata = members.loc[
        members["universe_track"].eq(identity["universe_track"])
        & members["selection_date"].eq(selection.date().isoformat())
    ][["ticker", "security_id", "issuer_id", "risk_chain"]].drop_duplicates("ticker")
    if metadata["ticker"].duplicated().any():
        raise ValueError("point-in-time ticker metadata is ambiguous")
    metadata_by_ticker = metadata.set_index("ticker").to_dict(orient="index")

    state_path = _resolve(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    incumbent_caps = {ticker: float(state["symbols"][ticker]["cap_total"]) for ticker in INCUMBENT}
    incumbent_total = sum(incumbent_caps.values())
    incumbent_weights = {ticker: value / incumbent_total for ticker, value in incumbent_caps.items()}
    incumbent_concentration = concentration_metrics(incumbent_weights)
    incumbent_rows = []
    incumbent_pit_chain_count = 0
    for ticker in INCUMBENT:
        meta = metadata_by_ticker.get(ticker)
        risk_chain = str(meta["risk_chain"]) if meta else None
        if risk_chain:
            incumbent_pit_chain_count += 1
        incumbent_rows.append({
            "ticker": ticker, "strategy_cap_total_usd": incumbent_caps[ticker],
            "strategy_weight": incumbent_weights[ticker],
            "point_in_time_risk_chain": risk_chain,
            "point_in_time_risk_chain_available": bool(risk_chain),
            "personal_off_strategy_position_included": False,
        })
    incumbent_frame = pd.DataFrame(incumbent_rows)
    incumbent_chain_delta_status = (
        "COMPARABLE" if incumbent_pit_chain_count == len(INCUMBENT)
        else f"BLOCKED_INCOMPLETE_POINT_IN_TIME_CLASSIFICATION:{incumbent_pit_chain_count}/{len(INCUMBENT)}"
    )

    inventory_by_manifest = {}
    source_inputs = []
    for source_value in sorted(set(frontiers["source_manifest"].astype(str))):
        source_path = Path(source_value)
        source = json.loads(source_path.read_text(encoding="utf-8"))
        inventory_artifact = (source.get("artifacts") or {}).get("price_inventory") or {}
        inventory_path = Path(str(inventory_artifact.get("path") or ""))
        if not inventory_path.is_absolute() or file_sha256(inventory_path) != inventory_artifact.get("sha256"):
            raise ValueError(f"price inventory mismatch: {source_path}")
        inventory = pd.read_csv(inventory_path)
        if len(inventory) != int(inventory_artifact.get("rows") or -1):
            raise ValueError(f"price inventory row count changed: {source_path}")
        inventory_by_manifest[source_value] = inventory.set_index("ticker")
        source_inputs.append({
            "manifest_path": source_path.as_posix(), "manifest_sha256": file_sha256(source_path),
            "inventory_path": inventory_path.as_posix(), "inventory_sha256": file_sha256(inventory_path),
        })

    cash = float(args.portfolio_cash_usd)
    buffer = float(args.minimum_cash_buffer_usd)
    if cash <= 0 or not 0 <= buffer < cash:
        raise ValueError("whole-lot attribution cash contract is invalid")
    investable = cash - buffer
    position_rows = []
    summary_rows = []
    for _, frontier in frontiers.iterrows():
        role = str(frontier["cross_cardinality_frontier_role"])
        source_value = str(frontier["source_manifest"])
        inventory = inventory_by_manifest[source_value]
        weights = parse_weight_string(frontier["weights"])
        chain_weights = {}
        issuer_weights = {}
        invested = 0.0
        shares_by_ticker = {}
        notionals_by_ticker = {}
        prices_by_ticker = {}
        for ticker, weight in sorted(weights.items()):
            if ticker not in metadata_by_ticker:
                raise ValueError(f"point-in-time metadata missing: {ticker}")
            if ticker not in inventory.index:
                raise ValueError(f"price inventory missing: {ticker}")
            price_path = Path(str(inventory.loc[ticker, "path"]))
            if file_sha256(price_path) != str(inventory.loc[ticker, "sha256"]):
                raise ValueError(f"price file hash changed: {ticker}")
            bars = _load_bars(price_path)
            prior = bars.loc[bars.index < selection]
            if prior.empty:
                raise ValueError(f"selection prior close missing: {ticker}")
            price = float(prior["Close"].iloc[-1])
            shares = int(math.floor(investable * weight / price))
            actual_notional = shares * price
            invested += actual_notional
            shares_by_ticker[ticker] = shares
            notionals_by_ticker[ticker] = actual_notional
            prices_by_ticker[ticker] = price
            meta = metadata_by_ticker[ticker]
            chain = str(meta["risk_chain"])
            issuer = str(meta["issuer_id"])
            chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
            issuer_weights[issuer] = issuer_weights.get(issuer, 0.0) + weight
            position_rows.append({
                "frontier_role": role, "holding_count": int(frontier["holding_count"]),
                "ticker": ticker, "security_id": meta["security_id"], "issuer_id": issuer,
                "risk_chain": chain, "target_weight": weight, "selection_prior_close": price,
                "target_notional_usd": investable * weight, "whole_shares": shares,
                "whole_lot_notional_usd": actual_notional,
                "whole_lot_notional_shortfall_usd": investable * weight - actual_notional,
            })
        chain_ordered = sorted(chain_weights.items(), key=lambda item: (-item[1], item[0]))
        drift = whole_lot_weight_drift(weights, notionals_by_ticker, cash)
        risk_chains_by_ticker = {
            ticker: str(metadata_by_ticker[ticker]["risk_chain"]) for ticker in weights
        }
        repaired_shares = repair_whole_lot_allocation(
            weights, prices_by_ticker, risk_chains_by_ticker,
            cash=cash, minimum_cash_buffer=buffer,
            risk_chain_top1_cap=risk_chain_top1_cap,
            min_single_weight=min_single_weight,
            max_single_weight=max_single_weight,
            top3_cap=top3_cap,
            minimum_effective_n_ratio=minimum_effective_n_ratio,
        )
        repaired_notionals = {
            ticker: repaired_shares[ticker] * prices_by_ticker[ticker] for ticker in weights
        }
        repaired_drift = whole_lot_weight_drift(weights, repaired_notionals, cash)
        target_concentration = concentration_metrics(weights)
        actual_concentration = concentration_metrics(drift["actual_risky_weights"])
        repaired_concentration = concentration_metrics(repaired_drift["actual_risky_weights"])
        actual_chain_weights = {}
        for ticker, actual_weight in drift["actual_risky_weights"].items():
            chain = str(metadata_by_ticker[ticker]["risk_chain"])
            actual_chain_weights[chain] = actual_chain_weights.get(chain, 0.0) + actual_weight
        actual_chain_top1 = max(actual_chain_weights.values())
        repaired_chain_weights = {}
        for ticker, actual_weight in repaired_drift["actual_risky_weights"].items():
            chain = risk_chains_by_ticker[ticker]
            repaired_chain_weights[chain] = repaired_chain_weights.get(chain, 0.0) + actual_weight
        repaired_chain_top1 = max(repaired_chain_weights.values())
        repaired_constraints = {
            "min_single": min(repaired_drift["actual_risky_weights"].values()) >= min_single_weight - 1e-12,
            "max_single": repaired_concentration["top1_weight"] <= max_single_weight + 1e-12,
            "top3": repaired_concentration["top3_weight"] <= top3_cap + 1e-12,
            "effective_n": repaired_concentration["effective_n"] >= len(weights) * minimum_effective_n_ratio - 1e-12,
            "risk_chain_top1": repaired_chain_top1 <= risk_chain_top1_cap + 1e-12,
            "whole_lot": all(value >= 1 for value in repaired_shares.values()),
        }
        for row in position_rows[-len(weights):]:
            ticker = row["ticker"]
            row["whole_lot_actual_risky_weight"] = drift["actual_risky_weights"][ticker]
            row["whole_lot_actual_total_cash_weight"] = drift["actual_total_cash_weights"][ticker]
            row["whole_lot_risky_weight_drift"] = drift["actual_risky_weights"][ticker] - row["target_weight"]
            row["repaired_whole_shares"] = repaired_shares[ticker]
            row["repaired_whole_lot_notional_usd"] = repaired_notionals[ticker]
            row["repaired_actual_risky_weight"] = repaired_drift["actual_risky_weights"][ticker]
            row["repaired_risky_weight_drift"] = repaired_drift["actual_risky_weights"][ticker] - row["target_weight"]
        summary_rows.append({
            "frontier_role": role, "holding_count": int(frontier["holding_count"]),
            "tickers": frontier["tickers"], "weights": frontier["weights"],
            "risk_chain_weights": ";".join(f"{chain}:{weight:.10f}" for chain, weight in chain_ordered),
            "risk_chain_top1_name": chain_ordered[0][0],
            "risk_chain_top1_weight": chain_ordered[0][1],
            "risk_chain_count": len(chain_weights), "issuer_count": len(issuer_weights),
            "issuer_top1_weight": max(issuer_weights.values()),
            "target_top3_weight": target_concentration["top3_weight"],
            "target_effective_n": target_concentration["effective_n"],
            "incumbent_top1_weight": incumbent_concentration["top1_weight"],
            "incumbent_top3_weight": incumbent_concentration["top3_weight"],
            "incumbent_effective_n": incumbent_concentration["effective_n"],
            "top1_weight_delta_vs_original_8": target_concentration["top1_weight"] - incumbent_concentration["top1_weight"],
            "top3_weight_delta_vs_original_8": target_concentration["top3_weight"] - incumbent_concentration["top3_weight"],
            "effective_n_delta_vs_original_8": target_concentration["effective_n"] - incumbent_concentration["effective_n"],
            "risk_chain_delta_vs_original_8_status": incumbent_chain_delta_status,
            "portfolio_cash_usd": cash, "minimum_cash_buffer_usd": buffer,
            "whole_lot_invested_usd": invested, "whole_lot_residual_cash_usd": cash - invested,
            "whole_lot_deployment_ratio": drift["deployment_ratio"],
            "whole_lot_cash_weight": drift["cash_weight"],
            "whole_lot_risky_weight_l1_drift": drift["risky_weight_l1_drift"],
            "whole_lot_risky_weight_max_abs_drift": drift["risky_weight_max_abs_drift"],
            "whole_lot_risky_weight_max_abs_drift_ticker": drift["risky_weight_max_abs_drift_ticker"],
            "whole_lot_actual_top1_weight": actual_concentration["top1_weight"],
            "whole_lot_actual_top3_weight": actual_concentration["top3_weight"],
            "whole_lot_actual_effective_n": actual_concentration["effective_n"],
            "whole_lot_actual_risk_chain_top1_weight": actual_chain_top1,
            "whole_lot_risk_chain_top1_cap_preserved": actual_chain_top1 <= risk_chain_top1_cap + 1e-12,
            "repaired_whole_lot_invested_usd": sum(repaired_notionals.values()),
            "repaired_whole_lot_residual_cash_usd": cash - sum(repaired_notionals.values()),
            "repaired_whole_lot_deployment_ratio": repaired_drift["deployment_ratio"],
            "repaired_whole_lot_risky_weight_l1_drift": repaired_drift["risky_weight_l1_drift"],
            "repaired_whole_lot_risky_weight_max_abs_drift": repaired_drift["risky_weight_max_abs_drift"],
            "repaired_whole_lot_risky_weight_max_abs_drift_ticker": repaired_drift["risky_weight_max_abs_drift_ticker"],
            "repaired_whole_lot_actual_risk_chain_top1_weight": repaired_chain_top1,
            "repaired_whole_lot_risk_chain_top1_cap_preserved": repaired_chain_top1 <= risk_chain_top1_cap + 1e-12,
            "repaired_whole_lot_declared_constraints_passed": all(repaired_constraints.values()),
            "repaired_whole_lot_constraint_failures": ";".join(
                key for key, passed in repaired_constraints.items() if not passed
            ),
            "repaired_whole_lot_shares": ";".join(f"{ticker}:{repaired_shares[ticker]}" for ticker in sorted(repaired_shares)),
            "whole_lot_all_names_executable": all(shares >= 1 for shares in shares_by_ticker.values()),
            "whole_lot_shares": ";".join(f"{ticker}:{shares}" for ticker, shares in sorted(shares_by_ticker.items())),
            "return_p50": frontier["return_p50"], "return_p10": frontier["return_p10"],
            "max_drawdown_p50": frontier["max_drawdown_p50"],
            "max_drawdown_p90": frontier["max_drawdown_p90"],
            "paired_return_p50_vs_incumbent": frontier["paired_return_p50_vs_incumbent"],
            "paired_return_p10_vs_incumbent": frontier["paired_return_p10_vs_incumbent"],
            "paired_drawdown_cost_p50_vs_incumbent": frontier["paired_drawdown_cost_p50_vs_incumbent"],
            "paired_drawdown_cost_p90_vs_incumbent": frontier["paired_drawdown_cost_p90_vs_incumbent"],
            "target_012922_distance": frontier["target_012922_distance"],
            "initial_turnover": frontier["initial_turnover"],
        })
    positions = pd.DataFrame(position_rows)
    summaries = pd.DataFrame(summary_rows)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    position_path = output / "frontier_positions.csv"
    summary_path = output / "frontier_attribution.csv"
    incumbent_path = output / "original_8_strategy_baseline.csv"
    workbook_path = output / "ndx_cardinality_frontier_attribution.xlsx"
    _atomic_csv(positions, position_path)
    _atomic_csv(summaries, summary_path)
    _atomic_csv(incumbent_frame, incumbent_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summaries.to_excel(writer, sheet_name="前沿归因", index=False)
            positions.to_excel(writer, sheet_name="逐股整股回放", index=False)
            incumbent_frame.to_excel(writer, sheet_name="原始8只策略基线", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cross_cardinality_frontier_attribution",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_ATTRIBUTION_ONLY_NOT_ADMISSION",
        "selection_date": selection.date().isoformat(),
        "portfolio_cash_usd": cash, "minimum_cash_buffer_usd": buffer,
        "risk_chain_top1_cap": risk_chain_top1_cap,
        "max_single_weight": max_single_weight,
        "min_single_weight": min_single_weight,
        "top3_cap": top3_cap,
        "minimum_effective_n_ratio": minimum_effective_n_ratio,
        "whole_lot_repair_method": "DETERMINISTIC_CONSTRAINT_FIRST_GREEDY_NO_SALES_FROM_FLOOR",
        "frontier_count": len(summaries), "position_rows": len(positions),
        "point_in_time_risk_chain_used": True,
        "current_taxonomy_backfill_used": False,
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "personal_off_strategy_positions_included": False,
        "incumbent_point_in_time_risk_chain_count": incumbent_pit_chain_count,
        "incumbent_risk_chain_delta_status": incumbent_chain_delta_status,
        "fresh_oos_consumed": False, "promotion_allowed": False,
        "inputs": {
            "frontier_manifest": {"path": frontier_manifest_path.as_posix(), "sha256": file_sha256(frontier_manifest_path)},
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "frontiers": {"path": frontier_path.as_posix(), "sha256": file_sha256(frontier_path)},
            "discovery_manifest": {"path": discovery_manifest_path.as_posix(), "sha256": file_sha256(discovery_manifest_path)},
            "members": {"path": members_path.as_posix(), "sha256": file_sha256(members_path)},
            "state": {"path": state_path.as_posix(), "sha256": file_sha256(state_path)},
            "sources": source_inputs,
        },
        "artifacts": {
            "summary": {"path": summary_path.as_posix(), "rows": len(summaries), "sha256": file_sha256(summary_path)},
            "positions": {"path": position_path.as_posix(), "rows": len(positions), "sha256": file_sha256(position_path)},
            "incumbent_baseline": {"path": incumbent_path.as_posix(), "rows": len(incumbent_frame), "sha256": file_sha256(incumbent_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跨持仓数训练前沿风险链与整股归因")
    parser.add_argument("--frontier-manifest", default="data/cache/research/ndx_cross_cardinality_frontiers_v2/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--portfolio-cash-usd", type=float, default=5000.0)
    parser.add_argument("--minimum-cash-buffer-usd", type=float, default=100.0)
    parser.add_argument("--risk-chain-top1-cap", type=float)
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cross_cardinality_attribution_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"跨持仓数前沿归因失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"跨持仓数前沿归因完成 | frontiers={payload['frontier_count']} | "
        f"positions={payload['position_rows']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
