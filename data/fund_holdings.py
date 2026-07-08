"""Fund disclosed holdings access for research benchmarks.

This module fetches public F10 holdings for funds such as 012922.  It is a
research data source only: holdings are never read by live execution.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from core.helpers import atomic_write_text, proxy_env

log = logging.getLogger("us_ratchet")


class FundHoldingError(Exception):
    pass


US_EASTMONEY_MARKETS = {"105", "106", "107"}


@dataclass
class FundHoldingMeta:
    code: str
    source: str
    rows: int
    report_date: str | None = None
    fund_name: str = ""
    cached: bool = False
    errors: dict = field(default_factory=dict)


def _cache_path(code: str, cfg, report_date: str | None = None) -> Path:
    suffix = f"_{report_date}" if report_date else "_latest"
    return Path(cfg.cache_dir) / "fund_holdings" / f"{code}{suffix}.csv"


def _history_cache_path(code: str, cfg) -> Path:
    return Path(cfg.cache_dir) / "fund_holdings" / f"{code}_history.csv"


def _to_float(raw) -> float | None:
    txt = str(raw or "").strip().replace(",", "").replace("%", "")
    if not txt or txt in {"--", "---"}:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _clean_cell(raw: str) -> str:
    text = html.unescape(str(raw or ""))
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<.*?>", "", text, flags=re.S)
    return re.sub(r"\s+", " ", text).strip()


def _classify(secid: str, ticker: str) -> str:
    market = str(secid or "").split(".", 1)[0]
    tk = str(ticker or "").upper().strip()
    if market in US_EASTMONEY_MARKETS and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", tk):
        return "US"
    if market in {"0", "1"} and re.fullmatch(r"\d{6}", tk):
        return "CN_A"
    if market in {"116", "128"}:
        return "HK"
    return "OTHER"


def _parse_report_header(text: str) -> tuple[str | None, str]:
    report_date = None
    m = re.search(r"<font[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</font>", text)
    if m:
        report_date = m.group(1)
    fund_name = ""
    m = re.search(r"<h4[^>]*>.*?<a[^>]*title='([^']+)'", text, flags=re.S)
    if m:
        fund_name = html.unescape(m.group(1)).strip()
    return report_date, fund_name


def _report_blocks(text: str) -> list[str]:
    parts = re.split(r"(?=<div\s+class=['\"]boxitem\b)", str(text or ""), flags=re.I)
    blocks = [p for p in parts if "<table" in p and "<tr" in p]
    return blocks or [str(text or "")]


def _parse_holding_block(text: str, code: str) -> tuple[list[dict], str | None, str]:
    report_date, fund_name = _parse_report_header(text)
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", text, flags=re.S):
        cells_raw = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(cells_raw) < 7:
            continue
        cells = [_clean_cell(c) for c in cells_raw]
        if not cells[0].isdigit():
            continue
        href = re.search(r"unify/r/([^'\" >]+)", cells_raw[1])
        secid = html.unescape(href.group(1)).strip() if href else ""
        ticker = cells[1].upper().strip()
        pct_i = 6 if len(cells_raw) >= 9 else 4
        shares_i = pct_i + 1
        value_i = pct_i + 2
        pct = _to_float(cells[pct_i])
        rows.append({
            "rank": int(cells[0]),
            "secid": secid,
            "ticker": ticker,
            "name": cells[2],
            "asset_class": _classify(secid, ticker),
            "nav_weight": (pct / 100.0) if pct is not None else None,
            "shares_10k": _to_float(cells[shares_i]) if len(cells) > shares_i else None,
            "market_value_cny_10k": _to_float(cells[value_i]) if len(cells) > value_i else None,
            "report_date": report_date,
            "fund_code": code,
            "fund_name": fund_name,
        })
    return rows, report_date, fund_name


def _parse_holdings(text: str, code: str) -> tuple[pd.DataFrame, FundHoldingMeta]:
    rows = []
    report_dates = []
    fund_name = ""
    for block in _report_blocks(text):
        block_rows, report_date, block_name = _parse_holding_block(block, code)
        if block_rows:
            rows.extend(block_rows)
            if report_date:
                report_dates.append(report_date)
            if block_name and not fund_name:
                fund_name = block_name
    if not rows:
        raise FundHoldingError(f"{code}: 未解析到基金持仓")
    df = pd.DataFrame(rows)
    if "report_date" in df:
        df = df.sort_values(["report_date", "rank"], ascending=[False, True])
    else:
        df = df.sort_values("rank")
    latest_report = max(report_dates) if report_dates else None
    return df, FundHoldingMeta(
        code=code,
        source="eastmoney_fund_holdings",
        rows=len(df),
        report_date=latest_report,
        fund_name=fund_name,
        cached=False,
    )


def _write_cache(code: str, df: pd.DataFrame, cfg, report_date: str | None = None,
                 *, update_latest: bool = False) -> None:
    atomic_write_text(_cache_path(code, cfg, report_date), df.to_csv(index=False))
    if update_latest:
        atomic_write_text(_cache_path(code, cfg, None), df.to_csv(index=False))


def _write_history_cache(code: str, df: pd.DataFrame, cfg) -> None:
    atomic_write_text(_history_cache_path(code, cfg), df.to_csv(index=False))


def _read_cache(code: str, cfg, report_date: str | None = None) -> tuple[pd.DataFrame, FundHoldingMeta]:
    path = _cache_path(code, cfg, report_date)
    if not path.exists():
        raise FundHoldingError(f"基金持仓缓存不存在: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise FundHoldingError(f"基金持仓缓存为空: {path}")
    rd = str(df.get("report_date", pd.Series([report_date])).iloc[0] or "")
    name = str(df.get("fund_name", pd.Series([""])).iloc[0] or "")
    return df, FundHoldingMeta(
        code=code,
        source="fund_holdings_cache",
        rows=len(df),
        report_date=rd or None,
        fund_name=name,
        cached=True,
    )


def _read_history_cache(code: str, cfg) -> tuple[pd.DataFrame, FundHoldingMeta]:
    path = _history_cache_path(code, cfg)
    if not path.exists():
        raise FundHoldingError(f"基金历史持仓缓存不存在: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise FundHoldingError(f"基金历史持仓缓存为空: {path}")
    latest = str(df["report_date"].dropna().max()) if "report_date" in df else None
    name = ""
    if "fund_name" in df and not df["fund_name"].dropna().empty:
        name = str(df["fund_name"].dropna().iloc[0] or "")
    return df, FundHoldingMeta(
        code=code,
        source="fund_holdings_history_cache",
        rows=len(df),
        report_date=latest,
        fund_name=name,
        cached=True,
    )


def _fetch_eastmoney_holdings(code: str, cfg, *, top_line: int = 100,
                              report_date: str | None = None) -> tuple[pd.DataFrame, FundHoldingMeta]:
    import requests

    params = {
        "type": "jjcc",
        "code": code,
        "topline": int(top_line),
        "year": "",
        "month": "",
        "rt": "0.1",
    }
    headers = {
        "Referer": f"https://fundf10.eastmoney.com/ccmx_{code}.html",
        "User-Agent": "Mozilla/5.0",
    }
    with proxy_env(cfg.data.proxy):
        resp = requests.get(
            "https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
            params=params,
            headers=headers,
            timeout=20,
        )
    if resp.status_code != 200:
        raise FundHoldingError(f"{code}: 东方财富持仓接口 HTTP {resp.status_code}")
    df, meta = _parse_holdings(resp.text, code)
    if report_date and str(meta.report_date) != str(report_date):
        raise FundHoldingError(f"{code}: 返回报告期 {meta.report_date}，不是请求的 {report_date}")
    _write_cache(code, df, cfg, meta.report_date, update_latest=True)
    log.info("%s holdings ← eastmoney | %s | %d rows", code, meta.report_date, meta.rows)
    return df, meta


def _fetch_eastmoney_holdings_year(code: str, cfg, year: int, *,
                                   top_line: int = 100) -> tuple[pd.DataFrame, FundHoldingMeta]:
    import requests

    params = {
        "type": "jjcc",
        "code": code,
        "topline": int(top_line),
        "year": str(int(year)),
        "month": "",
        "rt": "0.1",
    }
    headers = {
        "Referer": f"https://fundf10.eastmoney.com/ccmx_{code}.html",
        "User-Agent": "Mozilla/5.0",
    }
    with proxy_env(cfg.data.proxy):
        resp = requests.get(
            "https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
            params=params,
            headers=headers,
            timeout=20,
        )
    if resp.status_code != 200:
        raise FundHoldingError(f"{code}: 东方财富持仓接口 HTTP {resp.status_code} year={year}")
    df, meta = _parse_holdings(resp.text, code)
    meta.source = f"eastmoney_fund_holdings_year_{int(year)}"
    for rd, g in df.groupby("report_date", dropna=True):
        _write_cache(code, g.sort_values("rank"), cfg, str(rd), update_latest=False)
    return df, meta


def get_fund_holdings(code: str, cfg, *, report_date: str | None = None,
                      local_only: bool = False,
                      top_line: int = 100) -> tuple[pd.DataFrame, FundHoldingMeta]:
    code = str(code or "").strip()
    if not (len(code) == 6 and code.isdigit()):
        raise FundHoldingError(f"基金代码必须是 6 位数字: {code!r}")
    cache_error = None
    try:
        return _read_cache(code, cfg, report_date)
    except Exception as e:
        cache_error = e
        if local_only:
            raise
    try:
        if report_date:
            year = int(str(report_date)[:4])
            df, meta = _fetch_eastmoney_holdings_year(code, cfg, year, top_line=top_line)
            picked = df[df["report_date"].astype(str) == str(report_date)].copy()
            if picked.empty:
                raise FundHoldingError(f"{code}: {report_date} 未在 {year} 年持仓页中找到")
            picked = picked.sort_values("rank")
            _write_cache(code, picked, cfg, str(report_date), update_latest=False)
            meta.rows = len(picked)
            meta.report_date = str(report_date)
            return picked, meta
        return _fetch_eastmoney_holdings(code, cfg, top_line=top_line, report_date=report_date)
    except Exception as e:
        try:
            df, meta = _read_cache(code, cfg, report_date)
            meta.source = "fund_holdings_cache_stale"
            meta.errors = {"fetch": repr(e)}
            return df, meta
        except Exception:
            raise FundHoldingError(
                f"{code}: 基金持仓取数失败；cache={cache_error!r}; fetch={e!r}"
            ) from e


def get_fund_holding_history(code: str, cfg, *, start_year: int | None = None,
                             end_year: int | None = None,
                             local_only: bool = False,
                             top_line: int = 100) -> tuple[pd.DataFrame, FundHoldingMeta]:
    """Return all fetched quarterly disclosed holdings for a fund."""
    code = str(code or "").strip()
    if not (len(code) == 6 and code.isdigit()):
        raise FundHoldingError(f"基金代码必须是 6 位数字: {code!r}")
    if local_only:
        return _read_history_cache(code, cfg)

    today = date.today()
    end_year = int(today.year if end_year is None else end_year)
    if start_year is None:
        start_raw = getattr(cfg.data, "start_date", None)
        start_year = int(pd.Timestamp(start_raw).year) if start_raw else end_year - 8
    start_year = max(1990, int(start_year))
    end_year = max(start_year, int(end_year))

    frames = []
    errors = {}
    for year in range(start_year, end_year + 1):
        try:
            df, _ = _fetch_eastmoney_holdings_year(code, cfg, year, top_line=top_line)
        except Exception as e:
            errors[str(year)] = repr(e)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        try:
            df, meta = _read_history_cache(code, cfg)
            meta.source = "fund_holdings_history_cache_stale"
            meta.errors = errors
            return df, meta
        except Exception as cache_error:
            raise FundHoldingError(
                f"{code}: 历史持仓取数失败; cache={cache_error!r}; fetch_errors={errors!r}"
            ) from cache_error

    hist = pd.concat(frames, ignore_index=True)
    hist = hist.drop_duplicates(subset=["report_date", "rank", "ticker", "secid"], keep="last")
    hist = hist.sort_values(["report_date", "rank"], ascending=[False, True]).reset_index(drop=True)
    _write_history_cache(code, hist, cfg)
    latest = str(hist["report_date"].dropna().max()) if "report_date" in hist else None
    name = ""
    if "fund_name" in hist and not hist["fund_name"].dropna().empty:
        name = str(hist["fund_name"].dropna().iloc[0] or "")
    return hist, FundHoldingMeta(
        code=code,
        source="eastmoney_fund_holdings_history",
        rows=len(hist),
        report_date=latest,
        fund_name=name,
        cached=False,
        errors=errors,
    )
