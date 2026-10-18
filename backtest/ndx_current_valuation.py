"""Current point-in-time valuation guard for the v11 NDX competition.

The module consumes SEC accounting evidence and a separately versioned raw
nominal-price basis.  It never reads returns and never enables live admission.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.ndx_valuation_diagnostics import calculate_valuation_values
from data.ndx_valuation_readiness import build_valuation_factor_readiness
from data.ndx_valuation_score import (
    VALUATION_OVERPAY_GUARD_POLICY_ID,
    ValuationScorePolicy,
    build_overpay_guard_scores,
)


CURRENT_VALUATION_POLICY_ID = "ndx_v11_current_fcf_overpay_guard_v1"
OVERPAY_PENALTY_QUANTILE = 0.30
VALUATION_WEIGHT = 0.10


class NdxCurrentValuationError(ValueError):
    pass


def _assert_current_universe(
    frame: pd.DataFrame, label: str, *, require_cik: bool = True
) -> None:
    required = {"selection_date", "ticker"}
    if require_cik:
        required.add("cik")
    missing = sorted(required - set(frame.columns))
    if missing:
        raise NdxCurrentValuationError(f"{label} lacks columns: {missing}")
    if frame.duplicated(["selection_date", "ticker"]).any():
        raise NdxCurrentValuationError(f"{label} contains duplicate date/ticker rows")


def build_current_valuation_guard(
    current_readiness: pd.DataFrame,
    factor_inputs: pd.DataFrame,
    raw_prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return readiness, values, frozen one-sided scores, and coverage."""
    _assert_current_universe(current_readiness, "current readiness")
    _assert_current_universe(factor_inputs, "factor inputs")
    _assert_current_universe(raw_prices, "raw prices", require_cik=False)
    keys = ["selection_date", "ticker"]
    expected = set(map(tuple, current_readiness[keys].astype(str).to_numpy()))
    for frame, label in ((factor_inputs, "factor inputs"), (raw_prices, "raw prices")):
        actual = set(map(tuple, frame[keys].astype(str).to_numpy()))
        if actual != expected:
            raise NdxCurrentValuationError(f"{label} universe differs from readiness")

    factor_columns = {
        "selection_date", "ticker", "cik", "revenue_value", "revenue_unit",
        "operating_cash_flow_value", "operating_cash_flow_unit",
        "capital_expenditure_value", "capital_expenditure_unit", "cash_value",
        "cash_unit", "free_cash_flow_margin_status", "revenue_growth_status",
    }
    price_columns = {
        "selection_date", "ticker", "price_ready", "price_future_data_guard_passed",
        "price_status", "price", "price_date", "price_age_days",
    }
    missing_factors = sorted(factor_columns - set(factor_inputs.columns))
    missing_prices = sorted(price_columns - set(raw_prices.columns))
    if missing_factors or missing_prices:
        raise NdxCurrentValuationError(
            f"valuation inputs incomplete: factors={missing_factors}, prices={missing_prices}"
        )
    overlapping = (factor_columns | price_columns) - {"selection_date", "ticker", "cik"}
    accounting = current_readiness.drop(
        columns=[column for column in overlapping if column in current_readiness.columns]
    ).copy()
    multi = set(
        current_readiness.loc[
            current_readiness.get("multi_security_issuer", False)
            .fillna(False).astype(bool), "ticker"
        ].astype(str)
    ) if "multi_security_issuer" in current_readiness.columns else set()
    readiness = build_valuation_factor_readiness(
        accounting,
        factor_inputs[sorted(factor_columns)],
        raw_prices[sorted(price_columns)],
        multi_security_tickers=multi,
        price_basis_ready=True,
    )
    values = calculate_valuation_values(readiness)
    scores, coverage = build_overpay_guard_scores(
        values,
        policy=ValuationScorePolicy(),
        penalty_quantile=OVERPAY_PENALTY_QUANTILE,
    )
    if coverage.empty or not coverage["factor_active"].astype(bool).all():
        raise NdxCurrentValuationError(
            "current FCF Yield coverage does not activate the frozen valuation factor"
        )
    if scores["return_data_read"].astype(bool).any():
        raise NdxCurrentValuationError("valuation guard unexpectedly read return data")
    if not scores["valuation_policy_id"].eq(
        VALUATION_OVERPAY_GUARD_POLICY_ID
    ).all():
        raise NdxCurrentValuationError("valuation policy identity changed")
    if pd.to_numeric(scores["valuation_score"], errors="raise").gt(50.0).any():
        raise NdxCurrentValuationError("valuation guard rewards cheap securities")

    scores["current_valuation_policy_id"] = CURRENT_VALUATION_POLICY_ID
    scores["valuation_score_generated"] = True
    scores["valuation_score_allowed"] = True
    scores["candidate_admission_allowed"] = False
    scores["live_scoring_allowed"] = False
    scores["valuation_weight"] = VALUATION_WEIGHT
    scores["valuation_blockers"] = np.where(
        scores["valuation_missing_neutral_applied"].astype(bool),
        "FCF_YIELD_MISSING_NEUTRAL_50_APPLIED",
        "",
    )
    return readiness, values, scores, coverage


def attach_overpay_guard(
    competition: pd.DataFrame,
    valuation_scores: pd.DataFrame,
    *,
    selection_date: str,
) -> pd.DataFrame:
    """Apply the frozen v10 10% guard without turning quality into a grid."""
    required = {
        "selection_date", "ticker", "valuation_score", "valuation_policy_id",
        "valuation_factor_active", "valuation_missing_neutral_applied",
        "valuation_cheap_reward_allowed",
    }
    missing = sorted(required - set(valuation_scores.columns))
    if missing:
        raise NdxCurrentValuationError(f"valuation scores lack columns: {missing}")
    selected = valuation_scores.loc[
        valuation_scores["selection_date"].astype(str).eq(selection_date),
        list(required),
    ].copy()
    if len(selected) != len(competition) or selected["ticker"].duplicated().any():
        raise NdxCurrentValuationError("valuation score coverage is not one-to-one")
    if not selected["valuation_policy_id"].eq(
        VALUATION_OVERPAY_GUARD_POLICY_ID
    ).all():
        raise NdxCurrentValuationError("valuation policy identity changed")
    if not selected["valuation_factor_active"].astype(bool).all():
        raise NdxCurrentValuationError("valuation factor is inactive")
    if selected["valuation_cheap_reward_allowed"].astype(bool).any():
        raise NdxCurrentValuationError("cheap reward is unexpectedly enabled")
    score = pd.to_numeric(selected["valuation_score"], errors="raise")
    if score.lt(0.0).any() or score.gt(50.0).any():
        raise NdxCurrentValuationError("valuation score escapes the one-sided [0, 50] guard")
    selected["valuation_score"] = score
    output = competition.merge(
        selected.drop(columns="selection_date"), on="ticker", how="left", validate="one_to_one"
    )
    attack = pd.to_numeric(output["attack_score"], errors="coerce")
    valuation = pd.to_numeric(output["valuation_score"], errors="coerce")
    output["valuation_guard_weight"] = VALUATION_WEIGHT
    normalized_valuation = valuation / 100.0
    output["valuation_guard_score_normalized"] = normalized_valuation
    output["valuation_guard_penalty_attack_equivalent"] = (
        (0.50 - normalized_valuation)
        * VALUATION_WEIGHT
        / (1.0 - VALUATION_WEIGHT)
    )
    output["valuation_guarded_price_score"] = (
        (1.0 - VALUATION_WEIGHT) * attack
        + VALUATION_WEIGHT * normalized_valuation
    )
    output["valuation_guard_ready"] = valuation.notna()
    return output
