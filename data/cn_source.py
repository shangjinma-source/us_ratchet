# -*- coding: utf-8 -*-
"""国内美股数据源原语（移植自 us_grid 的 providers/core.py，回测取数专用）。

设计沿用 us_grid 已在生产验证的结论：
  1. 用东财 / 新浪，不依赖 yahoo（限流严重）。
  2. 强制直连（这两个是国内源，走代理反而会断）——build_opener(ProxyHandler({}))。
  3. 历史K线主源用东财 push2his + fqt=1 前复权（splits/分红已平滑，回测必需）；
     新浪 getDailyK 为备援，但**不复权**，跨多年会有拆股跳变 → 由复权校验标红。
  4. secid 自动探测 105/106/107 市场前缀 + 缓存。

只暴露回测要的历史抓取；实盘实时报价 / 时段判断等留到第 4 步再从 us_grid 移植。
"""
from __future__ import annotations

import gzip
import io
import json
import threading
import time
from typing import List, Optional
from urllib.request import urlopen, Request, build_opener, ProxyHandler

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

_US_MARKETS = ["105", "106", "107"]   # 105=纳斯达克 106=纽交所 107=AMEX

# 预置常见标的，减少探测请求（探测接口也会被限流）
_secid_cache = {
    "NVDA": "105.NVDA", "AMD": "105.AMD", "MSFT": "105.MSFT", "AAPL": "105.AAPL",
    "AVGO": "105.AVGO", "GOOGL": "105.GOOGL", "GOOG": "105.GOOG", "AMZN": "105.AMZN",
    "META": "105.META", "TSLA": "105.TSLA", "MU": "105.MU", "INTC": "105.INTC",
    "TSM": "106.TSM",   # 台积电 ADR 纽交所
}

# 强制直连的 opener（国内源不走代理）
_direct_opener = build_opener(ProxyHandler({}))

# 请求节流：东财对密集请求会 RemoteDisconnected，强制请求间隔
_MIN_INTERVAL = 0.35
_throttle_lock = threading.Lock()
_last_req = [0.0]


def _throttle() -> None:
    with _throttle_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


def _http_get(url: str, timeout: int = 15, retries: int = 5,
              referer: Optional[str] = None) -> Optional[str]:
    """带指数退避重试的 HTTP GET，强制直连 + 请求节流。捕获所有网络异常
    （含 RemoteDisconnected / ConnectionReset / 超时 / 限流断连）。"""
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
    last_err = None
    for attempt in range(retries + 1):
        try:
            _throttle()
            req = Request(url, headers=headers)
            with _direct_opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                for enc in ("utf-8", "gbk"):   # 新浪 GBK，东财 UTF-8
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", errors="ignore")
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = 1.2 * (attempt + 1)   # 退避更长，治间歇性断连
                print(f"[cn_source] 请求抖动({type(e).__name__})，{wait:.1f}s 后重试 "
                      f"({attempt + 1}/{retries})")
                time.sleep(wait)
    print(f"[cn_source] HTTP 最终失败: {type(last_err).__name__}: {last_err}")
    return None


def resolve_secid(symbol: str) -> Optional[str]:
    """探测 symbol 所属交易所，返回完整 secid（如 '105.NVDA'）。带缓存。"""
    symbol = symbol.upper().strip()
    if symbol in _secid_cache:
        return _secid_cache[symbol]
    for market in _US_MARKETS:
        secid = f"{market}.{symbol}"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f58"
        content = _http_get(url, referer="https://quote.eastmoney.com/")
        if not content:
            continue
        try:
            d = json.loads(content).get("data")
            if d and d.get("f43") not in (None, "-", 0):
                _secid_cache[symbol] = secid
                return secid
        except Exception:
            continue
    print(f"[cn_source] 无法解析 {symbol} 的交易所（105/106/107 都未命中）")
    return None


def fetch_eastmoney_kline(symbol: str, fqt: int = 1,
                          beg: str = "0", end: str = "20500101") -> List[dict]:
    """东财 push2his 日K，带复权。返回升序 [{date,open,high,low,close,volume}]。
    fqt: 0=不复权 1=前复权 2=后复权。
    klines 字段顺序(f51..f56): 日期,开盘,收盘,最高,最低,成交量。"""
    secid = resolve_secid(symbol)
    if not secid:
        return []
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
           f"secid={secid}&klt=101&fqt={fqt}"
           "&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57"
           f"&beg={beg}&end={end}")
    content = _http_get(url, referer="https://quote.eastmoney.com/")
    if not content:
        return []
    try:
        data = json.loads(content).get("data")
    except Exception as e:
        print(f"[cn_source] 东财K线解析失败 {symbol}: {e}")
        return []
    if not data or not data.get("klines"):
        return []
    out = []
    for line in data["klines"]:
        p = line.split(",")
        if len(p) < 6:
            continue
        try:
            o, c, h, low = float(p[1]), float(p[2]), float(p[3]), float(p[4])
            v = float(p[5]) if p[5] not in ("", "-") else 0.0
        except (ValueError, IndexError):
            continue
        if c <= 0:
            continue
        out.append({"date": p[0], "open": o, "high": h, "low": low,
                    "close": c, "volume": v})
    return out   # 东财升序


def fetch_sina_daily(symbol: str) -> List[dict]:
    """新浪美股日K（**不复权**，备援用）。返回升序 [{date,open,high,low,close,volume}]。
    返回 JS 包裹的 JSON 数组，字段 d/o/h/l/c/v。"""
    symbol = symbol.upper().strip()
    url = ("https://stock.finance.sina.com.cn/usstock/api/jsonp.php/"
           f"var%20_={symbol}_day/US_MinKService.getDailyK?symbol={symbol}")
    content = _http_get(url, referer="https://finance.sina.com.cn/")
    if not content:
        return []
    start = content.find("(")
    end = content.rfind(")")
    if start == -1 or end <= start:
        print(f"[cn_source] 新浪返回格式异常 {symbol}")
        return []
    try:
        arr = json.loads(content[start + 1:end])
    except Exception as e:
        print(f"[cn_source] 新浪JSON解析失败 {symbol}: {e}")
        return []
    out = []
    for r in arr or []:
        d = r.get("d")
        c_raw = r.get("c")
        if not d or c_raw in (None, "", "0", "0.000"):
            continue
        try:
            c = float(c_raw)
            o = float(r.get("o") or c)
            h = float(r.get("h") or c)
            low = float(r.get("l") or c)
            v = float(r.get("v") or 0)
        except (ValueError, TypeError):
            continue
        if c <= 0:
            continue
        out.append({"date": d, "open": o, "high": h, "low": low,
                    "close": c, "volume": v})
    return out   # 新浪升序


# ============================================================
# 拆股自检测 + 前复权（东财历史在部分网络被掐死时，用新浪原始数据自复权）
# ============================================================

def match_split_event(r: float, tol: float = 0.06):
    """判断相邻日比值 r=close[t]/close[t-1] 是否像一次拆股。
    只认整数倍：N:1 正向拆股(r≈1/N，价格下跌) 或 1:N 反向拆股(r≈N，价格上涨)。
    刻意不认 1.5/0.67 这类分数比，避免把真实大涨大跌(如财报)误判为拆股。
    命中返回 {ratio: 实际比值, factor: 标准倍数, kind: 展示标签}，否则 None。"""
    if r <= 0:
        return None
    reverse_tol = min(tol, 0.02)  # 反向拆股更容易与真实暴涨混淆，显示/复权都更谨慎。
    candidates = []
    for n in range(2, 51):
        target = 1.0 / n
        rel_err = abs(r - target) / target
        if rel_err <= tol:                         # 正向拆股 N:1
            candidates.append((rel_err, {"ratio": r, "factor": n, "kind": f"{n}:1"}))
        rel_err = abs(r - n) / n
        if rel_err <= reverse_tol:                 # 反向拆股 1:N
            candidates.append((rel_err, {"ratio": r, "factor": n, "kind": f"1:{n}"}))
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[0])[1]


def match_split_ratio(r: float, tol: float = 0.06):
    event = match_split_event(r, tol)
    return None if event is None else event["ratio"]


def is_clean_split_jump(r: float, tol: float = 0.06) -> bool:
    return match_split_event(r, tol) is not None


def _display_split_kind(prev: dict, cur: dict, event: dict, tol: float) -> str:
    """用相邻两天 OHLC 的中位隐含倍数做展示标签，避免 close/close 受当日涨跌污染。"""
    forward = event["ratio"] < 1
    implied = []
    for key in ("open", "high", "low", "close"):
        a = float(prev.get(key) or 0)
        b = float(cur.get(key) or 0)
        if a <= 0 or b <= 0:
            continue
        implied.append(a / b if forward else b / a)
    if implied:
        vals = sorted(implied)
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        factor = int(round(median))
        if 2 <= factor <= 50 and abs(median - factor) <= tol * factor:
            return f"{factor}:1" if forward else f"1:{factor}"
    return event["kind"]


def split_adjust(rows: List[dict], tol: float = 0.06):
    """对升序原始日线做**前复权**：最近价不变，历史价按其后所有拆股比例缩放。
    返回 (adjusted_rows, detected_splits)；detected_splits=[(date, 约定倍数), ...]。
    rows 原地不改，返回新列表。"""
    if len(rows) < 2:
        return rows, []
    closes = [r["close"] for r in rows]
    split_at = {}   # index i(后复权首日) -> 实际比值
    detected = []
    for i in range(1, len(rows)):
        if closes[i - 1] <= 0:
            continue
        ratio = closes[i] / closes[i - 1]
        event = match_split_event(ratio, tol)
        if event is not None:
            split_at[i] = event["ratio"]
            detected.append((rows[i]["date"], _display_split_kind(rows[i - 1], rows[i], event, tol)))

    # 前复权累乘：从最新往回，经过一个拆股边界后，更早的 bar 都要 ×ratio
    adj = [1.0] * len(rows)
    cum = 1.0
    for i in range(len(rows) - 1, -1, -1):
        adj[i] = cum
        if i in split_at:
            cum *= split_at[i]

    out = []
    for i, r in enumerate(rows):
        a = adj[i]
        nr = dict(r)
        for k in ("open", "high", "low", "close"):
            nr[k] = round(r[k] * a, 6)
        nr["volume"] = (r["volume"] / a) if a else r["volume"]
        out.append(nr)
    return out, detected
