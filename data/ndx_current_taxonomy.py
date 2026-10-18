"""Point-in-time SEC annual-filing selection for current NDX taxonomy evidence."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Mapping

import pandas as pd

from data.ndx_taxonomy import NdxTaxonomyError


CURRENT_TAXONOMY_PLAN_SCHEMA_VERSION = 1
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
ANNUAL_BUSINESS_FORMS = frozenset({"10-K", "20-F", "40-F"})


def normalized_cik(value: object) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not digits:
        return ""
    return digits.zfill(10)


def submissions_url(cik: object) -> str:
    normalized = normalized_cik(cik)
    return SEC_SUBMISSIONS_URL.format(cik=normalized) if normalized else ""


def filing_index_url(cik: object, accession_number: object) -> str:
    """Return the SEC archive directory JSON for one filing."""
    normalized = normalized_cik(cik)
    accession = str(accession_number or "").strip()
    if not normalized or not accession:
        return ""
    return (
        f"{SEC_ARCHIVES_URL}/{int(normalized)}/{accession.replace('-', '')}/"
        "index.json"
    )


def filing_html_index_url(cik: object, accession_number: object) -> str:
    """Return the official SEC HTML filing index used only as JSON fallback."""
    normalized = normalized_cik(cik)
    accession = str(accession_number or "").strip()
    if not normalized or not accession:
        return ""
    return (
        f"{SEC_ARCHIVES_URL}/{int(normalized)}/{accession.replace('-', '')}/"
        f"{accession}-index.html"
    )


def filing_document_url(
    cik: object,
    accession_number: object,
    primary_document: object,
) -> str:
    normalized = normalized_cik(cik)
    accession = str(accession_number or "").strip()
    document = str(primary_document or "").strip().replace("\\", "/")
    if not normalized or not accession or not document or "/" in document or ".." in document:
        return ""
    return (
        f"{SEC_ARCHIVES_URL}/{int(normalized)}/{accession.replace('-', '')}/"
        f"{document}"
    )


def _as_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def select_latest_business_filing(
    payload: Mapping[str, object],
    observation_date: str,
) -> dict:
    """Select the latest complete annual business filing available by the date.

    Amendments are allowed only as a fallback.  This function selects a filing
    locator; it never reads business text and never assigns a risk chain.
    """
    observed = _as_date(observation_date)
    if observed is None:
        raise NdxTaxonomyError(f"invalid observation date: {observation_date}")
    cik = normalized_cik(payload.get("cik"))
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, Mapping) else None
    if not isinstance(recent, Mapping):
        return {
            "status": "submissions_recent_missing",
            "reason": "SEC submissions payload has no recent filing arrays",
            "cik": cik,
        }
    required_arrays = {}
    for column in ("form", "filingDate", "accessionNumber", "primaryDocument"):
        value = recent.get(column)
        if not isinstance(value, list):
            return {
                "status": "submissions_schema_invalid",
                "reason": f"SEC submissions field {column} is not an array",
                "cik": cik,
            }
        required_arrays[column] = value
    lengths = {len(value) for value in required_arrays.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        return {
            "status": "submissions_schema_invalid",
            "reason": "SEC submissions annual filing arrays have different lengths",
            "cik": cik,
        }
    row_count = next(iter(lengths))
    acceptance_values = recent.get("acceptanceDateTime")
    if not isinstance(acceptance_values, list) or len(acceptance_values) != row_count:
        acceptance_values = [""] * row_count
    candidates = []
    for position, form_value in enumerate(required_arrays["form"]):
        form = str(form_value or "").strip().upper()
        base_form = form.replace("/A", "")
        filed = _as_date(required_arrays["filingDate"][position])
        accession = str(required_arrays["accessionNumber"][position] or "").strip()
        primary = str(required_arrays["primaryDocument"][position] or "").strip()
        if base_form not in ANNUAL_BUSINESS_FORMS or filed is None or filed > observed:
            continue
        document_url = filing_document_url(cik, accession, primary)
        if not document_url:
            continue
        acceptance = str(acceptance_values[position] or "")
        candidates.append({
            "cik": cik,
            "form": form,
            "base_form": base_form,
            "filing_date": filed.isoformat(),
            "acceptance_datetime": acceptance,
            "accession_number": accession,
            "primary_document": primary,
            "index_url": filing_index_url(cik, accession),
            "document_url": document_url,
            "source_available_date": filed.isoformat(),
            "selection_method": "latest_annual_business_filing_asof_observation",
        })
    if not candidates:
        return {
            "status": "no_eligible_annual_filing",
            "reason": "no 10-K/20-F/40-F with a primary document was filed by observation date",
            "cik": cik,
        }
    base_candidates = [candidate for candidate in candidates if candidate["form"] in ANNUAL_BUSINESS_FORMS]
    eligible_candidates = base_candidates or candidates
    selected = max(
        eligible_candidates,
        key=lambda row: (
            row["filing_date"],
            row["acceptance_datetime"],
            row["accession_number"],
        ),
    )
    selected["selection_method"] = (
        "latest_annual_business_filing_asof_observation"
        if base_candidates
        else "latest_annual_business_amendment_fallback_asof_observation"
    )
    selected["status"] = "planned"
    selected["reason"] = "annual SEC business filing is available by observation date"
    return selected


def build_current_taxonomy_plan(
    observations: pd.DataFrame,
    submissions_by_cik: Mapping[str, Mapping[str, object]],
    *,
    observation_date: str,
) -> pd.DataFrame:
    """Build one current evidence job per issuer and retain every security class."""
    required = {
        "observation_date",
        "ticker",
        "cik",
        "issuer_id",
        "security_id",
    }
    missing = sorted(required - set(observations.columns))
    if missing:
        raise NdxTaxonomyError(f"current taxonomy observations missing: {missing}")
    observed = _as_date(observation_date)
    if observed is None:
        raise NdxTaxonomyError(f"invalid observation date: {observation_date}")
    frame = observations.copy()
    frame["observation_date"] = frame["observation_date"].astype(str).str[:10]
    if frame["observation_date"].ne(observed.isoformat()).any():
        raise NdxTaxonomyError("current taxonomy observations contain another date")
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    if frame["ticker"].eq("QQQ").any():
        raise NdxTaxonomyError("QQQ cannot enter current taxonomy evidence")
    frame["cik"] = frame["cik"].map(normalized_cik)
    if frame["cik"].eq("").any():
        raise NdxTaxonomyError("current taxonomy observations contain an unresolved CIK")

    rows = []
    for cik, group in frame.groupby("cik", sort=True):
        payload = submissions_by_cik.get(cik)
        selected = (
            select_latest_business_filing(payload, observation_date)
            if payload is not None
            else {
                "status": "submission_not_cached",
                "reason": "SEC submissions JSON is not cached; fetch required",
                "cik": cik,
            }
        )
        selected_status = str(selected.get("status") or "")
        accession = str(selected.get("accession_number") or "")
        document_url = str(selected.get("document_url") or "")
        job_id = (
            hashlib.sha256(
                f"{cik}|{accession}|{document_url}".encode("utf-8")
            ).hexdigest()[:16]
            if accession and document_url
            else f"pending_{cik}"
        )
        for item in group.sort_values("ticker").itertuples(index=False):
            rows.append({
                "job_id": job_id,
                "issuer_id": str(item.issuer_id),
                "security_id": str(item.security_id),
                "ticker": str(item.ticker).upper(),
                "cik": cik,
                "cusip": "",
                "observation_from": observed.isoformat(),
                "evidence_required_from": observed.isoformat(),
                "form": str(selected.get("form") or ""),
                "filing_date": str(selected.get("filing_date") or ""),
                "acceptance_datetime": str(selected.get("acceptance_datetime") or ""),
                "source_available_date": str(selected.get("source_available_date") or ""),
                "accession_number": accession,
                "primary_document": str(selected.get("primary_document") or ""),
                "sec_index_url": str(selected.get("index_url") or submissions_url(cik)),
                "document_url": document_url,
                "plan_status": selected_status,
                "selection_method": str(selected.get("selection_method") or ""),
                "reason": str(selected.get("reason") or ""),
                "future_data_guard": "evidence_available_date <= selection_date",
                "classification_allowed": False,
            })
    columns = [
        "job_id", "issuer_id", "security_id", "ticker", "cik", "cusip",
        "observation_from", "evidence_required_from", "form", "filing_date",
        "acceptance_datetime", "source_available_date", "accession_number",
        "primary_document", "sec_index_url", "document_url", "plan_status",
        "selection_method", "reason", "future_data_guard", "classification_allowed",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["cik", "ticker"], kind="stable"
    ).reset_index(drop=True)


__all__ = [
    "ANNUAL_BUSINESS_FORMS",
    "CURRENT_TAXONOMY_PLAN_SCHEMA_VERSION",
    "build_current_taxonomy_plan",
    "filing_document_url",
    "filing_html_index_url",
    "filing_index_url",
    "normalized_cik",
    "select_latest_business_filing",
    "submissions_url",
]
