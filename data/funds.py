"""Fund NAV data access for external benchmarks.

The strategy itself trades US equities, but target benchmarking can require a
mutual-fund NAV series such as 012922.  This module keeps that data in the
research/backtest data layer and never feeds it into live execution signals.
"""
from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from core.helpers import atomic_write_text, proxy_env
from data.versioning import (
    ensure_dataset_manifest,
    utc_now_iso,
    write_dataset_manifest,
)

log = logging.getLogger("us_ratchet")


class FundDataError(Exception):
    pass


@dataclass
class FundMeta:
    code: str
    source: str
    rows: int
    start: str
    end: str
    cached: bool = False
    errors: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)


def _fund_cache_path(code: str, cfg) -> Path:
    return Path(cfg.cache_dir) / "funds" / f"{code}.csv"


def _to_float(raw: str) -> float | None:
    txt = str(raw or "").strip().replace(",", "")
    if not txt or txt in {"--", "---"}:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _pct_to_float(raw: str) -> float | None:
    txt = str(raw or "").strip().replace("%", "")
    val = _to_float(txt)
    return val / 100.0 if val is not None else None


def _parse_eastmoney_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", text, flags=re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        cells = [re.sub(r"<.*?>", "", html.unescape(c)).strip() for c in cells]
        if len(cells) < 3 or not re.match(r"\d{4}-\d{2}-\d{2}$", cells[0]):
            continue
        unit_nav = _to_float(cells[1])
        accum_nav = _to_float(cells[2])
        if unit_nav is None and accum_nav is None:
            continue
        rows.append({
            "Date": cells[0],
            "UnitNav": unit_nav,
            "AccumNav": accum_nav,
            "DailyPct": _pct_to_float(cells[3]) if len(cells) > 3 else None,
        })
    return rows


def _parse_eastmoney_api_rows(payload: dict) -> list[dict]:
    data = payload.get("Data") or {}
    rows: list[dict] = []
    for item in data.get("LSJZList") or []:
        date = str(item.get("FSRQ") or "").strip()
        if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
            continue
        unit_nav = _to_float(item.get("DWJZ"))
        accum_nav = _to_float(item.get("LJJZ"))
        if unit_nav is None and accum_nav is None:
            continue
        rows.append({
            "Date": date,
            "UnitNav": unit_nav,
            "AccumNav": accum_nav,
            "DailyPct": _pct_to_float(item.get("JZZZL")),
        })
    return rows


def _normalize(rows: list[dict], code: str, cfg) -> pd.DataFrame:
    if not rows:
        raise FundDataError(f"{code}: 基金净值返回空数据")
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.drop_duplicates("Date", keep="last").sort_values("Date").set_index("Date")
    df["Close"] = df["AccumNav"].where(df["AccumNav"].notna(), df["UnitNav"])
    if cfg.data.start_date:
        df = df[df.index >= pd.to_datetime(cfg.data.start_date)]
    if cfg.data.end_date:
        df = df[df.index <= pd.to_datetime(cfg.data.end_date)]
    if df.empty:
        raise FundDataError(f"{code}: 按配置日期截断后为空")
    if df["Close"].isna().any() or (df["Close"] <= 0).any():
        raise FundDataError(f"{code}: 基金净值含空值或非正值")
    return df[["UnitNav", "AccumNav", "DailyPct", "Close"]]


def _read_cache(code: str, cfg) -> tuple[pd.DataFrame, FundMeta]:
    path = _fund_cache_path(code, cfg)
    if not path.exists():
        raise FundDataError(f"基金缓存不存在: {path}")
    raw = pd.read_csv(path)
    if raw.empty:
        raise FundDataError(f"基金缓存为空: {path}")
    raw_dates = (
        pd.to_datetime(raw["Date"], errors="coerce").dropna()
        if "Date" in raw else pd.Series(dtype="datetime64[ns]")
    )
    manifest = ensure_dataset_manifest(
        path,
        dataset_type="fund_nav",
        dataset_key=code,
        row_count=len(raw),
        data_start=raw_dates.min().strftime("%Y-%m-%d") if len(raw_dates) else None,
        data_end=raw_dates.max().strftime("%Y-%m-%d") if len(raw_dates) else None,
        legacy_source="legacy_fund_nav_cache",
        extra={"fund_code": code},
    )
    df = _normalize(raw.to_dict(orient="records"), code, cfg)
    return df, FundMeta(
        code=code, source="fund_cache", rows=len(df),
        start=df.index[0].strftime("%Y-%m-%d"),
        end=df.index[-1].strftime("%Y-%m-%d"),
        cached=True,
        manifest=manifest,
    )


def _write_cache(code: str, df: pd.DataFrame, cfg, *, source: str,
                 source_locator: str, fetched_at: str,
                 source_record_count: int, source_page_count: int) -> dict:
    path = _fund_cache_path(code, cfg)
    out = df.copy()
    out.index = out.index.strftime("%Y-%m-%d")
    atomic_write_text(path, out.to_csv(index_label="Date"))
    return write_dataset_manifest(
        path,
        dataset_type="fund_nav",
        dataset_key=code,
        source=source,
        source_locator=source_locator,
        fetched_at=fetched_at,
        row_count=len(df),
        data_start=df.index[0].strftime("%Y-%m-%d"),
        data_end=df.index[-1].strftime("%Y-%m-%d"),
        extra={
            "fund_code": code,
            "publication_time_known": False,
            "source_confidence": "runtime_http_response",
            "completeness": "verified_against_source_record_count",
            "source_record_count": int(source_record_count),
            "source_page_count": int(source_page_count),
        },
    )


def _fetch_eastmoney_fund_nav(code: str, cfg) -> tuple[pd.DataFrame, FundMeta]:
    import requests

    base = "https://api.fund.eastmoney.com/f10/lsjz"
    headers = {
        "Referer": f"https://fundf10.eastmoney.com/jjjz_{code}.html",
        "User-Agent": "Mozilla/5.0",
    }
    rows: list[dict] = []
    errors: dict = {}
    with proxy_env(cfg.data.proxy):
        session = requests.Session()
        first = session.get(
            base,
            params={"fundCode": code, "pageIndex": 1, "pageSize": 20},
            headers=headers,
            timeout=20,
        )
        if first.status_code != 200:
            raise FundDataError(f"{code}: 东方财富基金接口 HTTP {first.status_code}")
        try:
            payload = json.loads(first.text)
        except (TypeError, ValueError) as exc:
            raise FundDataError(f"{code}: 东方财富基金接口返回非 JSON 数据") from exc
        first_rows = _parse_eastmoney_api_rows(payload)
        expected_records = int(payload.get("TotalCount") or 0)
        page_size = int(payload.get("PageSize") or 0)
        if payload.get("ErrCode") != 0 or not expected_records or not page_size or not first_rows:
            raise FundDataError(f"{code}: 东方财富基金接口缺少完整性元数据或首屏净值")
        rows.extend(first_rows)
        pages = (expected_records + page_size - 1) // page_size
        for page in range(2, pages + 1):
            try:
                resp = session.get(
                    base,
                    params={"fundCode": code, "pageIndex": page, "pageSize": page_size},
                    headers=headers,
                    timeout=20,
                )
                if resp.status_code != 200:
                    errors[f"page_{page}"] = f"HTTP {resp.status_code}"
                    continue
                page_payload = json.loads(resp.text)
                page_rows = _parse_eastmoney_api_rows(page_payload)
                if not page_rows:
                    errors[f"page_{page}"] = "no parsed NAV rows"
                    continue
                rows.extend(page_rows)
            except Exception as e:
                errors[f"page_{page}"] = repr(e)

    if errors:
        raise FundDataError(f"{code}: 东方财富基金净值分页不完整: {errors!r}")
    fetched_dates = {str(row.get("Date") or "") for row in rows}
    if len(fetched_dates) != expected_records:
        raise FundDataError(
            f"{code}: 东方财富基金净值记录数不完整; "
            f"expected={expected_records}, parsed_unique={len(fetched_dates)}"
        )
    df = _normalize(rows, code, cfg)
    fetched_at = utc_now_iso()
    meta = FundMeta(
        code=code, source="eastmoney_fund_api", rows=len(df),
        start=df.index[0].strftime("%Y-%m-%d"),
        end=df.index[-1].strftime("%Y-%m-%d"),
        cached=False,
        errors=errors,
    )
    meta.manifest = _write_cache(
        code,
        df,
        cfg,
        source="eastmoney_fund_nav_api",
        source_locator=base,
        fetched_at=fetched_at,
        source_record_count=expected_records,
        source_page_count=pages,
    )
    log.info("%s ← eastmoney_fund | %s..%s | %d 行",
             code, meta.start, meta.end, meta.rows)
    return df, meta


def get_fund_nav(code: str, cfg, *, local_only: bool = False,
                 refresh: bool = False) -> tuple[pd.DataFrame, FundMeta]:
    code = str(code or "").strip()
    if not (len(code) == 6 and code.isdigit()):
        raise FundDataError(f"基金代码必须是 6 位数字: {code!r}")
    cache_error = None
    if local_only:
        return _read_cache(code, cfg)
    if not refresh:
        try:
            return _read_cache(code, cfg)
        except Exception as e:
            cache_error = e
    try:
        return _fetch_eastmoney_fund_nav(code, cfg)
    except Exception as e:
        try:
            df, meta = _read_cache(code, cfg)
            meta.source = "fund_cache_stale"
            meta.errors = {"fetch": repr(e)}
            return df, meta
        except Exception:
            raise FundDataError(
                f"{code}: 基金净值取数失败；cache={cache_error!r}; fetch={e!r}"
            ) from e
