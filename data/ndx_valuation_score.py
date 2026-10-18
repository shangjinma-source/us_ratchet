"""Frozen neutral-missing valuation score contract for NDX research."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


VALUATION_SCORE_POLICY_ID = "ndx_fcf_yield_neutral_missing_v1"
VALUATION_OVERPAY_GUARD_POLICY_ID = "ndx_fcf_yield_overpay_guard_v1"
SUPPORTED_VALUATION_SCORE_POLICY_IDS = {
    VALUATION_SCORE_POLICY_ID,
    VALUATION_OVERPAY_GUARD_POLICY_ID,
}


class NdxValuationScoreError(ValueError):
    pass


@dataclass(frozen=True)
class ValuationScorePolicy:
    winsor_lower: float = 0.05
    winsor_upper: float = 0.95
    minimum_factor_coverage: float = 0.70
    minimum_observations: int = 20
    missing_neutral_score: float = 50.0

    def validate(self) -> None:
        if not 0 <= self.winsor_lower < self.winsor_upper <= 1:
            raise NdxValuationScoreError("winsor bounds are invalid")
        if not 0 < self.minimum_factor_coverage <= 1:
            raise NdxValuationScoreError("minimum factor coverage must be in (0, 1]")
        if self.minimum_observations < 2:
            raise NdxValuationScoreError("minimum observations must be at least 2")
        if not 0 <= self.missing_neutral_score <= 100:
            raise NdxValuationScoreError("neutral score must be in [0, 100]")


def _as_bool(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(bool)
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def build_neutral_missing_scores(
    values: pd.DataFrame,
    *,
    policy: ValuationScorePolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank observed FCF Yield and assign exactly neutral scores to missing rows."""
    selected = policy or ValuationScorePolicy()
    selected.validate()
    required = {
        "selection_date",
        "ticker",
        "cik",
        "fcf_yield_value",
        "fcf_yield_value_ready",
        "ev_sales_value_ready",
    }
    if not required.issubset(values.columns):
        raise NdxValuationScoreError(
            f"valuation values lack {sorted(required - set(values.columns))}"
        )
    if values.duplicated(["selection_date", "ticker"]).any():
        raise NdxValuationScoreError("valuation values contain duplicate keys")
    output = []
    coverage_rows = []
    for selection_date, raw_group in values.groupby("selection_date", sort=True):
        group = raw_group.copy()
        raw_values = pd.to_numeric(group["fcf_yield_value"], errors="coerce")
        ready = _as_bool(group["fcf_yield_value_ready"]) & raw_values.map(np.isfinite)
        observed_count = int(ready.sum())
        universe_count = len(group)
        coverage = observed_count / universe_count if universe_count else 0.0
        active = bool(
            coverage >= selected.minimum_factor_coverage
            and observed_count >= selected.minimum_observations
        )
        group["fcf_yield_observed"] = ready
        group["fcf_yield_missing"] = ~ready
        group["fcf_yield_winsorized"] = np.nan
        group["fcf_yield_score"] = float(selected.missing_neutral_score)
        if active:
            observed = raw_values[ready]
            lower = float(observed.quantile(selected.winsor_lower))
            upper = float(observed.quantile(selected.winsor_upper))
            winsorized = observed.clip(lower=lower, upper=upper)
            ranks = winsorized.rank(method="average")
            scores = (ranks - 1.0) / (observed_count - 1.0) * 100.0
            group.loc[ready, "fcf_yield_winsorized"] = winsorized
            group.loc[ready, "fcf_yield_score"] = scores
        else:
            lower = np.nan
            upper = np.nan
        group["valuation_score"] = group["fcf_yield_score"]
        group["valuation_factor_active"] = active
        group["valuation_factor_coverage"] = coverage
        group["valuation_missing_neutral_score"] = float(
            selected.missing_neutral_score
        )
        group["valuation_missing_neutral_applied"] = ~ready
        group["valuation_policy_id"] = VALUATION_SCORE_POLICY_ID
        group["ev_sales_included_in_score"] = False
        group["return_data_read"] = False
        group["training_spec_generation_allowed"] = False
        group["live_scoring_allowed"] = False
        observed_score_median = (
            float(group.loc[ready, "valuation_score"].median())
            if active else float(selected.missing_neutral_score)
        )
        neutral_matches_median = bool(
            np.isclose(
                observed_score_median,
                float(selected.missing_neutral_score),
                rtol=0.0,
                atol=1e-10,
            )
        )
        output.append(group)
        ev_ready = int(_as_bool(group["ev_sales_value_ready"]).sum())
        coverage_rows.append({
            "selection_date": str(selection_date)[:10],
            "universe_count": universe_count,
            "fcf_yield_observed_count": observed_count,
            "fcf_yield_coverage": coverage,
            "factor_active": active,
            "winsor_lower_value": lower,
            "winsor_upper_value": upper,
            "missing_neutral_count": int((~ready).sum()),
            "missing_neutral_score": float(selected.missing_neutral_score),
            "observed_score_median": observed_score_median,
            "neutral_matches_observed_median": neutral_matches_median,
            "ev_sales_ready_count_diagnostic_only": ev_ready,
            "ev_sales_coverage_diagnostic_only": (
                ev_ready / universe_count if universe_count else 0.0
            ),
        })
    scores = pd.concat(output, ignore_index=True).sort_values(
        ["selection_date", "ticker"], kind="stable"
    ).reset_index(drop=True)
    missing = scores["valuation_missing_neutral_applied"].astype(bool)
    if not scores.loc[missing, "valuation_score"].eq(
        float(selected.missing_neutral_score)
    ).all():
        raise NdxValuationScoreError("missing values are not exactly neutral")
    if not pd.to_numeric(scores["valuation_score"], errors="coerce").between(
        0, 100, inclusive="both"
    ).all():
        raise NdxValuationScoreError("valuation scores escape [0, 100]")
    coverage = pd.DataFrame(coverage_rows)
    if not coverage["neutral_matches_observed_median"].astype(bool).all():
        raise NdxValuationScoreError("neutral score differs from observed median")
    return scores, coverage


def build_overpay_guard_scores(
    values: pd.DataFrame,
    *,
    policy: ValuationScorePolicy | None = None,
    penalty_quantile: float = 0.30,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Penalize only the lowest FCF Yield ranks; never reward cheap stocks."""
    if not 0.0 < float(penalty_quantile) < 0.5:
        raise NdxValuationScoreError("overpay penalty quantile must be in (0, 0.5)")
    scores, coverage = build_neutral_missing_scores(values, policy=policy)
    threshold = float(penalty_quantile) * 100.0
    observed = scores["fcf_yield_observed"].astype(bool)
    full_rank = pd.to_numeric(scores["fcf_yield_score"], errors="raise")
    guard = (full_rank / threshold * 50.0).clip(lower=0.0, upper=50.0)
    scores["fcf_yield_full_rank_diagnostic"] = full_rank
    scores["fcf_yield_overpay_guard_score"] = 50.0
    scores.loc[observed, "fcf_yield_overpay_guard_score"] = guard[observed]
    scores["fcf_yield_score"] = scores["fcf_yield_overpay_guard_score"]
    scores["valuation_score"] = scores["fcf_yield_overpay_guard_score"]
    scores["valuation_policy_id"] = VALUATION_OVERPAY_GUARD_POLICY_ID
    scores["valuation_overpay_penalty_quantile"] = float(penalty_quantile)
    scores["valuation_cheap_reward_allowed"] = False
    missing = scores["valuation_missing_neutral_applied"].astype(bool)
    if not scores.loc[missing, "valuation_score"].eq(50.0).all():
        raise NdxValuationScoreError("overpay guard missing values are not neutral")
    if float(scores["valuation_score"].max()) > 50.0:
        raise NdxValuationScoreError("overpay guard unexpectedly rewards cheap values")
    coverage = coverage.copy()
    coverage["overpay_penalty_quantile"] = float(penalty_quantile)
    coverage["cheap_reward_allowed"] = False
    coverage["observed_guard_score_median"] = scores.loc[
        observed
    ].groupby("selection_date")["valuation_score"].median().reindex(
        coverage["selection_date"].astype(str)
    ).to_numpy()
    return scores, coverage
