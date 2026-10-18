"""Current point-in-time evidence gates for the v11 forward watch.

This module deliberately stops before quality or valuation ranking.  It turns
the current SEC Company Facts snapshot into unranked factor inputs and
fail-closed evidence gates so that a later v11 shadow selection cannot confuse
accounting readiness with candidate admission.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from backtest.ndx_quality import (
    BALANCE_FACTORS,
    GROWTH_FACTORS,
    PROFITABILITY_FACTORS,
)
from data.ndx_fundamentals import NdxFundamentalError


CURRENT_EVIDENCE_POLICY_ID = "ndx_v11_current_fundamental_evidence_v1"
QUALITY_INPUT_POLICY_ID = "ndx_v11_quality_input_audit_v1"
MINIMUM_CORE_FACTORS = 5
MINIMUM_PROFITABILITY_FACTORS = 2
MINIMUM_BALANCE_FACTORS = 2


def _required(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise NdxFundamentalError(f"{label} columns missing: {missing}")


def _status_count(row: pd.Series, factors: Iterable[str]) -> int:
    return sum(row.get(f"{factor}_status") == "ready" for factor in factors)


def build_quality_input_readiness(
    factor_inputs: pd.DataFrame,
    *,
    minimum_core_factors: int = MINIMUM_CORE_FACTORS,
    minimum_profitability_factors: int = MINIMUM_PROFITABILITY_FACTORS,
    minimum_balance_factors: int = MINIMUM_BALANCE_FACTORS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audit unranked quality-factor completeness without calculating scores."""
    factors = tuple(GROWTH_FACTORS) + tuple(PROFITABILITY_FACTORS) + tuple(BALANCE_FACTORS)
    _required(
        factor_inputs,
        {"selection_date", "ticker", "cik"}
        | {f"{factor}_status" for factor in factors},
        "quality factor inputs",
    )
    if factor_inputs.duplicated(["selection_date", "ticker"]).any():
        raise NdxFundamentalError("quality factor inputs contain duplicate keys")
    if minimum_core_factors < 1 or minimum_core_factors > len(factors):
        raise NdxFundamentalError("minimum core-factor threshold is invalid")
    if minimum_profitability_factors < 1 or minimum_profitability_factors > len(PROFITABILITY_FACTORS):
        raise NdxFundamentalError("minimum profitability-factor threshold is invalid")
    if minimum_balance_factors < 1 or minimum_balance_factors > len(BALANCE_FACTORS):
        raise NdxFundamentalError("minimum balance-factor threshold is invalid")

    rows = []
    for row in factor_inputs.copy().itertuples(index=False):
        values = row._asdict()
        core_count = sum(values.get(f"{factor}_status") == "ready" for factor in factors)
        growth_count = sum(values.get(f"{factor}_status") == "ready" for factor in GROWTH_FACTORS)
        profitability_count = sum(
            values.get(f"{factor}_status") == "ready"
            for factor in PROFITABILITY_FACTORS
        )
        balance_count = sum(
            values.get(f"{factor}_status") == "ready"
            for factor in BALANCE_FACTORS
        )
        blockers = []
        if core_count < minimum_core_factors:
            blockers.append(
                f"core_factor_count:{core_count}<{minimum_core_factors}"
            )
        if growth_count < 1:
            blockers.append("growth_factor_missing")
        if profitability_count < minimum_profitability_factors:
            blockers.append(
                f"profitability_factor_count:{profitability_count}"
                f"<{minimum_profitability_factors}"
            )
        if balance_count < minimum_balance_factors:
            blockers.append(
                f"balance_factor_count:{balance_count}<{minimum_balance_factors}"
            )
        rows.append({
            "selection_date": str(values["selection_date"])[:10],
            "ticker": str(values["ticker"]).upper(),
            "cik": int(values["cik"]),
            "core_factor_count": core_count,
            "growth_factor_count": growth_count,
            "profitability_factor_count": profitability_count,
            "balance_factor_count": balance_count,
            "quality_factor_input_ready": not blockers,
            "quality_factor_blockers": ";".join(blockers),
            "quality_score_generated": False,
            "quality_score_allowed": False,
        })
    readiness = pd.DataFrame(rows).sort_values(
        ["selection_date", "ticker"], kind="stable"
    ).reset_index(drop=True)
    coverage_rows = []
    for selection_date, group in readiness.groupby("selection_date", sort=True):
        coverage_rows.append({
            "selection_date": selection_date,
            "universe_count": len(group),
            "quality_factor_input_ready_count": int(
                group["quality_factor_input_ready"].sum()
            ),
            "quality_factor_input_coverage": float(
                group["quality_factor_input_ready"].mean()
            ) if len(group) else 0.0,
            "minimum_core_factors": int(minimum_core_factors),
            "minimum_profitability_factors": int(minimum_profitability_factors),
            "minimum_balance_factors": int(minimum_balance_factors),
            "quality_score_generated": False,
            "quality_score_allowed": False,
        })
    return readiness, pd.DataFrame(coverage_rows)


def build_valuation_gate_summary(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize valuation readiness while preserving all explicit blockers."""
    _required(
        rows,
        {
            "selection_date",
            "ticker",
            "fcf_yield_ready",
            "ev_sales_ready",
            "fcf_yield_blockers",
            "ev_sales_blockers",
            "valuation_scoring_allowed",
        },
        "valuation readiness",
    )
    output = rows.copy()
    output["valuation_score_generated"] = False
    output["valuation_score_allowed"] = False
    output["valuation_accounting_evidence_ready"] = (
        output["fcf_yield_accounting_ready"].fillna(False).astype(bool)
        if "fcf_yield_accounting_ready" in output
        else False
    ) | (
        output["ev_sales_accounting_ready"].fillna(False).astype(bool)
        if "ev_sales_accounting_ready" in output
        else False
    )
    output["valuation_blockers"] = output.apply(
        lambda row: ";".join(dict.fromkeys(filter(
            None,
            [
                str(row.get("fcf_yield_blockers") or ""),
                str(row.get("ev_sales_blockers") or ""),
                "valuation_score_generation_disabled",
            ],
        ))),
        axis=1,
    )
    coverage_rows = []
    for selection_date, group in output.groupby("selection_date", sort=True):
        coverage_rows.append({
            "selection_date": str(selection_date)[:10],
            "universe_count": len(group),
            "shares_ready_count": int(group["shares_ready"].fillna(False).astype(bool).sum()),
            "debt_ready_count": int(group["debt_ready"].fillna(False).astype(bool).sum()),
            "price_ready_count": int(group["price_ready"].fillna(False).astype(bool).sum()),
            "fcf_yield_accounting_ready_count": int(
                group["fcf_yield_accounting_ready"].fillna(False).astype(bool).sum()
            ),
            "ev_sales_accounting_ready_count": int(
                group["ev_sales_accounting_ready"].fillna(False).astype(bool).sum()
            ),
            "fcf_yield_ready_count": int(group["fcf_yield_ready"].fillna(False).astype(bool).sum()),
            "ev_sales_ready_count": int(group["ev_sales_ready"].fillna(False).astype(bool).sum()),
            "valuation_score_generated": False,
            "valuation_score_allowed": False,
        })
    return output, pd.DataFrame(coverage_rows)


def build_security_evidence_gate(
    observations: pd.DataFrame,
    quality_readiness: pd.DataFrame,
    valuation_readiness: pd.DataFrame,
) -> pd.DataFrame:
    """Join current taxonomy, quality-input and valuation blockers per security."""
    _required(
        observations,
        {"observation_date", "ticker", "cik", "security_id", "issuer_id", "risk_chain", "taxonomy_status"},
        "forward observations",
    )
    _required(
        quality_readiness,
        {"selection_date", "ticker", "cik", "quality_factor_input_ready", "quality_factor_blockers"},
        "quality readiness",
    )
    _required(
        valuation_readiness,
        {"selection_date", "ticker", "cik", "valuation_blockers"},
        "valuation readiness",
    )
    if observations["ticker"].astype(str).str.upper().eq("QQQ").any():
        raise NdxFundamentalError("QQQ cannot enter current security evidence")
    base = observations.copy()
    base["selection_date"] = base["observation_date"].astype(str).str[:10]
    base["ticker"] = base["ticker"].astype(str).str.upper()
    base["cik"] = pd.to_numeric(base["cik"], errors="coerce")
    quality = quality_readiness.copy()
    valuation = valuation_readiness.copy()
    for frame in (quality, valuation):
        frame["selection_date"] = frame["selection_date"].astype(str).str[:10]
        frame["ticker"] = frame["ticker"].astype(str).str.upper()
        frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce")
    output = base.merge(
        quality,
        on=["selection_date", "ticker", "cik"],
        how="left",
        validate="one_to_one",
    ).merge(
        valuation[
            [
                "selection_date",
                "ticker",
                "cik",
                "valuation_accounting_evidence_ready",
                "valuation_blockers",
                "fcf_yield_ready",
                "ev_sales_ready",
            ]
        ],
        on=["selection_date", "ticker", "cik"],
        how="left",
        validate="one_to_one",
    )
    rows = []
    for row in output.itertuples(index=False):
        values = row._asdict()
        blockers = []
        if values.get("taxonomy_status") != "accepted":
            blockers.append("taxonomy_current_evidence_missing_or_unclassified")
        if not bool(values.get("quality_factor_input_ready")):
            blockers.append("quality_factor_input_incomplete")
        if not bool(values.get("valuation_accounting_evidence_ready")):
            blockers.append("valuation_accounting_evidence_incomplete")
        blockers.append("quality_score_generation_disabled_until_current_risk_audit")
        blockers.append("valuation_score_generation_disabled_until_price_fx_identity_audit")
        rows.append({
            **values,
            "evidence_gate_status": "blocked",
            "evidence_gate_blockers": ";".join(dict.fromkeys(blockers)),
            "candidate_admission_allowed": False,
            "old_holding_sale_allowed": False,
            "return_data_read": False,
        })
    return pd.DataFrame(rows).sort_values(
        ["selection_date", "ticker"], kind="stable"
    ).reset_index(drop=True)


__all__ = [
    "CURRENT_EVIDENCE_POLICY_ID",
    "QUALITY_INPUT_POLICY_ID",
    "build_quality_input_readiness",
    "build_valuation_gate_summary",
    "build_security_evidence_gate",
]
