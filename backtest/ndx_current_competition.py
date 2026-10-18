"""Current-security quality and price competition for v11 stage 1.

This is a research ranking layer, not an admission or live-allocation rule.  It
uses the frozen quality policy and the existing attack-score definition, then
ranks accepted challengers inside each reviewed risk chain.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from backtest.ndx_marginal_stage1 import INCUMBENTS, NdxMarginalStage1Error
from backtest.ndx_quality import (
    BALANCE_FACTORS,
    CORE_FACTORS,
    DIAGNOSTIC_FACTORS,
    GROWTH_FACTORS,
    PROFITABILITY_FACTORS,
    QUALITY_POLICY_ID,
    QualityPolicy,
    _factor_percentiles,
)
from backtest.preference_walkforward import _metrics_asof
from backtest.ndx_current_valuation import attach_overpay_guard


CURRENT_COMPETITION_POLICY_ID = (
    "ndx_v11_price_overpay_guard_then_quality_within_risk_chain_v2"
)


def build_current_quality_scores(
    factor_inputs: pd.DataFrame,
    *,
    policy: QualityPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score current factor inputs without inventing unavailable SIC evidence."""
    selected = policy or QualityPolicy()
    selected.validate()
    required = {"selection_date", "ticker", "cik"}
    for factor in CORE_FACTORS + DIAGNOSTIC_FACTORS:
        required.update({factor, f"{factor}_status"})
    missing = sorted(required - set(factor_inputs.columns))
    if missing:
        raise NdxMarginalStage1Error(f"quality factor columns missing: {missing}")
    factors = factor_inputs.drop_duplicates(["selection_date", "ticker"]).copy()
    if len(factors) != len(factor_inputs):
        raise NdxMarginalStage1Error("duplicate current quality ticker/date rows")

    score_frames: list[pd.DataFrame] = []
    audit_rows: list[dict] = []
    for _, group in factors.groupby("selection_date", sort=True):
        group = group.copy()
        for factor in CORE_FACTORS + DIAGNOSTIC_FACTORS:
            percentile, audit = _factor_percentiles(group, factor, selected)
            group[f"{factor}_percentile"] = percentile
            audit_rows.extend(audit)
        group["core_factor_count"] = group[
            [f"{factor}_percentile" for factor in CORE_FACTORS]
        ].notna().sum(axis=1)
        group["profitability_factor_count"] = group[
            [f"{factor}_percentile" for factor in PROFITABILITY_FACTORS]
        ].notna().sum(axis=1)
        group["balance_factor_count"] = group[
            [f"{factor}_percentile" for factor in BALANCE_FACTORS]
        ].notna().sum(axis=1)
        group["growth_sleeve"] = group[
            [f"{factor}_percentile" for factor in GROWTH_FACTORS]
        ].mean(axis=1, skipna=False)
        group["profitability_sleeve"] = group[
            [f"{factor}_percentile" for factor in PROFITABILITY_FACTORS]
        ].mean(axis=1, skipna=True)
        group["balance_sleeve"] = group[
            [f"{factor}_percentile" for factor in BALANCE_FACTORS]
        ].mean(axis=1, skipna=True)
        group["quality_eligible"] = (
            group["core_factor_count"].ge(selected.minimum_core_factors)
            & group["growth_sleeve"].notna()
            & group["profitability_factor_count"].ge(selected.minimum_profitability_factors)
            & group["balance_factor_count"].ge(selected.required_balance_factors)
        )
        group["quality_score"] = np.where(
            group["quality_eligible"],
            100.0 * (
                selected.sleeve_weight_growth * group["growth_sleeve"]
                + selected.sleeve_weight_profitability * group["profitability_sleeve"]
                + selected.sleeve_weight_balance * group["balance_sleeve"]
            ),
            np.nan,
        )
        group["quality_confidence"] = np.where(
            ~group["quality_eligible"],
            "rejected",
            np.where(group["core_factor_count"].eq(len(CORE_FACTORS)), "high", "medium"),
        )
        group["quality_policy_id"] = QUALITY_POLICY_ID
        score_frames.append(group)
    scores = pd.concat(score_frames, ignore_index=True)
    coverage = scores.groupby("selection_date").agg(
        universe_count=("ticker", "size"),
        eligible_count=("quality_eligible", "sum"),
        score_coverage=("quality_eligible", "mean"),
        high_confidence_count=("quality_confidence", lambda x: int(x.eq("high").sum())),
        medium_confidence_count=("quality_confidence", lambda x: int(x.eq("medium").sum())),
    ).reset_index()
    return scores, pd.DataFrame(audit_rows), coverage


def load_local_price_series(
    tickers: list[str],
    *,
    cache_dir: Path,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    series: dict[str, pd.DataFrame] = {}
    rows: list[dict] = []
    for ticker in sorted(set(tickers)):
        path = cache_dir / f"{ticker}.csv"
        if not path.exists():
            rows.append({"ticker": ticker, "path": path.as_posix(), "status": "missing"})
            continue
        frame = pd.read_csv(path)
        required = {"Date", "Close"}
        if not required.issubset(frame.columns):
            rows.append({"ticker": ticker, "path": path.as_posix(), "status": "invalid_columns"})
            continue
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
        frame = frame.dropna(subset=["Date", "Close"]).drop_duplicates("Date").sort_values("Date")
        series[ticker] = frame.set_index("Date")[["Close"]]
        rows.append({
            "ticker": ticker,
            "path": path.as_posix(),
            "status": "ready",
            "rows": len(frame),
            "data_start": frame["Date"].min().strftime("%Y-%m-%d"),
            "data_end": frame["Date"].max().strftime("%Y-%m-%d"),
        })
    return series, pd.DataFrame(rows)


def build_current_competition(
    taxonomy: pd.DataFrame,
    quality_scores: pd.DataFrame,
    price_series: Mapping[str, pd.DataFrame],
    *,
    selection_date: str = "2026-07-13",
    lookback_days: int = 756,
    min_history_days: int = 757,
    valuation_scores: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return all-security audit and one risk-chain champion per chain."""
    selection = pd.Timestamp(selection_date)
    metrics = _metrics_asof(
        price_series,
        selection,
        lookback_days=lookback_days,
        min_history_days=min_history_days,
    ).reset_index(drop=True)
    if not metrics.empty and (pd.to_datetime(metrics["asof_date"]) >= selection).any():
        raise NdxMarginalStage1Error("price future-data guard failed")
    quality = quality_scores.loc[
        quality_scores["selection_date"].astype(str).eq(selection_date),
        ["ticker", "quality_score", "quality_eligible", "quality_confidence", "quality_policy_id"],
    ]
    frame = taxonomy.merge(quality, on="ticker", how="left", validate="one_to_one")
    frame = frame.merge(metrics, on="ticker", how="left", validate="one_to_one")
    frame["selection_date"] = selection_date
    incumbent_issuers = set(frame.loc[frame["ticker"].isin(INCUMBENTS), "issuer_id"].astype(str))
    frame["is_incumbent"] = frame["ticker"].isin(INCUMBENTS)
    frame["issuer_already_incumbent"] = frame["issuer_id"].astype(str).isin(incumbent_issuers)
    frame["taxonomy_accepted"] = frame["status"].eq("accepted")
    frame["price_score_ready"] = frame["attack_score"].notna()
    frame["competition_eligible"] = (
        ~frame["is_incumbent"]
        & ~frame["issuer_already_incumbent"]
        & frame["taxonomy_accepted"]
        & frame["quality_eligible"].fillna(False)
        & frame["price_score_ready"]
    )
    blockers = []
    for row in frame.to_dict("records"):
        reasons = []
        if row["is_incumbent"]:
            reasons.append("INCUMBENT_FROZEN")
        elif row["issuer_already_incumbent"]:
            reasons.append("ISSUER_ALREADY_PRESENT_IN_INCUMBENT")
        if not row["taxonomy_accepted"]:
            reasons.append("RISK_CHAIN_UNCLASSIFIED_OR_UNACCEPTED")
        if not bool(row.get("quality_eligible")):
            reasons.append("QUALITY_SCORE_NOT_ELIGIBLE")
        if not row["price_score_ready"]:
            reasons.append("STRICT_PRIOR_PRICE_HISTORY_NOT_READY")
        blockers.append(";".join(reasons))
    frame["competition_blockers"] = blockers
    if valuation_scores is not None:
        frame = attach_overpay_guard(
            frame, valuation_scores, selection_date=selection_date
        )
    else:
        frame["valuation_guarded_price_score"] = frame["attack_score"]
        frame["valuation_guard_ready"] = False
    frame["risk_chain_price_rank"] = np.nan
    frame["risk_chain_quality_rank"] = np.nan
    eligible = frame.loc[frame["competition_eligible"]].copy()
    eligible["risk_chain_price_rank"] = eligible.groupby("risk_chain")[
        "valuation_guarded_price_score"
    ].rank(
        method="first", ascending=False
    )
    eligible["risk_chain_quality_rank"] = eligible.groupby("risk_chain")["quality_score"].rank(
        method="first", ascending=False
    )
    frame.update(eligible[["risk_chain_price_rank", "risk_chain_quality_rank"]])
    champions = eligible.sort_values(
        [
            "risk_chain", "valuation_guarded_price_score", "attack_score",
            "quality_score", "ticker",
        ],
        ascending=[True, False, False, False, True],
    ).groupby("risk_chain", as_index=False).head(1)
    champions = champions.sort_values(
        ["valuation_guarded_price_score", "attack_score", "quality_score", "ticker"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    champions.insert(0, "shortlist_rank", range(1, len(champions) + 1))
    champions["selection_policy_id"] = CURRENT_COMPETITION_POLICY_ID
    champions["admission_status"] = "RESEARCH_SHORTLIST_ONLY_NOT_ADMITTED"
    champions["admission_blockers"] = (
        "FRESH_OOS_NOT_AVAILABLE;EXACT_NDX_EVENT_EXECUTION_BLOCKED;"
        "HSBC_TRADABILITY_UNVERIFIED"
        if valuation_scores is not None else
        "VALUATION_OVERPAY_GUARD_NOT_READY;FRESH_OOS_NOT_AVAILABLE;"
        "EXACT_NDX_EVENT_EXECUTION_BLOCKED;HSBC_TRADABILITY_UNVERIFIED"
    )
    frame["selection_policy_id"] = CURRENT_COMPETITION_POLICY_ID
    return frame, champions
