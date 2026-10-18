"""Point-in-time Nasdaq-100 security proxy from public QQQ SEC filings.

QQQ is not a candidate asset here. Invesco states that the trust holds all
component securities of the Nasdaq-100; its SEC N-PORT filings therefore give
a complete, official quarterly security snapshot. A snapshot becomes usable
only after its actual SEC filing date, preventing report-period look-ahead.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from core.helpers import atomic_write_text, project_root, proxy_env
from data.versioning import file_sha256, manifest_path, utc_now_iso, write_dataset_manifest


QQQ_CIK = "0001067839"
SEC_SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{QQQ_CIK}.json"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/1067839"
DEFAULT_SEC_USER_AGENT = "us_ratchet/1.0 research-contact@example.com"

MIN_REPORT_SECURITIES = 100
MAX_REPORT_SECURITIES = 110
MIN_REPORT_EQUITY_WEIGHT = 0.98
MAX_REPORT_EQUITY_WEIGHT = 1.02
HISTORY_SCOPE = "last_public_sec_filing_available_date"

HISTORY_COLUMNS = [
    "report_date",
    "filed_date",
    "available_date",
    "accession_number",
    "ticker",
    "name",
    "cusip",
    "isin",
    "weight",
    "value_usd",
    "mapping_method",
    "source_locator",
]


class NdxHistoryError(RuntimeError):
    pass


@dataclass
class NdxHistoryMeta:
    source: str
    rows: int
    report_count: int
    cached: bool
    stale: bool = False
    manifest: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "rows": int(self.rows),
            "report_count": int(self.report_count),
            "cached": bool(self.cached),
            "stale": bool(self.stale),
            "version_id": self.manifest.get("version_id"),
            "data_start": self.manifest.get("data_start"),
            "data_end": self.manifest.get("data_end"),
            "fetched_at": self.manifest.get("fetched_at"),
            "point_in_time_scope": self.manifest.get("point_in_time_scope"),
            "historical_backtest_allowed": bool(
                self.manifest.get("historical_backtest_allowed", False)
            ),
            "errors": dict(self.errors),
        }


def _cache_dir(cfg) -> Path:
    direct = getattr(cfg, "cache_dir", None)
    if direct is not None:
        return Path(direct)
    data_cfg = getattr(cfg, "data", None)
    return Path(getattr(data_cfg, "cache_dir", "data/cache"))


def _history_dir(cfg) -> Path:
    return _cache_dir(cfg) / "candidate_pools" / "ndx_history"


def _history_path(cfg) -> Path:
    return _history_dir(cfg) / "qqq_nport_constituents.csv"


def _company_tickers_path(cfg) -> Path:
    return _history_dir(cfg) / "sec_company_tickers_exchange.json"


def _proxy_cfg(cfg):
    return getattr(getattr(cfg, "data", None), "proxy", None)


def _sec_user_agent(value: str | None = None) -> str:
    agent = str(value or os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT).strip()
    if "@" not in agent or len(agent) < 12:
        raise NdxHistoryError(
            "SEC_USER_AGENT must identify the research client and include a contact email"
        )
    return agent


def _sec_headers(user_agent: str) -> dict:
    email_match = re.search(r"[^\s<>]+@[^\s<>]+", user_agent)
    return {
        "User-Agent": user_agent,
        "From": email_match.group(0) if email_match else "",
        "Accept-Encoding": "gzip, deflate",
    }


def _normalize_company_name(value: str) -> str:
    text = str(value or "").lower().replace("&", "and")
    text = re.sub(r"\(the\)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    ignored = {
        "the", "inc", "incorporated", "corp", "corporation", "co", "company",
        "plc", "nv", "n", "v", "se", "ltd", "limited", "holdings", "holding",
        "group", "de", "uk", "mo", "md", "ca", "ma", "new", "can",
    }
    return "".join(token for token in text.split() if token not in ignored)


def _load_overrides(path: str | Path | None = None) -> tuple[dict, dict]:
    target = Path(path) if path else project_root() / "config" / "ndx_ticker_overrides.yaml"
    if not target.exists():
        raise NdxHistoryError(f"NDX ticker override file missing: {target}")
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise NdxHistoryError(f"invalid NDX ticker override file: {target}") from exc
    if int(payload.get("schema_version") or 0) != 1:
        raise NdxHistoryError("NDX ticker override schema_version must be 1")
    overrides = {}
    for cusip, item in (payload.get("overrides") or {}).items():
        ticker = str((item or {}).get("ticker") or "").upper().strip()
        reason = str((item or {}).get("reason") or "").strip()
        match_name = str((item or {}).get("match_name") or "").strip()
        min_report_date = str((item or {}).get("min_report_date") or "").strip()
        max_report_date = str((item or {}).get("max_report_date") or "").strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker) or not reason:
            raise NdxHistoryError(f"invalid CUSIP override: {cusip}")
        for value in (min_report_date, max_report_date):
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise NdxHistoryError(f"invalid report date in CUSIP override: {cusip}") from exc
        overrides[str(cusip).upper().strip()] = {
            "ticker": ticker,
            "reason": reason,
            "match_name": _normalize_company_name(match_name) if match_name else "",
            "min_report_date": min_report_date,
            "max_report_date": max_report_date,
        }
    meta = {
        "mapping_id": payload.get("mapping_id"),
        "path": target.as_posix(),
        "content_sha256": file_sha256(target),
    }
    return overrides, meta


def _local_tag(element) -> str:
    return str(element.tag).split("}")[-1]


def _first_text(root, tag: str) -> str | None:
    for element in root.iter():
        if _local_tag(element) == tag:
            value = str(element.text or "").strip()
            return value or None
    return None


def parse_nport_equities(
    raw_xml: bytes,
    *,
    report_date: str,
    filed_date: str,
    accession_number: str,
    source_locator: str,
) -> pd.DataFrame:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise NdxHistoryError(f"{accession_number}: invalid N-PORT XML") from exc
    xml_report_date = _first_text(root, "repPdDate")
    if xml_report_date != report_date:
        raise NdxHistoryError(
            f"{accession_number}: report date mismatch metadata={report_date} xml={xml_report_date}"
        )
    registrant = _first_text(root, "regName") or ""
    if "QQQ" not in registrant.upper():
        raise NdxHistoryError(f"{accession_number}: filing is not Invesco QQQ")
    available_date = (date.fromisoformat(filed_date) + timedelta(days=1)).isoformat()
    rows = []
    for item in root.iter():
        if _local_tag(item) != "invstOrSec":
            continue
        values = {_local_tag(child): str(child.text or "").strip() for child in list(item)}
        try:
            balance = float(values.get("balance") or 0.0)
            value_usd = float(values.get("valUSD") or 0.0)
            weight = float(values.get("pctVal") or 0.0) / 100.0
        except ValueError as exc:
            raise NdxHistoryError(f"{accession_number}: invalid numeric holding") from exc
        if (
            values.get("assetCat") != "EC"
            or values.get("units") != "NS"
            or values.get("payoffProfile") not in {"", "Long"}
            or balance <= 0
            or value_usd <= 0
        ):
            continue
        isin = ""
        for child in list(item):
            if _local_tag(child) != "identifiers":
                continue
            for identifier in list(child):
                if _local_tag(identifier) == "isin":
                    isin = str(identifier.attrib.get("value") or "").strip()
        rows.append({
            "report_date": report_date,
            "filed_date": filed_date,
            "available_date": available_date,
            "accession_number": accession_number,
            "ticker": "",
            "name": values.get("name") or values.get("title") or "",
            "cusip": (values.get("cusip") or "").upper(),
            "isin": isin,
            "weight": weight,
            "value_usd": value_usd,
            "mapping_method": "",
            "source_locator": source_locator,
        })
    frame = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    if not MIN_REPORT_SECURITIES <= len(frame) <= MAX_REPORT_SECURITIES:
        raise NdxHistoryError(
            f"{accession_number}: equity count outside {MIN_REPORT_SECURITIES}.."
            f"{MAX_REPORT_SECURITIES}: {len(frame)}"
        )
    total_weight = float(frame["weight"].sum())
    if not MIN_REPORT_EQUITY_WEIGHT <= total_weight <= MAX_REPORT_EQUITY_WEIGHT:
        raise NdxHistoryError(
            f"{accession_number}: equity weight sum outside completeness range: {total_weight:.6f}"
        )
    if frame["name"].eq("").any() or frame["cusip"].eq("").any():
        raise NdxHistoryError(f"{accession_number}: blank holding name or CUSIP")
    if frame["cusip"].duplicated().any():
        duplicates = sorted(frame.loc[frame["cusip"].duplicated(False), "cusip"].unique())
        raise NdxHistoryError(f"{accession_number}: duplicate CUSIPs {duplicates}")
    return frame


def _company_ticker_index(payload: dict) -> dict[str, list[dict]]:
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    if fields != ["cik", "name", "ticker", "exchange"] or not data:
        raise NdxHistoryError("SEC company ticker response schema changed or is empty")
    index: dict[str, list[dict]] = {}
    for values in data:
        row = dict(zip(fields, values))
        name_key = _normalize_company_name(row.get("name"))
        ticker = str(row.get("ticker") or "").upper().strip()
        if name_key and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker):
            index.setdefault(name_key, []).append(row)
    return index


def resolve_nport_tickers(
    frame: pd.DataFrame,
    *,
    company_ticker_payload: dict,
    overrides: dict,
) -> pd.DataFrame:
    index = _company_ticker_index(company_ticker_payload)
    out = frame.copy()
    unresolved = []
    tickers = []
    methods = []
    for row in out.itertuples(index=False):
        override = overrides.get(str(row.cusip).upper())
        if override and (
            not override.get("match_name")
            or override["match_name"] == _normalize_company_name(row.name)
        ) and (
            not override.get("min_report_date")
            or str(row.report_date) >= override["min_report_date"]
        ) and (
            not override.get("max_report_date")
            or str(row.report_date) <= override["max_report_date"]
        ):
            tickers.append(override["ticker"])
            methods.append("explicit_cusip_override")
            continue
        candidates = index.get(_normalize_company_name(row.name), [])
        nasdaq = [item for item in candidates if item.get("exchange") == "Nasdaq"]
        selected = nasdaq or candidates
        unique = sorted({str(item.get("ticker") or "").upper() for item in selected})
        if len(unique) != 1:
            unresolved.append({
                "report_date": row.report_date,
                "cusip": row.cusip,
                "name": row.name,
                "candidate_tickers": unique,
            })
            tickers.append("")
            methods.append("unresolved")
            continue
        tickers.append(unique[0])
        methods.append("sec_company_name_exact")
    if unresolved:
        unique_errors = {
            (item["cusip"], item["name"], tuple(item["candidate_tickers"]))
            for item in unresolved
        }
        preview = sorted(unique_errors)[:20]
        raise NdxHistoryError(
            f"N-PORT ticker mapping incomplete; unresolved={len(unique_errors)} preview={preview}"
        )
    out["ticker"] = tickers
    out["mapping_method"] = methods
    duplicate_reports = []
    for report_date, group in out.groupby("report_date"):
        duplicates = sorted(group.loc[group["ticker"].duplicated(False), "ticker"].unique())
        if duplicates:
            duplicate_reports.append((report_date, duplicates))
    if duplicate_reports:
        raise NdxHistoryError(f"duplicate tickers after mapping: {duplicate_reports}")
    return out[HISTORY_COLUMNS]


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(HISTORY_COLUMNS) - set(frame.columns)
    if missing:
        raise NdxHistoryError(f"NDX history missing columns: {sorted(missing)}")
    out = frame[HISTORY_COLUMNS].copy()
    for column in (
        "report_date", "filed_date", "available_date", "accession_number", "ticker",
        "name", "cusip", "isin", "mapping_method", "source_locator",
    ):
        out[column] = out[column].fillna("").astype(str).str.strip()
    out["ticker"] = out["ticker"].str.upper()
    out["cusip"] = out["cusip"].str.upper()
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce")
    out["value_usd"] = pd.to_numeric(out["value_usd"], errors="coerce")
    if out.empty:
        raise NdxHistoryError("NDX history is empty")
    for column in ("report_date", "filed_date", "available_date"):
        parsed = pd.to_datetime(out[column], errors="coerce")
        if parsed.isna().any():
            raise NdxHistoryError(f"NDX history has invalid {column}")
        out[column] = parsed.dt.strftime("%Y-%m-%d")
    if out["ticker"].eq("").any() or out["weight"].isna().any():
        raise NdxHistoryError("NDX history has unresolved tickers or weights")
    if ((out["weight"] < 0) | (out["weight"] > 1)).any():
        raise NdxHistoryError("NDX history weights outside [0,1]")
    for report_date, group in out.groupby("report_date"):
        if not MIN_REPORT_SECURITIES <= len(group) <= MAX_REPORT_SECURITIES:
            raise NdxHistoryError(f"{report_date}: incomplete security count {len(group)}")
        if group["ticker"].duplicated().any():
            raise NdxHistoryError(f"{report_date}: duplicate mapped ticker")
        if group["available_date"].nunique() != 1:
            raise NdxHistoryError(f"{report_date}: multiple availability dates")
        if not MIN_REPORT_EQUITY_WEIGHT <= float(group["weight"].sum()) <= MAX_REPORT_EQUITY_WEIGHT:
            raise NdxHistoryError(f"{report_date}: incomplete equity weight sum")
    return out.sort_values(["report_date", "ticker"], kind="stable").reset_index(drop=True)


def _write_company_tickers_cache(cfg, raw: bytes, fetched_at: str) -> dict:
    path = _company_tickers_path(cfg)
    atomic_write_text(path, raw.decode("utf-8"))
    return write_dataset_manifest(
        path,
        dataset_type="sec_company_ticker_crosswalk",
        dataset_key="company_tickers_exchange",
        source="sec_company_tickers_exchange_json",
        source_locator=SEC_COMPANY_TICKERS_URL,
        fetched_at=fetched_at,
        row_count=len(json.loads(raw).get("data") or []),
        extra={"publication_time_known": False, "source_confidence": "official_sec_runtime"},
    )


def _write_history_cache(
    cfg,
    frame: pd.DataFrame,
    *,
    fetched_at: str,
    crosswalk_manifest: dict,
    override_meta: dict,
) -> dict:
    normalized = _normalize_history(frame)
    report_dates = sorted(normalized["report_date"].unique())
    filed_dates = sorted(normalized["filed_date"].unique())
    available_dates = sorted(normalized["available_date"].unique())
    accessions = sorted(normalized["accession_number"].unique())
    csv_text = normalized.to_csv(index=False, lineterminator="\n")
    content_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    archive = _history_dir(cfg) / "snapshots" / f"qqq_nport_{content_hash[:16]}.csv"
    common_extra = {
        "fund_ticker": "QQQ",
        "fund_cik": QQQ_CIK,
        "proxy_for": "Nasdaq-100 component securities",
        "observation_frequency": "quarterly_public_filing",
        "report_count": len(report_dates),
        "report_dates": report_dates,
        "filed_dates": filed_dates,
        "available_dates": available_dates,
        "accession_numbers": accessions,
        "publication_time_known": True,
        "availability_date_kind": "sec_filing_date_plus_one_calendar_day",
        "future_data_guard": "available_date <= selection_date",
        "point_in_time_scope": HISTORY_SCOPE,
        "historical_backtest_allowed": True,
        "exact_index_event_timing": False,
        "weight_kind": "QQQ_percent_of_net_assets_at_report_date",
        "completeness": "all_discovered_nport_requests_and_ticker_mappings_succeeded",
        "source_confidence": "official_sec_filings",
        "crosswalk_version_id": crosswalk_manifest.get("version_id"),
        "crosswalk_content_sha256": crosswalk_manifest.get("content_sha256"),
        "override_mapping_id": override_meta.get("mapping_id"),
        "override_content_sha256": override_meta.get("content_sha256"),
    }
    if not archive.exists():
        atomic_write_text(archive, csv_text)
        write_dataset_manifest(
            archive,
            dataset_type="ndx_constituent_proxy_snapshot",
            dataset_key=f"qqq_nport:{content_hash[:16]}",
            source="sec_edgar_qqq_nport_p",
            source_locator=SEC_SUBMISSIONS_URL,
            fetched_at=fetched_at,
            row_count=len(normalized),
            data_start=available_dates[0],
            data_end=available_dates[-1],
            extra={**common_extra, "immutable_snapshot": True},
        )
    path = _history_path(cfg)
    atomic_write_text(path, csv_text)
    return write_dataset_manifest(
        path,
        dataset_type="ndx_point_in_time_constituents",
        dataset_key="qqq_nport_public_filings",
        source="sec_edgar_qqq_nport_p",
        source_locator=SEC_SUBMISSIONS_URL,
        fetched_at=fetched_at,
        row_count=len(normalized),
        data_start=available_dates[0],
        data_end=available_dates[-1],
        extra={**common_extra, "immutable_snapshot": False, "archive_path": archive.as_posix()},
    )


def _strict_manifest(path: Path) -> dict:
    target = manifest_path(path)
    if not path.exists() or not target.exists():
        raise NdxHistoryError(f"NDX point-in-time cache or manifest missing: {path}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxHistoryError(f"invalid NDX history manifest: {target}") from exc
    if payload.get("content_sha256") != file_sha256(path):
        raise NdxHistoryError("NDX history content hash does not match manifest")
    if (
        payload.get("dataset_type") != "ndx_point_in_time_constituents"
        or payload.get("dataset_key") != "qqq_nport_public_filings"
    ):
        raise NdxHistoryError("NDX history manifest identity mismatch")
    if payload.get("historical_backtest_allowed") is not True:
        raise NdxHistoryError("NDX history manifest is not approved for point-in-time backtest")
    if payload.get("point_in_time_scope") != HISTORY_SCOPE:
        raise NdxHistoryError("NDX history availability guard missing")
    return payload


def _read_history_cache(cfg) -> tuple[pd.DataFrame, NdxHistoryMeta]:
    path = _history_path(cfg)
    manifest = _strict_manifest(path)
    frame = _normalize_history(pd.read_csv(path, keep_default_na=False))
    if len(frame) != int(manifest.get("row_count") or -1):
        raise NdxHistoryError("NDX history row count does not match manifest")
    report_count = frame["report_date"].nunique()
    if report_count != int(manifest.get("report_count") or -1):
        raise NdxHistoryError("NDX history report count does not match manifest")
    return frame, NdxHistoryMeta(
        source="ndx_history_cache",
        rows=len(frame),
        report_count=report_count,
        cached=True,
        manifest=manifest,
    )


def _nport_filings(submissions: dict, *, start_report_date: str) -> list[dict]:
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    required = ["form", "reportDate", "filingDate", "accessionNumber", "primaryDocument"]
    if not all(isinstance(recent.get(key), list) for key in required):
        raise NdxHistoryError("SEC submissions response is missing recent filing arrays")
    length = len(recent["form"])
    if any(len(recent[key]) != length for key in required):
        raise NdxHistoryError("SEC submissions filing arrays have inconsistent lengths")
    rows = []
    for i, form in enumerate(recent["form"]):
        report_date = str(recent["reportDate"][i] or "")
        if form != "NPORT-P" or report_date < start_report_date:
            continue
        accession = str(recent["accessionNumber"][i])
        accession_compact = accession.replace("-", "")
        primary_name = Path(str(recent["primaryDocument"][i])).name or "primary_doc.xml"
        source_locator = f"{SEC_ARCHIVES_BASE}/{accession_compact}/{primary_name}"
        rows.append({
            "report_date": report_date,
            "filed_date": str(recent["filingDate"][i]),
            "accession_number": accession,
            "source_locator": source_locator,
        })
    rows.sort(key=lambda item: item["report_date"])
    if not rows:
        raise NdxHistoryError("no QQQ NPORT-P filings discovered")
    periods = [pd.Period(item["report_date"], freq="Q") for item in rows]
    if len(set(periods)) != len(periods):
        raise NdxHistoryError("duplicate QQQ NPORT-P report quarter discovered")
    expected = list(pd.period_range(periods[0], periods[-1], freq="Q"))
    if periods != expected:
        missing = [str(period) for period in expected if period not in set(periods)]
        raise NdxHistoryError(f"QQQ NPORT-P quarterly sequence is incomplete: {missing}")
    return rows


def refresh_ndx_point_in_time_history(
    cfg,
    *,
    start_report_date: str = "2019-09-30",
    sec_user_agent: str | None = None,
) -> tuple[pd.DataFrame, NdxHistoryMeta]:
    import requests

    agent = _sec_user_agent(sec_user_agent)
    headers = _sec_headers(agent)
    fetched_at = utc_now_iso()
    try:
        with proxy_env(_proxy_cfg(cfg)):
            session = requests.Session()
            session.headers.update(headers)
            submissions_response = session.get(SEC_SUBMISSIONS_URL, timeout=30)
            submissions_response.raise_for_status()
            submissions = submissions_response.json()
            if str(submissions.get("cik") or "").zfill(10) != QQQ_CIK:
                raise NdxHistoryError("SEC submissions CIK mismatch")
            filings = _nport_filings(submissions, start_report_date=start_report_date)
            frames = []
            for filing in filings:
                response = session.get(filing["source_locator"], timeout=30)
                response.raise_for_status()
                frames.append(parse_nport_equities(response.content, **filing))
                time.sleep(0.12)
            ticker_response = session.get(SEC_COMPANY_TICKERS_URL, timeout=30)
            ticker_response.raise_for_status()
            ticker_payload = ticker_response.json()

        overrides, override_meta = _load_overrides()
        combined = pd.concat(frames, ignore_index=True)
        mapped = resolve_nport_tickers(
            combined,
            company_ticker_payload=ticker_payload,
            overrides=overrides,
        )
        crosswalk_manifest = _write_company_tickers_cache(
            cfg, ticker_response.content, fetched_at
        )
        manifest = _write_history_cache(
            cfg,
            mapped,
            fetched_at=fetched_at,
            crosswalk_manifest=crosswalk_manifest,
            override_meta=override_meta,
        )
        return mapped, NdxHistoryMeta(
            source="sec_edgar_qqq_nport_p",
            rows=len(mapped),
            report_count=mapped["report_date"].nunique(),
            cached=False,
            manifest=manifest,
        )
    except Exception as exc:
        try:
            frame, meta = _read_history_cache(cfg)
        except Exception as cache_exc:
            raise NdxHistoryError(
                "NDX history refresh failed and no complete cache is available; "
                f"refresh={exc!r}; cache={cache_exc!r}"
            ) from cache_exc
        meta.stale = True
        meta.source = "ndx_history_cache_stale"
        meta.errors = {"refresh": str(exc)}
        return frame, meta


def get_ndx_point_in_time_history(
    cfg,
    *,
    refresh: bool = False,
    start_report_date: str = "2019-09-30",
    sec_user_agent: str | None = None,
) -> tuple[pd.DataFrame, NdxHistoryMeta]:
    if refresh:
        return refresh_ndx_point_in_time_history(
            cfg,
            start_report_date=start_report_date,
            sec_user_agent=sec_user_agent,
        )
    return _read_history_cache(cfg)


def constituents_asof(
    history: pd.DataFrame,
    selection_date: str | pd.Timestamp,
) -> tuple[pd.DataFrame, dict]:
    frame = _normalize_history(history)
    cutoff = pd.Timestamp(selection_date).normalize()
    available = frame[pd.to_datetime(frame["available_date"]) <= cutoff]
    if available.empty:
        raise NdxHistoryError(
            f"no public NDX constituent proxy available by {cutoff.strftime('%Y-%m-%d')}"
        )
    selected_available = str(available["available_date"].max())
    snapshot = available[available["available_date"] == selected_available].copy()
    if snapshot["report_date"].nunique() != 1 or snapshot["accession_number"].nunique() != 1:
        raise NdxHistoryError("selected availability date is not a single filing snapshot")
    report_date = str(snapshot["report_date"].iloc[0])
    if pd.Timestamp(selected_available) > cutoff:
        raise NdxHistoryError("future constituent filing selected")
    evidence = {
        "selection_date": cutoff.strftime("%Y-%m-%d"),
        "report_date": report_date,
        "filed_date": str(snapshot["filed_date"].iloc[0]),
        "available_date": selected_available,
        "accession_number": str(snapshot["accession_number"].iloc[0]),
        "security_count": len(snapshot),
        "weight_sum": float(snapshot["weight"].sum()),
        "future_data_guard_passed": True,
        "lag_calendar_days": int((cutoff - pd.Timestamp(report_date)).days),
    }
    return snapshot.reset_index(drop=True), evidence


def history_coverage_report(history: pd.DataFrame) -> dict:
    frame = _normalize_history(history)
    reports = []
    for report_date, group in frame.groupby("report_date", sort=True):
        reports.append({
            "report_date": report_date,
            "filed_date": str(group["filed_date"].iloc[0]),
            "available_date": str(group["available_date"].iloc[0]),
            "security_count": len(group),
            "weight_sum": float(group["weight"].sum()),
            "override_count": int((group["mapping_method"] == "explicit_cusip_override").sum()),
        })
    union = sorted(frame["ticker"].unique())
    return {
        "report_count": len(reports),
        "first_report_date": reports[0]["report_date"],
        "last_report_date": reports[-1]["report_date"],
        "first_available_date": reports[0]["available_date"],
        "last_available_date": reports[-1]["available_date"],
        "union_ticker_count": len(union),
        "union_tickers": union,
        "reports": reports,
    }
