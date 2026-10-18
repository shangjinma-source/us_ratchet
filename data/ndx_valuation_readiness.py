"""Point-in-time valuation input readiness for historical NDX securities.

The module resolves only accounting evidence and compatibility blockers. It
does not calculate valuation factors, rank securities, or authorize scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


VALUATION_READINESS_V3_POLICY_ID = "ndx_sec_valuation_readiness_v3"
VALUATION_READINESS_POLICY_ID = "ndx_sec_valuation_readiness_v4"
DEBT_CONCEPT_POLICY_ID = "ndx_sec_debt_concepts_v2"
EXPANDED_DEBT_METRIC_CONCEPTS = {
    "debt": {
        "us-gaap": (
            "DebtLongtermAndShorttermCombinedAmount",
            "DebtCurrent",
            "CommercialPaper",
        ),
        "ifrs-full": (),
    },
}
PROMOTED_DEBT_CONCEPTS = frozenset({
    "DebtLongtermAndShorttermCombinedAmount",
})
FOREIGN_FILING_FORMS = {
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
}
SHARE_CONCEPT_PRIORITY = {
    ("dei", "EntityCommonStockSharesOutstanding"): 0,
    ("us-gaap", "CommonStockSharesOutstanding"): 1,
    ("ifrs-full", "NumberOfSharesOutstanding"): 2,
}
COMPONENT_COLUMNS = (
    "selection_date",
    "ticker",
    "cik",
    "metric",
    "component_role",
    "selected",
    "namespace",
    "concept",
    "unit",
    "value",
    "form",
    "available_date",
    "period_end",
    "accession_number",
)


class NdxValuationReadinessError(ValueError):
    """Raised when valuation-readiness evidence is incomplete or inconsistent."""


@dataclass(frozen=True)
class ValuationReadinessPolicy:
    maximum_shares_age_days: int = 200
    maximum_debt_age_days: int = 200
    maximum_price_age_days: int = 7
    debt_crosscheck_tolerance: float = 0.05
    share_value_tolerance: float = 0.05
    split_ratio_tolerance: float = 0.06
    split_ratios: tuple[int, ...] = (2, 3, 4, 5, 10, 20)

    def validate(self) -> None:
        if min(
            self.maximum_shares_age_days,
            self.maximum_debt_age_days,
            self.maximum_price_age_days,
        ) < 0:
            raise NdxValuationReadinessError("readiness age limits must be nonnegative")
        for value in (
            self.debt_crosscheck_tolerance,
            self.share_value_tolerance,
            self.split_ratio_tolerance,
        ):
            if not 0 <= float(value) < 1:
                raise NdxValuationReadinessError("readiness tolerances must be in [0, 1)")
        if not self.split_ratios or any(int(value) < 2 for value in self.split_ratios):
            raise NdxValuationReadinessError("split ratios must contain integers >= 2")


def _required(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise NdxValuationReadinessError(f"{label} columns missing: {missing}")


def _record_key(record: Mapping[str, Any]) -> tuple:
    return (
        record["metric"],
        record["namespace"],
        record["concept"],
        record["unit"],
        record["period_end"],
    )


def _prepare_records(records: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, pd.Timestamp]]:
    _required(
        records,
        {
            "cik",
            "metric",
            "namespace",
            "concept",
            "unit",
            "value",
            "form",
            "available_date",
            "period_end",
            "accession_number",
        },
        "fact availability",
    )
    prepared = records.copy()
    prepared["cik"] = pd.to_numeric(prepared["cik"], errors="coerce")
    prepared["value"] = pd.to_numeric(prepared["value"], errors="coerce")
    prepared["available_date"] = pd.to_datetime(
        prepared["available_date"], errors="coerce"
    )
    prepared["period_end"] = pd.to_datetime(prepared["period_end"], errors="coerce")
    prepared["form"] = prepared["form"].fillna("").astype(str).str.upper()
    prepared["namespace"] = prepared["namespace"].fillna("").astype(str)
    prepared["concept"] = prepared["concept"].fillna("").astype(str)
    prepared["unit"] = prepared["unit"].fillna("").astype(str)
    prepared["accession_number"] = (
        prepared["accession_number"].fillna("").astype(str)
    )
    prepared = prepared[
        prepared["cik"].notna()
        & prepared["available_date"].notna()
        & prepared["period_end"].notna()
        & np.isfinite(prepared["value"])
    ].copy()
    prepared["cik"] = prepared["cik"].astype(int)
    foreign = (
        prepared[prepared["form"].isin(FOREIGN_FILING_FORMS)]
        .groupby("cik")["available_date"]
        .min()
        .to_dict()
    )
    accounting = prepared[
        prepared["metric"].isin(("debt", "shares_outstanding"))
    ].sort_values(
        ["cik", "available_date", "accession_number", "form"],
        kind="stable",
    )
    return accounting, foreign


def _empty_share_result(status: str) -> dict[str, Any]:
    return {
        "shares_status": status,
        "shares_ready": False,
        "shares_value": None,
        "shares_unit": None,
        "shares_namespace": None,
        "shares_concept": None,
        "shares_period_end": None,
        "shares_age_days": None,
        "shares_source_available_date": None,
        "shares_same_date_candidate_count": 0,
        "shares_same_date_value_spread": None,
        "shares_future_data_guard_passed": True,
    }


def _share_result(
    records: list[dict[str, Any]],
    cutoff: pd.Timestamp,
    policy: ValuationReadinessPolicy,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any], bool]]]:
    candidates = [
        record
        for record in records
        if record["metric"] == "shares_outstanding"
        and record["unit"].lower() == "shares"
        and float(record["value"]) > 0
    ]
    if not candidates:
        return _empty_share_result("missing"), []
    latest_end = max(record["period_end"] for record in candidates)
    same_date = [record for record in candidates if record["period_end"] == latest_end]
    same_date.sort(
        key=lambda record: (
            SHARE_CONCEPT_PRIORITY.get(
                (record["namespace"], record["concept"]), 99
            ),
            -int(record["available_date"].value),
            record["accession_number"],
        )
    )
    selected = same_date[0]
    values = np.asarray([float(record["value"]) for record in same_date], dtype=float)
    spread = (
        float((values.max() - values.min()) / values.max())
        if len(values) > 1 and values.max() > 0
        else 0.0
    )
    age_days = int((cutoff - latest_end).days)
    future_guard = bool(
        selected["available_date"] <= cutoff and selected["period_end"] < cutoff
    )
    status = (
        "ambiguous_multiple_values"
        if spread > float(policy.share_value_tolerance)
        else "stale"
        if age_days > int(policy.maximum_shares_age_days)
        else "ready"
    )
    result = {
        "shares_status": status,
        "shares_ready": status == "ready" and future_guard,
        "shares_value": float(selected["value"]),
        "shares_unit": selected["unit"],
        "shares_namespace": selected["namespace"],
        "shares_concept": selected["concept"],
        "shares_period_end": latest_end.strftime("%Y-%m-%d"),
        "shares_age_days": age_days,
        "shares_source_available_date": selected["available_date"].strftime(
            "%Y-%m-%d"
        ),
        "shares_same_date_candidate_count": len(same_date),
        "shares_same_date_value_spread": spread,
        "shares_future_data_guard_passed": future_guard,
    }
    components = [
        ("selected_share_fact" if record is selected else "same_date_crosscheck", record, record is selected)
        for record in same_date
    ]
    return result, components


def _relative_error(left: float, right: float) -> float:
    scale = max(abs(float(left)), abs(float(right)), 1.0)
    return abs(float(left) - float(right)) / scale


def _empty_debt_result(status: str, unit: str | None = None) -> dict[str, Any]:
    return {
        "debt_status": status,
        "debt_ready": False,
        "debt_strict_complete": False,
        "debt_value": None,
        "debt_unit": unit,
        "debt_method": None,
        "debt_completeness": None,
        "debt_period_end": None,
        "debt_age_days": None,
        "debt_source_available_date_max": None,
        "debt_crosscheck_relative_error": None,
        "debt_crosscheck_status": None,
        "debt_concepts": None,
        "debt_component_count": 0,
        "debt_future_data_guard_passed": True,
    }


def _debt_result(
    records: list[dict[str, Any]],
    cutoff: pd.Timestamp,
    statement_unit: str | None,
    policy: ValuationReadinessPolicy,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any], bool]]]:
    unit = str(statement_unit or "").strip()
    if not unit:
        return _empty_debt_result("statement_unit_missing"), []
    candidates = [
        record
        for record in records
        if record["metric"] == "debt"
        and record["unit"] == unit
        and float(record["value"]) >= 0
    ]
    if not candidates:
        return _empty_debt_result("missing", unit), []
    latest_end = max(record["period_end"] for record in candidates)
    same_date = [record for record in candidates if record["period_end"] == latest_end]
    by_concept: dict[str, dict[str, Any]] = {}
    for record in sorted(
        same_date,
        key=lambda item: (item["available_date"], item["accession_number"]),
    ):
        by_concept[record["concept"]] = record
    value = {concept: float(record["value"]) for concept, record in by_concept.items()}
    selected: list[tuple[str, dict[str, Any]]] = []
    method = None
    completeness = None
    crosscheck = None
    reported_combined_total = False

    combined_debt = value.get("DebtLongtermAndShorttermCombinedAmount")
    if combined_debt is not None:
        reported_combined_total = True
        total = combined_debt
        selected = [
            (
                "reported_long_and_short_term_total",
                by_concept["DebtLongtermAndShorttermCombinedAmount"],
            )
        ]
        method = "us_reported_long_and_short_term_total"
        completeness = "reported_total"
        component_total = None
        if {"LongTermDebt", "ShortTermBorrowings"}.issubset(value):
            component_total = value["LongTermDebt"] + value["ShortTermBorrowings"]
        elif {
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
            "ShortTermBorrowings",
        }.issubset(value):
            component_total = (
                value["LongTermDebtCurrent"]
                + value["LongTermDebtNoncurrent"]
                + value["ShortTermBorrowings"]
            )
        if component_total is not None:
            crosscheck = _relative_error(total, component_total)
    elif "Borrowings" in value:
        total = value["Borrowings"]
        selected = [("borrowings_total", by_concept["Borrowings"])]
        method = "ifrs_borrowings_total"
        completeness = "reported_total"
        if {"CurrentBorrowings", "NoncurrentBorrowings"}.issubset(value):
            component_total = value["CurrentBorrowings"] + value["NoncurrentBorrowings"]
            crosscheck = _relative_error(total, component_total)
    elif {"CurrentBorrowings", "NoncurrentBorrowings"}.issubset(value):
        total = value["CurrentBorrowings"] + value["NoncurrentBorrowings"]
        selected = [
            ("current_borrowings", by_concept["CurrentBorrowings"]),
            ("noncurrent_borrowings", by_concept["NoncurrentBorrowings"]),
        ]
        method = "ifrs_current_plus_noncurrent"
        completeness = "current_plus_noncurrent"
    else:
        current_pair = {"LongTermDebtCurrent", "LongTermDebtNoncurrent"}.issubset(
            value
        )
        long_total = value.get("LongTermDebt")
        if current_pair:
            pair_total = value["LongTermDebtCurrent"] + value["LongTermDebtNoncurrent"]
            if long_total is not None:
                crosscheck = _relative_error(long_total, pair_total)
                if crosscheck > float(policy.debt_crosscheck_tolerance):
                    result = _empty_debt_result("ambiguous_total_components", unit)
                    result.update({
                        "debt_period_end": latest_end.strftime("%Y-%m-%d"),
                        "debt_crosscheck_relative_error": crosscheck,
                        "debt_concepts": ";".join(sorted(by_concept)),
                    })
                    return result, [
                        ("ambiguous_crosscheck", record, False)
                        for record in same_date
                    ]
                total = long_total
                selected = [("long_term_total", by_concept["LongTermDebt"])]
                method = "us_long_term_total_crosschecked"
            else:
                total = pair_total
                selected = [
                    ("long_term_current", by_concept["LongTermDebtCurrent"]),
                    ("long_term_noncurrent", by_concept["LongTermDebtNoncurrent"]),
                ]
                method = "us_long_term_current_plus_noncurrent"
        elif long_total is not None:
            total = long_total
            selected = [("long_term_total", by_concept["LongTermDebt"])]
            method = "us_long_term_total"
        else:
            result = _empty_debt_result("incomplete_components", unit)
            result.update({
                "debt_period_end": latest_end.strftime("%Y-%m-%d"),
                "debt_concepts": ";".join(sorted(by_concept)),
            })
            return result, [
                ("incomplete_candidate", record, False) for record in same_date
            ]
        if "ShortTermBorrowings" in value:
            total += value["ShortTermBorrowings"]
            selected.append(("short_term_borrowings", by_concept["ShortTermBorrowings"]))
            method += "_plus_short_term"
            completeness = "long_term_plus_short_term"
        else:
            completeness = "long_term_only"

    if (
        crosscheck is not None
        and crosscheck > float(policy.debt_crosscheck_tolerance)
        and not reported_combined_total
    ):
        result = _empty_debt_result("ambiguous_total_components", unit)
        result.update({
            "debt_period_end": latest_end.strftime("%Y-%m-%d"),
            "debt_crosscheck_relative_error": crosscheck,
            "debt_concepts": ";".join(sorted(by_concept)),
        })
        return result, [
            ("ambiguous_crosscheck", record, False) for record in same_date
        ]

    age_days = int((cutoff - latest_end).days)
    future_guard = all(
        record["available_date"] <= cutoff and record["period_end"] < cutoff
        for _, record in selected
    )
    status = "stale" if age_days > int(policy.maximum_debt_age_days) else "ready"
    strict_complete = completeness in {
        "reported_total",
        "current_plus_noncurrent",
        "long_term_plus_short_term",
    }
    result = {
        "debt_status": status,
        "debt_ready": status == "ready" and future_guard,
        "debt_strict_complete": status == "ready" and future_guard and strict_complete,
        "debt_value": float(total),
        "debt_unit": unit,
        "debt_method": method,
        "debt_completeness": completeness,
        "debt_period_end": latest_end.strftime("%Y-%m-%d"),
        "debt_age_days": age_days,
        "debt_source_available_date_max": max(
            record["available_date"] for _, record in selected
        ).strftime("%Y-%m-%d"),
        "debt_crosscheck_relative_error": crosscheck,
        "debt_crosscheck_status": (
            "component_mismatch_reported_total_preferred"
            if reported_combined_total
            and crosscheck is not None
            and crosscheck > float(policy.debt_crosscheck_tolerance)
            else "components_matched"
            if crosscheck is not None
            else "not_available"
        ),
        "debt_concepts": ";".join(sorted(by_concept)),
        "debt_component_count": len(selected),
        "debt_future_data_guard_passed": future_guard,
    }
    selected_ids = {id(record) for _, record in selected}
    roles = {id(record): role for role, record in selected}
    components = [
        (
            roles.get(id(record), "same_date_crosscheck"),
            record,
            id(record) in selected_ids,
        )
        for record in same_date
    ]
    return result, components


def _component_row(
    *,
    selection_date: str,
    ticker: str,
    cik: int,
    metric: str,
    role: str,
    record: Mapping[str, Any],
    selected: bool,
) -> dict[str, Any]:
    return {
        "selection_date": selection_date,
        "ticker": ticker,
        "cik": cik,
        "metric": metric,
        "component_role": role,
        "selected": bool(selected),
        "namespace": record["namespace"],
        "concept": record["concept"],
        "unit": record["unit"],
        "value": float(record["value"]),
        "form": record["form"],
        "available_date": record["available_date"].strftime("%Y-%m-%d"),
        "period_end": record["period_end"].strftime("%Y-%m-%d"),
        "accession_number": record["accession_number"],
    }


def build_point_in_time_accounting_readiness(
    plan: pd.DataFrame,
    records: pd.DataFrame,
    statement_units: pd.DataFrame,
    *,
    policy: ValuationReadinessPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resolve shares and debt evidence available at every selection date."""
    selected_policy = policy or ValuationReadinessPolicy()
    selected_policy.validate()
    _required(plan, {"selection_date", "ticker", "cik"}, "selection plan")
    _required(
        statement_units,
        {"selection_date", "ticker", "cik", "statement_unit"},
        "statement units",
    )
    base = plan[["selection_date", "ticker", "cik"]].drop_duplicates().copy()
    base["selection_date"] = pd.to_datetime(base["selection_date"], errors="coerce")
    base["ticker"] = base["ticker"].astype(str).str.upper()
    base["cik"] = pd.to_numeric(base["cik"], errors="coerce")
    if base[["selection_date", "cik"]].isna().any().any():
        raise NdxValuationReadinessError("selection plan has invalid dates or CIKs")
    base["cik"] = base["cik"].astype(int)
    units = statement_units.copy()
    units["selection_date"] = pd.to_datetime(units["selection_date"], errors="coerce")
    units["ticker"] = units["ticker"].astype(str).str.upper()
    units["cik"] = pd.to_numeric(units["cik"], errors="coerce").astype("Int64")
    units = units.drop_duplicates(["selection_date", "ticker", "cik"])
    base = base.merge(
        units,
        on=["selection_date", "ticker", "cik"],
        how="left",
        validate="one_to_one",
    )
    accounting, foreign_first = _prepare_records(records)
    readiness_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []

    for cik, plan_group in base.groupby("cik", sort=True):
        source = accounting[accounting["cik"].eq(int(cik))].to_dict(orient="records")
        source.sort(
            key=lambda record: (
                record["available_date"],
                record["accession_number"],
                record["form"],
            )
        )
        state: dict[tuple, dict[str, Any]] = {}
        source_position = 0
        for selection_date, date_rows in plan_group.groupby(
            "selection_date", sort=True
        ):
            cutoff = pd.Timestamp(selection_date)
            while (
                source_position < len(source)
                and source[source_position]["available_date"] <= cutoff
            ):
                record = source[source_position]
                state[_record_key(record)] = record
                source_position += 1
            eligible = [
                record for record in state.values() if record["period_end"] < cutoff
            ]
            share_result, share_components = _share_result(
                eligible, cutoff, selected_policy
            )
            debt_by_unit: dict[str, tuple[dict[str, Any], list]] = {}
            for row in date_rows.itertuples(index=False):
                ticker = str(row.ticker).upper()
                unit = str(row.statement_unit or "") if pd.notna(row.statement_unit) else ""
                if unit not in debt_by_unit:
                    debt_by_unit[unit] = _debt_result(
                        eligible, cutoff, unit, selected_policy
                    )
                debt_result, debt_components = debt_by_unit[unit]
                foreign_date = foreign_first.get(int(cik))
                foreign_filer = bool(
                    foreign_date is not None and foreign_date <= cutoff
                )
                selection_text = cutoff.strftime("%Y-%m-%d")
                readiness_rows.append({
                    "selection_date": selection_text,
                    "ticker": ticker,
                    "cik": int(cik),
                    "statement_unit": unit or None,
                    "foreign_filer_asof": foreign_filer,
                    "foreign_filing_first_available_date": (
                        foreign_date.strftime("%Y-%m-%d")
                        if foreign_date is not None and foreign_date <= cutoff
                        else None
                    ),
                    **share_result,
                    **debt_result,
                })
                for role, record, selected in share_components:
                    component_rows.append(_component_row(
                        selection_date=selection_text,
                        ticker=ticker,
                        cik=int(cik),
                        metric="shares_outstanding",
                        role=role,
                        record=record,
                        selected=selected,
                    ))
                for role, record, selected in debt_components:
                    component_rows.append(_component_row(
                        selection_date=selection_text,
                        ticker=ticker,
                        cik=int(cik),
                        metric="debt",
                        role=role,
                        record=record,
                        selected=selected,
                    ))
    readiness = pd.DataFrame(readiness_rows).sort_values(
        ["selection_date", "ticker"], kind="stable"
    ).reset_index(drop=True)
    components = pd.DataFrame(component_rows, columns=COMPONENT_COLUMNS).sort_values(
        ["selection_date", "ticker", "metric", "selected", "concept"],
        ascending=[True, True, True, False, True],
        kind="stable",
    ).reset_index(drop=True)
    return readiness, components


def point_in_time_price_rows(
    plan: pd.DataFrame,
    series: Mapping[str, pd.DataFrame],
    *,
    maximum_age_days: int = 7,
) -> pd.DataFrame:
    """Select the latest close strictly before each selection date."""
    _required(plan, {"selection_date", "ticker"}, "price plan")
    rows = []
    for row in plan[["selection_date", "ticker"]].drop_duplicates().itertuples(
        index=False
    ):
        selection_date = pd.Timestamp(row.selection_date)
        ticker = str(row.ticker).upper()
        frame = series.get(ticker)
        close = pd.Series(dtype=float)
        if frame is not None and "Close" in frame:
            close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
            close.index = pd.to_datetime(close.index, errors="coerce")
            close = close[close.index.notna() & (close.index < selection_date)]
        if close.empty:
            rows.append({
                "selection_date": selection_date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "price_status": "missing",
                "price_ready": False,
                "price": None,
                "price_date": None,
                "price_age_days": None,
                "price_future_data_guard_passed": True,
            })
            continue
        price_date = pd.Timestamp(close.index[-1])
        price = float(close.iloc[-1])
        age_days = int((selection_date.normalize() - price_date.normalize()).days)
        status = "ready" if age_days <= int(maximum_age_days) else "stale"
        rows.append({
            "selection_date": selection_date.strftime("%Y-%m-%d"),
            "ticker": ticker,
            "price_status": status,
            "price_ready": status == "ready" and np.isfinite(price) and price > 0,
            "price": price,
            "price_date": price_date.strftime("%Y-%m-%d"),
            "price_age_days": age_days,
            "price_future_data_guard_passed": bool(price_date < selection_date),
        })
    return pd.DataFrame(rows).sort_values(
        ["selection_date", "ticker"], kind="stable"
    ).reset_index(drop=True)


def build_valuation_factor_readiness(
    accounting: pd.DataFrame,
    factor_inputs: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    multi_security_tickers: set[str] | None = None,
    price_basis_ready: bool = False,
) -> pd.DataFrame:
    """Attach factor components and explicit fail-closed valuation blockers."""
    _required(
        accounting,
        {
            "selection_date",
            "ticker",
            "cik",
            "statement_unit",
            "foreign_filer_asof",
            "shares_ready",
            "debt_ready",
            "debt_strict_complete",
        },
        "accounting readiness",
    )
    factor_columns = {
        "selection_date",
        "ticker",
        "cik",
        "revenue_value",
        "revenue_unit",
        "operating_cash_flow_value",
        "operating_cash_flow_unit",
        "capital_expenditure_value",
        "capital_expenditure_unit",
        "cash_value",
        "cash_unit",
        "free_cash_flow_margin_status",
        "revenue_growth_status",
    }
    _required(factor_inputs, factor_columns, "quality factor inputs")
    _required(
        prices,
        {"selection_date", "ticker", "price_ready", "price_future_data_guard_passed"},
        "price readiness",
    )
    accounting_frame = accounting.copy()
    factors = factor_inputs[sorted(factor_columns)].copy()
    prices_frame = prices.copy()
    for frame in (accounting_frame, factors, prices_frame):
        frame["selection_date"] = frame["selection_date"].astype(str).str[:10]
        frame["ticker"] = frame["ticker"].astype(str).str.upper()
    rows = accounting_frame.merge(
        factors,
        on=["selection_date", "ticker", "cik"],
        how="left",
        validate="one_to_one",
    ).merge(
        prices_frame,
        on=["selection_date", "ticker"],
        how="left",
        validate="one_to_one",
    )
    multi = {str(value).upper() for value in (multi_security_tickers or set())}
    rows["multi_security_issuer"] = rows["ticker"].isin(multi)
    rows["price_basis_ready"] = bool(price_basis_ready)
    ocf = pd.to_numeric(rows["operating_cash_flow_value"], errors="coerce")
    capex = pd.to_numeric(rows["capital_expenditure_value"], errors="coerce")
    fcf_units_match = (
        rows["operating_cash_flow_unit"].eq(rows["capital_expenditure_unit"])
        & rows["operating_cash_flow_unit"].eq(rows["revenue_unit"])
    )
    fcf_components_ready = (
        rows["free_cash_flow_margin_status"].eq("ready")
        & ocf.notna()
        & capex.notna()
        & fcf_units_match
    )
    rows["free_cash_flow_value"] = (ocf - capex).where(fcf_components_ready)
    rows["free_cash_flow_unit"] = rows["revenue_unit"].where(fcf_components_ready)
    rows["free_cash_flow_components_ready"] = fcf_components_ready
    statement_usd = rows["statement_unit"].eq("USD") & rows["revenue_unit"].eq(
        "USD"
    )
    common_identity_ready = (
        rows["shares_ready"].fillna(False).astype(bool)
        & ~rows["foreign_filer_asof"].fillna(False).astype(bool)
        & ~rows["multi_security_issuer"]
        & statement_usd
    )
    rows["fcf_yield_accounting_ready"] = common_identity_ready & fcf_components_ready
    revenue = pd.to_numeric(rows["revenue_value"], errors="coerce")
    cash = pd.to_numeric(rows["cash_value"], errors="coerce")
    ev_components_ready = (
        rows["debt_ready"].fillna(False).astype(bool)
        & rows["debt_strict_complete"].fillna(False).astype(bool)
        & revenue.notna()
        & cash.notna()
        & rows["revenue_unit"].eq(rows["debt_unit"])
        & rows["revenue_unit"].eq(rows["cash_unit"])
    )
    rows["ev_sales_accounting_ready"] = common_identity_ready & ev_components_ready
    price_ready = (
        rows["price_ready"].fillna(False).astype(bool)
        & rows["price_future_data_guard_passed"].fillna(False).astype(bool)
        & bool(price_basis_ready)
    )
    rows["fcf_yield_ready"] = rows["fcf_yield_accounting_ready"] & price_ready
    rows["ev_sales_ready"] = rows["ev_sales_accounting_ready"] & price_ready
    rows["valuation_scoring_allowed"] = False

    def finite(value: Any) -> bool:
        try:
            return bool(np.isfinite(float(value)))
        except (TypeError, ValueError):
            return False

    def blockers(row: pd.Series, *, ev: bool) -> str:
        values = []
        if not bool(row.get("shares_ready")):
            values.append(f"shares:{row.get('shares_status') or 'missing'}")
        if bool(row.get("foreign_filer_asof")):
            values.append("foreign_filer_fx_and_adr_ratio_required")
        if bool(row.get("multi_security_issuer")):
            values.append("multi_security_issuer_share_allocation_pending")
        if row.get("statement_unit") != "USD" or row.get("revenue_unit") != "USD":
            values.append("point_in_time_fx_required")
        if not bool(row.get("free_cash_flow_components_ready")) and not ev:
            values.append("free_cash_flow_components_not_ready")
        if ev:
            if not bool(row.get("debt_ready")):
                values.append(f"debt:{row.get('debt_status') or 'missing'}")
            elif not bool(row.get("debt_strict_complete")):
                values.append("short_term_debt_completeness_unproven")
            if not finite(row.get("revenue_value")):
                values.append("revenue_missing")
            if not finite(row.get("cash_value")):
                values.append("cash_missing")
        if not bool(row.get("price_ready")):
            values.append(f"price:{row.get('price_status') or 'missing'}")
        if not bool(row.get("price_basis_ready")):
            values.append("unadjusted_price_or_adjustment_factor_missing")
        return ";".join(dict.fromkeys(values))

    rows["fcf_yield_blockers"] = rows.apply(blockers, axis=1, ev=False)
    rows["ev_sales_blockers"] = rows.apply(blockers, axis=1, ev=True)
    return rows.sort_values(["selection_date", "ticker"], kind="stable").reset_index(
        drop=True
    )


def share_basis_events(
    accounting: pd.DataFrame,
    *,
    policy: ValuationReadinessPolicy | None = None,
) -> pd.DataFrame:
    """Flag large point-in-time share-count changes that resemble split ratios."""
    selected_policy = policy or ValuationReadinessPolicy()
    selected_policy.validate()
    _required(
        accounting,
        {"selection_date", "ticker", "shares_ready", "shares_value"},
        "accounting readiness",
    )
    rows = []
    for ticker, group in accounting.groupby("ticker", sort=True):
        usable = group[group["shares_ready"].fillna(False).astype(bool)].copy()
        usable["selection_date"] = pd.to_datetime(
            usable["selection_date"], errors="coerce"
        )
        usable["shares_value"] = pd.to_numeric(
            usable["shares_value"], errors="coerce"
        )
        usable = usable.dropna(subset=["selection_date", "shares_value"]).sort_values(
            "selection_date"
        )
        prior = None
        for current in usable.itertuples(index=False):
            if prior is not None and prior.shares_value > 0 and current.shares_value > 0:
                raw_ratio = float(current.shares_value / prior.shares_value)
                magnitude = max(raw_ratio, 1.0 / raw_ratio)
                if magnitude >= 1.25:
                    nearest = min(
                        selected_policy.split_ratios,
                        key=lambda value: abs(magnitude - value),
                    )
                    relative_error = abs(magnitude - nearest) / nearest
                    rows.append({
                        "ticker": str(ticker),
                        "prior_selection_date": prior.selection_date.strftime(
                            "%Y-%m-%d"
                        ),
                        "selection_date": current.selection_date.strftime("%Y-%m-%d"),
                        "prior_shares": float(prior.shares_value),
                        "shares": float(current.shares_value),
                        "raw_ratio": raw_ratio,
                        "ratio_magnitude": magnitude,
                        "nearest_split_ratio": int(nearest),
                        "split_ratio_relative_error": relative_error,
                        "split_like": relative_error
                        <= float(selected_policy.split_ratio_tolerance),
                    })
            prior = current
    columns = [
        "ticker",
        "prior_selection_date",
        "selection_date",
        "prior_shares",
        "shares",
        "raw_ratio",
        "ratio_magnitude",
        "nearest_split_ratio",
        "split_ratio_relative_error",
        "split_like",
    ]
    return pd.DataFrame(rows, columns=columns)
