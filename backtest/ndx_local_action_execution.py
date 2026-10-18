"""Whole-share execution checks for frozen local challenger selections."""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from backtest.ndx_cardinality_aggressive import compress_local_action_families
from scripts.ndx_cardinality_frontier_attribution import (
    concentration_metrics,
    repair_whole_lot_allocation,
    whole_lot_weight_drift,
)


def evaluate_local_action_execution(
    weights: Mapping[str, float],
    prices: Mapping[str, float],
    risk_chains: Mapping[str, str],
    *,
    cash: float,
    minimum_cash_buffer: float,
    min_single_weight: float,
    max_single_weight: float,
    top3_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict:
    """Return a deterministic whole-share audit without selecting a candidate."""

    target = {str(ticker): float(weight) for ticker, weight in weights.items()}
    if set(target) != set(prices) or set(target) != set(risk_chains):
        raise ValueError("weights, prices and risk chains must cover the same tickers")
    if any(float(value) <= 0 for value in prices.values()):
        raise ValueError("execution prices must be positive")
    if any(not str(value).strip() for value in risk_chains.values()):
        raise ValueError("execution risk chains must be classified")

    shares = repair_whole_lot_allocation(
        target, dict(prices), dict(risk_chains), cash=cash,
        minimum_cash_buffer=minimum_cash_buffer,
        risk_chain_top1_cap=risk_chain_top1_cap,
        min_single_weight=min_single_weight, max_single_weight=max_single_weight,
        top3_cap=top3_cap, minimum_effective_n_ratio=minimum_effective_n_ratio,
    )
    notionals = {ticker: shares[ticker] * float(prices[ticker]) for ticker in target}
    drift = whole_lot_weight_drift(target, notionals, cash)
    concentration = concentration_metrics(drift["actual_risky_weights"])
    chain_weights: dict[str, float] = {}
    for ticker, weight in drift["actual_risky_weights"].items():
        chain = str(risk_chains[ticker])
        chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
    chain_top1 = max(chain_weights.values())
    residual = cash - sum(notionals.values())
    checks = {
        "whole_lot": all(value >= 1 for value in shares.values()),
        "min_single": min(drift["actual_risky_weights"].values()) >= min_single_weight - 1e-12,
        "max_single": concentration["top1_weight"] <= max_single_weight + 1e-12,
        "top3": concentration["top3_weight"] <= top3_cap + 1e-12,
        "effective_n": concentration["effective_n"] >= len(target) * minimum_effective_n_ratio - 1e-12,
        "risk_chain_top1": chain_top1 <= risk_chain_top1_cap + 1e-12,
        "cash_buffer": residual >= minimum_cash_buffer - 1e-9,
    }
    return {
        "constraints_passed": all(checks.values()),
        "constraint_failures": ";".join(key for key, passed in checks.items() if not passed),
        "shares": shares,
        "notionals": notionals,
        "invested_usd": sum(notionals.values()),
        "residual_cash_usd": residual,
        "deployment_ratio": drift["deployment_ratio"],
        "risky_weight_l1_drift": drift["risky_weight_l1_drift"],
        "risky_weight_max_abs_drift": drift["risky_weight_max_abs_drift"],
        "actual_risky_weights": drift["actual_risky_weights"],
        "actual_top1_weight": concentration["top1_weight"],
        "actual_top3_weight": concentration["top3_weight"],
        "actual_effective_n": concentration["effective_n"],
        "actual_risk_chain_top1_weight": chain_top1,
        "risk_chain_weights": chain_weights,
    }


def select_execution_aware_local_leaders(
    stability: pd.DataFrame,
    execution_audit: pd.DataFrame,
) -> pd.DataFrame:
    """Keep metric-first controls and select fallbacks only when execution fails."""

    required = {"structure_key", "execution_eligible"}
    if not required.issubset(execution_audit.columns):
        raise ValueError("local execution audit is incomplete")
    if execution_audit["structure_key"].duplicated().any():
        raise ValueError("local execution audit contains duplicate structures")
    original = compress_local_action_families(stability)
    eligible_keys = set(execution_audit.loc[
        execution_audit["execution_eligible"].astype(bool), "structure_key"
    ].astype(str))
    filtered = stability.loc[stability["structure_key"].astype(str).isin(eligible_keys)].copy()
    selected = compress_local_action_families(filtered)
    if set(zip(selected["action_family"], selected["selection_role"])) != set(
        zip(original["action_family"], original["selection_role"])
    ):
        raise ValueError("an action family lost all execution-compliant role candidates")
    original_keys = original.set_index(["action_family", "selection_role"])["structure_key"].to_dict()
    selected["metric_first_structure_key"] = selected.apply(
        lambda row: original_keys[(row["action_family"], row["selection_role"])], axis=1,
    )
    selected["metric_first_was_executable"] = selected["metric_first_structure_key"].isin(eligible_keys)
    selected["fallback_used"] = selected["structure_key"].ne(selected["metric_first_structure_key"])
    selected["selection_status"] = selected["fallback_used"].map({
        True: "EXECUTION_COMPLIANT_FALLBACK",
        False: "METRIC_FIRST_ALREADY_EXECUTABLE",
    })
    selected["promotion_allowed"] = False
    return selected
