"""Diagnostic valuation values derived from readiness-approved components."""
from __future__ import annotations

import numpy as np
import pandas as pd


VALUATION_DIAGNOSTIC_POLICY_ID = "ndx_valuation_value_diagnostics_v3"


class NdxValuationDiagnosticError(ValueError):
    pass


def _required(frame: pd.DataFrame, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise NdxValuationDiagnosticError(
            f"valuation readiness columns missing: {missing}"
        )


def calculate_valuation_values(readiness: pd.DataFrame) -> pd.DataFrame:
    """Calculate values only where every upstream readiness gate is true."""
    required = {
        "selection_date",
        "ticker",
        "cik",
        "price",
        "shares_value",
        "free_cash_flow_value",
        "debt_value",
        "cash_value",
        "revenue_value",
        "fcf_yield_ready",
        "ev_sales_ready",
        "valuation_scoring_allowed",
    }
    _required(readiness, required)
    rows = readiness.copy()
    if rows["valuation_scoring_allowed"].fillna(False).astype(bool).any():
        raise NdxValuationDiagnosticError(
            "readiness input unexpectedly enables valuation scoring"
        )
    for column in (
        "price",
        "shares_value",
        "free_cash_flow_value",
        "debt_value",
        "cash_value",
        "revenue_value",
    ):
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    market_cap = rows["price"] * rows["shares_value"]
    market_cap_valid = np.isfinite(market_cap) & (market_cap > 0)
    rows["market_cap_value"] = market_cap.where(market_cap_valid)
    rows["market_cap_unit"] = "USD"
    fcf_ready = rows["fcf_yield_ready"].fillna(False).astype(bool)
    fcf_ready &= market_cap_valid & np.isfinite(rows["free_cash_flow_value"])
    rows["fcf_yield_value"] = (
        rows["free_cash_flow_value"] / market_cap
    ).where(fcf_ready)
    ev_ready = rows["ev_sales_ready"].fillna(False).astype(bool)
    ev_ready &= (
        market_cap_valid
        & np.isfinite(rows["debt_value"])
        & np.isfinite(rows["cash_value"])
        & np.isfinite(rows["revenue_value"])
        & rows["revenue_value"].gt(0)
    )
    enterprise_value = market_cap + rows["debt_value"] - rows["cash_value"]
    rows["enterprise_value"] = enterprise_value.where(ev_ready)
    rows["enterprise_value_unit"] = "USD"
    rows["ev_sales_value"] = (
        enterprise_value / rows["revenue_value"]
    ).where(ev_ready)
    rows["fcf_yield_value_ready"] = (
        fcf_ready & np.isfinite(rows["fcf_yield_value"])
    )
    rows["ev_sales_value_ready"] = (
        ev_ready & np.isfinite(rows["ev_sales_value"])
    )
    rows["negative_enterprise_value"] = (
        rows["ev_sales_value_ready"] & rows["enterprise_value"].lt(0)
    )
    rows["fcf_yield_unit_review"] = (
        rows["fcf_yield_value_ready"] & rows["fcf_yield_value"].abs().gt(2.0)
    )
    rows["ev_sales_unit_review"] = (
        rows["ev_sales_value_ready"] & rows["ev_sales_value"].abs().gt(100.0)
    )
    rows["valuation_value_integrity_ready"] = (
        (~rows["fcf_yield_ready"].fillna(False).astype(bool)
         | rows["fcf_yield_value_ready"])
        & (~rows["ev_sales_ready"].fillna(False).astype(bool)
           | rows["ev_sales_value_ready"])
    )
    rows["valuation_scoring_allowed"] = False
    selected = [
        "selection_date",
        "ticker",
        "cik",
        "price",
        "price_date",
        "shares_value",
        "shares_period_end",
        "market_cap_value",
        "market_cap_unit",
        "free_cash_flow_value",
        "free_cash_flow_unit",
        "fcf_yield_value",
        "fcf_yield_value_ready",
        "debt_value",
        "debt_unit",
        "debt_method",
        "cash_value",
        "cash_unit",
        "revenue_value",
        "revenue_unit",
        "enterprise_value",
        "enterprise_value_unit",
        "ev_sales_value",
        "ev_sales_value_ready",
        "negative_enterprise_value",
        "fcf_yield_unit_review",
        "ev_sales_unit_review",
        "valuation_value_integrity_ready",
        "fcf_yield_blockers",
        "ev_sales_blockers",
        "valuation_scoring_allowed",
    ]
    return rows[selected].sort_values(
        ["selection_date", "ticker"], kind="stable"
    ).reset_index(drop=True)


def valuation_distributions(values: pd.DataFrame) -> pd.DataFrame:
    _required(
        values,
        {
            "selection_date",
            "ticker",
            "fcf_yield_value",
            "ev_sales_value",
        },
    )
    output = []
    for selection_date, group in values.groupby("selection_date", sort=True):
        for factor, column in (
            ("fcf_yield", "fcf_yield_value"),
            ("ev_sales", "ev_sales_value"),
        ):
            series = pd.to_numeric(group[column], errors="coerce")
            series = series[np.isfinite(series)]
            item = {
                "selection_date": selection_date,
                "factor": factor,
                "universe_count": len(group),
                "ready_count": len(series),
                "ready_coverage": len(series) / len(group) if len(group) else None,
                "negative_count": int(series.lt(0).sum()),
                "negative_rate": float(series.lt(0).mean()) if len(series) else None,
            }
            for name, quantile in (
                ("p01", 0.01),
                ("p10", 0.10),
                ("p25", 0.25),
                ("p50", 0.50),
                ("p75", 0.75),
                ("p90", 0.90),
                ("p99", 0.99),
            ):
                item[name] = float(series.quantile(quantile)) if len(series) else None
            item["minimum"] = float(series.min()) if len(series) else None
            item["maximum"] = float(series.max()) if len(series) else None
            output.append(item)
    return pd.DataFrame(output)


def valuation_tail_review(values: pd.DataFrame, *, tail_size: int = 5) -> pd.DataFrame:
    if int(tail_size) < 1:
        raise NdxValuationDiagnosticError("tail_size must be >= 1")
    output = []
    for selection_date, group in values.groupby("selection_date", sort=True):
        for factor, column in (
            ("fcf_yield", "fcf_yield_value"),
            ("ev_sales", "ev_sales_value"),
        ):
            ready = group[np.isfinite(pd.to_numeric(group[column], errors="coerce"))]
            if ready.empty:
                continue
            ordered = ready.sort_values([column, "ticker"], kind="stable")
            for tail, selected in (
                ("low", ordered.head(int(tail_size))),
                ("high", ordered.tail(int(tail_size)).sort_values(
                    [column, "ticker"], ascending=[False, True], kind="stable"
                )),
            ):
                for rank, row in enumerate(selected.itertuples(index=False), start=1):
                    output.append({
                        "selection_date": selection_date,
                        "factor": factor,
                        "tail": tail,
                        "tail_rank": rank,
                        "ticker": row.ticker,
                        "cik": row.cik,
                        "value": getattr(row, column),
                        "price": row.price,
                        "shares_value": row.shares_value,
                        "market_cap_value": row.market_cap_value,
                        "debt_value": row.debt_value,
                        "cash_value": row.cash_value,
                        "revenue_value": row.revenue_value,
                        "free_cash_flow_value": row.free_cash_flow_value,
                        "review_only": True,
                    })
    return pd.DataFrame(output)


def valuation_integrity_failures(values: pd.DataFrame) -> pd.DataFrame:
    output = []
    invalid = values[
        ~values["valuation_value_integrity_ready"].fillna(False).astype(bool)
    ]
    for row in invalid.itertuples(index=False):
        output.append({
            "selection_date": row.selection_date,
            "ticker": row.ticker,
            "failure_type": "ready_component_did_not_produce_finite_value",
        })
    scoring = values[
        values["valuation_scoring_allowed"].fillna(False).astype(bool)
    ]
    for row in scoring.itertuples(index=False):
        output.append({
            "selection_date": row.selection_date,
            "ticker": row.ticker,
            "failure_type": "valuation_scoring_enabled",
        })
    return pd.DataFrame(
        output,
        columns=["selection_date", "ticker", "failure_type"],
    )
