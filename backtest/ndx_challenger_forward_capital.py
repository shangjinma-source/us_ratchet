"""Mechanical capital-feasibility checks for frozen forward portfolios."""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from backtest.ndx_challenger_forward_cohort import _constraints
from backtest.ndx_local_action_execution import evaluate_local_action_execution


def audit_observation_capital(
    positions: pd.DataFrame,
    cash_levels: Iterable[float],
    *,
    minimum_cash_buffer: float,
) -> pd.DataFrame:
    """Audit fixed cash levels using observation-close inputs only.

    The input is an immutable cohort position snapshot.  No post-observation
    prices or returns are consumed, so the result can support a prospective
    execution-capital contract without selecting on outcomes.
    """
    required = {
        "observation_date", "registry_entry_id", "candidate_id", "track_role",
        "action_scope", "research_track", "holding_count_interpretation",
        "ticker", "risk_chain", "target_weight", "observation_close",
    }
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"cohort position columns are incomplete: {missing}")
    levels = sorted({float(value) for value in cash_levels})
    if not levels or levels[0] <= 0:
        raise ValueError("cash levels must be positive")

    rows = []
    for entry_id, group in positions.groupby("registry_entry_id", sort=True):
        identity = group.iloc[0]
        if group["observation_date"].astype(str).nunique() != 1:
            raise ValueError(f"mixed observation dates: {entry_id}")
        if group["ticker"].astype(str).duplicated().any():
            raise ValueError(f"duplicate ticker in cohort track: {entry_id}")
        weights = dict(zip(group["ticker"].astype(str), pd.to_numeric(group["target_weight"], errors="raise")))
        prices = dict(zip(group["ticker"].astype(str), pd.to_numeric(group["observation_close"], errors="raise")))
        chains = dict(zip(group["ticker"].astype(str), group["risk_chain"].astype(str)))
        one_share_threshold = max(prices[ticker] / weights[ticker] for ticker in weights) + float(minimum_cash_buffer)
        for cash in levels:
            try:
                result = evaluate_local_action_execution(
                    weights, prices, chains, cash=cash,
                    minimum_cash_buffer=float(minimum_cash_buffer),
                    **_constraints(str(identity["action_scope"])),
                )
            except ValueError as exc:
                if "positive invested notional and cash" not in str(exc):
                    raise
                result = {
                    "constraints_passed": False,
                    "constraint_failures": "no_feasible_positive_whole_lot_allocation",
                    "residual_cash_usd": cash,
                    "deployment_ratio": 0.0,
                }
            rows.append({
                "observation_date": str(identity["observation_date"]),
                "registry_entry_id": str(entry_id),
                "candidate_id": str(identity["candidate_id"]),
                "track_role": str(identity["track_role"]),
                "action_scope": str(identity["action_scope"]),
                "research_track": str(identity["research_track"]),
                "holding_count_interpretation": str(identity["holding_count_interpretation"]),
                "holding_count": len(weights),
                "cash_usd": cash,
                "one_share_weight_threshold_usd": one_share_threshold,
                "constraints_passed": bool(result["constraints_passed"]),
                "constraint_failures": str(result["constraint_failures"]),
                "residual_cash_usd": float(result["residual_cash_usd"]),
                "deployment_ratio": float(result["deployment_ratio"]),
                "return_data_read": False,
                "promotion_allowed": False,
            })
    return pd.DataFrame(rows)


__all__ = ["audit_observation_capital"]
