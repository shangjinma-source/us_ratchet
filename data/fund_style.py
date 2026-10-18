"""Versioned public style data for fund attribution research.

The datasets in this module come from Eastmoney's fund archive pages/APIs and
remain isolated from live execution.  Network refreshes are fail-closed: a
partial response never replaces an existing complete cache.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from core.helpers import atomic_write_text, proxy_env
from data.versioning import (
    ensure_dataset_manifest,
    utc_now_iso,
    write_dataset_manifest,
)


class FundStyleDataError(Exception):
    pass


STYLE_API_BASE = "https://api.fund.eastmoney.com"
INDUSTRY_URL = f"{STYLE_API_BASE}/f10/HYPZ/"
TURNOVER_URL = f"{STYLE_API_BASE}/f10/JJHSL/"
ASSET_URL_TEMPLATE = "https://fundf10.eastmoney.com/zcpz_{code}.html"


@dataclass
class FundStyleMeta:
    code: str
    dataset: str
    source: str
    rows: int
    cached: bool = False
    errors: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _cache_path(code: str, cfg, dataset: str) -> Path:
    return Path(cfg.cache_dir) / "fund_style" / f"{code}_{dataset}.csv"


def _source_locator(dataset: str, code: str) -> str:
    if dataset == "industry":
        return INDUSTRY_URL
    if dataset == "asset_allocation":
        return ASSET_URL_TEMPLATE.format(code=code)
    if dataset == "turnover":
        return TURNOVER_URL
    raise ValueError(f"unknown fund style dataset: {dataset}")


def _dataset_type(dataset: str) -> str:
    return f"fund_style_{dataset}"


def _normalize_dataset(dataset: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "report_date" not in out:
        raise FundStyleDataError(f"{dataset}: missing report_date")
    out["report_date"] = pd.to_datetime(out["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["report_date"])

    if dataset == "industry":
        columns = ["report_date", "sector_code", "sector", "nav_weight", "market_value_cny"]
        key = ["report_date", "sector_code"]
        numeric = ["nav_weight", "market_value_cny"]
    elif dataset == "asset_allocation":
        columns = [
            "report_date", "stock_weight", "bond_weight", "cash_weight",
            "depositary_receipt_weight", "net_assets_cny_100m",
        ]
        key = ["report_date"]
        numeric = columns[1:]
    elif dataset == "turnover":
        columns = ["report_date", "stock_turnover"]
        key = ["report_date"]
        numeric = ["stock_turnover"]
    else:
        raise ValueError(f"unknown fund style dataset: {dataset}")

    missing = [column for column in columns if column not in out]
    if missing:
        raise FundStyleDataError(f"{dataset}: missing columns {missing}")
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out[columns].drop_duplicates(key, keep="last")
    out = out.sort_values(key, ascending=[False] + [True] * (len(key) - 1)).reset_index(drop=True)
    if out.empty:
        raise FundStyleDataError(f"{dataset}: normalized dataset is empty")
    return out


def _manifest_extra(df: pd.DataFrame, code: str, extra: dict | None = None) -> dict:
    report_dates = sorted(df["report_date"].dropna().astype(str).unique().tolist())
    payload = {
        "fund_code": code,
        "report_dates": report_dates,
        "report_count": len(report_dates),
        "publication_time_known": False,
        "source_confidence": "runtime_http_response",
    }
    payload.update(extra or {})
    return payload


def _write_cache(code: str, cfg, dataset: str, df: pd.DataFrame, *,
                 source: str, fetched_at: str, extra: dict | None = None) -> tuple[pd.DataFrame, dict]:
    normalized = _normalize_dataset(dataset, df)
    path = _cache_path(code, cfg, dataset)
    atomic_write_text(path, normalized.to_csv(index=False))
    report_dates = sorted(normalized["report_date"].unique().tolist())
    manifest = write_dataset_manifest(
        path,
        dataset_type=_dataset_type(dataset),
        dataset_key=code,
        source=source,
        source_locator=_source_locator(dataset, code),
        fetched_at=fetched_at,
        row_count=len(normalized),
        data_start=report_dates[0],
        data_end=report_dates[-1],
        extra=_manifest_extra(normalized, code, extra),
    )
    return normalized, manifest


def _read_cache(code: str, cfg, dataset: str) -> tuple[pd.DataFrame, FundStyleMeta]:
    path = _cache_path(code, cfg, dataset)
    if not path.exists():
        raise FundStyleDataError(f"fund style cache missing: {path}")
    raw = pd.read_csv(path)
    normalized = _normalize_dataset(dataset, raw)
    report_dates = sorted(normalized["report_date"].unique().tolist())
    manifest = ensure_dataset_manifest(
        path,
        dataset_type=_dataset_type(dataset),
        dataset_key=code,
        row_count=len(normalized),
        data_start=report_dates[0],
        data_end=report_dates[-1],
        legacy_source=f"legacy_{_dataset_type(dataset)}_cache",
        extra=_manifest_extra(normalized, code),
    )
    return normalized, FundStyleMeta(
        code=code,
        dataset=dataset,
        source=f"{dataset}_cache",
        rows=len(normalized),
        cached=True,
        manifest=manifest,
    )


def _validate_code(code: str) -> str:
    value = str(code or "").strip()
    if not (len(value) == 6 and value.isdigit()):
        raise FundStyleDataError(f"fund code must be 6 digits: {code!r}")
    return value


def _fetch_industry(code: str, cfg, start_year: int, end_year: int) -> tuple[pd.DataFrame, FundStyleMeta]:
    import requests

    rows = []
    confirmed_empty_years = []
    headers = {
        "Referer": f"https://fundf10.eastmoney.com/hytz_{code}.html",
        "User-Agent": "Mozilla/5.0",
    }
    with proxy_env(cfg.data.proxy):
        for year in range(int(start_year), int(end_year) + 1):
            resp = requests.get(
                INDUSTRY_URL,
                params={"fundCode": code, "year": year},
                headers=headers,
                timeout=20,
            )
            if resp.status_code != 200:
                raise FundStyleDataError(f"industry HTTP {resp.status_code} year={year}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise FundStyleDataError(f"industry invalid JSON year={year}") from exc
            if int(payload.get("ErrCode") or 0) != 0:
                raise FundStyleDataError(f"industry source error year={year}: {payload.get('ErrMsg')}")
            data = payload.get("Data") or {}
            if str(data.get("FundCode") or "") != code:
                raise FundStyleDataError(f"industry fund mismatch year={year}")
            if int(data.get("Curyear") or 0) != int(year):
                raise FundStyleDataError(
                    f"industry year mismatch requested={year} returned={data.get('Curyear')}"
                )
            available_years = {int(value) for value in (data.get("ListYears") or [])}
            quarters = data.get("QuarterInfos") or []
            if year not in available_years:
                if quarters:
                    raise FundStyleDataError(f"industry unavailable year returned rows: {year}")
                confirmed_empty_years.append(year)
                continue
            if not quarters:
                raise FundStyleDataError(f"industry listed year has no quarters: {year}")
            for quarter in quarters:
                report_date = str(quarter.get("JZRQ") or "")[:10]
                if not report_date or pd.Timestamp(report_date).year != year:
                    raise FundStyleDataError(f"industry invalid report date year={year}: {report_date!r}")
                sectors = quarter.get("HYPZInfo") or []
                if not sectors:
                    raise FundStyleDataError(f"industry empty report: {report_date}")
                for item in sectors:
                    rows.append({
                        "report_date": report_date,
                        "sector_code": str(item.get("HYDM") or ""),
                        "sector": str(item.get("HYMC") or "").strip(),
                        "nav_weight": float(item.get("ZJZBL") or 0.0) / 100.0,
                        "market_value_cny": float(item.get("SZ") or 0.0),
                    })

    fetched_at = utc_now_iso()
    frame = _normalize_dataset("industry", pd.DataFrame(rows))
    for report_date, group in frame.groupby("report_date"):
        total = float(group["nav_weight"].sum())
        if total <= 0 or total > 1.5 or (group["nav_weight"] < 0).any():
            raise FundStyleDataError(f"industry invalid weights {report_date}: {total}")
    frame, manifest = _write_cache(
        code,
        cfg,
        "industry",
        frame,
        source="eastmoney_fund_industry_allocation",
        fetched_at=fetched_at,
        extra={
            "completeness": "all_requested_year_requests_succeeded",
            "requested_years": list(range(int(start_year), int(end_year) + 1)),
            "confirmed_empty_years": confirmed_empty_years,
            "industry_standard": "GICS",
        },
    )
    return frame, FundStyleMeta(
        code=code,
        dataset="industry",
        source="eastmoney_fund_industry_allocation",
        rows=len(frame),
        cached=False,
        manifest=manifest,
    )


def _parse_percent(value: str) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"--", "---"}:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text) / 100.0
    except ValueError:
        return None


def _parse_asset_table(html_text: str) -> pd.DataFrame:
    parser = _TableParser()
    parser.feed(html_text)
    target = None
    for table in parser.tables:
        if not table:
            continue
        header = table[0]
        if "报告期" in header and "股票占净比" in header and "现金占净比" in header:
            target = table
            break
    if target is None:
        raise FundStyleDataError("asset allocation table not found")

    rows = []
    for cells in target[1:]:
        if len(cells) < 6 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
            continue
        try:
            net_assets = float(cells[5].replace(",", ""))
        except ValueError:
            net_assets = math.nan
        rows.append({
            "report_date": cells[0],
            "stock_weight": _parse_percent(cells[1]),
            "bond_weight": _parse_percent(cells[2]),
            "cash_weight": _parse_percent(cells[3]),
            "depositary_receipt_weight": _parse_percent(cells[4]),
            "net_assets_cny_100m": net_assets,
        })
    return _normalize_dataset("asset_allocation", pd.DataFrame(rows))


def _fetch_asset_allocation(code: str, cfg) -> tuple[pd.DataFrame, FundStyleMeta]:
    import requests

    url = ASSET_URL_TEMPLATE.format(code=code)
    headers = {"Referer": url, "User-Agent": "Mozilla/5.0"}
    with proxy_env(cfg.data.proxy):
        resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise FundStyleDataError(f"asset allocation HTTP {resp.status_code}")
    frame = _parse_asset_table(resp.content.decode("utf-8", errors="replace"))
    if (frame["stock_weight"].fillna(0) < 0).any() or (frame["cash_weight"].fillna(0) < 0).any():
        raise FundStyleDataError("asset allocation contains negative weights")
    fetched_at = utc_now_iso()
    frame, manifest = _write_cache(
        code,
        cfg,
        "asset_allocation",
        frame,
        source="eastmoney_fund_periodic_report_asset_allocation",
        fetched_at=fetched_at,
        extra={"completeness": "periodic_report_table_parsed"},
    )
    return frame, FundStyleMeta(
        code=code,
        dataset="asset_allocation",
        source="eastmoney_fund_periodic_report_asset_allocation",
        rows=len(frame),
        cached=False,
        manifest=manifest,
    )


def _fetch_turnover(code: str, cfg) -> tuple[pd.DataFrame, FundStyleMeta]:
    import requests

    headers = {
        "Referer": f"https://fundf10.eastmoney.com/ccbdzs_{code}.html",
        "User-Agent": "Mozilla/5.0",
    }
    page_size = 100
    params = {"fundcode": code, "pageindex": 1, "pagesize": page_size}
    with proxy_env(cfg.data.proxy):
        resp = requests.get(TURNOVER_URL, params=params, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise FundStyleDataError(f"turnover HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise FundStyleDataError("turnover invalid JSON") from exc
    if int(payload.get("ErrCode") or 0) != 0:
        raise FundStyleDataError(f"turnover source error: {payload.get('ErrMsg')}")
    total_count = int(payload.get("TotalCount") or 0)
    data = payload.get("Data") or []
    if total_count <= 0 or len(data) != total_count:
        raise FundStyleDataError(
            f"turnover incomplete response expected={total_count} rows={len(data)}"
        )
    rows = [{
        "report_date": str(item.get("REPORTDATE") or "")[:10],
        "stock_turnover": float(item.get("STOCKTURNOVER")) / 100.0,
    } for item in data]
    frame = _normalize_dataset("turnover", pd.DataFrame(rows))
    if (frame["stock_turnover"] < 0).any():
        raise FundStyleDataError("turnover contains negative values")
    fetched_at = utc_now_iso()
    frame, manifest = _write_cache(
        code,
        cfg,
        "turnover",
        frame,
        source="eastmoney_fund_reported_stock_turnover",
        fetched_at=fetched_at,
        extra={
            "completeness": "verified_against_source_total_count",
            "source_record_count": total_count,
            "observation_frequency": "semiannual_and_annual_report_dates",
        },
    )
    return frame, FundStyleMeta(
        code=code,
        dataset="turnover",
        source="eastmoney_fund_reported_stock_turnover",
        rows=len(frame),
        cached=False,
        manifest=manifest,
    )


def _get_dataset(code: str, cfg, dataset: str, *, local_only: bool,
                 refresh: bool, start_year: int, end_year: int) -> tuple[pd.DataFrame, FundStyleMeta]:
    if local_only:
        return _read_cache(code, cfg, dataset)
    if not refresh:
        try:
            return _read_cache(code, cfg, dataset)
        except Exception:
            pass
    try:
        if dataset == "industry":
            return _fetch_industry(code, cfg, start_year, end_year)
        if dataset == "asset_allocation":
            return _fetch_asset_allocation(code, cfg)
        if dataset == "turnover":
            return _fetch_turnover(code, cfg)
        raise ValueError(dataset)
    except Exception as exc:
        try:
            frame, meta = _read_cache(code, cfg, dataset)
            meta.source = f"{dataset}_cache_stale"
            meta.errors = {"fetch": repr(exc)}
            return frame, meta
        except Exception as cache_exc:
            raise FundStyleDataError(
                f"{code} {dataset} fetch failed; cache={cache_exc!r}; fetch={exc!r}"
            ) from exc


def get_fund_style_datasets(code: str, cfg, *, start_year: int = 2022,
                            end_year: int | None = None, local_only: bool = False,
                            refresh: bool = False) -> tuple[dict[str, pd.DataFrame], dict[str, FundStyleMeta]]:
    code = _validate_code(code)
    final_year = int(date.today().year if end_year is None else end_year)
    first_year = max(1990, int(start_year))
    final_year = max(first_year, final_year)
    datasets = {}
    metas = {}
    for dataset in ("industry", "asset_allocation", "turnover"):
        frame, meta = _get_dataset(
            code,
            cfg,
            dataset,
            local_only=bool(local_only),
            refresh=bool(refresh),
            start_year=first_year,
            end_year=final_year,
        )
        datasets[dataset] = frame
        metas[dataset] = meta
    return datasets, metas
