"""Point-in-time SEC evidence plan for the live incumbent overlay.

The historical NDX identity universe does not contain TSM, while the live
configuration does.  This module keeps that distinction explicit and selects
annual SEC filings for the incumbent names without assigning a risk chain.
Classification remains a separate, hash-locked review decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import yaml

from data.ndx_taxonomy_review import _classification_excerpt, extract_business_section
from data.versioning import file_sha256, manifest_path, write_dataset_manifest


OVERLAY_SCHEMA_VERSION = 1
ANNUAL_FORMS = {"10-K", "20-F", "40-F"}

OVERLAY_PLAN_COLUMNS = [
    "overlay_id",
    "ticker",
    "security_id",
    "issuer_id",
    "cik",
    "cusip",
    "identity_status",
    "selection_date_start",
    "selection_date_end",
    "form",
    "report_date",
    "filed_date",
    "evidence_available_date",
    "accession_number",
    "document_url",
    "sec_index_url",
    "selection_method",
    "classification_allowed",
    "future_data_guard",
    "status",
]

REVIEW_DOCUMENT_COLUMNS = [
    "overlay_id",
    "ticker",
    "security_id",
    "issuer_id",
    "cik",
    "cusip",
    "form",
    "report_date",
    "filed_date",
    "evidence_available_date",
    "accession_number",
    "document_url",
    "raw_path",
    "raw_manifest_path",
    "raw_sha256",
    "raw_manifest_sha256",
    "raw_manifest_verified",
    "extraction_status",
    "section_label",
    "section_text_chars",
    "section_text_sha256",
    "business_excerpt",
    "business_excerpt_sha256",
    "business_excerpt_truncated",
    "review_status",
]

REVIEW_TEMPLATE_COLUMNS = [
    "evidence_id",
    "overlay_id",
    "ticker",
    "security_id",
    "issuer_id",
    "risk_chain",
    "effective_from",
    "effective_to",
    "evidence_source_type",
    "evidence_source",
    "evidence_locator",
    "evidence_available_date",
    "accession_number",
    "evidence_excerpt",
    "confidence",
    "status",
    "notes",
]

ATTEMPT_COLUMNS = [
    "overlay_id",
    "ticker",
    "cik",
    "status",
    "attempted_at",
    "submission_url",
    "accession_number",
    "document_url",
    "raw_path",
    "content_sha256",
    "error",
]


class NdxIncumbentOverlayError(ValueError):
    """Raised when an incumbent evidence overlay is unsafe or incomplete."""


def _ticker(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
        raise NdxIncumbentOverlayError(f"invalid incumbent ticker: {value!r}")
    return symbol


def _cik(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw.isdigit() or int(raw) <= 0:
        raise NdxIncumbentOverlayError(f"invalid incumbent CIK: {value!r}")
    return f"{int(raw):010d}"


def _iso_date(value: Any, *, field: str) -> str:
    raw = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise NdxIncumbentOverlayError(f"invalid {field}: {value!r}") from exc


def _optional_iso_date(value: Any) -> str:
    raw = str(value or "").strip()[:10]
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return ""


def load_incumbent_tickers(config: Mapping[str, Any]) -> list[str]:
    symbols = config.get("symbols") or []
    if not isinstance(symbols, list) or not symbols:
        raise NdxIncumbentOverlayError("config.symbols is empty")
    tickers = [_ticker(item.get("ticker")) for item in symbols if isinstance(item, Mapping)]
    if len(tickers) != len(symbols) or len(tickers) != len(set(tickers)):
        raise NdxIncumbentOverlayError("config.symbols contains invalid or duplicate tickers")
    if "QQQ" in tickers or "SGOV" in tickers:
        raise NdxIncumbentOverlayError("ETF/safe-leg ticker cannot be an incumbent stock")
    return tickers


def resolve_sec_company_tickers(
    payload: Mapping[str, Any],
    tickers: Iterable[str],
    *,
    allow_missing: bool = False,
) -> dict[str, dict]:
    fields = payload.get("fields") or []
    rows = payload.get("data") or []
    if fields != ["cik", "name", "ticker", "exchange"] or not isinstance(rows, list):
        raise NdxIncumbentOverlayError("SEC company ticker payload schema changed")
    wanted = {_ticker(value) for value in tickers}
    matches: dict[str, list[dict]] = {ticker: [] for ticker in wanted}
    for values in rows:
        if not isinstance(values, list) or len(values) != len(fields):
            continue
        row = dict(zip(fields, values))
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker in matches:
            matches[ticker].append(row)
    resolved = {}
    for ticker, candidates in matches.items():
        if not candidates and allow_missing:
            continue
        if len(candidates) != 1:
            raise NdxIncumbentOverlayError(
                f"SEC company ticker mapping is not unique for {ticker}: {len(candidates)}"
            )
        row = candidates[0]
        resolved[ticker] = {
            "ticker": ticker,
            "cik": _cik(row.get("cik")),
            "name": str(row.get("name") or "").strip(),
            "exchange": str(row.get("exchange") or "").strip(),
        }
    return resolved


def load_identity_overrides(
    path: str | Path,
    tickers: Iterable[str],
) -> dict[str, dict]:
    """Load explicitly sourced SEC submissions identities not in the ticker file."""

    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise NdxIncumbentOverlayError(
            f"invalid incumbent identity overrides: {target}"
        ) from exc
    if int(payload.get("schema_version") or 0) != 1:
        raise NdxIncumbentOverlayError("incumbent identity overrides schema_version must be 1")
    rows = payload.get("identities")
    if not isinstance(rows, list):
        raise NdxIncumbentOverlayError("incumbent identity overrides identities must be a list")
    wanted = {_ticker(value) for value in tickers}
    result: dict[str, dict] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            raise NdxIncumbentOverlayError("incumbent identity override is not a mapping")
        ticker = _ticker(item.get("ticker"))
        if ticker not in wanted:
            continue
        if ticker in result:
            raise NdxIncumbentOverlayError(f"duplicate incumbent identity override: {ticker}")
        source_type = str(item.get("source_type") or "").strip()
        source_locator = str(item.get("source_locator") or "").strip()
        if source_type != "sec_submissions" or not source_locator.startswith(
            "https://data.sec.gov/submissions/"
        ):
            raise NdxIncumbentOverlayError(
                f"identity override must cite SEC submissions: {ticker}"
            )
        result[ticker] = {
            "ticker": ticker,
            "cik": _cik(item.get("cik")),
            "name": str(item.get("name") or "").strip(),
            "exchange": str(item.get("exchange") or "").strip(),
            "identity_status": "incumbent_overlay_identity_by_sec_submissions_crosswalk",
            "identity_source_type": source_type,
            "identity_source_locator": source_locator,
        }
    return result


def load_local_identity(identity_path: str | Path, tickers: Iterable[str]) -> dict[str, dict]:
    path = Path(identity_path)
    if not path.exists():
        raise NdxIncumbentOverlayError(f"incumbent identity file is missing: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"security_id", "issuer_id", "ticker", "cik", "cusip", "identity_status"}
    if not required.issubset(frame.columns):
        raise NdxIncumbentOverlayError(
            f"incumbent identity file missing columns: {sorted(required - set(frame.columns))}"
        )
    wanted = {_ticker(value) for value in tickers}
    result: dict[str, dict] = {}
    for row in frame.to_dict(orient="records"):
        ticker = str(row.get("ticker") or "").upper()
        if ticker in wanted:
            result[ticker] = {
                "security_id": str(row.get("security_id") or ""),
                "issuer_id": str(row.get("issuer_id") or ""),
                "cik": _cik(row.get("cik")),
                "cusip": str(row.get("cusip") or "").upper(),
                "identity_status": str(row.get("identity_status") or ""),
            }
    return result


def build_identity_rows(
    config: Mapping[str, Any],
    *,
    identity_path: str | Path,
    sec_company_tickers: Mapping[str, Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Join seven NDX identities with the separate TSM overlay identity."""

    tickers = load_incumbent_tickers(config)
    local = load_local_identity(identity_path, tickers)
    rows = []
    for ticker in tickers:
        if ticker in local:
            identity = local[ticker]
            rows.append({
                "ticker": ticker,
                **identity,
                "identity_status": "ndx_historical_identity",
            })
            continue
        if not sec_company_tickers or ticker not in sec_company_tickers:
            rows.append({
                "ticker": ticker,
                "security_id": f"security:incumbent_overlay:{ticker}",
                "issuer_id": "",
                "cik": "",
                "cusip": "",
                "identity_status": "requires_sec_company_ticker_resolution",
            })
            continue
        item = sec_company_tickers[ticker]
        cik = _cik(item.get("cik"))
        rows.append({
            "ticker": ticker,
            "security_id": f"security:incumbent_overlay:{ticker}",
            "issuer_id": f"issuer:{cik}",
            "cik": cik,
            "cusip": "",
            "identity_status": str(
                item.get(
                    "identity_status",
                    "incumbent_overlay_identity_by_sec_ticker_crosswalk",
                )
            ),
        })
    return pd.DataFrame(rows, columns=[
        "ticker", "security_id", "issuer_id", "cik", "cusip", "identity_status"
    ])


def parse_submission_filings(
    payload: Mapping[str, Any],
    *,
    cik: str | None = None,
) -> list[dict]:
    filings_payload = payload.get("filings") or {}
    recent = filings_payload.get("recent") if isinstance(filings_payload, Mapping) else None
    source = recent if isinstance(recent, Mapping) else payload
    required = ["form", "reportDate", "filingDate", "accessionNumber", "primaryDocument"]
    if not all(isinstance(source.get(key), list) for key in required):
        raise NdxIncumbentOverlayError("SEC submissions payload missing filing arrays")
    length = len(source["form"])
    if any(len(source[key]) != length for key in required):
        raise NdxIncumbentOverlayError("SEC submissions filing arrays have inconsistent lengths")
    resolved_cik = _cik(cik or payload.get("cik"))
    rows = []
    for index, raw_form in enumerate(source["form"]):
        raw_form_text = str(raw_form or "").upper().strip()
        # An amendment often contains only a cover page or incorporated
        # exhibits.  It is not a safe substitute for the original business
        # description, so the selector uses the original annual filing.
        if raw_form_text.endswith("/A"):
            continue
        form = raw_form_text
        if form not in ANNUAL_FORMS:
            continue
        filed_date = _optional_iso_date(source["filingDate"][index])
        if not filed_date:
            continue
        accession = str(source["accessionNumber"][index] or "").strip()
        primary = Path(str(source["primaryDocument"][index] or "")).name
        if not accession or not primary:
            continue
        compact = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(resolved_cik)}/{compact}"
        rows.append({
            "cik": resolved_cik,
            "form": form,
            "report_date": _optional_iso_date(source["reportDate"][index]),
            "filed_date": filed_date,
            "evidence_available_date": (
                date.fromisoformat(filed_date) + timedelta(days=1)
            ).isoformat(),
            "accession_number": accession,
            "document_url": f"{base}/{primary}",
            "sec_index_url": f"{base}/index.json",
        })
    return sorted(rows, key=lambda row: (row["filed_date"], row["accession_number"]))


def select_annual_filing(filings: Iterable[Mapping[str, Any]], selection_start: str) -> dict:
    """Select the latest annual filing available by the research start date."""

    cutoff = _iso_date(selection_start, field="selection_date_start")
    rows = [dict(row) for row in filings if str(row.get("form") or "") in ANNUAL_FORMS]
    rows.sort(key=lambda row: (str(row.get("filed_date") or ""), str(row.get("accession_number") or "")))
    before = [row for row in rows if str(row.get("evidence_available_date") or "") <= cutoff]
    if before:
        selected = dict(before[-1])
        selected["selection_method"] = "latest_annual_filing_available_by_selection_start"
        selected["status"] = "selected_pit_annual_filing"
        return selected
    if rows:
        selected = dict(rows[0])
        selected["selection_method"] = "earliest_annual_filing_after_selection_start"
        selected["status"] = "selected_after_observation_start_unclassified_before_evidence"
        return selected
    return {
        "form": "",
        "report_date": "",
        "filed_date": "",
        "evidence_available_date": "",
        "accession_number": "",
        "document_url": "",
        "sec_index_url": "",
        "selection_method": "no_annual_sec_filing_found",
        "status": "no_annual_sec_filing_found",
    }


def build_overlay_plan(
    identities: pd.DataFrame,
    *,
    selection_start: str = "2019-09-30",
    selection_end: str = "2026-03-31",
    submissions_by_cik: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
) -> pd.DataFrame:
    start = _iso_date(selection_start, field="selection_date_start")
    end = _iso_date(selection_end, field="selection_date_end")
    rows = []
    for identity in identities.to_dict(orient="records"):
        ticker = _ticker(identity.get("ticker"))
        cik = str(identity.get("cik") or "")
        selected = {}
        if cik and submissions_by_cik:
            selected = select_annual_filing(
                submissions_by_cik.get(cik, []), start
            )
        rows.append({
            "overlay_id": f"incumbent_overlay:{ticker}",
            "ticker": ticker,
            "security_id": str(identity.get("security_id") or ""),
            "issuer_id": str(identity.get("issuer_id") or ""),
            "cik": cik,
            "cusip": str(identity.get("cusip") or ""),
            "identity_status": str(identity.get("identity_status") or ""),
            "selection_date_start": start,
            "selection_date_end": end,
            "form": selected.get("form", ""),
            "report_date": selected.get("report_date", ""),
            "filed_date": selected.get("filed_date", ""),
            "evidence_available_date": selected.get("evidence_available_date", ""),
            "accession_number": selected.get("accession_number", ""),
            "document_url": selected.get("document_url", ""),
            "sec_index_url": selected.get("sec_index_url", ""),
            "selection_method": selected.get(
                "selection_method", "requires_sec_submissions_resolution"
            ),
            "classification_allowed": False,
            "future_data_guard": (
                bool(selected.get("evidence_available_date"))
                and str(selected.get("evidence_available_date")) <= start
            ),
            "status": selected.get("status", "requires_sec_submissions_resolution"),
        })
    return pd.DataFrame(rows, columns=OVERLAY_PLAN_COLUMNS)


def _manifest_verified(path: Path) -> tuple[bool, str, str, str]:
    sidecar = manifest_path(path)
    if not path.exists() or not sidecar.exists():
        return False, "", str(sidecar), ""
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False, "", str(sidecar), ""
    digest = file_sha256(path)
    return (
        payload.get("content_sha256") == digest,
        digest,
        str(sidecar),
        hashlib.sha256(sidecar.read_bytes()).hexdigest(),
    )


def build_review_pack(
    plan: pd.DataFrame,
    *,
    raw_root: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract source text into a pending-only review pack."""

    root = Path(raw_root).resolve()
    documents = []
    templates = []
    for row in plan.to_dict(orient="records"):
        raw_path_text = str(row.get("raw_path") or "").strip()
        if not raw_path_text:
            continue
        raw_path = Path(raw_path_text)
        try:
            raw_path.resolve().relative_to(root)
        except ValueError as exc:
            raise NdxIncumbentOverlayError(
                f"overlay raw path escapes raw root: {raw_path}"
            ) from exc
        if not raw_path.exists() or not str(row.get("form") or ""):
            continue
        manifest_ok, raw_sha, raw_manifest_path, raw_manifest_sha = _manifest_verified(raw_path)
        if not manifest_ok:
            raise NdxIncumbentOverlayError(f"overlay raw manifest is not verified: {raw_path}")
        extraction = extract_business_section(raw_path.read_bytes(), str(row["form"]))
        section = str(extraction.get("section_text") or "")
        excerpt = _classification_excerpt(section, str(row["form"]))
        documents.append({
            "overlay_id": row["overlay_id"],
            "ticker": row["ticker"],
            "security_id": row["security_id"],
            "issuer_id": row["issuer_id"],
            "cik": row["cik"],
            "cusip": row["cusip"],
            "form": row["form"],
            "report_date": row["report_date"],
            "filed_date": row["filed_date"],
            "evidence_available_date": row["evidence_available_date"],
            "accession_number": row["accession_number"],
            "document_url": row["document_url"],
            "raw_path": raw_path.as_posix(),
            "raw_manifest_path": raw_manifest_path,
            "raw_sha256": raw_sha,
            "raw_manifest_sha256": raw_manifest_sha,
            "raw_manifest_verified": manifest_ok,
            "extraction_status": extraction.get("extraction_status", ""),
            "section_label": extraction.get("section_label", ""),
            "section_text_chars": len(section),
            "section_text_sha256": hashlib.sha256(section.encode("utf-8")).hexdigest() if section else "",
            "business_excerpt": excerpt,
            "business_excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest() if excerpt else "",
            "business_excerpt_truncated": len(section) > len(excerpt),
            "review_status": "pending_manual_review",
        })
        templates.append({
            "evidence_id": f"sec_overlay:{row['overlay_id']}:{row['accession_number']}",
            "overlay_id": row["overlay_id"],
            "ticker": row["ticker"],
            "security_id": row["security_id"],
            "issuer_id": row["issuer_id"],
            "risk_chain": "",
            "effective_from": "",
            "effective_to": "",
            "evidence_source_type": "sec_filing_business_description",
            "evidence_source": f"SEC {row['form']} business description review",
            "evidence_locator": row["document_url"],
            "evidence_available_date": row["evidence_available_date"],
            "accession_number": row["accession_number"],
            "evidence_excerpt": excerpt,
            "confidence": "",
            "status": "pending_review",
            "notes": (
                f"extraction_status={extraction.get('extraction_status', '')}; "
                "risk_chain/confidence must be decided from the source text, never from returns."
            ),
        })
    return (
        pd.DataFrame(documents, columns=REVIEW_DOCUMENT_COLUMNS),
        pd.DataFrame(templates, columns=REVIEW_TEMPLATE_COLUMNS),
    )
