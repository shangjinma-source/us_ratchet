"""Fund NAV data access for external benchmarks.

The strategy itself trades US equities, but target benchmarking can require a
mutual-fund NAV series such as 012922.  This module keeps that data in the
research/backtest data layer and never feeds it into live execution signals.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from core.helpers import atomic_write_text, proxy_env

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
    df = pd.read_csv(path)
    if df.empty:
        raise FundDataError(f"基金缓存为空: {path}")
    df = _normalize(df.to_dict(orient="records"), code, cfg)
    return df, FundMeta(
        code=code, source="fund_cache", rows=len(df),
        start=df.index[0].strftime("%Y-%m-%d"),
        end=df.index[-1].strftime("%Y-%m-%d"),
        cached=True,
    )


def _write_cache(code: str, df: pd.DataFrame, cfg) -> None:
    out = df.copy()
    out.index = out.index.strftime("%Y-%m-%d")
    atomic_write_text(_fund_cache_path(code, cfg), out.to_csv(index_label="Date"))


def _fetch_eastmoney_fund_nav(code: str, cfg) -> tuple[pd.DataFrame, FundMeta]:
    import requests

    base = "https://fundf10.eastmoney.com/F10DataApi.aspx"
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
            params={"type": "lsjz", "code": code, "page": 1, "per": 20},
            headers=headers,
            timeout=20,
        )
        if first.status_code != 200:
            raise FundDataError(f"{code}: 东方财富基金接口 HTTP {first.status_code}")
        text = first.text
        rows.extend(_parse_eastmoney_rows(text))
        m = re.search(r"pages:(\d+)", text)
        pages = int(m.group(1)) if m else 1
        for page in range(2, pages + 1):
            try:
                resp = session.get(
                    base,
                    params={"type": "lsjz", "code": code, "page": page, "per": 20},
                    headers=headers,
                    timeout=20,
                )
                if resp.status_code != 200:
                    errors[f"page_{page}"] = f"HTTP {resp.status_code}"
                    continue
                rows.extend(_parse_eastmoney_rows(resp.text))
            except Exception as e:
                errors[f"page_{page}"] = repr(e)

    df = _normalize(rows, code, cfg)
    meta = FundMeta(
        code=code, source="eastmoney_fund", rows=len(df),
        start=df.index[0].strftime("%Y-%m-%d"),
        end=df.index[-1].strftime("%Y-%m-%d"),
        cached=False,
        errors=errors,
    )
    _write_cache(code, df, cfg)
    log.info("%s ← eastmoney_fund | %s..%s | %d 行",
             code, meta.start, meta.end, meta.rows)
    return df, meta


def get_fund_nav(code: str, cfg, *, local_only: bool = False) -> tuple[pd.DataFrame, FundMeta]:
    code = str(code or "").strip()
    if not (len(code) == 6 and code.isdigit()):
        raise FundDataError(f"基金代码必须是 6 位数字: {code!r}")
    cache_error = None
    try:
        return _read_cache(code, cfg)
    except Exception as e:
        cache_error = e
        if local_only:
            raise
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
