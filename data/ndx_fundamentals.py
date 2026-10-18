"""Point-in-time SEC Company Facts readiness for historical NDX securities.

This module intentionally stops before factor scoring. It establishes an
official CIK crosswalk, caches raw SEC payloads, and measures whether declared
facts were publicly available at each historical selection date.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from data.ndx_history import _normalize_company_name, constituents_asof


CIK_LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ALLOWED_FORMS = {
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
    "8-K",
    "8-K/A",
}

# Aliases are a coverage vocabulary, not an accounting normalization policy.
METRIC_CONCEPTS = {
    "revenue": {
        "us-gaap": (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RegulatedAndUnregulatedOperatingRevenue",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
        ),
        "ifrs-full": ("Revenue",),
    },
    "operating_income": {
        "us-gaap": ("OperatingIncomeLoss",),
        "ifrs-full": ("ProfitLossFromOperatingActivities",),
    },
    "net_income": {
        "us-gaap": (
            "NetIncomeLoss",
            "ProfitLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
        ),
        "ifrs-full": ("ProfitLoss",),
    },
    "operating_cash_flow": {
        "us-gaap": ("NetCashProvidedByUsedInOperatingActivities",),
        "ifrs-full": ("CashFlowsFromUsedInOperatingActivities",),
    },
    "capital_expenditure": {
        "us-gaap": (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquireOtherPropertyPlantAndEquipment",
            "PaymentsToAcquireOtherProductiveAssets",
            "PaymentsForProceedsFromOtherPropertyPlantAndEquipment",
        ),
        "ifrs-full": (
            "PurchaseOfPropertyPlantAndEquipment",
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        ),
    },
    "research_and_development": {
        "us-gaap": (
            "ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
        ),
        "ifrs-full": ("ResearchAndDevelopmentExpense",),
    },
    "assets": {
        "us-gaap": ("Assets",),
        "ifrs-full": ("Assets",),
    },
    "equity": {
        "us-gaap": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        "ifrs-full": ("Equity",),
    },
    "cash": {
        "us-gaap": (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
        ),
        "ifrs-full": ("CashAndCashEquivalents",),
    },
    "debt": {
        "us-gaap": (
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
            "LongTermDebt",
            "ShortTermBorrowings",
        ),
        "ifrs-full": ("Borrowings", "CurrentBorrowings", "NoncurrentBorrowings"),
    },
    "shares_outstanding": {
        "dei": ("EntityCommonStockSharesOutstanding",),
        "us-gaap": ("CommonStockSharesOutstanding",),
        "ifrs-full": ("NumberOfSharesOutstanding",),
    },
}


class NdxFundamentalError(ValueError):
    """Raised when SEC fundamental evidence is incomplete or inconsistent."""


def fundamental_cache_dir(cfg) -> Path:
    direct = getattr(cfg, "cache_dir", None)
    if direct:
        return Path(direct) / "candidate_pools" / "ndx_fundamentals"
    data_cfg = getattr(cfg, "data", None)
    return Path(getattr(data_cfg, "cache_dir", "data/cache")) / "candidate_pools" / "ndx_fundamentals"


def _exact_company_name_key(value: str) -> str:
    text = str(value or "").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", text)


def parse_cik_lookup(text: str) -> pd.DataFrame:
    rows = []
    skipped_empty_names = 0
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^(.*):(\d+):$", line)
        if not match:
            raise NdxFundamentalError(
                f"invalid SEC CIK lookup row at line {line_number}"
            )
        name = match.group(1).strip()
        cik = int(match.group(2))
        if cik <= 0:
            raise NdxFundamentalError(
                f"invalid SEC CIK lookup value at line {line_number}"
            )
        # The SEC source currently contains a small number of valid CIK rows
        # with no name. They cannot contribute to exact historical-name mapping.
        if not name:
            skipped_empty_names += 1
            continue
        rows.append({
            "cik": cik,
            "name": name,
            "normalized_name": _normalize_company_name(name),
        })
    if not rows:
        raise NdxFundamentalError("SEC CIK lookup is empty")
    result = pd.DataFrame(rows).drop_duplicates(["cik", "name"])
    result.attrs["skipped_empty_name_rows"] = skipped_empty_names
    return result


def _ticker_rows(payload: Mapping) -> pd.DataFrame:
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    if fields != ["cik", "name", "ticker", "exchange"] or not data:
        raise NdxFundamentalError("SEC ticker crosswalk schema changed or is empty")
    frame = pd.DataFrame(data, columns=fields)
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce")
    if frame["cik"].isna().any() or (frame["cik"] <= 0).any():
        raise NdxFundamentalError("SEC ticker crosswalk contains invalid CIKs")
    frame["cik"] = frame["cik"].astype(int)
    return frame


def build_cik_crosswalk(
    history: pd.DataFrame,
    *,
    company_ticker_payload: Mapping,
    historical_cik_names: pd.DataFrame | None = None,
) -> pd.DataFrame:
    required = {"ticker", "name", "cusip", "report_date"}
    missing = sorted(required - set(history.columns))
    if missing:
        raise NdxFundamentalError(f"NDX history columns missing: {missing}")
    ticker_rows = _ticker_rows(company_ticker_payload)
    ticker_index = {
        ticker: sorted(set(group["cik"].astype(int)))
        for ticker, group in ticker_rows.groupby("ticker")
    }
    exact_name_index: dict[str, set[int]] = defaultdict(set)
    name_index: dict[str, set[int]] = defaultdict(set)
    if historical_cik_names is not None and not historical_cik_names.empty:
        if not {"cik", "normalized_name"}.issubset(historical_cik_names.columns):
            raise NdxFundamentalError("historical CIK names have an invalid schema")
        for row in historical_cik_names.itertuples(index=False):
            name = str(getattr(row, "name", "") or "").strip()
            if name:
                exact_name_index[_exact_company_name_key(name)].add(int(row.cik))
            if row.normalized_name:
                name_index[str(row.normalized_name)].add(int(row.cik))

    rows = []
    for ticker, group in history.groupby(history["ticker"].astype(str).str.upper()):
        names = sorted(set(group["name"].dropna().astype(str)))
        cusips = sorted(set(group["cusip"].dropna().astype(str).str.upper()))
        exact = ticker_index.get(ticker, [])
        candidates: set[int] = set(exact)
        method = "sec_current_ticker_exact" if len(exact) == 1 else None
        exact_historical_name_found = False
        if len(candidates) != 1 and exact_name_index:
            historical_candidates = set()
            for name in names:
                historical_candidates.update(
                    exact_name_index.get(_exact_company_name_key(name), set())
                )
            if historical_candidates:
                exact_historical_name_found = True
                candidates = historical_candidates
                method = (
                    "sec_historical_name_exact"
                    if len(historical_candidates) == 1
                    else "ambiguous_historical_name_exact"
                )
        if len(candidates) != 1 and name_index and not exact_historical_name_found:
            historical_candidates = set()
            for name in names:
                normalized = _normalize_company_name(name)
                matches = name_index.get(normalized, set())
                if matches:
                    historical_candidates.update(matches)
            if len(historical_candidates) == 1:
                candidates = historical_candidates
                method = "sec_historical_name_normalized_unique"
            elif historical_candidates:
                candidates = historical_candidates
                method = "ambiguous_historical_name"
        cik = next(iter(candidates)) if len(candidates) == 1 else None
        rows.append({
            "ticker": ticker,
            "cik": cik,
            "mapping_status": "mapped" if cik is not None else "unresolved",
            "mapping_method": method or "unresolved",
            "candidate_ciks": ";".join(str(value) for value in sorted(candidates)),
            "names": ";".join(names),
            "cusips": ";".join(cusips),
            "first_report_date": str(group["report_date"].min())[:10],
            "last_report_date": str(group["report_date"].max())[:10],
        })
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def validate_companyfacts_payload(payload: Mapping, expected_cik: int) -> None:
    try:
        observed_cik = int(payload.get("cik"))
    except (TypeError, ValueError):
        observed_cik = -1
    if observed_cik != int(expected_cik):
        raise NdxFundamentalError(
            f"Company Facts CIK mismatch: expected={expected_cik} observed={observed_cik}"
        )
    if not str(payload.get("entityName") or "").strip():
        raise NdxFundamentalError(f"Company Facts entity name missing for CIK {expected_cik}")
    if not isinstance(payload.get("facts"), Mapping):
        raise NdxFundamentalError(f"Company Facts payload missing facts for CIK {expected_cik}")


def companyfacts_records(
    payload: Mapping,
    *,
    metric_concepts: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
) -> pd.DataFrame:
    cik = int(payload["cik"])
    entity_name = str(payload.get("entityName") or "")
    facts = payload.get("facts") or {}
    rows = []
    selected_concepts = metric_concepts or METRIC_CONCEPTS
    for metric, namespaces in selected_concepts.items():
        for namespace, concepts in namespaces.items():
            namespace_facts = facts.get(namespace) or {}
            for concept in concepts:
                item = namespace_facts.get(concept)
                if not isinstance(item, Mapping):
                    continue
                for unit, records in (item.get("units") or {}).items():
                    for record in records or []:
                        filed = pd.to_datetime(record.get("filed"), errors="coerce")
                        end = pd.to_datetime(record.get("end"), errors="coerce")
                        value = pd.to_numeric(record.get("val"), errors="coerce")
                        if (
                            pd.isna(filed)
                            or pd.isna(end)
                            or pd.isna(value)
                            or not np.isfinite(value)
                        ):
                            continue
                        form = str(record.get("form") or "").upper()
                        if form not in ALLOWED_FORMS:
                            continue
                        rows.append({
                            "cik": cik,
                            "entity_name": entity_name,
                            "metric": metric,
                            "namespace": namespace,
                            "concept": concept,
                            "unit": str(unit),
                            "value": float(value),
                            "form": form,
                            "filed_date": filed.strftime("%Y-%m-%d"),
                            "available_date": (
                                filed + pd.Timedelta(days=1)
                            ).strftime("%Y-%m-%d"),
                            "period_start": str(record.get("start") or "")[:10],
                            "period_end": end.strftime("%Y-%m-%d"),
                            "fiscal_year": record.get("fy"),
                            "fiscal_period": record.get("fp"),
                            "accession_number": record.get("accn"),
                            "frame": record.get("frame"),
                        })
    columns = [
        "cik",
        "entity_name",
        "metric",
        "namespace",
        "concept",
        "unit",
        "value",
        "form",
        "filed_date",
        "available_date",
        "period_start",
        "period_end",
        "fiscal_year",
        "fiscal_period",
        "accession_number",
        "frame",
    ]
    return pd.DataFrame(rows, columns=columns)


def concept_inventory(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame(columns=[
            "cik", "entity_name", "metric", "namespace", "concept", "unit",
            "record_count", "first_available_date", "last_available_date",
            "first_period_end", "last_period_end", "forms",
        ])
    return records.groupby(
        ["cik", "entity_name", "metric", "namespace", "concept", "unit"],
        dropna=False,
    ).agg(
        record_count=("available_date", "size"),
        first_available_date=("available_date", "min"),
        last_available_date=("available_date", "max"),
        first_period_end=("period_end", "min"),
        last_period_end=("period_end", "max"),
        forms=("form", lambda values: ";".join(sorted(set(values)))),
    ).reset_index()


def selection_universe_plan(
    history: pd.DataFrame,
    selection_dates: Iterable[str],
) -> pd.DataFrame:
    rows = []
    for date in sorted({str(value)[:10] for value in selection_dates if str(value)}):
        snapshot, evidence = constituents_asof(history, pd.Timestamp(date))
        for item in snapshot.itertuples(index=False):
            rows.append({
                "selection_date": date,
                "report_date": evidence.get("report_date"),
                "membership_available_date": evidence.get("available_date"),
                "ticker": str(item.ticker).upper(),
            })
    return pd.DataFrame(rows).drop_duplicates(
        ["selection_date", "ticker"]
    ).sort_values(["selection_date", "ticker"]).reset_index(drop=True)


def point_in_time_coverage(
    universe_plan: pd.DataFrame,
    crosswalk: pd.DataFrame,
    records: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    plan_input = universe_plan.copy()
    if "cik" in plan_input.columns:
        # Some current-universe plans already carry the CIK.  Keep the
        # crosswalk as the authoritative mapping, but validate that the two
        # identity sources do not silently disagree before dropping the
        # duplicate input column.
        plan_input = plan_input.rename(columns={"cik": "plan_cik"})
    plan = plan_input.merge(
        crosswalk[["ticker", "cik", "mapping_status", "mapping_method"]],
        on="ticker",
        how="left",
        validate="many_to_one",
    )
    if "plan_cik" in plan.columns:
        plan_cik = pd.to_numeric(plan["plan_cik"], errors="coerce")
        crosswalk_cik = pd.to_numeric(plan["cik"], errors="coerce")
        conflicts = (
            plan_cik.notna()
            & crosswalk_cik.notna()
            & plan_cik.ne(crosswalk_cik)
        )
        if bool(conflicts.any()):
            tickers = sorted(plan.loc[conflicts, "ticker"].astype(str).unique())
            raise NdxFundamentalError(
                "universe plan CIK conflicts with SEC crosswalk for ticker(s): "
                + ", ".join(tickers)
            )
        plan = plan.drop(columns=["plan_cik"])
    record_groups = {
        (int(cik), metric): frame.sort_values(
            ["available_date", "period_end"], kind="stable"
        )
        for (cik, metric), frame in records.groupby(["cik", "metric"])
    } if not records.empty else {}
    detail_rows = []
    for row in plan.itertuples(index=False):
        for metric in METRIC_CONCEPTS:
            cik = int(row.cik) if pd.notna(row.cik) else None
            available = pd.DataFrame()
            if cik is not None:
                source = record_groups.get((cik, metric))
                if source is not None:
                    available = source[
                        (source["available_date"] <= row.selection_date)
                        & (source["period_end"] < row.selection_date)
                    ]
            latest = available.iloc[-1] if not available.empty else None
            detail_rows.append({
                "selection_date": row.selection_date,
                "report_date": row.report_date,
                "membership_available_date": row.membership_available_date,
                "ticker": row.ticker,
                "cik": cik,
                "mapping_status": row.mapping_status,
                "mapping_method": row.mapping_method,
                "metric": metric,
                "available": latest is not None,
                "latest_fact_available_date": (
                    latest["available_date"] if latest is not None else None
                ),
                "latest_period_end": latest["period_end"] if latest is not None else None,
                "age_days": (
                    int((pd.Timestamp(row.selection_date) - pd.Timestamp(latest["period_end"])).days)
                    if latest is not None else None
                ),
                "namespace": latest["namespace"] if latest is not None else None,
                "concept": latest["concept"] if latest is not None else None,
                "unit": latest["unit"] if latest is not None else None,
                "form": latest["form"] if latest is not None else None,
                "accession_number": (
                    latest["accession_number"] if latest is not None else None
                ),
                "future_data_guard_passed": bool(
                    latest is None
                    or (
                        str(latest["available_date"]) <= row.selection_date
                        and str(latest["period_end"]) < row.selection_date
                    )
                ),
            })
    detail = pd.DataFrame(detail_rows)
    summary = detail.groupby(["selection_date", "metric"]).agg(
        universe_count=("ticker", "size"),
        cik_mapped_count=("cik", "count"),
        available_count=("available", "sum"),
        coverage=("available", "mean"),
        age_days_p50=("age_days", "median"),
        age_days_p90=("age_days", lambda values: values.quantile(0.90)),
        future_data_guard_passed=("future_data_guard_passed", "all"),
    ).reset_index()
    return detail, summary


def raw_bundle_sha256(index: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for row in index.sort_values("cik").itertuples(index=False):
        digest.update(str(int(row.cik)).encode("ascii"))
        digest.update(str(row.content_sha256).encode("ascii"))
    return digest.hexdigest()


def load_companyfacts_records(
    raw_dir: str | Path,
    ciks: Iterable[int],
    *,
    metric_concepts: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = Path(raw_dir)
    records = []
    index_rows = []
    for cik in sorted({int(value) for value in ciks}):
        path = raw / f"CIK{cik:010d}.json"
        if not path.exists():
            continue
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
        validate_companyfacts_payload(payload, cik)
        frame = companyfacts_records(payload, metric_concepts=metric_concepts)
        if not frame.empty:
            records.append(frame)
        index_rows.append({
            "cik": cik,
            "entity_name": payload.get("entityName"),
            "path": path.as_posix(),
            "content_bytes": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "target_record_count": len(frame),
        })
    combined = (
        pd.concat(records, ignore_index=True)
        if records
        else companyfacts_records(
            {"cik": 0, "facts": {}},
            metric_concepts=metric_concepts,
        )
    )
    return combined, pd.DataFrame(index_rows)
