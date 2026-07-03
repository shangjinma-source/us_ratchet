"""FastAPI 后端：单页前端 + 回测曲线 + 实盘状态/阶梯 + 加本金/建仓/回填。

运行（PyCharm 终端）:
    python -m api.server
    # 然后浏览器打开 http://127.0.0.1:8010
数据抓取与回测复用 core/backtest 逻辑；价格在内存缓存，避免每次请求都打数据源。
"""
from __future__ import annotations

import csv
import copy
import io
import logging
import re
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Body
from fastapi.responses import FileResponse, JSONResponse

from core.config import load_config, Symbol
from core.helpers import setup_logging, resolve
from core import engine as eng
from core import live
from core.persist import load_portfolio, save_portfolio, backup_state, audit_log
from core.state import CashFlow, Portfolio, SymbolState, TierFire, TacticalFill
from backtest.engine import (
    run_nav_panel,
    run_rolling_start_panel,
    run_trend_gate_ab,
    run_crash_sleeve_ab,
    run_param_scan_ab,
    run_injection_mode_ab,
    run_tactical_overlay_ab,
    _align_prices,
)
from data.fetch import get_bars
from data.quotes import fetch_sina_quotes
from datetime import date

setup_logging(logging.WARNING)
app = FastAPI(title="us_ratchet")
CFG = load_config()
STATE_PATH = "data/state.json"
WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"

_px_cache: dict = {}          # {"dates":..., "px":...}
_bt_cache: dict = {}          # {monthly: result_dict}
_roll_cache: dict = {}        # {(monthly, min_years, state_mtime): result_dict}
_trend_cache: dict = {}       # {(monthly, state_mtime): result_dict}
_crash_cache: dict = {}       # {(monthly, state_mtime): result_dict}
_param_cache: dict = {}       # {(monthly, state_mtime): result_dict}
_inject_mode_cache: dict = {} # {(monthly, state_mtime): result_dict}
_tactical_cache: dict = {}    # {(monthly, state_mtime): result_dict}
_safe_cache: dict = {}        # {"price": SGOV 最新收盘}
_bars_cache: dict = {}        # ticker -> OHLCV DataFrame
_quote_cache: dict = {}       # {key: (ts, quotes)}
QUOTE_TTL_SEC = 12


def _state_mtime_ns() -> int:
    p = resolve(STATE_PATH)
    return p.stat().st_mtime_ns if p.exists() else 0


def _reweight_symbols(symbols) -> None:
    total = sum(s.cap_total for s in symbols)
    if total <= 0:
        return
    for s in symbols:
        s.weight = s.cap_total / total
        s.core_target = s.cap_total * CFG.portfolio.core_ratio
        s.reserve_quota = s.cap_total * (1 - CFG.portfolio.core_ratio)


def _symbols_from_portfolio(pf: Portfolio) -> list[Symbol]:
    symbols = [
        Symbol(ticker=t, cap_total=float(st.cap_total))
        for t, st in sorted(pf.symbols.items())
        if float(st.cap_total) > 0
    ]
    _reweight_symbols(symbols)
    return symbols


def _cfg_for_portfolio(pf: Portfolio):
    c = copy.deepcopy(CFG)
    c.symbols = _symbols_from_portfolio(pf)
    if getattr(c, "safe_leg", None) is not None and pf.target_safe_weight > 0:
        c.safe_leg.target_weight = float(pf.target_safe_weight)
        c.safe_leg.ticker = pf.safe_ticker
    return c


def _backtest_cfg():
    """仪表板回测优先跟随当前 state 的本金配置；无 state 时回退 config.yaml。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return copy.deepcopy(CFG)
    return _cfg_for_portfolio(pf)


def _history_high_since(ticker: str, buy_date: str) -> float:
    try:
        d0 = date.fromisoformat(str(buy_date)[:10])
    except ValueError as e:
        raise ValueError("买入日期必须为 YYYY-MM-DD") from e
    if d0 > date.today():
        raise ValueError("买入日期不能晚于今天")
    df, _ = get_bars(ticker, CFG)
    idx_dates = df.index.date
    d2 = df[idx_dates >= d0]
    if d2.empty:
        raise ValueError(f"{ticker} 在 {buy_date} 之后没有可用行情")
    col = "High" if CFG.portfolio.high_basis == "high" and "High" in d2.columns else "Close"
    return float(d2[col].max())


_TRADE_LINE_RE = re.compile(
    r"(?P<date>\d{4}[-/]?\d{2}[-/]?\d{2}).*?"
    r"(?:成交|买入|BUY|Buy|buy)?\s*"
    r"(?P<ticker>[A-Za-z]{1,8})\s*"
    r"(?P<shares>\d+(?:\.\d+)?)\s*(?:股|shares?|SHARES?)?.*?"
    r"(?P<price>\d+(?:\.\d+)?)\s*(?:美元|美金|USD|usd|元)?"
)


def _normalize_trade_date(raw: str) -> str:
    s = str(raw).strip().replace("/", "-")
    if re.fullmatch(r"\d{8}", s):
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        d = date.fromisoformat(s[:10])
    except ValueError as e:
        raise ValueError(f"成交日期无效: {raw}") from e
    if d > date.today():
        raise ValueError(f"成交日期不能晚于今天: {raw}")
    return d.isoformat()


def _parse_trade_text(text: str) -> list[dict]:
    trades = []
    parts = re.split(r"[\n;；]+", str(text or ""))
    for part in parts:
        line = part.strip()
        if not line:
            continue
        if not re.search(r"\d{4}[-/]?\d{2}[-/]?\d{2}", line):
            continue
        m = _TRADE_LINE_RE.search(line)
        if not m:
            raise ValueError(f"无法解析成交记录: {line}")
        trades.append({
            "date": _normalize_trade_date(m.group("date")),
            "ticker": m.group("ticker").upper(),
            "shares": float(m.group("shares")),
            "price": float(m.group("price")),
            "raw": line,
        })
    return trades


def _norm_header(raw: str) -> str:
    return re.sub(r"[\s_\-./()（）]+", "", str(raw or "").strip().lower())


def _num(raw, default: float | None = None) -> float | None:
    if raw is None:
        return default
    s = str(raw).strip()
    if not s:
        return default
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[$,\s股美元美金]", "", s.replace("，", ""))
    try:
        val = float(s)
    except ValueError:
        return default
    return -val if neg else val


def _csv_rows(text: str) -> list[dict]:
    raw = str(text or "").strip()
    if not raw:
        return []
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0]
    if not any(sep in header for sep in [",", "\t", ";", "，"]):
        return []
    normalized_header = {_norm_header(x) for x in re.split(r"[,;\t，]", header)}
    if not normalized_header.intersection({"ticker", "symbol", "代码", "证券代码", "标的", "股票代码"}):
        return []
    sample = raw.replace("，", ",")
    try:
        dialect = csv.Sniffer().sniff(sample[:2048], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(sample), dialect=dialect)
    out = []
    for row in reader:
        mapped = {_norm_header(k): (v.strip() if isinstance(v, str) else v)
                  for k, v in (row or {}).items()}
        if any(v not in (None, "") for v in mapped.values()):
            out.append(mapped)
    return out


def _pick(row: dict, aliases: set[str]):
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


_TICKER_FIELDS = {"ticker", "symbol", "代码", "证券代码", "标的", "股票代码"}
_DATE_FIELDS = {"date", "tradedate", "transactiondate", "成交日期", "交易日期", "日期"}
_SHARE_FIELDS = {"shares", "share", "qty", "quantity", "持仓数量", "数量", "股数", "成交数量"}
_PRICE_FIELDS = {"price", "avgprice", "averageprice", "avgcost", "costprice",
                 "成交价", "成交价格", "均价", "成本价", "平均成本", "买入价"}
_COST_FIELDS = {"cost", "costbasis", "amount", "netamount", "成交金额", "成本", "总成本", "金额"}


def _parse_trade_csv(text: str) -> list[dict]:
    rows = []
    for row in _csv_rows(text):
        ticker = str(_pick(row, _TICKER_FIELDS) or "").upper().strip()
        date_raw = _pick(row, _DATE_FIELDS)
        shares = _num(_pick(row, _SHARE_FIELDS))
        price = _num(_pick(row, _PRICE_FIELDS))
        if not ticker and date_raw is None and shares is None and price is None:
            continue
        if not ticker or date_raw is None or shares is None or price is None:
            raise ValueError(f"CSV 成交流水缺少 date/ticker/shares/price 字段: {row}")
        rows.append({
            "date": _normalize_trade_date(date_raw),
            "ticker": ticker,
            "shares": float(shares),
            "price": float(price),
            "raw": row,
        })
    return rows


def _snapshot_rows_from_body(body: dict) -> list[dict]:
    rows = []
    for row in _csv_rows(str(body.get("text", ""))):
        ticker = str(_pick(row, _TICKER_FIELDS) or "").upper().strip()
        shares = _num(_pick(row, _SHARE_FIELDS))
        price = _num(_pick(row, _PRICE_FIELDS))
        cost = _num(_pick(row, _COST_FIELDS))
        date_raw = _pick(row, _DATE_FIELDS)
        if not ticker and shares is None and price is None and cost is None:
            continue
        if not ticker or shares is None:
            raise ValueError(f"CSV 持仓快照缺少 ticker/shares 字段: {row}")
        if cost is None:
            if price is None:
                raise ValueError(f"{ticker} 缺少均价/成本字段")
            cost = float(shares) * float(price)
        if price is None:
            if float(shares) <= 0:
                raise ValueError(f"{ticker} 股数必须 > 0")
            price = float(cost) / float(shares)
        rows.append({
            "date": _normalize_trade_date(date_raw) if date_raw else None,
            "ticker": ticker,
            "shares": float(shares),
            "price": float(price),
            "cost": float(cost),
            "raw": row,
        })
    if body.get("positions"):
        for p in body.get("positions") or []:
            ticker = str(p.get("ticker", "")).upper().strip()
            shares = _num(p.get("shares"))
            price = _num(p.get("price") if p.get("price") is not None else p.get("avg_price"))
            cost = _num(p.get("cost") if p.get("cost") is not None else p.get("cost_basis"))
            if cost is None and shares is not None and price is not None:
                cost = float(shares) * float(price)
            if price is None and shares and cost is not None:
                price = float(cost) / float(shares)
            rows.append({
                "date": _normalize_trade_date(p.get("date")) if p.get("date") else None,
                "ticker": ticker,
                "shares": float(shares or 0),
                "price": float(price or 0),
                "cost": float(cost or 0),
                "raw": p,
            })
    if not rows:
        raise ValueError("请提供 CSV 持仓快照（至少包含 ticker/shares/avg price 或 cost）")
    for row in rows:
        if not row["ticker"]:
            raise ValueError("持仓快照缺少 ticker")
        if row["shares"] <= 0 or row["price"] <= 0 or row["cost"] <= 0:
            raise ValueError(f"{row['ticker']} 的股数、均价和成本必须 > 0")
    return rows


def _trade_rows_from_body(body: dict) -> list[dict]:
    rows = []
    for tr in body.get("trades") or []:
        try:
            row = {
                "date": _normalize_trade_date(tr.get("date", "")),
                "ticker": str(tr.get("ticker", "")).upper().strip(),
                "shares": float(tr.get("shares", 0)),
                "price": float(tr.get("price", 0)),
                "raw": tr,
            }
        except (TypeError, ValueError) as e:
            raise ValueError(f"成交记录字段无效: {tr}") from e
        rows.append(row)
    if body.get("text"):
        text = str(body.get("text", ""))
        csv_rows = _parse_trade_csv(text)
        rows.extend(csv_rows if csv_rows else _parse_trade_text(text))
    if not rows:
        raise ValueError("请提供至少一笔成交记录")
    for row in rows:
        if not row["ticker"]:
            raise ValueError("成交记录缺少 ticker")
        if row["shares"] <= 0 or row["price"] <= 0:
            raise ValueError(f"{row['ticker']} 的股数和价格必须 > 0")
    return rows


def _replacement_map_from_body(body: dict) -> dict[str, str]:
    repl: dict[str, str] = {}
    raw = body.get("replace") or {}
    if isinstance(raw, dict):
        for old, new in raw.items():
            old_t = str(old).upper().strip()
            new_t = str(new).upper().strip()
            if old_t and new_t:
                repl[old_t] = new_t
    txt = str(body.get("replace_text", "") or "")
    for part in re.split(r"[\n,，;；\s]+", txt):
        item = part.strip()
        if not item:
            continue
        if "->" in item:
            old, new = item.split("->", 1)
        elif "=" in item:
            old, new = item.split("=", 1)
        else:
            continue
        old_t = old.upper().strip()
        new_t = new.upper().strip()
        if old_t and new_t:
            repl[old_t] = new_t
    return repl


def _group_trade_rows(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        g = grouped.setdefault(row["ticker"], {
            "ticker": row["ticker"],
            "shares": 0.0,
            "cost": 0.0,
            "first_date": row["date"],
            "last_date": row["date"],
            "trades": [],
        })
        g["shares"] += row["shares"]
        g["cost"] += row["shares"] * row["price"]
        g["first_date"] = min(g["first_date"], row["date"])
        g["last_date"] = max(g["last_date"], row["date"])
        g["trades"].append(row)
    for g in grouped.values():
        g["avg_price"] = g["cost"] / g["shares"]
    return grouped


def _group_snapshot_rows(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        g = grouped.setdefault(row["ticker"], {
            "ticker": row["ticker"],
            "shares": 0.0,
            "cost": 0.0,
            "first_date": row.get("date"),
            "last_date": row.get("date"),
            "rows": [],
        })
        g["shares"] += row["shares"]
        g["cost"] += row["cost"]
        dates = [d for d in [g.get("first_date"), row.get("date")] if d]
        if dates:
            g["first_date"] = min(dates)
            g["last_date"] = max(dates)
        g["rows"].append(row)
    for g in grouped.values():
        if g["shares"] <= 0:
            raise ValueError(f"{g['ticker']} 股数必须 > 0")
        g["avg_price"] = g["cost"] / g["shares"]
    return grouped


def _sync_diff(pf: Portfolio, grouped: dict[str, dict], repl: dict[str, str],
               mode: str) -> list[dict]:
    old_by_new = {new: old for old, new in repl.items()}
    diff = []
    for ticker, g in grouped.items():
        old_ticker = old_by_new.get(ticker)
        source_ticker = ticker if ticker in pf.symbols else old_ticker
        source = pf.symbols.get(source_ticker) if source_ticker else None
        old_shares = float(source.shares) if source else 0.0
        old_cost = float(source.cost_basis) if source else 0.0
        old_avg = old_cost / old_shares if old_shares > 0 else None
        diff.append({
            "ticker": ticker,
            "mode": mode,
            "status": "replace" if old_ticker else ("update" if source else "new"),
            "replaced_from": old_ticker if old_ticker != ticker else None,
            "old_shares": round(old_shares, 6),
            "new_shares": round(float(g["shares"]), 6),
            "delta_shares": round(float(g["shares"]) - old_shares, 6),
            "old_cost_basis": round(old_cost, 2),
            "new_cost_basis": round(float(g["cost"]), 2),
            "delta_cost_basis": round(float(g["cost"]) - old_cost, 2),
            "old_avg_price": round(old_avg, 4) if old_avg is not None else None,
            "new_avg_price": round(float(g["avg_price"]), 4),
            "first_date": g.get("first_date") or (source.entry_date if source else None),
            "needs_date": bool(mode == "snapshot" and source is None and not g.get("first_date")),
        })
    missing = sorted(t for t in pf.symbols.keys()
                     if t not in grouped and t not in repl.keys())
    for ticker in missing:
        st = pf.symbols[ticker]
        avg = st.cost_basis / st.shares if st.shares > 0 else None
        diff.append({
            "ticker": ticker,
            "mode": mode,
            "status": "missing_in_import",
            "replaced_from": None,
            "old_shares": round(float(st.shares), 6),
            "new_shares": 0.0,
            "delta_shares": round(-float(st.shares), 6),
            "old_cost_basis": round(float(st.cost_basis), 2),
            "new_cost_basis": 0.0,
            "delta_cost_basis": round(-float(st.cost_basis), 2),
            "old_avg_price": round(avg, 4) if avg is not None else None,
            "new_avg_price": None,
            "first_date": st.entry_date,
            "needs_date": False,
        })
    return diff


def _rebuild_flows_from_symbols(pf: Portfolio) -> None:
    pf.flows = [
        CashFlow(date=(st.entry_date or pf.last_run_date or "init"),
                 amount=float(st.cum_injected),
                 note=f"当前持仓 {ticker}")
        for ticker, st in pf.symbols.items()
    ]


def _prices():
    if not _px_cache:
        dates, px, _ = _align_prices(CFG)
        _px_cache["dates"], _px_cache["px"] = dates, px
    return _px_cache["dates"], _px_cache["px"]


def _bars_for(ticker: str, cfg=None):
    key = str(ticker).upper()
    if key not in _bars_cache:
        df, _ = get_bars(key, cfg or CFG)
        _bars_cache[key] = df
    return _bars_cache[key]


def _daily_closes(cfg=None):
    """按传入 universe 获取日线最后收盘；支持 state 中新增的非 config 标的。"""
    c = cfg or CFG
    out = {}
    for s in c.symbols:
        df = _bars_for(s.ticker, c)
        out[s.ticker] = float(df["Close"].iloc[-1])
    return out


def _safe_daily_price(cfg=None):
    """安全腿(SGOV)日线最后收盘。无 safe_leg 配置 → None（防御层关闭）。"""
    c = cfg or CFG
    sl = getattr(c, "safe_leg", None)
    if sl is None:
        return None
    key = sl.ticker
    if key not in _safe_cache:
        df, _ = get_bars(sl.ticker, c)
        _safe_cache[key] = float(df["Close"].iloc[-1])
    return _safe_cache[key]


def _quote_tickers(cfg, include_safe: bool = True) -> list[str]:
    tickers = [s.ticker for s in (cfg or CFG).symbols]
    sl = getattr(cfg or CFG, "safe_leg", None)
    if include_safe and sl is not None:
        tickers.append(sl.ticker)
    tc = getattr(cfg or CFG, "tactical_orders", None)
    for ticker in getattr(tc, "market_gate_tickers", ()) if tc is not None else ():
        tickers.append(ticker)
    return sorted({str(t).upper() for t in tickers if t})


def _quotes_for(tickers: list[str]) -> dict:
    key = tuple(sorted({str(t).upper() for t in tickers if t}))
    if not key:
        return {}
    now = time.time()
    cached = _quote_cache.get(key)
    if cached and now - cached["ts"] <= QUOTE_TTL_SEC:
        return cached["quotes"]
    try:
        quotes = fetch_sina_quotes(key)
    except Exception as e:
        logging.getLogger("us_ratchet").warning("盘中报价失败: %s", e)
        quotes = {}
    _quote_cache[key] = {"ts": now, "quotes": quotes}
    return quotes


def _latest_prices(cfg=None, include_safe: bool = True):
    """盘中价格优先；失败逐只回退到日线最后收盘。

    返回 (prices, meta)。meta 里保留每只标的的价格源和时间，供前端显式展示。
    """
    c = cfg or CFG
    prices = _daily_closes(c)
    daily_price = dict(prices)
    tickers = _quote_tickers(c, include_safe=include_safe)
    quotes = _quotes_for(tickers)
    items = {}
    quote_times = []
    fallback = []

    for tk in tickers:
        q = quotes.get(tk)
        if q and q.price > 0:
            prices[tk] = float(q.price)
            if q.quote_time:
                quote_times.append(q.quote_time)
            items[tk] = {
                "ticker": tk,
                "source": q.source,
                "mode": "quote",
                "price": round(float(q.price), 4),
                "previous_close": round(float(q.previous_close), 4) if q.previous_close else None,
                "change": round(float(q.change), 4) if q.change is not None else None,
                "change_pct": round(float(q.change_pct) / 100.0, 6) if q.change_pct is not None else None,
                "quote_time": q.quote_time,
                "market_time": q.market_time,
            }
        elif tk in daily_price:
            fallback.append(tk)
            items[tk] = {
                "ticker": tk,
                "source": "daily_close",
                "mode": "daily_close",
                "price": round(float(daily_price[tk]), 4),
                "previous_close": round(float(daily_price[tk]), 4),
                "change": None,
                "change_pct": None,
                "quote_time": "",
                "market_time": "",
            }

    meta = {
        "mode": "quote" if any(x.get("mode") == "quote" for x in items.values()) else "daily_close",
        "source": "sina_quote" if any(x.get("mode") == "quote" for x in items.values()) else "daily_close",
        "as_of": max(quote_times) if quote_times else "",
        "quote_count": sum(1 for x in items.values() if x.get("mode") == "quote"),
        "fallback": fallback,
        "ttl_sec": QUOTE_TTL_SEC,
        "items": items,
        "note": "盘中价用于估值和今日建议预览；H/re-arm 仍以收盘落盘为准。",
    }
    return prices, meta


def _latest_closes(cfg=None):
    """兼容旧调用：返回盘中价优先的最新价格。"""
    return _latest_prices(cfg, include_safe=False)[0]


def _safe_price(cfg=None):
    """兼容旧调用：安全腿盘中价优先，失败回退日线收盘。"""
    c = cfg or CFG
    sl = getattr(c, "safe_leg", None)
    if sl is None:
        return None
    prices, _ = _latest_prices(c, include_safe=True)
    return prices.get(sl.ticker) or _safe_daily_price(c)


def _mean_tail(series, n: int) -> float | None:
    if n <= 0 or len(series) < n:
        return None
    return float(series.tail(n).mean())


def _atr_tail(df, n: int) -> float | None:
    if n <= 0 or len(df) < n + 1:
        return None
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    val = tr.tail(n).mean()
    return float(val) if np.isfinite(val) else None


def _market_regime(last_close: float, ma20: float | None, ma50: float | None,
                   ma200: float | None) -> str:
    if ma20 is None or ma50 is None:
        return "UNKNOWN"
    if last_close >= ma20 and ma20 >= ma50 and (ma200 is None or ma50 >= ma200):
        return "BULL"
    if last_close < ma50 or (ma200 is not None and last_close < ma200):
        return "BEAR"
    return "NEUTRAL"


def _regime_label(regime: str) -> str:
    return {
        "BULL": "牛市",
        "NEUTRAL": "震荡",
        "BEAR": "熊市/破趋势",
        "UNKNOWN": "未知",
    }.get(regime, str(regime or "UNKNOWN"))


def _regime_rank(regime: str) -> int:
    return {"BULL": 0, "NEUTRAL": 1, "UNKNOWN": 1, "BEAR": 2}.get(regime, 1)


def _worse_regime(a: str, b: str | None) -> str:
    if not b:
        return a
    return a if _regime_rank(a) >= _regime_rank(b) else b


def _market_stats(ticker: str, cfg, tc, latest_price: float | None = None,
                  price_info: dict | None = None) -> dict:
    df = _bars_for(ticker, cfg)
    close = df["Close"]
    last = float(latest_price) if latest_price and latest_price > 0 else float(close.iloc[-1])
    ma5 = _mean_tail(close, tc.ma_short)
    ma20 = _mean_tail(close, tc.ma_mid)
    ma50 = _mean_tail(close, tc.ma_trend)
    ma200 = _mean_tail(close, tc.ma_long)
    atr = _atr_tail(df, tc.atr_window)
    regime = _market_regime(last, ma20, ma50, ma200)
    return {
        "ticker": ticker,
        "as_of": close.index[-1].strftime("%Y-%m-%d"),
        "source": (price_info or {}).get("source", "daily_close"),
        "mode": (price_info or {}).get("mode", "daily_close"),
        "price_source": (price_info or {}).get("source", "daily_close"),
        "quote_time": (price_info or {}).get("quote_time", ""),
        "market_time": (price_info or {}).get("market_time", ""),
        "last": round(last, 2),
        "regime": regime,
        "label": _regime_label(regime),
        "ma5": round(ma5, 2) if ma5 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "ma50": round(ma50, 2) if ma50 else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "atr": round(atr, 2) if atr else None,
        "above_ma50": bool(ma50 is not None and last >= ma50),
        "above_ma200": bool(ma200 is not None and last >= ma200),
    }


def _market_phase_payload(cfg, latest_prices: dict | None = None,
                          price_meta: dict | None = None) -> dict | None:
    tc = getattr(cfg, "tactical_orders", None)
    if tc is None or not getattr(tc, "market_gate_enabled", False):
        return None
    items = []
    errors = {}
    for ticker in getattr(tc, "market_gate_tickers", ("QQQ", "SPY")):
        tk = str(ticker).upper()
        try:
            info = ((price_meta or {}).get("items") or {}).get(tk, {})
            items.append(_market_stats(tk, cfg, tc,
                                       (latest_prices or {}).get(tk), info))
        except Exception as e:
            errors[tk] = str(e)
    regimes = [x["regime"] for x in items if x.get("regime") != "UNKNOWN"]
    if not regimes:
        regime = "UNKNOWN"
    elif any(r == "BEAR" for r in regimes):
        regime = "BEAR"
    elif all(r == "BULL" for r in regimes):
        regime = "BULL"
    else:
        regime = "NEUTRAL"
    rule = {
        "BULL": "允许牛市回踩小额战术挂单；深跌棘轮照常装填。",
        "NEUTRAL": "战术买入降到震荡标准；只接受更深的 20日线/ATR 缓冲价。",
        "BEAR": "暂停浅层战术买入；保留储备金给深跌棘轮或后续再平衡。",
        "UNKNOWN": "市场层数据不足；仅按个股状态给出建议。",
    }[regime]
    return {
        "enabled": True,
        "regime": regime,
        "label": _regime_label(regime),
        "rule": rule,
        "method": "QQQ/SPY：收盘价、MA20/MA50/MA200；任一破趋势则按更保守阶段处理。",
        "as_of": max((x.get("quote_time") or x["as_of"] for x in items), default=None),
        "items": items,
        "errors": errors,
    }


def _tactical_order(ticker: str, st, live_price: float, cfg, market: dict | None = None,
                    price_info: dict | None = None) -> dict:
    tc = getattr(cfg, "tactical_orders", None)
    if tc is None or not getattr(tc, "enabled", False):
        return {"enabled": False, "action": "WAIT", "text": "战术挂单层未启用"}
    if st.frozen:
        return {"enabled": True, "action": "FROZEN", "text": "冻结：不做战术挂单"}
    if st.reserve_cash <= 0:
        return {"enabled": True, "action": "WAIT", "text": "无储备金，不做战术挂单"}

    try:
        df = _bars_for(ticker, cfg)
    except Exception as e:
        return {"enabled": True, "action": "WAIT", "text": f"战术挂单无法取数: {e}"}

    close = df["Close"]
    daily_ref = float(close.iloc[-1])
    basis_price = float((price_info or {}).get("previous_close") or daily_ref)
    ma5 = _mean_tail(close, tc.ma_short)
    ma20 = _mean_tail(close, tc.ma_mid)
    ma50 = _mean_tail(close, tc.ma_trend)
    ma200 = _mean_tail(close, tc.ma_long)
    atr = _atr_tail(df, tc.atr_window)
    if ma20 is None or ma50 is None or atr is None:
        return {"enabled": True, "action": "WAIT", "text": "战术挂单数据窗口不足"}

    # 限价生成必须使用稳定锚点；实时价只做触发判断，避免盘中 quote 下跌时限价跟着下移。
    stock_regime = _market_regime(basis_price, ma20, ma50, ma200)
    market_regime = market.get("regime") if market and market.get("enabled") else None
    regime = _worse_regime(stock_regime, market_regime)
    gate_note = None
    if market_regime and regime != stock_regime:
        if regime == "BEAR":
            gate_note = f"市场层{_regime_label(market_regime)}：暂停浅层战术买入"
        elif regime == "NEUTRAL":
            gate_note = f"市场层{_regime_label(market_regime)}：牛市信号降为震荡标准"

    cap = basis_price * (1 - tc.min_discount_pct)
    if regime == "BULL":
        ratio = tc.bull_reserve_ratio
        anchor = max(x for x in [ma5, ma20, basis_price - tc.bull_atr_mult * atr] if x is not None)
        reason = f"牛市：5/20日回踩或 {tc.bull_atr_mult:g}ATR 小回落"
    elif regime == "NEUTRAL":
        ratio = tc.neutral_reserve_ratio
        anchor = min(ma20, basis_price - tc.neutral_atr_mult * atr)
        reason = f"震荡：20日线下方并留 {tc.neutral_atr_mult:g}ATR 缓冲"
    else:
        ratio = tc.bear_reserve_ratio
        anchor = min(ma50, basis_price - tc.bear_atr_mult * atr)
        reason = "熊市/破趋势：默认不做浅层战术买入，保留弹药给深跌棘轮"
    if gate_note:
        reason = f"{gate_note}；{reason}"

    daily_limit = min(anchor, cap)
    amount = min(st.reserve_cash, st.reserve_cash * ratio)
    if amount <= 0:
        return {
            "enabled": True, "regime": regime, "action": "WAIT", "text": reason,
            "limit": round(float(daily_limit), 2), "trigger": round(float(daily_limit), 2),
            "amount": 0,
            "live_price": round(float(live_price), 2),
            "basis_price": round(float(basis_price), 2),
            "daily_ref": round(float(daily_ref), 2),
            "limit_fixed": True,
            "limit_basis": "previous_close_or_daily_close",
            "stock_regime": stock_regime, "market_regime": market_regime,
            "market_gate_applied": bool(gate_note),
            "metrics": {"ma5": round(ma5, 2) if ma5 else None,
                        "ma20": round(ma20, 2) if ma20 else None,
                        "ma50": round(ma50, 2) if ma50 else None,
                        "ma200": round(ma200, 2) if ma200 else None,
                        "atr": round(atr, 2) if atr else None},
        }

    triggered = live_price <= daily_limit
    limit = daily_limit
    shares = amount / limit if limit > 0 else 0.0
    text = (f"已触发今日固定限价 ${limit:.2f}，建议买入约 ${amount:,.0f}"
            if triggered else f"今日固定战术限价 ${limit:.2f}，金额 ${amount:,.0f}")
    return {
        "enabled": True, "regime": regime,
        "action": "BUY_NOW" if triggered else "PLACE_LIMIT",
        "text": text, "reason": reason,
        "limit": round(limit, 2), "trigger": round(limit, 2),
        "live_price": round(float(live_price), 2),
        "basis_price": round(float(basis_price), 2),
        "daily_ref": round(float(daily_ref), 2),
        "limit_fixed": True,
        "limit_basis": "previous_close_or_daily_close",
        "amount": round(amount, 0), "shares": round(shares, 3),
        "stock_regime": stock_regime, "market_regime": market_regime,
        "market_gate_applied": bool(gate_note),
        "metrics": {"ma5": round(ma5, 2) if ma5 else None,
                    "ma20": round(ma20, 2) if ma20 else None,
                    "ma50": round(ma50, 2) if ma50 else None,
                    "ma200": round(ma200, 2) if ma200 else None,
                    "atr": round(atr, 2) if atr else None},
    }


def _symbol_advice(sig, tactical=None):
    immediate = [{"amount": round(a, 0), "price": round(p, 2), "reason": why}
                 for a, p, why in sig.immediate_buys]
    triggered = [
        {"tier": e.tier_index, "threshold": e.threshold,
         "limit": round(e.limit_price, 2), "amount": round(e.amount, 0),
         "shares": round(e.shares, 3)}
        for e in sig.ladder
        if sig.last_close <= e.limit_price
    ]
    next_order = None
    if sig.ladder:
        e = sig.ladder[0]
        next_order = {"tier": e.tier_index, "threshold": e.threshold,
                      "limit": round(e.limit_price, 2),
                      "amount": round(e.amount, 0),
                      "shares": round(e.shares, 3)}
    if sig.frozen:
        return {"action": "FROZEN", "text": "冻结：不自动买入", "immediate": immediate,
                "triggered": triggered, "next_order": next_order}
    if immediate:
        total = sum(x["amount"] for x in immediate)
        return {"action": "BUY_NOW", "text": f"分批到期，建议买入约 ${total:,.0f}",
                "immediate": immediate, "triggered": triggered, "next_order": next_order}
    if triggered:
        total = sum(x["amount"] for x in triggered)
        return {"action": "BUY_NOW", "text": f"现价低于触发价，建议买入约 ${total:,.0f}",
                "immediate": immediate, "triggered": triggered, "next_order": next_order}
    if tactical and tactical.get("action") in {"BUY_NOW", "PLACE_LIMIT"}:
        return {**tactical, "immediate": immediate, "triggered": triggered,
                "next_order": next_order}
    if next_order:
        prefix = "等待战术信号" if tactical else "等待"
        return {"action": "WAIT",
                "text": f"{prefix}；深跌棘轮 ${next_order['limit']:.2f}",
                "immediate": immediate, "triggered": triggered, "next_order": next_order}
    return {"action": "WAIT", "text": "无活跃买入建议", "immediate": immediate,
            "triggered": triggered, "next_order": next_order}


def _defensive_payload(dfn):
    """把 DefensiveSignal 序列化给前端（None → 不触发）。"""
    if dfn is None:
        return None
    return {
        "direction": dfn.direction, "move": round(dfn.move, 0),
        "basket_value": round(dfn.basket_value, 0), "safe_value": round(dfn.safe_value, 0),
        "safe_weight": round(dfn.safe_weight, 4), "target_weight": round(dfn.target_weight, 4),
        "orders": [{"ticker": o.ticker, "side": o.side, "amount": round(o.amount, 0),
                    "shares": round(o.shares, 3), "from_reserve": round(o.from_reserve, 0),
                    "from_pending_core_cash": round(o.from_pending_core_cash, 0)}
                   for o in dfn.orders],
        "safe_order": {"ticker": dfn.safe_order.ticker, "side": dfn.safe_order.side,
                       "amount": round(dfn.safe_order.amount, 0),
                       "shares": round(dfn.safe_order.shares, 3)},
    }


def _apply_tactical_fill(pf: Portfolio, body: dict, cfg) -> dict:
    ticker = str(body.get("ticker", "")).upper().strip()
    if not ticker or ticker not in pf.symbols:
        raise ValueError(f"状态不存在或无此标的 {ticker}")
    st = pf.symbols[ticker]
    if st.frozen:
        raise ValueError(f"{ticker} 已冻结，不应回填战术成交")
    if st.reserve_cash <= 0:
        raise ValueError(f"{ticker} 无储备金可用于战术成交")

    prices, price_meta = _latest_prices(cfg, include_safe=True)
    info = ((price_meta or {}).get("items") or {}).get(ticker, {})
    market = _market_phase_payload(cfg, prices, price_meta)
    live_price = float(prices.get(ticker) or 0)
    tactical = _tactical_order(ticker, st, live_price, cfg, market, info)
    suggested_amount = float(tactical.get("amount") or 0.0)
    suggested_limit = float(tactical.get("limit") or 0.0)

    amount = float(body.get("amount") or suggested_amount or 0.0)
    price = float(body.get("price") or suggested_limit or 0.0)
    if amount <= 0:
        raise ValueError("战术成交金额必须 > 0")
    if price <= 0:
        raise ValueError("战术成交价必须 > 0")
    amount = min(amount, float(st.reserve_cash))
    shares = amount / price

    fill_date = str(body.get("date") or date.today().isoformat()).strip()
    fill_date = _normalize_trade_date(fill_date)
    note = str(body.get("note", "") or "").strip()

    st.shares += shares
    st.cost_basis += amount
    st.reserve_cash -= amount
    fill = TacticalFill(
        date=fill_date,
        limit_price=float(suggested_limit or price),
        fill_price=price,
        amount=amount,
        shares=shares,
        basis_price=float(tactical.get("basis_price") or 0.0),
        live_price=float(tactical.get("live_price") or live_price or 0.0),
        regime=str(tactical.get("regime") or ""),
        reason=str(tactical.get("reason") or ""),
        note=note,
    )
    st.tactical_fills.append(fill)
    return {
        "ticker": ticker,
        "date": fill.date,
        "amount": round(amount, 2),
        "shares": round(shares, 6),
        "fill_price": round(price, 4),
        "limit_price": round(fill.limit_price, 4),
        "reserve_left": round(st.reserve_cash, 2),
        "regime": fill.regime,
        "reason": fill.reason,
        "note": fill.note,
    }


def _execution_payload(symbols: list[dict], defensive: dict | None, price_meta: dict | None) -> dict:
    """统一生成今日可执行建议；研究层规则不得在这里改变实盘动作。"""
    items: list[dict] = []

    def add_item(priority: int, source: str, ticker: str, action: str, side: str,
                 label: str, amount: float | None = None, shares: float | None = None,
                 limit: float | None = None, live_price: float | None = None,
                 trigger: float | None = None, threshold: float | None = None,
                 status: str = "active", reason: str = "", text: str = ""):
        items.append({
            "priority": priority,
            "source": source,
            "ticker": ticker,
            "action": action,
            "side": side,
            "label": label,
            "amount": round(float(amount), 0) if amount is not None else None,
            "shares": round(float(shares), 3) if shares is not None else None,
            "limit": round(float(limit), 2) if limit is not None else None,
            "live_price": round(float(live_price), 2) if live_price is not None else None,
            "trigger": round(float(trigger), 2) if trigger is not None else None,
            "threshold": round(float(threshold), 4) if threshold is not None else None,
            "status": status,
            "reason": reason,
            "text": text,
        })

    for s in symbols:
        ticker = s.get("ticker", "")
        advice = s.get("advice") or {}
        tactical = s.get("tactical") or {}

        if s.get("frozen") or advice.get("action") == "FROZEN":
            add_item(
                priority=85, source="symbol_wait", ticker=ticker,
                action="FROZEN", side="NONE", label="冻结",
                live_price=s.get("last_close"), status="wait",
                text=advice.get("text", "冻结：不自动买入"),
            )
            continue

        for im in advice.get("immediate") or []:
            add_item(
                priority=10, source="pending_core", ticker=ticker,
                action="BUY_NOW", side="BUY", label="分批核心到期",
                amount=im.get("amount"), live_price=im.get("price"),
                reason=im.get("reason", ""), text="待分批核心现金到期，按今日执行价买入。",
            )

        for tr in advice.get("triggered") or []:
            add_item(
                priority=20, source="ratchet_trigger", ticker=ticker,
                action="BUY_NOW", side="BUY", label=f"深跌棘轮档 {tr.get('tier')}",
                amount=tr.get("amount"), shares=tr.get("shares"), limit=tr.get("limit"),
                trigger=tr.get("limit"), threshold=tr.get("threshold"),
                text="现价已低于已装填档位限价，属于主策略即时买入。",
            )

        has_primary_buy = bool(advice.get("immediate") or advice.get("triggered"))
        if (not has_primary_buy and tactical.get("action") in {"BUY_NOW", "PLACE_LIMIT"}
                and tactical.get("amount")):
            is_now = tactical.get("action") == "BUY_NOW"
            add_item(
                priority=30 if is_now else 50, source="tactical_limit", ticker=ticker,
                action=tactical.get("action"), side="BUY",
                label="战术固定限价",
                amount=tactical.get("amount"), shares=tactical.get("shares"),
                limit=tactical.get("limit"), live_price=tactical.get("live_price"),
                trigger=tactical.get("trigger"), status="triggered" if is_now else "pending",
                reason=tactical.get("reason", ""), text=tactical.get("text", ""),
            )

        next_order = advice.get("next_order")
        has_triggered_ladder = bool(advice.get("triggered"))
        if next_order and not has_triggered_ladder:
            add_item(
                priority=70, source="ratchet_next", ticker=ticker,
                action="PLACE_LIMIT", side="BUY", label=f"深跌棘轮档 {next_order.get('tier')}",
                amount=next_order.get("amount"), shares=next_order.get("shares"),
                limit=next_order.get("limit"), trigger=next_order.get("limit"),
                threshold=next_order.get("threshold"), status="pending",
                text="深跌棘轮的下一档限价，可作为预先挂单参考。",
            )

        if not advice.get("immediate") and not advice.get("triggered") and not next_order \
                and tactical.get("action") not in {"BUY_NOW", "PLACE_LIMIT"}:
            add_item(
                priority=90, source="symbol_wait", ticker=ticker,
                action=advice.get("action", "WAIT"), side="NONE", label="无动作",
                live_price=s.get("last_close"), status="wait",
                reason=tactical.get("reason", ""), text=advice.get("text", "无活跃买入建议"),
            )

    if defensive:
        direction = defensive.get("direction")
        safe_order = defensive.get("safe_order") or {}
        label = "防御层减风险" if direction == "trim" else "防御层回补风险"
        add_item(
            priority=5, source="defensive_safe", ticker=safe_order.get("ticker", ""),
            action="REBALANCE", side=safe_order.get("side", ""), label=label,
            amount=safe_order.get("amount"), shares=safe_order.get("shares"),
            status="needs_confirm",
            text="防御层偏离执行带，需要点击确认后才会落盘。",
        )
        for o in defensive.get("orders") or []:
            add_item(
                priority=6, source="defensive_basket", ticker=o.get("ticker", ""),
                action="REBALANCE", side=o.get("side", ""), label=label,
                amount=o.get("amount"), shares=o.get("shares"),
                status="needs_confirm",
                text="防御层篮子侧再平衡指令。",
            )

    items.sort(key=lambda x: (x["priority"], x["ticker"], x["source"]))
    counts = {"buy_now": 0, "place_limit": 0, "rebalance": 0, "wait": 0}
    for it in items:
        action = it.get("action")
        if action == "BUY_NOW":
            counts["buy_now"] += 1
        elif action == "PLACE_LIMIT":
            counts["place_limit"] += 1
        elif action == "REBALANCE":
            counts["rebalance"] += 1
        else:
            counts["wait"] += 1

    actionable = counts["buy_now"] + counts["place_limit"] + counts["rebalance"]
    if actionable:
        summary = (f"今日执行层：立即买入 {counts['buy_now']} 条，固定/深跌限价 "
                   f"{counts['place_limit']} 条，防御再平衡 {counts['rebalance']} 条。")
    else:
        summary = "今日执行层：无立即买入、无防御再平衡；仅保留观察。"
    return {
        "as_of": (price_meta or {}).get("as_of"),
        "mode": (price_meta or {}).get("mode", "daily_close"),
        "counts": counts,
        "actionable_count": actionable,
        "summary": summary,
        "items": items,
        "research_note": "MA门控、崩盘sleeve、参数扫描、注资模式A/B和战术挂单A/B仍是研究层；未显式接入前不会改变今日建议。",
    }


@app.get("/")
def index():
    return FileResponse(WEB)


@app.post("/api/refresh")
def refresh():
    _px_cache.clear()
    _bt_cache.clear()
    _roll_cache.clear()
    _trend_cache.clear()
    _crash_cache.clear()
    _param_cache.clear()
    _inject_mode_cache.clear()
    _tactical_cache.clear()
    _safe_cache.clear()
    _bars_cache.clear()
    _quote_cache.clear()
    return {"ok": True}


@app.get("/api/backtest")
def api_backtest(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _bt_cache:
        return _bt_cache[key]
    try:
        res = run_nav_panel(bt_cfg, monthly=monthly,
                            safe_weight=(bt_cfg.safe_leg.target_weight
                                         if bt_cfg.safe_leg else 0.0),
                            safe_annual=0.04, rebal_days=21,
                            rebal_band=0.0, benchmark_tickers=("QQQ", "SPY"))
    except Exception as e:
        return JSONResponse({"error": f"回测失败: {e}"}, status_code=500)

    # 下采样到 ~400 点
    dates = res["grid"]
    n = len(dates)
    step = max(1, n // 400)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    dlabels = [dates[i].strftime("%Y-%m-%d") for i in idx]

    def curve(arr):
        return [round(float(arr[i]), 4) for i in idx]

    order = list(res["curves"].keys())
    summary = {name: item["metrics"] for name, item in res["curves"].items()}
    out = {
        "dates": dlabels,
        "series": {name: curve(item["nav"]) for name, item in res["curves"].items()},
        "summary": summary,
        "order": order,
        "baseline": res["baseline_label"],
        "strategy_label": res["strategy_label"],
        "contributed": res["contributed"],
        "range": [dlabels[0], dlabels[-1]],
        "tier_contrib": res.get("tier_contrib", {}),
        "meta": {
            "unit": "NAV",
            "safe_weight": res["safe_weight"],
            "safe_annual": res["safe_annual"],
            "benchmark_errors": res.get("benchmark_errors", {}),
        },
    }
    _bt_cache[key] = out
    return out


@app.get("/api/rolling_starts")
def api_rolling_starts(monthly: float = 3000.0, min_years: float = 3.0):
    bt_cfg = _backtest_cfg()
    min_years = max(1.0, float(min_years))
    key = (round(monthly, 2), round(min_years, 2), _state_mtime_ns())
    if key in _roll_cache:
        return _roll_cache[key]
    try:
        res = run_rolling_start_panel(
            bt_cfg, monthly=monthly, min_years=min_years,
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0,
            benchmark_tickers=("QQQ", "SPY"), baseline_ticker="QQQ")
    except Exception as e:
        return JSONResponse({"error": f"滚动回测失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    out = {
        "summary": res.get("summary", {}),
        "rows": rows,
        "strategy_label": res.get("strategy_label"),
        "range": [rows[0]["start"], rows[-1]["start"]] if rows else None,
        "meta": {
            "unit": "NAV",
            "safe_weight": res.get("safe_weight"),
            "safe_annual": res.get("safe_annual"),
            "benchmark_errors": res.get("benchmark_errors", {}),
        },
    }
    _roll_cache[key] = out
    return out


@app.get("/api/trend_ab")
def api_trend_ab(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _trend_cache:
        return _trend_cache[key]
    try:
        res = run_trend_gate_ab(
            bt_cfg, monthly=monthly,
            ma_days=(5, 20, 50, 200),
            floors=(0.75, 0.50, 0.0),
            band=0.0, cost=0.001,
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0)
    except Exception as e:
        return JSONResponse({"error": f"趋势门控 A/B 失败: {e}"}, status_code=500)

    out = {
        "summary": res.get("summary", {}),
        "baselines": res.get("baselines", {}),
        "rows": res.get("rows", []),
        "execution_rows": res.get("execution_rows", []),
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "meta": {"unit": "NAV", "research_only": True},
    }
    _trend_cache[key] = out
    return out


@app.get("/api/crash_sleeve")
def api_crash_sleeve(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _crash_cache:
        return _crash_cache[key]
    try:
        res = run_crash_sleeve_ab(
            bt_cfg, monthly=monthly,
            sleeve_weights=(0.10, 0.15),
            thresholds=(0.20, 0.30, 0.40),
            deploy_ratios=(0.30, 0.40, 1.00),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0,
            benchmark_tickers=("QQQ", "SPY"))
    except Exception as e:
        return JSONResponse({"error": f"崩盘 sleeve A/B 失败: {e}"}, status_code=500)

    out = {
        "summary": res.get("summary", {}),
        "baselines": res.get("baselines", {}),
        "rows": res.get("rows", []),
        "correlation": res.get("correlation", {}),
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "meta": {
            "unit": "NAV",
            "research_only": True,
            "benchmark_errors": res.get("benchmark_errors", {}),
        },
    }
    _crash_cache[key] = out
    return out


@app.get("/api/param_scan")
def api_param_scan(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _param_cache:
        return _param_cache[key]
    try:
        res = run_param_scan_ab(
            bt_cfg, monthly=monthly,
            core_ratios=(0.75, 0.85, 0.90, 0.95),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0)
    except Exception as e:
        return JSONResponse({"error": f"参数扫描失败: {e}"}, status_code=500)

    out = {
        "summary": res.get("summary", {}),
        "baselines": res.get("baselines", {}),
        "rows": res.get("rows", []),
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "meta": {"unit": "NAV", "research_only": True},
    }
    _param_cache[key] = out
    return out


@app.get("/api/injection_ab")
def api_injection_ab(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _inject_mode_cache:
        return _inject_mode_cache[key]
    try:
        res = run_injection_mode_ab(
            bt_cfg, monthly=monthly,
            modes=("lump_core", "ladder_core", "all_reserve"),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0)
    except Exception as e:
        return JSONResponse({"error": f"注资模式 A/B 失败: {e}"}, status_code=500)

    out = {
        "summary": res.get("summary", {}),
        "baselines": res.get("baselines", {}),
        "rows": res.get("rows", []),
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "meta": {"unit": "NAV", "research_only": True},
    }
    _inject_mode_cache[key] = out
    return out


@app.get("/api/tactical_ab")
def api_tactical_ab(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _tactical_cache:
        return _tactical_cache[key]
    try:
        res = run_tactical_overlay_ab(
            bt_cfg, monthly=monthly,
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21,
            rebal_band=(bt_cfg.safe_leg.exec_band if bt_cfg.safe_leg else 0.0),
            rolling_step_months=12)
    except Exception as e:
        return JSONResponse({"error": f"战术挂单 A/B 失败: {e}"}, status_code=500)

    out = {
        "summary": res.get("summary", {}),
        "baselines": res.get("baselines", {}),
        "rows": res.get("rows", []),
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "meta": {"unit": "NAV", "research_only": True},
    }
    _tactical_cache[key] = out
    return out


def _state_payload(pf):
    cfg = _cfg_for_portfolio(pf)
    closes, price_meta = _latest_prices(cfg, include_safe=True)
    safe_px = None
    if getattr(cfg, "safe_leg", None) is not None:
        safe_px = closes.get(cfg.safe_leg.ticker) or _safe_daily_price(cfg)
    preview = copy.deepcopy(pf)
    live.advance_trading_day(preview, date.today().isoformat())
    # 被动状态页使用盘中 quote 估值，但不把盘中价用于 H/re-arm 预览，避免开盘阶段误刷新策略高点。
    signals = live.generate_signals(preview, closes, cfg, update_highs=False)
    market = _market_phase_payload(cfg, closes, price_meta)
    # 防御层：被动 GET 只预览（apply=False，不改持仓），执行走 /api/rebalance
    dfn = live.compute_defensive(preview, closes, safe_px, cfg, apply=False)
    thr = cfg.portfolio.tiers.thresholds
    syms = []
    tot_mv = tot_res = tot_pending = tot_cost = tot_injected = 0.0
    for sig in signals:
        st = preview.symbols[sig.ticker]
        info = ((price_meta or {}).get("items") or {}).get(sig.ticker, {})
        tactical = _tactical_order(sig.ticker, st, sig.last_close, cfg, market, info)
        advice = _symbol_advice(sig, tactical)
        avg_price = (st.cost_basis / st.shares) if st.shares > 0 else None
        tot_mv += sig.market_value
        tot_res += sig.reserve_cash
        tot_pending += st.pending_core_cash
        tot_cost += st.cost_basis
        tot_injected += st.cum_injected
        tactical_fills = getattr(st, "tactical_fills", []) or []
        tactical_fill_amount = sum(float(f.amount) for f in tactical_fills)
        syms.append({
            **info,
            "ticker": sig.ticker, "last_close": round(sig.last_close, 2),
            "H": round(sig.H, 2), "drawdown": round(sig.drawdown, 4),
            "reserve": round(sig.reserve_cash, 0), "shares": round(sig.shares, 3),
            "pending_core_cash": round(st.pending_core_cash, 0),
            "market_value": round(sig.market_value, 0), "cost_basis": round(st.cost_basis, 0),
            "avg_price": round(avg_price, 4) if avg_price is not None else None,
            "entry_date": st.entry_date,
            "entry_price": round(st.entry_price, 4) if st.entry_price else None,
            "cap_total": round(st.cap_total, 0), "cum_injected": round(st.cum_injected, 0),
            "frozen": st.frozen, "tier_armed": st.tier_armed, "thresholds": thr,
            "tactical_fill_count": len(tactical_fills),
            "tactical_fill_amount": round(tactical_fill_amount, 0),
            "tactical_fills": [
                {"date": f.date, "amount": round(f.amount, 0),
                 "fill_price": round(f.fill_price, 2), "limit_price": round(f.limit_price, 2),
                 "shares": round(f.shares, 3), "regime": f.regime, "note": f.note}
                for f in tactical_fills[-5:]
            ],
            "advice": advice,
            "tactical": tactical,
            "immediate_buys": [{"amount": round(a, 0), "price": round(p, 2), "reason": why}
                               for a, p, why in sig.immediate_buys],
            "ladder": [{"tier": e.tier_index, "threshold": e.threshold,
                        "limit": round(e.limit_price, 2), "amount": round(e.amount, 0),
                        "shares": round(e.shares, 3)} for e in sig.ladder],
            "pnl": round(sig.market_value - st.cost_basis, 0),
        })
    safe_value = (pf.safe_shares * safe_px) if safe_px else 0.0
    total_value = tot_mv + tot_res + tot_pending + safe_value
    safe = None
    if pf.target_safe_weight > 0 and safe_px:
        safe_info = ((price_meta or {}).get("items") or {}).get(pf.safe_ticker, {})
        safe = {"ticker": pf.safe_ticker, "shares": round(pf.safe_shares, 3),
                "price": round(safe_px, 2), "value": round(safe_value, 0),
                "source": safe_info.get("source", "daily_close"),
                "mode": safe_info.get("mode", "daily_close"),
                "price_source": safe_info.get("source", "daily_close"),
                "quote_time": safe_info.get("quote_time", ""),
                "market_time": safe_info.get("market_time", ""),
                "target_weight": round(pf.target_safe_weight, 4),
                "weight": round(safe_value / total_value, 4) if total_value > 0 else 0.0,
                "exec_band": round(getattr(CFG.safe_leg, "exec_band", 0.0), 4)}
    defensive = _defensive_payload(dfn)
    return {
        "initialized": True, "symbols": syms, "safe": safe, "market": market,
        "price_meta": price_meta,
        "as_of": date.today().isoformat(),
        "state_last_run_date": pf.last_run_date,
        "preview_day_index": preview.day_index,
        "needs_daily_update": pf.last_run_date != date.today().isoformat(),
        "defensive": defensive,
        "execution": _execution_payload(syms, defensive, price_meta),
        "totals": {"market_value": round(tot_mv, 0), "reserve": round(tot_res, 0),
                   "pending_core_cash": round(tot_pending, 0),
                   "cost_basis": round(tot_cost, 0),
                   "contributed": round(tot_injected, 0),
                   "basket_value": round(tot_mv + tot_res + tot_pending, 0),
                   "safe_value": round(safe_value, 0),
                   "total_value": round(total_value, 0),
                   "pnl": round(tot_mv - tot_cost, 0)},
    }


@app.get("/api/state")
def api_state():
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        caps = {s.ticker: s.cap_total for s in CFG.symbols}
        return {"initialized": False, "caps": caps,
                "core_ratio": CFG.portfolio.core_ratio}
    try:
        return _state_payload(pf)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)


@app.post("/api/daily_update")
def api_daily_update():
    """显式落盘今日状态：推进交易日、处理到期分批、刷新 H/re-arm。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        closes = _daily_closes(cfg)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    backup_state(resolve(STATE_PATH))
    live.advance_trading_day(pf, date.today().isoformat())
    signals = live.generate_signals(pf, closes, cfg)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("daily_update",
              {"date": date.today().isoformat(),
               "immediate_buys": {s.ticker: [{"amount": round(a, 2), "price": round(p, 4), "reason": why}
                                             for a, p, why in s.immediate_buys]
                                  for s in signals if s.immediate_buys}},
              "前端显式落盘今日状态")
    return _state_payload(pf)


@app.post("/api/init")
def api_init():
    if load_portfolio(resolve(STATE_PATH)) is not None:
        return JSONResponse({"error": "已存在状态，拒绝覆盖。如需重建请删除 data/state.json"}, status_code=400)
    try:
        closes = _latest_closes(CFG)
        safe_px = _safe_price(CFG)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    pf = live.init_portfolio(CFG, closes, safe_px)   # safe_px 提供 → 同时播种 SGOV 安全腿至目标比
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("init", {"caps": {t: s.cap_total for t, s in pf.symbols.items()},
                       "safe": {"ticker": pf.safe_ticker, "shares": pf.safe_shares,
                                "target_weight": pf.target_safe_weight}}, "前端建仓")
    return _state_payload(pf)


@app.post("/api/rebalance")
def api_rebalance():
    """显式执行防御层再平衡（把预览指令落到 state：改 shares/reserve/safe_shares）。
    被动 GET /api/state 只预览不执行；用户确认后调本接口落盘。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        closes = _latest_closes(cfg)
        safe_px = _safe_price(cfg)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    if safe_px is None or pf.target_safe_weight <= 0:
        return JSONResponse({"error": "未启用安全腿（config 无 safe_leg 或未播种）"}, status_code=400)
    live.advance_trading_day(pf, date.today().isoformat())
    dfn = live.compute_defensive(pf, closes, safe_px, cfg, apply=True)   # 真正落 state
    if dfn is None:
        return {"rebalanced": False, "msg": "当前在执行带内，无需再平衡"}
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("rebalance", {"direction": dfn.direction, "move": round(dfn.move, 0),
                            "safe_weight_before": round(dfn.safe_weight, 4)}, "前端执行防御层再平衡")
    payload = _state_payload(pf)
    payload["rebalanced"] = True
    payload["executed"] = _defensive_payload(dfn)
    return payload


@app.post("/api/inject")
def api_inject(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper()
    new_cap = float(body.get("new_cap", 0))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if ticker not in pf.symbols:
        return JSONResponse({"error": f"无此标的 {ticker}"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    closes = _latest_closes(cfg)
    backup_state(resolve(STATE_PATH))
    live.advance_trading_day(pf, date.today().isoformat())   # 注资前先推进当日序号
    delta = live.apply_cap_change(pf, ticker, new_cap, closes[ticker], cfg)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("inject", {"ticker": ticker, "new_cap": new_cap, "delta": delta}, "前端加本金")
    payload = _state_payload(pf)
    payload["injected_delta"] = round(delta, 0)
    return payload


@app.post("/api/scale_up")
def api_scale_up(body: dict = Body(...)):
    """按 74:26 提高总持仓 $amount：(1-W)×amount 分摊注资进 8 名（lump），W×amount 加 SGOV。
    保持篮子内逆波动率权重 + 篮子:安全腿目标比精确不变。"""
    amount = float(body.get("amount", 0))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if amount <= 0:
        return JSONResponse({"error": "金额必须 > 0"}, status_code=400)
    if pf.target_safe_weight <= 0:
        return JSONResponse({"error": "未启用安全腿，无法按 74:26 加仓（请用「加本金」逐只）"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        closes = _latest_closes(cfg)
        safe_px = _safe_price(cfg)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    if safe_px is None:
        return JSONResponse({"error": "取安全腿价失败"}, status_code=500)
    backup_state(resolve(STATE_PATH))
    live.advance_trading_day(pf, date.today().isoformat())
    res = live.scale_up_portfolio(pf, amount, closes, safe_px, cfg)
    if res is None:
        return JSONResponse({"error": "加仓失败（金额或组合状态无效）"}, status_code=400)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("scale_up", {"total": amount, "basket": res.basket_portion,
                           "safe": res.safe_portion}, "前端按74:26提高总持仓")
    payload = _state_payload(pf)
    payload["scale_up"] = {
        "total": round(res.total, 0),
        "basket_portion": round(res.basket_portion, 0),
        "safe_portion": round(res.safe_portion, 0),
        "orders": [{"ticker": t, "delta": round(d, 0)} for t, d in res.orders],
        "safe_ticker": res.safe_ticker,
        "safe_added_shares": round(res.safe_added_shares, 3),
    }
    return payload


@app.post("/api/fill")
def api_fill(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper()
    tier = int(body.get("tier", -1))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None or ticker not in pf.symbols:
        return JSONResponse({"error": "状态不存在或无此标的"}, status_code=400)
    st = pf.symbols[ticker]
    cfg = _cfg_for_portfolio(pf)
    thr = cfg.portfolio.tiers.thresholds
    if not (0 <= tier < len(thr)) or not st.tier_armed[tier]:
        return JSONResponse({"error": "档位无效或未装填"}, status_code=400)
    limit = st.H * (1 + thr[tier])
    ladder = {e.tier_index: e for e in eng.compute_ladder(st, cfg)}
    amount = float(body.get("amount") or (ladder[tier].amount if tier in ladder else 0))
    price = float(body.get("price") or limit)
    amount = min(amount, st.reserve_cash)
    if amount <= 0 or price <= 0:
        return JSONResponse({"error": "金额/价格无效"}, status_code=400)
    sh = amount / price
    st.shares += sh; st.cost_basis += amount; st.reserve_cash -= amount
    st.tier_armed[tier] = False
    st.fires.append(TierFire(date=date.today().isoformat(), tier_index=tier, threshold=thr[tier],
                             limit_price=limit, fill_price=price, amount=amount, shares=sh))
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("fill", {"ticker": ticker, "tier": tier, "price": price, "amount": amount}, "前端回填成交")
    return _state_payload(pf)


@app.post("/api/tactical_fill")
def api_tactical_fill(body: dict = Body(...)):
    """回填战术固定限价成交：只写 tactical_fills，不关闭深跌棘轮档位。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        detail = _apply_tactical_fill(pf, body, cfg)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("tactical_fill", detail, "前端回填战术固定限价成交")
    payload = _state_payload(pf)
    payload["tactical_fill"] = detail
    return payload


@app.post("/api/add_symbol")
def api_add_symbol(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper().strip()
    buy_date = str(body.get("buy_date", "")).strip()
    try:
        buy_price = float(body.get("buy_price", 0))
        shares = float(body.get("shares", 0))
        reserve_cash = float(body.get("reserve_cash", 0) or 0)
    except (TypeError, ValueError):
        return JSONResponse({"error": "股数/买入价/储备金必须为数字"}, status_code=400)
    if not ticker:
        return JSONResponse({"error": "请填写 ticker"}, status_code=400)
    if buy_price <= 0 or shares <= 0 or reserve_cash < 0:
        return JSONResponse({"error": "股数和买入价必须 > 0，储备金不能为负"}, status_code=400)
    if not buy_date:
        return JSONResponse({"error": "请填写买入日期"}, status_code=400)
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if ticker in pf.symbols:
        return JSONResponse({"error": f"{ticker} 已在当前持仓中，请用校准持仓或加本金"}, status_code=400)
    try:
        h = _history_high_since(ticker, buy_date)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    cost_basis = shares * buy_price
    cap_total = cost_basis + reserve_cash
    st = SymbolState(
        ticker=ticker,
        cap_total=cap_total,
        shares=shares,
        reserve_cash=reserve_cash,
        reserve_budget=reserve_cash,
        H=h,
        tier_armed=[True] * len(CFG.portfolio.tiers.thresholds),
        cost_basis=cost_basis,
        cum_injected=cap_total,
        entry_date=buy_date[:10],
        entry_price=buy_price,
    )
    backup_state(resolve(STATE_PATH))
    pf.symbols[ticker] = st
    pf.flows.append(CashFlow(date=buy_date[:10], amount=cap_total, note=f"新增持仓 {ticker}"))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("add_symbol",
              {"ticker": ticker, "buy_date": st.entry_date, "buy_price": buy_price,
               "shares": shares, "reserve_cash": reserve_cash,
               "cap_total": round(cap_total, 2), "H": round(h, 4)},
              "前端新增持仓")
    return _state_payload(pf)


@app.post("/api/remove_symbol")
def api_remove_symbol(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper().strip()
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if ticker not in pf.symbols:
        return JSONResponse({"error": f"当前持仓中没有 {ticker}"}, status_code=400)
    if len(pf.symbols) <= 1:
        return JSONResponse({"error": "至少保留一只风险腿标的"}, status_code=400)
    old = pf.symbols[ticker].to_dict()
    backup_state(resolve(STATE_PATH))
    del pf.symbols[ticker]
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("remove_symbol", {"ticker": ticker, "old": old}, "前端删除持仓")
    return _state_payload(pf)


@app.post("/api/sync_trades")
def api_sync_trades(body: dict = Body(...)):
    """按券商已成交流水或持仓快照覆盖当前聚合持仓。

    mode=trades：同一 ticker 多笔成交会聚合为真实股数和加权均价；默认保留该标的已有储备金。
    mode=snapshot：CSV 至少包含 ticker/shares/avg_price 或 cost；新标的需要 date/buy_date。
    preview=true 时只返回差异，不落盘。replace/replace_text 用于 GOOGL=GOOG
    这种从旧 ticker 迁移到新 ticker 的场景。
    """
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    try:
        mode = str(body.get("mode", "trades") or "trades").lower()
        if mode in {"snapshot", "positions", "position"}:
            mode = "snapshot"
            rows = _snapshot_rows_from_body(body)
            grouped = _group_snapshot_rows(rows)
        else:
            mode = "trades"
            rows = _trade_rows_from_body(body)
            grouped = _group_trade_rows(rows)
        repl = _replacement_map_from_body(body)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    preserve_reserve = bool(body.get("preserve_reserve", True))
    reset_tiers = bool(body.get("reset_tiers", True))
    sync_cap = bool(body.get("sync_cap", True))
    old_by_new = {new: old for old, new in repl.items()}
    changed = []
    diff = _sync_diff(pf, grouped, repl, mode)
    if bool(body.get("preview", False)):
        return {
            "preview": True,
            "mode": mode,
            "rows": len(rows),
            "diff": diff,
            "blocked": [d for d in diff if d.get("needs_date")],
            "note": "预览不落盘；确认同步后才会备份并改写 data/state.json。",
        }
    blocked = [d for d in diff if d.get("needs_date")]
    if blocked:
        names = ", ".join(d["ticker"] for d in blocked)
        return JSONResponse({"error": f"持仓快照新增标的需要买入日期: {names}"}, status_code=400)

    try:
        for ticker, g in grouped.items():
            old_ticker = old_by_new.get(ticker)
            if old_ticker and old_ticker != ticker and ticker in pf.symbols:
                return JSONResponse({"error": f"{ticker} 已存在，无法同时从 {old_ticker} 替换"}, status_code=400)
            source_ticker = ticker if ticker in pf.symbols else old_ticker
            source = pf.symbols.get(source_ticker) if source_ticker else None
            reserve = (float(source.reserve_cash) + float(source.pending_core_cash)
                       if (source and preserve_reserve) else 0.0)
            buy_date = g.get("first_date") or (source.entry_date if source else None)
            if not buy_date:
                return JSONResponse({"error": f"{ticker} 缺少买入日期，无法重算 H"}, status_code=400)
            h = _history_high_since(ticker, buy_date)
            old_snapshot = source.to_dict() if source else None

            if source is None:
                st = SymbolState(ticker=ticker, cap_total=0.0)
            else:
                st = copy.deepcopy(source)
                st.ticker = ticker
            st.shares = float(g["shares"])
            st.cost_basis = float(g["cost"])
            st.entry_date = str(buy_date)[:10]
            st.entry_price = float(g["avg_price"])
            st.H = h
            st.reserve_cash = reserve
            st.reserve_budget = reserve
            st.pending_ladder = []
            st.pending_core_cash = 0.0
            if reset_tiers:
                st.tier_armed = [True] * len(CFG.portfolio.tiers.thresholds)
            if sync_cap:
                st.cum_injected = st.cost_basis + st.reserve_cash + st.pending_core_cash
                st.cap_total = st.cum_injected

            if old_ticker and old_ticker in pf.symbols and old_ticker != ticker:
                del pf.symbols[old_ticker]
            pf.symbols[ticker] = st
            changed.append({
                "ticker": ticker,
                "replaced_from": old_ticker if old_ticker != ticker else None,
                "shares": round(st.shares, 6),
                "avg_price": round(st.entry_price, 4),
                "cost_basis": round(st.cost_basis, 2),
                "reserve_cash": round(st.reserve_cash, 2),
                "cap_total": round(st.cap_total, 2),
                "H": round(st.H, 4),
                "first_date": st.entry_date,
                "old": old_snapshot,
            })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    backup_state(resolve(STATE_PATH))
    _rebuild_flows_from_symbols(pf)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("sync_trades", {"mode": mode, "rows": rows, "replace": repl, "changed": changed},
              "按券商导入同步当前持仓")
    payload = _state_payload(pf)
    payload["synced"] = changed
    payload["sync_diff"] = diff
    return payload


@app.post("/api/set_position")
def api_set_position(body: dict = Body(...)):
    """按真实聚合买入信息校准当前持仓。

    buy_date 用来重算自买入以来的 H；buy_price/shares 用来重算成本。
    sync_cap=True 时，把 cap_total/cum_injected 同步为 成本+当前储备，使回测面板跟随新本金权重。
    """
    ticker = str(body.get("ticker", "")).upper()
    buy_date = str(body.get("buy_date", "")).strip()
    sync_cap = bool(body.get("sync_cap", False))
    try:
        buy_price = float(body.get("buy_price", 0))
        shares = float(body.get("shares", 0))
    except (TypeError, ValueError):
        return JSONResponse({"error": "股数/买入价必须为数字"}, status_code=400)
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None or ticker not in pf.symbols:
        return JSONResponse({"error": "状态不存在或无此标的"}, status_code=400)
    if not buy_date:
        return JSONResponse({"error": "请填写买入日期"}, status_code=400)
    if buy_price <= 0 or shares <= 0:
        return JSONResponse({"error": "股数和买入价必须 > 0"}, status_code=400)
    try:
        h = _history_high_since(ticker, buy_date)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    st = pf.symbols[ticker]
    old = {"shares": st.shares, "cost_basis": st.cost_basis, "H": st.H,
           "cap_total": st.cap_total, "cum_injected": st.cum_injected}
    st.shares = shares
    st.cost_basis = shares * buy_price
    st.H = h
    st.entry_date = buy_date[:10]
    st.entry_price = buy_price
    if not st.fires:
        st.reserve_budget = st.reserve_cash
    if sync_cap:
        st.cum_injected = st.cost_basis + st.reserve_cash + st.pending_core_cash
        st.cap_total = st.cum_injected

    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("set_position",
              {"ticker": ticker, "buy_date": st.entry_date, "buy_price": buy_price,
               "shares": shares, "sync_cap": sync_cap, "old": old,
               "new": {"cost_basis": round(st.cost_basis, 2), "H": round(st.H, 4),
                       "cap_total": round(st.cap_total, 2),
                       "cum_injected": round(st.cum_injected, 2)}},
              "前端校准当前持仓")
    return _state_payload(pf)


@app.post("/api/set_cost")
def api_set_cost(body: dict = Body(...)):
    """修正某标的的成本：cost_basis = 当前股数 × 真实平均成本价。
    成本仅影响「盈亏」展示，不参与任何棘轮/防御层信号——纯显示修正，安全。"""
    ticker = str(body.get("ticker", "")).upper()
    avg_price = float(body.get("avg_price", 0))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None or ticker not in pf.symbols:
        return JSONResponse({"error": "状态不存在或无此标的"}, status_code=400)
    if avg_price <= 0:
        return JSONResponse({"error": "平均成本价必须 > 0"}, status_code=400)
    st = pf.symbols[ticker]
    old_cost = st.cost_basis
    st.cost_basis = st.shares * avg_price
    st.entry_price = avg_price
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("set_cost", {"ticker": ticker, "avg_price": avg_price,
                           "old_cost": round(old_cost, 2), "new_cost": round(st.cost_basis, 2)},
              "前端修正成本")
    return _state_payload(pf)


def main():
    import argparse
    import os
    import uvicorn
    ap = argparse.ArgumentParser(description="us_ratchet 服务")
    ap.add_argument("--host", default=os.environ.get("US_RATCHET_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("US_RATCHET_PORT", "8010")))
    args = ap.parse_args()
    print(f"\n>>> 打开浏览器访问 http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
