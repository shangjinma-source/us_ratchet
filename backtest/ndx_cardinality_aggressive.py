"""Deterministic compression for the pure-US-equity cardinality frontier."""
from __future__ import annotations

from collections.abc import Iterable
import hashlib

import numpy as np
import pandas as pd


class NdxCardinalityAggressiveError(ValueError):
    """Raised when aggressive-sleeve inputs violate the frozen contract."""


REQUIRED_COLUMNS = {
    "holding_count",
    "issuer_structure",
    "canonical_tickers",
    "worst_return_p50",
    "worst_return_p10",
    "worst_max_drawdown_p50",
    "worst_max_drawdown_p90",
    "worst_paired_return_p50_vs_incumbent",
    "worst_paired_return_p10_vs_incumbent",
    "worst_paired_drawdown_cost_p50_vs_incumbent",
    "worst_paired_drawdown_cost_p90_vs_incumbent",
    "worst_target_012922_distance",
}


def ticker_set(value: str) -> frozenset[str]:
    return frozenset(part.strip().upper() for part in str(value).split(";") if part.strip())


def mark_incumbent_risk_reward_pareto(structures: pd.DataFrame) -> pd.Series:
    """Return the four-dimensional Pareto mask without inventing a composite score."""
    missing = sorted(REQUIRED_COLUMNS - set(structures.columns))
    if missing:
        raise NdxCardinalityAggressiveError(f"common structures missing columns: {missing}")
    values = structures[
        [
            "worst_paired_return_p50_vs_incumbent",
            "worst_paired_return_p10_vs_incumbent",
            "worst_paired_drawdown_cost_p50_vs_incumbent",
            "worst_paired_drawdown_cost_p90_vs_incumbent",
        ]
    ].astype(float).to_numpy()
    if not np.isfinite(values).all():
        raise NdxCardinalityAggressiveError("non-finite risk/return value in common structures")
    keep = np.ones(len(values), dtype=bool)
    for index, row in enumerate(values):
        no_worse = (
            (values[:, 0] >= row[0])
            & (values[:, 1] >= row[1])
            & (values[:, 2] <= row[2])
            & (values[:, 3] <= row[3])
        )
        strictly_better = (
            (values[:, 0] > row[0])
            | (values[:, 1] > row[1])
            | (values[:, 2] < row[2])
            | (values[:, 3] < row[3])
        )
        if np.any(no_worse & strictly_better):
            keep[index] = False
    return pd.Series(keep, index=structures.index, name="incumbent_risk_reward_pareto")


def compress_aggressive_shortlist(
    structures: pd.DataFrame,
    *,
    preference_tickers: Iterable[str],
    per_role: int = 3,
) -> pd.DataFrame:
    """Keep transparent role leaders plus the user's explicitly named anchor."""
    if per_role <= 0:
        raise NdxCardinalityAggressiveError("per_role must be positive")
    frame = structures.copy()
    frame["incumbent_risk_reward_pareto"] = mark_incumbent_risk_reward_pareto(frame)
    pareto = frame.loc[frame["incumbent_risk_reward_pareto"]].copy()
    roles = {
        "RETURN": (
            pareto,
            ["worst_paired_return_p50_vs_incumbent", "worst_paired_return_p10_vs_incumbent", "worst_paired_drawdown_cost_p90_vs_incumbent", "holding_count", "issuer_structure"],
            [False, False, True, True, True],
        ),
        "BAD_TAIL": (
            pareto,
            ["worst_paired_return_p10_vs_incumbent", "worst_paired_return_p50_vs_incumbent", "worst_paired_drawdown_cost_p90_vs_incumbent", "holding_count", "issuer_structure"],
            [False, False, True, True, True],
        ),
        "DRAWDOWN": (
            pareto,
            ["worst_paired_drawdown_cost_p90_vs_incumbent", "worst_paired_drawdown_cost_p50_vs_incumbent", "worst_paired_return_p10_vs_incumbent", "holding_count", "issuer_structure"],
            [True, True, False, True, True],
        ),
        "012922_DISTANCE": (
            frame,
            ["worst_target_012922_distance", "worst_paired_return_p10_vs_incumbent", "worst_paired_drawdown_cost_p90_vs_incumbent", "holding_count", "issuer_structure"],
            [True, False, True, True, True],
        ),
    }
    rows: list[pd.Series] = []
    for role, (source, columns, ascending) in roles.items():
        selected = source.sort_values(columns, ascending=ascending, kind="stable").head(per_role)
        for rank, (_, row) in enumerate(selected.iterrows(), start=1):
            item = row.copy()
            item["selection_role"] = role
            item["role_rank"] = rank
            rows.append(item)

    preferred = frozenset(str(value).upper() for value in preference_tickers)
    matches = frame.loc[frame["canonical_tickers"].map(ticker_set).eq(preferred)]
    if len(matches) != 1:
        raise NdxCardinalityAggressiveError(
            f"preference anchor must match exactly one issuer structure, got {len(matches)}"
        )
    anchor = matches.iloc[0].copy()
    anchor["selection_role"] = "USER_PREFERENCE"
    anchor["role_rank"] = 1
    rows.append(anchor)
    result = pd.DataFrame(rows).reset_index(drop=True)
    result.insert(0, "candidate_id", result["issuer_structure"].map(
        lambda value: "COMMON_" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
    ))
    result.insert(1, "portfolio_scope", "HSBC_US_EQUITY_SLEEVE_ONLY")
    result.insert(2, "safe_leg_included", False)
    result.insert(3, "external_index_included", False)
    result["promotion_allowed"] = False
    result["result_status"] = "REUSED_TRAINING_SHORTLIST_ONLY_NOT_ADMISSION"
    return result


def compress_local_action_families(stability: pd.DataFrame) -> pd.DataFrame:
    """Select one transparent leader per metric role for each local action family."""
    required = {
        "structure_key", "operation", "worst_paired_return_p50", "worst_paired_return_p10",
        "worst_paired_drawdown_cost_p50", "worst_paired_drawdown_cost_p90",
        "median_target_012922_distance", "holding_count", "turnover",
    }
    missing = sorted(required - set(stability.columns))
    if missing:
        raise NdxCardinalityAggressiveError(f"local stability missing columns: {missing}")
    frame = stability.copy()
    frame["action_family"] = np.select(
        [
            frame["operation"].astype(str).str.startswith("ADD_"),
            frame["operation"].eq("SINGLE_REPLACE"),
            frame["operation"].eq("DOUBLE_REPLACE"),
        ],
        ["ADD_ONLY", "SINGLE_REPLACEMENT", "DOUBLE_REPLACEMENT"],
        default="OUT_OF_SCOPE",
    )
    frame = frame.loc[frame["action_family"].ne("OUT_OF_SCOPE")].copy()
    selectors = {
        "RETURN": (
            ["worst_paired_return_p50", "worst_paired_return_p10", "worst_paired_drawdown_cost_p90", "turnover", "structure_key"],
            [False, False, True, True, True],
        ),
        "BAD_TAIL": (
            ["worst_paired_return_p10", "worst_paired_return_p50", "worst_paired_drawdown_cost_p90", "turnover", "structure_key"],
            [False, False, True, True, True],
        ),
        "DRAWDOWN": (
            ["worst_paired_drawdown_cost_p90", "worst_paired_drawdown_cost_p50", "worst_paired_return_p10", "turnover", "structure_key"],
            [True, True, False, True, True],
        ),
        "012922_DISTANCE": (
            ["median_target_012922_distance", "worst_paired_return_p10", "worst_paired_drawdown_cost_p90", "turnover", "structure_key"],
            [True, False, True, True, True],
        ),
    }
    rows = []
    for family, family_rows in frame.groupby("action_family", sort=True):
        for role, (columns, ascending) in selectors.items():
            row = family_rows.sort_values(columns, ascending=ascending, kind="stable").iloc[0].copy()
            row["selection_role"] = role
            rows.append(row)
    result = pd.DataFrame(rows).reset_index(drop=True)
    result.insert(0, "candidate_id", result["structure_key"].map(
        lambda value: "LOCAL_" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
    ))
    result["portfolio_scope"] = "HSBC_US_EQUITY_SLEEVE_ONLY"
    result["safe_leg_included"] = False
    result["external_index_included"] = False
    result["promotion_allowed"] = False
    return result
