"""盘中报价抓取。

日线数据用于回测和 H 的收盘更新；这里的 quote 只用于前端盘中估值、今日建议触发
和防御层预览。报价源不可用时，上层应回退到日线最后收盘价。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from data import cn_source


@dataclass
class Quote:
    ticker: str
    price: float
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    change: float | None = None
    change_pct: float | None = None
    quote_time: str = ""
    market_time: str = ""
    source: str = "sina_quote"
    name: str = ""


def _to_float(raw, default=None):
    try:
        if raw in (None, "", "-", "--"):
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def fetch_sina_quotes(tickers: Iterable[str]) -> dict[str, Quote]:
    """批量抓新浪美股盘口。

    返回字段索引基于 hq.sinajs.cn 的 gb_* 美股 quote：
      1 最新价，2 涨跌幅%，3 北京时间戳，4 涨跌额，5/6/7 开高低，10 成交量，
      25 美东市场时间文本，26 昨收。
    """
    symbols = []
    ticker_by_symbol = {}
    for ticker in tickers:
        tk = str(ticker).upper().strip()
        if not tk:
            continue
        symbol = "gb_" + tk.lower().replace(".", "$")
        symbols.append(symbol)
        ticker_by_symbol[symbol] = tk
    if not symbols:
        return {}

    url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
    content = cn_source._http_get(url, timeout=8, retries=1,
                                  referer="https://finance.sina.com.cn/")
    if not content:
        return {}

    out: dict[str, Quote] = {}
    for line in content.splitlines():
        m = re.match(r'var hq_str_(?P<sym>gb_[^=]+)="(?P<body>.*)";', line.strip())
        if not m:
            continue
        symbol = m.group("sym")
        ticker = ticker_by_symbol.get(symbol)
        if not ticker:
            continue
        parts = m.group("body").split(",")
        if len(parts) < 2:
            continue
        price = _to_float(parts[1])
        if price is None or price <= 0:
            continue
        out[ticker] = Quote(
            ticker=ticker,
            name=parts[0] if len(parts) > 0 else "",
            price=price,
            change_pct=_to_float(parts[2] if len(parts) > 2 else None),
            quote_time=parts[3] if len(parts) > 3 else "",
            change=_to_float(parts[4] if len(parts) > 4 else None),
            open=_to_float(parts[5] if len(parts) > 5 else None),
            high=_to_float(parts[6] if len(parts) > 6 else None),
            low=_to_float(parts[7] if len(parts) > 7 else None),
            volume=_to_float(parts[10] if len(parts) > 10 else None),
            market_time=parts[25] if len(parts) > 25 else "",
            previous_close=_to_float(parts[26] if len(parts) > 26 else None),
        )
    return out
