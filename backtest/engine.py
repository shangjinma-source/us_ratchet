"""回测驱动器：把共享信号引擎跑在历史日线上。

与实盘同源：每日调用 core.engine 的 update_high / process_pending / fire_tiers，
限价由 core.engine.compute_ladder 产出（实盘照挂用同一函数）。
所有基准领取与策略完全相同的注资时间表。
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import engine as eng
from core.config import Symbol
from core.state import CashFlow, Portfolio, SymbolState
from data.fetch import get_bars, DataError
from data.funds import get_fund_nav
from data.versioning import data_version_payload
from backtest import metrics as M
from backtest.benchmarks import run_benchmark

log = logging.getLogger("us_ratchet")


@dataclass
class BacktestResult:
    dates: pd.DatetimeIndex
    strat_equity: np.ndarray
    strat_invested: np.ndarray
    strat_reserve: np.ndarray
    flow_by_index: dict
    benchmarks: dict          # name -> equity curve
    portfolio: Portfolio
    summary: dict             # 指标汇总


def _align_prices(cfg, skip_missing: bool = False, strict: bool = False
                  ) -> tuple[pd.DatetimeIndex, dict, dict]:
    """抓取并对齐所有标的的收盘价/开盘价/最低价到共同交易日。

    skip_missing=True：取不到数据的标的跳过并列出（自定义篮子用，避免一只崩全盘）；
    strict=True：不跳过，直接抛错。两者都为默认 False 时行为与原先一致。
    注：仍取所有存活标的的交集窗口（dropna）——混入上市晚的标的会把窗口截短到它的起点
    （错峰起算留待 C6 修）。
    """
    from data import cn_source
    tol = getattr(cfg.data, "split_detect_tol", 0.06)
    closes, opens, lows = {}, {}, {}
    print("数据来源:")
    for s in cfg.symbols:
        try:
            df, meta = get_bars(s.ticker, cfg)
        except Exception as e:
            if skip_missing and not strict:
                print(f"  {s.ticker:<6} [跳过] 取不到数据：{e}")
                continue
            raise
        split_like = [(d, p) for d, p in meta.suspicious_jumps
                      if cn_source.is_clean_split_jump(1 + p, tol)]
        if split_like:
            flag = f"  ⚠ {len(split_like)} 处未复权拆股残留（数据可能失真，请核对）"
        elif meta.suspicious_jumps:
            flag = f"  （含 {len(meta.suspicious_jumps)} 处真实大波动，非拆股，正常）"
        else:
            flag = ""
        print(f"  {s.ticker:<6} [{meta.source}] {meta.start}..{meta.end} {meta.rows}行{flag}")
        closes[s.ticker] = df["Close"]
        opens[s.ticker] = df["Open"]
        lows[s.ticker] = df["Low"]
    print()
    if not closes:
        raise DataError("没有任何标的取到数据（请检查标的代码 / 数据源 / 网络）")
    close_df = pd.DataFrame(closes).dropna()
    dates = close_df.index
    px = {
        "close": {t: close_df[t].to_numpy() for t in close_df.columns},
        "open": {t: opens[t].reindex(dates).to_numpy() for t in closes},
        "low": {t: lows[t].reindex(dates).to_numpy() for t in closes},
    }
    return dates, px, closes


def _basket_to_symbols(basket, core_ratio: float) -> list:
    """把 [(ticker, cap), ...] 转成派生好 weight/core_target/reserve_quota 的 Symbol 列表。
    与 core.config.load_config 的推导口径一致（自定义篮子复用同一套权重/核心/储备推导）。"""
    syms = [Symbol(ticker=str(t).upper(), cap_total=float(cap)) for t, cap in basket]
    total = sum(s.cap_total for s in syms)
    if total <= 0:
        raise ValueError("篮子 cap_total 之和必须 > 0")
    for s in syms:
        s.weight = s.cap_total / total
        s.core_target = s.cap_total * core_ratio
        s.reserve_quota = s.cap_total * (1 - core_ratio)
    return syms


def run_basket_backtest(cfg, basket, monthly: float = 0.0,
                        skip_missing: bool = True, strict: bool = False
                        ) -> tuple[BacktestResult, list]:
    """用自定义篮子跑回测。C6a 起改用错峰起算 + 单位NAV 引擎（run_staggered_backtest）：
    每只标的从各自上市日并入、回撤按基金单位净值口径，避免共同窗口 dropna 的静默截断。

    basket: [(ticker, cap), ...]；返回 (BacktestResult, dropped_tickers)。
    （旧的共同窗口 + 含注资净值口径仍在 run_backtest 中，供非篮子默认跑法 / sweep / API 使用。）
    """
    c = copy.deepcopy(cfg)
    c.symbols = _basket_to_symbols(basket, c.portfolio.core_ratio)
    return run_staggered_backtest(c, monthly=monthly, skip_missing=skip_missing, strict=strict)


def run_basket_risk_sweep(cfg, basket, monthly: float = 0.0, *,
                          floors=(1.0, 0.75, 0.50, 0.25, 0.0),
                          ma_days: int = 200, band: float = 0.0, cost: float = 0.001,
                          skip_missing: bool = True, strict: bool = False):
    """用自定义篮子跑趋势风控扫描（C7）。symbol 注入与 run_basket_backtest 一致。"""
    c = copy.deepcopy(cfg)
    c.symbols = _basket_to_symbols(basket, c.portfolio.core_ratio)
    return run_risk_sweep(c, monthly=monthly, floors=floors, ma_days=ma_days,
                          band=band, cost=cost, skip_missing=skip_missing, strict=strict)


def run_basket_defensive_sweep(cfg, basket, monthly: float = 0.0, *,
                               weights=(0.0, 0.10, 0.20, 0.30, 0.40, 0.50),
                               safe_annual: float = 0.04, rebal_days: int = 21,
                               rebal_band: float = 0.0,
                               skip_missing: bool = True, strict: bool = False):
    """用自定义篮子跑防御层扫描（B）。symbol 注入与 run_basket_backtest 一致。"""
    c = copy.deepcopy(cfg)
    c.symbols = _basket_to_symbols(basket, c.portfolio.core_ratio)
    return run_defensive_sweep(c, monthly=monthly, weights=weights,
                               safe_annual=safe_annual, rebal_days=rebal_days,
                               rebal_band=rebal_band,
                               skip_missing=skip_missing, strict=strict)


# ===========================================================================
# C6a：错峰起算（各标的从自身上市日并入）+ 单位NAV 真实回撤（基金单位净值口径）
# 设计：把组合当成一只“基金”。每笔投入（标的上市日的初始 cap、按月注资）按当时
# 单位净值“申购份额”→ 注资不污染净值。回撤/Sharpe/Sortino 全算在单位净值序列上，
# 这是真实投资者体验，且在标的错峰上线导致美元净值一路爬升时仍有意义。
# 信号仍走 core.engine 同一套函数（process_pending/fire_tiers/apply_injection/update_high），
# 同源不变；这里只改“何时起算 + 如何计量”。
# ===========================================================================

def _fetch_series(cfg, skip_missing: bool, strict: bool) -> tuple[dict, list]:
    """逐只抓 Open/Low/Close（升序），返回 {ticker: DataFrame} + dropped。"""
    from data import cn_source
    tol = getattr(cfg.data, "split_detect_tol", 0.06)
    series, dropped = {}, []
    print("数据来源:")
    for s in cfg.symbols:
        try:
            df, meta = get_bars(s.ticker, cfg)
        except Exception as e:
            if skip_missing and not strict:
                print(f"  {s.ticker:<6} [跳过] 取不到数据：{e}")
                dropped.append(s.ticker)
                continue
            raise
        split_like = [(d, p) for d, p in meta.suspicious_jumps
                      if cn_source.is_clean_split_jump(1 + p, tol)]
        flag = f"  ⚠ {len(split_like)} 处未复权拆股残留（请核对）" if split_like else ""
        print(f"  {s.ticker:<6} [{meta.source}] {meta.start}..{meta.end} {meta.rows}行{flag}")
        series[s.ticker] = df[["Open", "High", "Low", "Close"]].copy()
    print()
    if not series:
        raise DataError("没有任何标的取到数据（请检查标的代码 / 数据源 / 网络）")
    return series, dropped


def _build_panels(series: dict, start_date, end_date):
    """对齐到 union 交易日网格。每只在其上市日前为 NaN，区间内 ffill（内部缺口补齐、
    末端之后按最后价 carry）。返回 grid, panels{t:{close,open,low}}, listing_i, last_i, coverage。"""
    all_idx = None
    for df in series.values():
        all_idx = df.index if all_idx is None else all_idx.union(df.index)
    grid = all_idx.sort_values()
    if start_date:
        grid = grid[grid >= pd.Timestamp(start_date)]
    if end_date:
        grid = grid[grid <= pd.Timestamp(end_date)]
    if len(grid) == 0:
        raise DataError("窗口内无任何交易日（检查 start/end）")
    gv = grid.values
    panels, listing_i, last_i, coverage = {}, {}, {}, []
    for t, df in series.items():
        d2 = df[(df.index >= grid[0]) & (df.index <= grid[-1])]
        if d2.empty:
            continue
        panels[t] = {
            "close": d2["Close"].reindex(grid).ffill().to_numpy(),
            "open": d2["Open"].reindex(grid).ffill().to_numpy(),
            "high": d2["High"].reindex(grid).ffill().to_numpy(),
            "low": d2["Low"].reindex(grid).ffill().to_numpy(),
        }
        li = int(np.searchsorted(gv, np.datetime64(d2.index[0])))
        la = int(np.searchsorted(gv, np.datetime64(d2.index[-1])))
        listing_i[t] = li
        last_i[t] = min(la, len(grid) - 1)
        coverage.append({"ticker": t, "start": str(d2.index[0].date()),
                         "end": str(d2.index[-1].date()), "rows": int(len(d2)),
                         "list_idx": li, "late": li > 0})
    return grid, panels, listing_i, last_i, coverage


def _symbol_total_value(st: SymbolState, price: float) -> float:
    return st.shares * price + st.reserve_cash + getattr(st, "pending_core_cash", 0.0)


def _run_strategy_fund(grid, panels, listing_i, last_i, caps, monthly, cfg):
    """棘轮策略基金：信号走 core.engine；按单位净值申购份额。返回 pf, nav, equity, invested, flows。"""
    n = len(grid)
    pf = Portfolio(symbols={}, flows=[])
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    invested = np.zeros(n)
    flows = []   # [(grid_index, amount)] 申购（标的上市 cap + 按月注资）
    list_on = {}
    for t, li in listing_i.items():
        list_on.setdefault(li, []).append(t)

    def fund_value(i):
        return sum(_symbol_total_value(st, panels[t]["close"][i])
                   for t, st in pf.symbols.items())

    for i in range(n):
        dstr = grid[i].strftime("%Y-%m-%d")
        tv_pre = fund_value(i)
        nav_b = (tv_pre / units) if units > 0 else 1.0
        # 1) 今日上市的标的：cap 作为一笔申购进场（按 nav_b 申购份额）
        for t in list_on.get(i, []):
            cap = caps[t]
            units += cap / nav_b
            pf.symbols[t] = eng.init_symbol(t, cap, panels[t]["close"][i], cfg)
            flows.append((i, cap))
        # 2) 按月注资（分到当日在场标的，按 cap 权重）；先决定 + 申购份额
        alive_held = [t for t in pf.symbols if listing_i[t] <= i <= last_i[t]]
        monthly_due = (monthly > 0 and i > 0 and i % 21 == 0 and bool(alive_held))
        if monthly_due:
            wsum = sum(caps[t] for t in alive_held)
            units += monthly / nav_b
            flows.append((i, monthly))
        # 3) 逐标的信号（镜像 run_backtest 顺序：process_pending → fire_tiers → 注资 → update_high）
        for t, st in pf.symbols.items():
            if not (listing_i[t] <= i <= last_i[t]):
                continue   # 数据结束/未上市：持仓按最后价计值，不再交易
            c = panels[t]["close"][i]
            o = panels[t]["open"][i]
            lo = panels[t]["low"][i]
            eng.process_pending(st, c, i)
            if i > listing_i[t]:
                eng.fire_tiers(st, o, lo, dstr, cfg)
            if monthly_due:
                eng.apply_injection(st, monthly * caps[t] / wsum, c, i, cfg)
            eng.update_high(st, c, cfg)
        # 4) 收盘计值
        tv = fund_value(i)
        inv = sum(st.shares * panels[t]["close"][i] for t, st in pf.symbols.items())
        equity[i] = tv
        invested[i] = inv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
    return pf, nav, equity, invested, flows


def _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly):
    """即时全仓·权重 基准基金：同样的申购现金流，100% 买入持有（无储备/无档位）。"""
    n = len(grid)
    shares = {}
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    list_on = {}
    for t, li in listing_i.items():
        list_on.setdefault(li, []).append(t)

    def val(i):
        return sum(sh * panels[t]["close"][i] for t, sh in shares.items())

    for i in range(n):
        tv_pre = val(i)
        nav_b = (tv_pre / units) if units > 0 else 1.0
        for t in list_on.get(i, []):
            cap = caps[t]
            units += cap / nav_b
            shares[t] = shares.get(t, 0.0) + cap / panels[t]["close"][i]
        alive = [t for t in shares if listing_i[t] <= i <= last_i[t]]
        if monthly > 0 and i > 0 and i % 21 == 0 and alive:
            wsum = sum(caps[t] for t in alive)
            units += monthly / nav_b
            for t in alive:
                shares[t] += (monthly * caps[t] / wsum) / panels[t]["close"][i]
        tv = val(i)
        equity[i] = tv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
    return nav, equity


def _run_single_asset_fund(grid, close, flows):
    """单一标的(外部基准，如 QQQ/SPY)买入持有基金：与篮子【完全相同】的申购现金流 flows，
    100% 投入该标的 → 在同一(回撤,收益)平面、同一资金时间表上可比。
    close = 已对齐到 grid 的收盘价数组(长度 n)。返回 (nav, equity)。"""
    n = len(grid)
    flow_by_i = {}
    for i, amt in flows:
        flow_by_i[i] = flow_by_i.get(i, 0.0) + amt
    shares = 0.0
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    for i in range(n):
        px = float(close[i]) if close[i] == close[i] else 0.0   # nan 守护
        val_pre = shares * px
        nav_b = (val_pre / units) if units > 0 else 1.0
        amt = flow_by_i.get(i, 0.0)
        if amt and px > 0:
            units += amt / nav_b
            shares += amt / px
        val = shares * px
        equity[i] = val
        nav[i] = (val / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
    return nav, equity


def _is_fund_code(ticker: str) -> bool:
    tk = str(ticker or "").strip()
    return len(tk) == 6 and tk.isdigit()


def _benchmark_label(ticker: str) -> str:
    tk = str(ticker or "").upper().strip()
    if tk == "QQQ":
        return "纳指100(QQQ)"
    if tk == "SPY":
        return "标普500(SPY)"
    if _is_fund_code(tk):
        return f"{tk}基金"
    return tk


def _fetch_benchmark_close(ticker, cfg, grid):
    """抓外部基准标的日线、对齐到 grid 收盘价数组(ffill/bfill)。返回 (close_arr, meta)。
    失败由调用方捕获(基准缺失不应让整份回测崩)。"""
    tk = str(ticker).upper().strip()
    if _is_fund_code(tk):
        df, meta = get_fund_nav(tk, cfg)
        s = df["Close"].copy()
        s.index = pd.to_datetime(s.index)
        # 基金成立前不 bfill，避免把未来第一天净值带回成立前窗口。
        aligned = s.reindex(pd.to_datetime(grid)).ffill()
        return aligned.to_numpy(dtype=float), meta
    df, meta = get_bars(tk, cfg)
    s = df["Close"].copy()
    s.index = pd.to_datetime(s.index)
    aligned = s.reindex(pd.to_datetime(grid)).ffill().bfill()
    return aligned.to_numpy(dtype=float), meta


def _first_valid_price_i(close) -> int | None:
    arr = np.asarray(close, dtype=float)
    ok = np.isfinite(arr) & (arr > 0)
    if not bool(ok.any()):
        return None
    return int(np.argmax(ok))


def _benchmark_run_inputs(close, flows):
    """Prepare benchmark close/flows without pre-inception look-ahead.

    If a benchmark starts after the strategy grid, earlier contributions are
    rolled into the benchmark's first available day.  Display callers can hide
    the pre-inception flat portion with the returned start index.
    """
    arr = np.asarray(close, dtype=float).copy()
    start_i = _first_valid_price_i(arr)
    if start_i is None:
        raise DataError("基准没有可用正价格")
    if start_i == 0:
        return arr, list(flows), start_i
    prior = sum(float(a) for i, a in flows if i < start_i)
    adjusted = []
    if prior > 0:
        adjusted.append((start_i, prior))
    adjusted.extend((i, a) for i, a in flows if i >= start_i)
    arr[:start_i] = arr[start_i]
    return arr, adjusted, start_i


def _drawdown_curve(nav) -> np.ndarray:
    arr = np.asarray(nav, dtype=float)
    peak = np.maximum.accumulate(arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, (peak - arr) / peak, 0.0)
    return np.nan_to_num(dd, nan=0.0, posinf=0.0, neginf=0.0)


def _rolling_mean_prev(arr, window: int) -> np.ndarray:
    """res[i] = mean(arr[i-window:i])，用于生成次日/当日盘前可见信号。"""
    x = np.asarray(arr, dtype=float)
    out = np.full(len(x), np.nan)
    if window <= 0 or len(x) <= window:
        return out
    csum = np.cumsum(np.insert(x, 0, 0.0))
    for i in range(window, len(x)):
        out[i] = (csum[i] - csum[i - window]) / window
    return out


def _atr_prev(high, low, close, window: int) -> np.ndarray:
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    tr = np.zeros(len(c))
    if len(c) == 0:
        return tr
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return _rolling_mean_prev(tr, window)


def _regime_rank(regime: str) -> int:
    return {"BULL": 0, "NEUTRAL": 1, "UNKNOWN": 1, "BEAR": 2}.get(regime, 1)


def _worse_regime(a: str, b: str | None) -> str:
    if not b:
        return a
    return a if _regime_rank(a) >= _regime_rank(b) else b


def _market_regime_at(price: float, ma20: float, ma50: float, ma200: float) -> str:
    vals = [price, ma20, ma50]
    if any(v is None or not np.isfinite(v) or v <= 0 for v in vals):
        return "UNKNOWN"
    if price >= ma20 and ma20 >= ma50 and (not np.isfinite(ma200) or ma50 >= ma200):
        return "BULL"
    if price < ma50 or (np.isfinite(ma200) and price < ma200):
        return "BEAR"
    return "NEUTRAL"


def _tactical_ab_specs(cfg):
    tc = getattr(cfg, "tactical_orders", None)
    if tc is None:
        return []
    return [
        {
            "mode": "current",
            "label": "当前配置 · 5/20+ATR",
            "operation": "牛市用5/20日与0.6ATR给浅回踩固定限价；震荡更深；熊市暂停。",
            "bull_anchor": "current", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": float(tc.bull_atr_mult), "neutral_atr": float(tc.neutral_atr_mult),
            "bear_atr": float(tc.bear_atr_mult),
            "bull_ratio": float(tc.bull_reserve_ratio),
            "neutral_ratio": float(tc.neutral_reserve_ratio),
            "bear_ratio": float(tc.bear_reserve_ratio),
            "min_discount": float(tc.min_discount_pct), "cooldown": 0,
        },
        {
            "mode": "current_cd10",
            "label": "当前配置 · 10日冷却",
            "operation": "限价算法不变，但同一标的战术成交后10个交易日不再重复挂浅层战术单。",
            "bull_anchor": "current", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": float(tc.bull_atr_mult), "neutral_atr": float(tc.neutral_atr_mult),
            "bear_atr": float(tc.bear_atr_mult),
            "bull_ratio": float(tc.bull_reserve_ratio),
            "neutral_ratio": float(tc.neutral_reserve_ratio),
            "bear_ratio": float(tc.bear_reserve_ratio),
            "min_discount": float(tc.min_discount_pct), "cooldown": 10,
        },
        {
            "mode": "ma20_patient",
            "label": "耐心20日 · 1ATR",
            "operation": "牛市也等20日线或1ATR回落；震荡等20日线下方1.4ATR；减少追涨成交。",
            "bull_anchor": "ma20_atr", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 1.0, "neutral_atr": 1.4, "bear_atr": 2.0,
            "bull_ratio": 0.16, "neutral_ratio": 0.08, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.005), "cooldown": 10,
        },
        {
            "mode": "ma50_heavy",
            "label": "耐心50日 · 重仓",
            "operation": "只在贴近50日线或深ATR回撤时动用更大储备比例，追求少买但买得更便宜。",
            "bull_anchor": "ma50_atr", "neutral_anchor": "ma50_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 1.2, "neutral_atr": 1.8, "bear_atr": 2.2,
            "bull_ratio": 0.30, "neutral_ratio": 0.18, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.008), "cooldown": 15,
        },
        {
            "mode": "ma5_fast",
            "label": "进攻5日 · 快速回踩",
            "operation": "更靠近5日线的小回撤即买，检验牛市追随是否只是过拟合。",
            "bull_anchor": "ma5_atr", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 0.5, "neutral_atr": 0.8, "bear_atr": 1.8,
            "bull_ratio": 0.22, "neutral_ratio": 0.10, "bear_ratio": 0.0,
            "min_discount": float(tc.min_discount_pct), "cooldown": 5,
        },
        {
            "mode": "prev_close_1pct",
            "label": "前收折价 · 1%",
            "operation": "不追 MA，只在前收下方约1%才挂浅层战术单；检验纯前收锚点是否改善成交质量。",
            "bull_anchor": "prev_close", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 0.0, "neutral_atr": 1.2, "bear_atr": 2.0,
            "bull_ratio": 0.16, "neutral_ratio": 0.08, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.010), "cooldown": 5,
        },
        {
            "mode": "open_gap",
            "label": "开盘锚点 · 缺口回补",
            "operation": "开盘后再定当日固定限价：牛市接受低开即买，震荡要求低于开盘且有ATR缓冲。",
            "bull_anchor": "open", "neutral_anchor": "open_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 0.0, "neutral_atr": 0.8, "bear_atr": 2.0,
            "bull_ratio": 0.18, "neutral_ratio": 0.08, "bear_ratio": 0.0,
            "min_discount": float(tc.min_discount_pct), "cooldown": 5,
        },
        {
            "mode": "quality_pullback",
            "label": "质量回踩 · 20日缓冲",
            "operation": "牛市不直接追5日线，要求接近20日线或0.8ATR回落；用更少成交换更高折价质量。",
            "bull_anchor": "ma20_atr", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 0.8, "neutral_atr": 1.5, "bear_atr": 2.0,
            "bull_ratio": 0.14, "neutral_ratio": 0.07, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.010), "cooldown": 15,
        },
        {
            "mode": "prev_close_2pct",
            "label": "前收折价 · 2%",
            "operation": "牛市也至少等前收下方2%才动用浅层战术单，用于测试减少追价后的成交质量。",
            "bull_anchor": "prev_close", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 0.0, "neutral_atr": 1.4, "bear_atr": 2.0,
            "bull_ratio": 0.14, "neutral_ratio": 0.07, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.020), "cooldown": 10,
        },
        {
            "mode": "ma50_light",
            "label": "耐心50日 · 轻仓",
            "operation": "仍等50日线/深ATR，但降低单次动用比例，检验少量高质量成交能否改善回撤拖累。",
            "bull_anchor": "ma50_atr", "neutral_anchor": "ma50_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 1.1, "neutral_atr": 1.7, "bear_atr": 2.2,
            "bull_ratio": 0.16, "neutral_ratio": 0.10, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.012), "cooldown": 20,
        },
        {
            "mode": "bull_ma5_neutral20_cd10",
            "label": "牛市5日 · 震荡20日",
            "operation": "牛市保持较快5日回踩，震荡切到20日/ATR缓冲，并加10日冷却，测试强趋势与震荡的折中。",
            "bull_anchor": "ma5_atr", "neutral_anchor": "ma20_atr", "bear_anchor": "ma50_atr",
            "bull_atr": 0.6, "neutral_atr": 1.2, "bear_atr": 2.0,
            "bull_ratio": 0.18, "neutral_ratio": 0.08, "bear_ratio": 0.0,
            "min_discount": max(float(tc.min_discount_pct), 0.006), "cooldown": 10,
        },
    ]


def _tactical_anchor(style: str, basis: float, ma5: float, ma20: float,
                     ma50: float, atr: float, atr_mult: float,
                     open_price: float | None = None) -> float | None:
    vals = [basis, atr]
    if any(v is None or not np.isfinite(v) or v <= 0 for v in vals):
        return None
    if style == "prev_close":
        return float(basis)
    if style in {"open", "open_atr"}:
        if open_price is None or not np.isfinite(open_price) or open_price <= 0:
            return None
        if style == "open":
            return float(open_price)
        return min(float(open_price), basis - atr_mult * atr)
    if style == "current":
        xs = [ma5, ma20, basis - atr_mult * atr]
        xs = [float(x) for x in xs if x is not None and np.isfinite(x) and x > 0]
        return max(xs) if xs else None
    if style == "ma5_atr":
        xs = [ma5, basis - atr_mult * atr]
        xs = [float(x) for x in xs if x is not None and np.isfinite(x) and x > 0]
        return max(xs) if xs else None
    if style == "ma20_atr":
        if ma20 is None or not np.isfinite(ma20) or ma20 <= 0:
            return None
        return min(float(ma20), basis - atr_mult * atr)
    if style == "ma50_atr":
        if ma50 is None or not np.isfinite(ma50) or ma50 <= 0:
            return None
        return min(float(ma50), basis - atr_mult * atr)
    return None


def _tactical_limit_for_spec(spec: dict, basis: float, ma5: float, ma20: float,
                             ma50: float, ma200: float, atr: float,
                             stock_regime: str, market_regime: str | None,
                             open_price: float | None = None):
    regime = _worse_regime(stock_regime, market_regime)
    if regime == "BULL":
        ratio = float(spec["bull_ratio"])
        anchor = _tactical_anchor(spec["bull_anchor"], basis, ma5, ma20, ma50, atr,
                                  float(spec["bull_atr"]), open_price)
    elif regime == "NEUTRAL":
        ratio = float(spec["neutral_ratio"])
        anchor = _tactical_anchor(spec["neutral_anchor"], basis, ma5, ma20, ma50, atr,
                                  float(spec["neutral_atr"]), open_price)
    else:
        ratio = float(spec["bear_ratio"])
        anchor = _tactical_anchor(spec["bear_anchor"], basis, ma5, ma20, ma50, atr,
                                  float(spec["bear_atr"]), open_price)
    if ratio <= 0 or anchor is None or not np.isfinite(anchor) or anchor <= 0:
        return None, 0.0, regime
    cap = basis * (1.0 - float(spec["min_discount"]))
    return min(float(anchor), float(cap)), ratio, regime


def _prepare_tactical_inputs(grid, panels, cfg):
    tc = getattr(cfg, "tactical_orders", None)
    out = {}
    if tc is None:
        return out, np.array(["UNKNOWN"] * len(grid), dtype=object)

    for t, p in panels.items():
        close = np.asarray(p["close"], dtype=float)
        out[t] = {
            "ma5": _rolling_mean_prev(close, int(tc.ma_short)),
            "ma20": _rolling_mean_prev(close, int(tc.ma_mid)),
            "ma50": _rolling_mean_prev(close, int(tc.ma_trend)),
            "ma200": _rolling_mean_prev(close, int(tc.ma_long)),
            "atr": _atr_prev(p["high"], p["low"], close, int(tc.atr_window)),
        }

    market_states = []
    if getattr(tc, "market_gate_enabled", False):
        for ticker in getattr(tc, "market_gate_tickers", ("QQQ", "SPY")):
            try:
                close, _ = _fetch_benchmark_close(ticker, cfg, grid)
            except Exception:
                continue
            market_states.append({
                "close": close,
                "ma20": _rolling_mean_prev(close, int(tc.ma_mid)),
                "ma50": _rolling_mean_prev(close, int(tc.ma_trend)),
                "ma200": _rolling_mean_prev(close, int(tc.ma_long)),
            })
    market_regime = np.array(["UNKNOWN"] * len(grid), dtype=object)
    for i in range(len(grid)):
        regimes = []
        for m in market_states:
            if i <= 0:
                continue
            regimes.append(_market_regime_at(float(m["close"][i - 1]),
                                             float(m["ma20"][i]),
                                             float(m["ma50"][i]),
                                             float(m["ma200"][i])))
        regimes = [r for r in regimes if r != "UNKNOWN"]
        if not regimes:
            market_regime[i] = "UNKNOWN"
        elif any(r == "BEAR" for r in regimes):
            market_regime[i] = "BEAR"
        elif all(r == "BULL" for r in regimes):
            market_regime[i] = "BULL"
        else:
            market_regime[i] = "NEUTRAL"
    return out, market_regime


def _run_strategy_fund_tactical(grid, panels, listing_i, last_i, caps, monthly, cfg,
                                spec: dict):
    """棘轮策略 + 战术限价 overlay。战术信号只用前一日可见数据，成交用当日 open/low。"""
    n = len(grid)
    pf = Portfolio(symbols={}, flows=[])
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    invested = np.zeros(n)
    flows = []
    tactical_inputs, market_regime = _prepare_tactical_inputs(grid, panels, cfg)
    fills = []
    skipped_by_deep = 0
    last_tactical_fill = {}
    list_on = {}
    for t, li in listing_i.items():
        list_on.setdefault(li, []).append(t)

    def fund_value(i):
        return sum(_symbol_total_value(st, panels[t]["close"][i])
                   for t, st in pf.symbols.items())

    for i in range(n):
        dstr = grid[i].strftime("%Y-%m-%d")
        tv_pre = fund_value(i)
        nav_b = (tv_pre / units) if units > 0 else 1.0
        for t in list_on.get(i, []):
            cap = caps[t]
            units += cap / nav_b
            pf.symbols[t] = eng.init_symbol(t, cap, panels[t]["close"][i], cfg)
            flows.append((i, cap))

        alive_held = [t for t in pf.symbols if listing_i[t] <= i <= last_i[t]]
        monthly_due = (monthly > 0 and i > 0 and i % 21 == 0 and bool(alive_held))
        if monthly_due:
            wsum = sum(caps[t] for t in alive_held)
            units += monthly / nav_b
            flows.append((i, monthly))

        for t, st in pf.symbols.items():
            if not (listing_i[t] <= i <= last_i[t]):
                continue
            c = float(panels[t]["close"][i])
            o = float(panels[t]["open"][i])
            lo = float(panels[t]["low"][i])
            eng.process_pending(st, c, i)

            deep_triggered = False
            if i > listing_i[t]:
                ladder_before = eng.compute_ladder(st, cfg)
                deep_triggered = any(lo <= e.limit_price for e in ladder_before)
                eng.fire_tiers(st, o, lo, dstr, cfg)

            if i > listing_i[t] and not deep_triggered and st.reserve_cash > 1e-9:
                cooldown = int(spec.get("cooldown", 0) or 0)
                last_i_fill = last_tactical_fill.get(t, -10**9)
                inp = tactical_inputs.get(t) or {}
                if i - last_i_fill >= cooldown and i > 0 and inp:
                    basis = float(panels[t]["close"][i - 1])
                    ma5 = float(inp["ma5"][i])
                    ma20 = float(inp["ma20"][i])
                    ma50 = float(inp["ma50"][i])
                    ma200 = float(inp["ma200"][i])
                    atr = float(inp["atr"][i])
                    stock_regime = _market_regime_at(basis, ma20, ma50, ma200)
                    mreg = str(market_regime[i])
                    mreg = None if mreg == "UNKNOWN" else mreg
                    limit, ratio, regime = _tactical_limit_for_spec(
                        spec, basis, ma5, ma20, ma50, ma200, atr, stock_regime, mreg,
                        open_price=o)
                    if limit is not None and lo <= limit:
                        fill_price = min(o, limit) if o > 0 else limit
                        amount = min(st.reserve_cash, st.reserve_cash * ratio)
                        if amount > 1e-9 and fill_price > 0:
                            shares = amount / fill_price
                            st.shares += shares
                            st.cost_basis += amount
                            st.reserve_cash -= amount
                            last_tactical_fill[t] = i
                            fwd_i = min(last_i[t], i + 20)
                            fwd_ret = (float(panels[t]["close"][fwd_i]) / fill_price - 1.0
                                       if fwd_i > i and fill_price > 0 else None)
                            fills.append({
                                "ticker": t, "date": dstr, "regime": regime,
                                "amount": float(amount), "shares": float(shares),
                                "limit": float(limit), "fill_price": float(fill_price),
                                "basis": float(basis),
                                "discount": float(fill_price / basis - 1.0) if basis > 0 else None,
                                "forward_20d": fwd_ret,
                            })
            elif deep_triggered:
                skipped_by_deep += 1

            if monthly_due:
                eng.apply_injection(st, monthly * caps[t] / wsum, c, i, cfg)
            eng.update_high(st, c, cfg)

        tv = fund_value(i)
        inv = sum(st.shares * panels[t]["close"][i] for t, st in pf.symbols.items())
        equity[i] = tv
        invested[i] = inv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)

    fwd = [x["forward_20d"] for x in fills
           if x.get("forward_20d") is not None and np.isfinite(x["forward_20d"])]
    discounts = [x["discount"] for x in fills
                 if x.get("discount") is not None and np.isfinite(x["discount"])]
    by_regime = {}
    for f in fills:
        r = f["regime"]
        by_regime[r] = by_regime.get(r, 0) + 1
    stats = {
        "fills": int(len(fills)),
        "fill_amount": float(sum(x["amount"] for x in fills)),
        "avg_fill_amount": float(np.mean([x["amount"] for x in fills])) if fills else 0.0,
        "avg_discount": float(np.mean(discounts)) if discounts else None,
        "median_discount": float(np.median(discounts)) if discounts else None,
        "fwd20_win_rate": float(sum(1 for x in fwd if x > 0) / len(fwd)) if fwd else None,
        "avg_fwd20": float(np.mean(fwd)) if fwd else None,
        "by_regime": by_regime,
        "skipped_by_deep": int(skipped_by_deep),
    }
    return pf, nav, equity, invested, flows, stats


# 信号源 = 即时全仓基准 NAV（干净价格指数，不含 overlay 自身动作，避免自我循环）。
# 跌破 MA → 按 floor 上限减仓到现金 + 暂停补跌；回到 MA 之上 → 用风控现金回补满仓。
# 这是回测原型：用于扫出“压多少回撤 vs 少赚多少”的甜点。参数定下后再移植进
# core.engine 做实盘同源（当前 overlay 仅在回测路径，未进 compute_ladder）。
# ===========================================================================
def _compute_risk_state(signal_nav, ma_days: int, band: float, warmup: int):
    """从基准NAV算趋势风控状态（带迟滞）：跌破 MA*(1-band)→risk_off；
    升破 MA*(1+band)→risk_on；其间保持。warmup 内强制 risk_on。返回 bool 数组。"""
    n = len(signal_nav)
    risk_off = np.zeros(n, dtype=bool)
    state_off = False
    for i in range(n):
        lo_i = max(0, i - ma_days + 1)
        ma = float(np.mean(signal_nav[lo_i:i + 1]))
        x = float(signal_nav[i])
        if i < warmup or ma <= 0:
            state_off = False
        elif state_off:
            if x > ma * (1.0 + band):
                state_off = False
        else:
            if x < ma * (1.0 - band):
                state_off = True
        risk_off[i] = state_off
    return risk_off


def _run_strategy_fund_rm(grid, panels, listing_i, last_i, caps, monthly, cfg,
                          risk_off, floor: float, cost: float):
    """棘轮策略 + 趋势风控 overlay。镜像 _run_strategy_fund，额外：risk_off 当日
    暂停补跌、并把敞口减到 floor*基金净值（卖出所得进 risk_cash）；risk_on 时用
    risk_cash 回补至满仓。返回 pf, nav, equity, invested, flows, turnover。"""
    n = len(grid)
    pf = Portfolio(symbols={}, flows=[])
    units = 0.0
    rc = [0.0]                       # 风控现金桶（减仓所得，独立于各标的 reserve_cash）
    turnover = 0.0
    nav = np.zeros(n); equity = np.zeros(n); invested = np.zeros(n)
    flows = []
    list_on = {}
    for t, li in listing_i.items():
        list_on.setdefault(li, []).append(t)

    def fund_value(i):
        return sum(_symbol_total_value(st, panels[t]["close"][i])
                   for t, st in pf.symbols.items()) + rc[0]

    for i in range(n):
        dstr = grid[i].strftime("%Y-%m-%d")
        tv_pre = fund_value(i)
        nav_b = (tv_pre / units) if units > 0 else 1.0
        for t in list_on.get(i, []):
            cap = caps[t]
            units += cap / nav_b
            pf.symbols[t] = eng.init_symbol(t, cap, panels[t]["close"][i], cfg)
            flows.append((i, cap))
        alive_held = [t for t in pf.symbols if listing_i[t] <= i <= last_i[t]]
        monthly_due = (monthly > 0 and i > 0 and i % 21 == 0 and bool(alive_held))
        if monthly_due:
            wsum = sum(caps[t] for t in alive_held)
            units += monthly / nav_b
            flows.append((i, monthly))
        off = bool(risk_off[i])
        for t, st in pf.symbols.items():
            if not (listing_i[t] <= i <= last_i[t]):
                continue
            c = panels[t]["close"][i]; o = panels[t]["open"][i]; lo = panels[t]["low"][i]
            eng.process_pending(st, c, i)
            if i > listing_i[t] and not off:        # 下跌趋势暂停补跌（趋势门优先）
                eng.fire_tiers(st, o, lo, dstr, cfg)
            if monthly_due:
                eng.apply_injection(st, monthly * caps[t] / wsum, c, i, cfg)
            eng.update_high(st, c, cfg)
        # ---- 风控 overlay：把敞口调到目标 ----
        inv = sum(st.shares * panels[t]["close"][i] for t, st in pf.symbols.items())
        fv = fund_value(i)
        target_inv = (floor if off else 1.0) * fv
        tol = fv * 1e-4
        if inv > target_inv + tol and inv > 0:               # 减仓 → 现金
            sell = inv - target_inv
            frac = sell / inv
            for t, st in pf.symbols.items():
                st.shares *= (1.0 - frac)
            rc[0] += sell * (1.0 - cost)
            turnover += sell
        elif (not off) and rc[0] > 0 and inv < target_inv - tol:   # 回补 ← 现金
            buy = min(target_inv - inv, rc[0])
            held = [t for t in pf.symbols if listing_i[t] <= i <= last_i[t]]
            if inv > 0:
                wts = {t: (st.shares * panels[t]["close"][i]) / inv
                       for t, st in pf.symbols.items()}
            else:
                ws = sum(caps[t] for t in held) or 1.0
                wts = {t: (caps[t] / ws if t in held else 0.0) for t in pf.symbols}
            for t, st in pf.symbols.items():
                w = wts.get(t, 0.0)
                if w > 0:
                    st.shares += (buy * w * (1.0 - cost)) / panels[t]["close"][i]
            rc[0] -= buy
            turnover += buy
        tv = fund_value(i)
        inv2 = sum(st.shares * panels[t]["close"][i] for t, st in pf.symbols.items())
        equity[i] = tv; invested[i] = inv2
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
    return pf, nav, equity, invested, flows, turnover


def _run_strategy_fund_gate(grid, panels, listing_i, last_i, caps, monthly, cfg,
                            risk_off, *, pause_tiers: bool = False,
                            pause_injection: bool = False,
                            pause_rearm: bool = False):
    """非卖出型趋势 gate：不降低已有仓位，只在 risk-off 时暂停指定执行位。

    当前用于验证最保守、最贴近实盘哲学的作用位：
    - pause_tiers=True：risk-off 当天不触发深跌档位买入，保留储备金。
    - pause_injection：risk-off 当天不买核心份额，新增本金留在该标的 reserve。
    - pause_rearm：risk-off 当天只抬高 H，不重装档位、不刷新 reserve_budget。
    """
    n = len(grid)
    pf = Portfolio(symbols={}, flows=[])
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    invested = np.zeros(n)
    flows = []
    skipped_tier_days = 0
    skipped_tier_count = 0
    skipped_tier_amount = 0.0
    skipped_injection_days = 0
    skipped_injection_amount = 0.0
    skipped_rearm_days = 0
    list_on = {}
    for t, li in listing_i.items():
        list_on.setdefault(li, []).append(t)

    def fund_value(i):
        return sum(_symbol_total_value(st, panels[t]["close"][i])
                   for t, st in pf.symbols.items())

    for i in range(n):
        dstr = grid[i].strftime("%Y-%m-%d")
        tv_pre = fund_value(i)
        nav_b = (tv_pre / units) if units > 0 else 1.0
        for t in list_on.get(i, []):
            cap = caps[t]
            units += cap / nav_b
            pf.symbols[t] = eng.init_symbol(t, cap, panels[t]["close"][i], cfg)
            flows.append((i, cap))

        alive_held = [t for t in pf.symbols if listing_i[t] <= i <= last_i[t]]
        monthly_due = (monthly > 0 and i > 0 and i % 21 == 0 and bool(alive_held))
        off = bool(risk_off[i])
        if monthly_due:
            wsum = sum(caps[t] for t in alive_held)
            units += monthly / nav_b
            flows.append((i, monthly))

        for t, st in pf.symbols.items():
            if not (listing_i[t] <= i <= last_i[t]):
                continue
            c = panels[t]["close"][i]
            o = panels[t]["open"][i]
            lo = panels[t]["low"][i]
            eng.process_pending(st, c, i)
            if i > listing_i[t]:
                if pause_tiers and off:
                    blocked = [x for x in eng.compute_ladder(st, cfg) if lo <= x.limit_price]
                    if blocked:
                        skipped_tier_days += 1
                        skipped_tier_count += len(blocked)
                        skipped_tier_amount += sum(float(x.amount) for x in blocked)
                else:
                    eng.fire_tiers(st, o, lo, dstr, cfg)
            if monthly_due:
                amt = monthly * caps[t] / wsum
                if pause_injection and off:
                    if not st.frozen:
                        st.cum_injected += amt
                        st.cap_total += amt
                        st.reserve_cash += amt
                        st.reserve_budget += amt
                        skipped_injection_days += 1
                        skipped_injection_amount += amt
                else:
                    eng.apply_injection(st, amt, c, i, cfg)
            if pause_rearm and off:
                eps = cfg.portfolio.rearm.new_high_epsilon_pct
                if c > st.H * (1 + eps):
                    skipped_rearm_days += 1
                    st.H = c
                elif c > st.H:
                    st.H = c
            else:
                eng.update_high(st, c, cfg)

        tv = fund_value(i)
        inv = sum(st.shares * panels[t]["close"][i] for t, st in pf.symbols.items())
        equity[i] = tv
        invested[i] = inv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)

    stats = {"skipped_tier_days": int(skipped_tier_days),
             "skipped_tier_count": int(skipped_tier_count),
             "skipped_tier_amount": float(skipped_tier_amount),
             "skipped_injection_days": int(skipped_injection_days),
             "skipped_injection_amount": float(skipped_injection_amount),
             "skipped_rearm_days": int(skipped_rearm_days),
             "frac_off": float(np.mean(risk_off)) if len(risk_off) else 0.0}
    return pf, nav, equity, invested, flows, stats


def run_risk_sweep(cfg, monthly: float = 0.0,
                   floors=(1.0, 0.75, 0.50, 0.25, 0.0),
                   ma_days: int = 200, band: float = 0.0, cost: float = 0.001,
                   warmup: int = 20, skip_missing: bool = True, strict: bool = False):
    """趋势风控扫描：固定 MA 门，扫 floor（下跌时保留的敞口）→ 回撤/收益权衡曲线。
    floor=1.0 = 基线（overlay 关闭，复用已验证 _run_strategy_fund）。
    返回 dict：rows=[(floor, metrics)...], bench=全仓基准, 以及信号统计。"""
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    b_nav, b_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    risk_off = _compute_risk_state(b_nav, ma_days, band, warmup)

    def metrics(navc, eqc, invc, flows, turnover):
        contributed = sum(a for _, a in flows)
        cf = [(grid[i].date(), -a) for i, a in flows]
        cf.append((grid[-1].date(), float(eqc[-1])))
        denom = np.where(eqc > 0, eqc, 1)
        ret = M.returns_from_equity(navc)
        return {"mult": float(eqc[-1] / contributed) if contributed else None,
                "xirr": M.xirr(cf), "maxdd": M.max_drawdown(navc),
                "sharpe": M.sharpe(ret), "sortino": M.sortino(ret),
                "avg_invested": float(np.mean(invc / denom)),
                "turnover_x": (turnover / contributed) if contributed else None}

    rows = []
    for fl in floors:
        if fl >= 1.0:
            pf, s_nav, s_eq, s_inv, flows = _run_strategy_fund(
                grid, panels, listing_i, last_i, caps, monthly, cfg)
            turn = 0.0
        else:
            pf, s_nav, s_eq, s_inv, flows, turn = _run_strategy_fund_rm(
                grid, panels, listing_i, last_i, caps, monthly, cfg, risk_off, fl, cost)
        rows.append((fl, metrics(s_nav, s_eq, s_inv, flows, turn)))

    contributed = sum(a for _, a in flows)   # flows 各 floor 相同（减仓不改申购）
    cf = [(grid[i].date(), -a) for i, a in flows]; cf.append((grid[-1].date(), float(b_eq[-1])))
    bench = {"mult": float(b_eq[-1] / contributed) if contributed else None,
             "xirr": M.xirr(cf), "maxdd": M.max_drawdown(b_nav)}
    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "rows": rows, "bench": bench,
            "ma_days": ma_days, "band": band, "cost": cost,
            "days_off": int(risk_off.sum()), "frac_off": float(risk_off.mean())}


def run_trend_gate_ab(cfg, monthly: float = 0.0, *,
                      ma_days=(5, 20, 50, 200),
                      floors=(0.75, 0.50, 0.0),
                      band: float = 0.0,
                      cost: float = 0.001,
                      warmup: int | None = None,
                      rolling_min_years: float = 5.0,
                      rolling_step_months: int = 3,
                      safe_weight: float | None = None,
                      safe_annual: float = 0.04,
                      rebal_days: int = 21,
                      rebal_band: float = 0.0,
                      skip_missing: bool = True,
                      strict: bool = False):
    """趋势门控 A/B：MA5/20/50/200 × risk-off 最低仓位，与长期持有和当前策略同口径比较。

    这是研究面板，不直接改变实盘建议。信号源使用“当前篮子长期持有不动”的 NAV，
    门控动作叠加在棘轮策略风险腿上；所有方案共用同一申购现金流。
    """
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    hold_nav, hold_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    _, risk_nav, risk_eq, risk_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    contributed = sum(a for _, a in flows)

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    def metric_block(navc, eqc, invested_curve=None, turnover=0.0, n_rebal=0):
        cf = [(grid[i].date(), -a) for i, a in flows]
        cf.append((grid[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        out = {"final": float(eqc[-1]),
               "mult": float(eqc[-1] / contributed) if contributed else None,
               "xirr": M.xirr(cf),
               "maxdd": M.max_drawdown(navc),
               "sharpe": M.sharpe(ret),
               "sortino": M.sortino(ret),
               "turnover_x": (turnover / contributed) if contributed else None,
               "n_rebal": int(n_rebal)}
        if invested_curve is not None:
            denom = np.where(eqc > 0, eqc, 1)
            out["avg_invested"] = float(np.mean(invested_curve / denom))
        return out

    def metric_for(grid2, navc, eqc, flows2, contributed2,
                   invested_curve=None, turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows2]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        out = {"final": float(eqc[-1]),
               "mult": float(eqc[-1] / contributed2) if contributed2 else None,
               "xirr": M.xirr(cf),
               "maxdd": M.max_drawdown(navc),
               "sharpe": M.sharpe(ret),
               "sortino": M.sortino(ret),
               "turnover_x": (turnover / contributed2) if contributed2 else None,
               "n_rebal": int(n_rebal)}
        if invested_curve is not None:
            denom = np.where(eqc > 0, eqc, 1)
            out["avg_invested"] = float(np.mean(invested_curve / denom))
        return out

    baselines = {
        "长期持有不动": metric_block(hold_nav, hold_eq),
        "纯棘轮": metric_block(risk_nav, risk_eq, risk_inv),
    }
    if safe_weight > 0:
        def_nav, def_eq, _, turn, nrb = _run_defensive_fund(
            grid, risk_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
        baselines[f"策略+防御层(W={safe_weight:.0%})"] = metric_block(def_nav, def_eq, None, turn, nrb)

    hold = baselines["长期持有不动"]
    risk = baselines["纯棘轮"]
    execution_specs = [
        {"mode": "pause_tiers", "suffix": "暂停深跌档位", "action_label": "拦截档位",
         "stat_key": "skipped_tier_count", "amount_key": "skipped_tier_amount",
         "kwargs": {"pause_tiers": True, "pause_injection": False, "pause_rearm": False}},
        {"mode": "pause_injection", "suffix": "暂停核心注资", "action_label": "拦截注资",
         "stat_key": "skipped_injection_days", "amount_key": "skipped_injection_amount",
         "kwargs": {"pause_tiers": False, "pause_injection": True, "pause_rearm": False}},
        {"mode": "pause_rearm", "suffix": "暂停re-arm", "action_label": "拦截re-arm",
         "stat_key": "skipped_rearm_days", "amount_key": None,
         "kwargs": {"pause_tiers": False, "pause_injection": False, "pause_rearm": True}},
    ]

    rows = []
    execution_rows = []
    for ma in ma_days:
        ma_i = int(ma)
        warm = int(warmup) if warmup is not None else ma_i
        risk_off = _compute_risk_state(hold_nav, ma_i, band, warm)
        for floor in floors:
            fl = float(floor)
            if fl >= 1.0:
                continue
            _, nav, eq, inv, _, turnover = _run_strategy_fund_rm(
                grid, panels, listing_i, last_i, caps, monthly, cfg,
                risk_off, fl, cost)
            m = metric_block(nav, eq, inv, turnover)
            xirr_vs_hold = (m["xirr"] - hold["xirr"]
                            if m["xirr"] is not None and hold["xirr"] is not None else None)
            xirr_vs_risk = (m["xirr"] - risk["xirr"]
                            if m["xirr"] is not None and risk["xirr"] is not None else None)
            dd_relief_vs_hold = (hold["maxdd"] - m["maxdd"]
                                 if hold["maxdd"] is not None and m["maxdd"] is not None else None)
            dd_relief_vs_risk = (risk["maxdd"] - m["maxdd"]
                                 if risk["maxdd"] is not None and m["maxdd"] is not None else None)
            if (xirr_vs_hold is not None and xirr_vs_hold >= 0
                    and dd_relief_vs_hold is not None and dd_relief_vs_hold > 0):
                verdict = "候选：收益不输长期持有且回撤更浅"
            elif dd_relief_vs_hold is not None and dd_relief_vs_hold > 0:
                verdict = "防守有效但收益落后"
            else:
                verdict = "不优于长期持有"
            rows.append({
                "ma_days": ma_i,
                "floor": fl,
                "label": f"MA{ma_i} · 最低仓位 {fl:.0%}",
                "metrics": m,
                "days_off": int(risk_off.sum()),
                "frac_off": float(risk_off.mean()),
                "warmup": warm,
                "xirr_vs_hold": xirr_vs_hold,
                "xirr_vs_risk": xirr_vs_risk,
                "dd_relief_vs_hold": dd_relief_vs_hold,
                "dd_relief_vs_risk": dd_relief_vs_risk,
                "verdict": verdict,
            })
        for spec in execution_specs:
            _, nav_g, eq_g, inv_g, _, gate_stats = _run_strategy_fund_gate(
                grid, panels, listing_i, last_i, caps, monthly, cfg, risk_off,
                **spec["kwargs"])
            mg = metric_block(nav_g, eq_g, inv_g)
            xirr_vs_hold = (mg["xirr"] - hold["xirr"]
                            if mg["xirr"] is not None and hold["xirr"] is not None else None)
            xirr_vs_risk = (mg["xirr"] - risk["xirr"]
                            if mg["xirr"] is not None and risk["xirr"] is not None else None)
            dd_relief_vs_hold = (hold["maxdd"] - mg["maxdd"]
                                 if hold["maxdd"] is not None and mg["maxdd"] is not None else None)
            dd_relief_vs_risk = (risk["maxdd"] - mg["maxdd"]
                                 if risk["maxdd"] is not None and mg["maxdd"] is not None else None)
            if (xirr_vs_risk is not None and xirr_vs_risk >= 0
                    and dd_relief_vs_risk is not None and dd_relief_vs_risk > 0):
                verdict = "执行候选：不卖出且优于纯棘轮"
            elif dd_relief_vs_risk is not None and dd_relief_vs_risk > 0:
                verdict = "保守有效但收益成本"
            else:
                verdict = "不优于纯棘轮"
            amount_key = spec.get("amount_key")
            execution_rows.append({
                "ma_days": ma_i,
                "mode": spec["mode"],
                "label": f"MA{ma_i} · {spec['suffix']}",
                "action_label": spec["action_label"],
                "action_count": int(gate_stats.get(spec["stat_key"], 0)),
                "action_amount": (float(gate_stats.get(amount_key, 0.0)) if amount_key else None),
                "metrics": mg,
                "days_off": int(risk_off.sum()),
                "frac_off": float(risk_off.mean()),
                "warmup": warm,
                "gate_stats": gate_stats,
                "xirr_vs_hold": xirr_vs_hold,
                "xirr_vs_risk": xirr_vs_risk,
                "dd_relief_vs_hold": dd_relief_vs_hold,
                "dd_relief_vs_risk": dd_relief_vs_risk,
                "verdict": verdict,
            })

    valid = [r for r in rows if r["metrics"]["xirr"] is not None]
    best_xirr = max(valid, key=lambda r: r["metrics"]["xirr"]) if valid else None
    best_dd = min(valid, key=lambda r: r["metrics"]["maxdd"]) if valid else None
    candidates = [r for r in valid if r["xirr_vs_hold"] is not None
                  and r["xirr_vs_hold"] >= 0
                  and r["dd_relief_vs_hold"] is not None
                  and r["dd_relief_vs_hold"] > 0]
    execution_candidates = [r for r in execution_rows if r["xirr_vs_risk"] is not None
                            and r["xirr_vs_risk"] >= 0
                            and r["dd_relief_vs_risk"] is not None
                            and r["dd_relief_vs_risk"] > 0]

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def rule_rollup(samples, x_field="xirr_vs_hold", dd_field="dd_relief_vs_hold"):
        xs = [s.get(x_field) for s in samples]
        dds = [s.get(dd_field) for s in samples]
        turns = [s["turnover_x"] for s in samples]
        cand = [s["candidate"] for s in samples]
        valid_x = [v for v in xs if v is not None and np.isfinite(v)]
        valid_dd = [v for v in dds if v is not None and np.isfinite(v)]
        windows = len(samples)
        win_rate = (sum(1 for v in valid_x if v >= 0) / len(valid_x)) if valid_x else None
        dd_win_rate = (sum(1 for v in valid_dd if v > 0) / len(valid_dd)) if valid_dd else None
        candidate_rate = (sum(1 for v in cand if v) / windows) if windows else None
        x50 = q(xs, 0.50)
        dd50 = q(dds, 0.50)
        if candidate_rate is not None and candidate_rate >= 0.50:
            verdict = "滚动候选"
        elif dd_win_rate is not None and dd_win_rate >= 0.60:
            verdict = "稳健防守但收益成本"
        else:
            verdict = "滚动不稳健"
        return {"windows": windows,
                "win_rate": win_rate,
                "dd_win_rate": dd_win_rate,
                "candidate_rate": candidate_rate,
                "xirr_vs_hold": {"p10": q(xs, 0.10), "p50": x50, "p90": q(xs, 0.90)},
                "dd_relief_vs_hold": {"p10": q(dds, 0.10), "p50": dd50, "p90": q(dds, 0.90)},
                "turnover_x": {"p50": q(turns, 0.50), "p90": q(turns, 0.90)},
                "verdict": verdict}

    rolling_samples = {r["label"]: [] for r in rows}
    execution_samples = {r["label"]: [] for r in execution_rows}
    min_len = max(2, int(float(rolling_min_years) * 252))
    starts = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            starts.append(i)
    step_months = max(1, int(rolling_step_months))
    starts = starts[::step_months]

    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue
        panels2 = {
            t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
            for t in alive
        }
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}

        hold_nav2, hold_eq2 = _run_fullinvest_fund(grid2, panels2, listing2, last2, caps2, monthly)
        _, risk_nav2, risk_eq2, risk_inv2, flows2 = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed2 = sum(a for _, a in flows2)
        if contributed2 <= 0:
            continue
        hold2 = metric_for(grid2, hold_nav2, hold_eq2, flows2, contributed2)
        risk2 = metric_for(grid2, risk_nav2, risk_eq2, flows2, contributed2, risk_inv2)
        for ma in ma_days:
            ma_i = int(ma)
            warm = int(warmup) if warmup is not None else ma_i
            risk_off2 = _compute_risk_state(hold_nav2, ma_i, band, warm)
            for floor in floors:
                fl = float(floor)
                if fl >= 1.0:
                    continue
                _, nav2, eq2, inv2, _, turn2 = _run_strategy_fund_rm(
                    grid2, panels2, listing2, last2, caps2, monthly, cfg,
                    risk_off2, fl, cost)
                m2 = metric_for(grid2, nav2, eq2, flows2, contributed2, inv2, turn2)
                xdiff = (m2["xirr"] - hold2["xirr"]
                         if m2["xirr"] is not None and hold2["xirr"] is not None else None)
                ddiff = (hold2["maxdd"] - m2["maxdd"]
                         if hold2["maxdd"] is not None and m2["maxdd"] is not None else None)
                label = f"MA{ma_i} · 最低仓位 {fl:.0%}"
                rolling_samples[label].append({
                    "start": grid2[0].strftime("%Y-%m-%d"),
                    "end": grid2[-1].strftime("%Y-%m-%d"),
                    "years": float((grid2[-1] - grid2[0]).days / 365.25),
                    "xirr_vs_hold": xdiff,
                    "dd_relief_vs_hold": ddiff,
                    "xirr": m2["xirr"],
                    "maxdd": m2["maxdd"],
                    "turnover_x": m2["turnover_x"],
                    "candidate": bool(xdiff is not None and xdiff >= 0
                                      and ddiff is not None and ddiff > 0),
                })
            for spec in execution_specs:
                _, nav_g2, eq_g2, inv_g2, _, stats_g2 = _run_strategy_fund_gate(
                    grid2, panels2, listing2, last2, caps2, monthly, cfg, risk_off2,
                    **spec["kwargs"])
                mg2 = metric_for(grid2, nav_g2, eq_g2, flows2, contributed2, inv_g2)
                xdiff_risk = (mg2["xirr"] - risk2["xirr"]
                              if mg2["xirr"] is not None and risk2["xirr"] is not None else None)
                ddiff_risk = (risk2["maxdd"] - mg2["maxdd"]
                              if risk2["maxdd"] is not None and mg2["maxdd"] is not None else None)
                xdiff_hold = (mg2["xirr"] - hold2["xirr"]
                              if mg2["xirr"] is not None and hold2["xirr"] is not None else None)
                ddiff_hold = (hold2["maxdd"] - mg2["maxdd"]
                              if hold2["maxdd"] is not None and mg2["maxdd"] is not None else None)
                label_g = f"MA{ma_i} · {spec['suffix']}"
                execution_samples[label_g].append({
                    "start": grid2[0].strftime("%Y-%m-%d"),
                    "end": grid2[-1].strftime("%Y-%m-%d"),
                    "years": float((grid2[-1] - grid2[0]).days / 365.25),
                    "xirr_vs_hold": xdiff_hold,
                    "dd_relief_vs_hold": ddiff_hold,
                    "xirr_vs_risk": xdiff_risk,
                    "dd_relief_vs_risk": ddiff_risk,
                    "xirr": mg2["xirr"],
                    "maxdd": mg2["maxdd"],
                    "turnover_x": mg2["turnover_x"],
                    "candidate": bool(xdiff_risk is not None and xdiff_risk >= 0
                                      and ddiff_risk is not None and ddiff_risk > 0),
                    "gate_stats": stats_g2,
                })

    rolling = {label: rule_rollup(samples) for label, samples in rolling_samples.items()}
    for r in rows:
        r["rolling"] = rolling.get(r["label"])
    rolling_candidates = [label for label, item in rolling.items()
                          if item and item.get("candidate_rate") is not None
                          and item["candidate_rate"] >= 0.50]
    execution_rolling = {
        label: rule_rollup(samples, "xirr_vs_risk", "dd_relief_vs_risk")
        for label, samples in execution_samples.items()
    }
    for r in execution_rows:
        roll = execution_rolling.get(r["label"])
        r["rolling"] = roll
        if roll:
            # For non-selling execution gates, candidate_rate is already based on vs pure ratchet samples.
            r["rolling"]["benchmark"] = "纯棘轮"
    execution_rolling_candidates = [
        label for label, item in execution_rolling.items()
        if item and item.get("candidate_rate") is not None and item["candidate_rate"] >= 0.50
    ]

    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "baselines": baselines, "rows": rows,
            "execution_rows": execution_rows,
            "summary": {
                "best_xirr": best_xirr["label"] if best_xirr else None,
                "best_drawdown": best_dd["label"] if best_dd else None,
                "candidate_count": len(candidates),
                "execution_candidate_count": len(execution_candidates),
                "rolling_candidate_count": len(rolling_candidates),
                "execution_rolling_candidate_count": len(execution_rolling_candidates),
                "rolling_windows": len(starts),
                "rolling_min_years": float(rolling_min_years),
                "rolling_step_months": step_months,
                "ma_days": [int(x) for x in ma_days],
                "floors": [float(x) for x in floors],
                "band": float(band), "cost": float(cost),
                "signal": "当前篮子长期持有NAV跌破自身MA时进入risk-off",
                "status": "research_only",
            }}


# ===========================================================================
# 篮子级崩盘 sleeve（研究层）——独立现金袖珍仓，只在市场/篮子级严重回撤时部署。
#
# 与永久防御层不同：这里不做周期再平衡，也不卖出风险腿；每笔外部投入按 sleeve_weight
# 留出一小块 crash cash，平时计固定收益，只有 signal_dd 达到 20/30/40% 这类极端阈值时
# 分批买入风险腿。这样可以验证“单独记账防双花”是否真有价值，而不是把个股储备金重复使用。
# ===========================================================================
def _run_crash_sleeve_fund(grid, risk_nav, flows, signal_dd, *,
                           sleeve_weight: float,
                           thresholds=(0.20, 0.30, 0.40),
                           deploy_ratios=(0.30, 0.40, 1.00),
                           safe_annual: float = 0.04,
                           rearm_dd: float = 0.01):
    """风险腿 + 独立 crash cash sleeve。返回 nav/equity/stats。

    外部现金流不变；sleeve_weight 只决定每笔申购内部留多少现金。触发时 cash -> risk，
    不产生外部现金流，也不消耗各标的 reserve_cash。
    """
    n = len(grid)
    rr = np.zeros(n)
    for i in range(1, n):
        prev = risk_nav[i - 1]
        rr[i] = (risk_nav[i] / prev - 1.0) if prev > 0 else 0.0
    rs = safe_annual / 252.0
    flow_by_i = {}
    for i, amt in flows:
        flow_by_i[i] = flow_by_i.get(i, 0.0) + amt

    thrs = [float(x) for x in thresholds]
    ratios = [float(x) for x in deploy_ratios]
    if len(ratios) < len(thrs):
        ratios = ratios + [ratios[-1] if ratios else 1.0] * (len(thrs) - len(ratios))
    armed = [True] * len(thrs)

    risk_val = 0.0
    cash_val = 0.0
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    cash_weight_sum = 0.0
    deployed = 0.0
    deploy_count = 0
    rearm_count = 0
    first_trigger = None
    trigger_hits = {f"{thr:.0%}": 0 for thr in thrs}

    for i in range(n):
        if i > 0:
            risk_val *= (1.0 + rr[i])
            cash_val *= (1.0 + rs)

        tv_pre = risk_val + cash_val
        nav_b = (tv_pre / units) if units > 0 else 1.0
        amt = flow_by_i.get(i, 0.0)
        if amt:
            units += amt / nav_b
            cash_val += amt * sleeve_weight
            risk_val += amt * (1.0 - sleeve_weight)

        dd = float(signal_dd[i]) if i < len(signal_dd) else 0.0
        if dd <= rearm_dd and any(not x for x in armed):
            armed = [True] * len(thrs)
            rearm_count += 1

        for k, thr in enumerate(thrs):
            if armed[k] and dd >= thr and cash_val > 0:
                move = cash_val * max(0.0, min(1.0, ratios[k]))
                if move > 1e-9:
                    cash_val -= move
                    risk_val += move
                    deployed += move
                    deploy_count += 1
                    trigger_hits[f"{thr:.0%}"] += 1
                    if first_trigger is None:
                        first_trigger = grid[i].strftime("%Y-%m-%d")
                armed[k] = False

        tv = risk_val + cash_val
        equity[i] = tv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
        cash_weight_sum += (cash_val / tv) if tv > 0 else 0.0

    stats = {
        "sleeve_weight": float(sleeve_weight),
        "avg_cash_weight": float(cash_weight_sum / n) if n else 0.0,
        "end_cash": float(cash_val),
        "deployed_amount": float(deployed),
        "deploy_count": int(deploy_count),
        "rearm_count": int(rearm_count),
        "first_trigger": first_trigger,
        "trigger_hits": trigger_hits,
    }
    return nav, equity, stats


def run_crash_sleeve_ab(cfg, monthly: float = 0.0, *,
                        sleeve_weights=(0.10, 0.15),
                        thresholds=(0.20, 0.30, 0.40),
                        deploy_ratios=(0.30, 0.40, 1.00),
                        safe_weight: float | None = None,
                        safe_annual: float = 0.04,
                        rebal_days: int = 21,
                        rebal_band: float = 0.0,
                        rolling_min_years: float = 5.0,
                        rolling_step_months: int = 3,
                        benchmark_tickers=("QQQ", "SPY"),
                        skip_missing: bool = True,
                        strict: bool = False):
    """篮子级崩盘 sleeve A/B：相关性诊断 + 10/15% 独立储备触发验证。"""
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    hold_nav, hold_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    _, risk_nav, risk_eq, risk_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    contributed = sum(a for _, a in flows)

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    def metric_block(grid2, navc, eqc, flows2, contributed2, turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows2]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        return {"final": float(eqc[-1]),
                "mult": float(eqc[-1] / contributed2) if contributed2 else None,
                "xirr": M.xirr(cf),
                "maxdd": M.max_drawdown(navc),
                "sharpe": M.sharpe(ret),
                "sortino": M.sortino(ret),
                "turnover_x": (turnover / contributed2) if contributed2 else None,
                "n_rebal": int(n_rebal)}

    baselines = {
        "长期持有不动": metric_block(grid, hold_nav, hold_eq, flows, contributed),
        "纯棘轮": metric_block(grid, risk_nav, risk_eq, flows, contributed),
    }
    if safe_weight > 0:
        def_nav, def_eq, _, turn, nrb = _run_defensive_fund(
            grid, risk_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
        baselines[f"策略+防御层(W={safe_weight:.0%})"] = metric_block(
            grid, def_nav, def_eq, flows, contributed, turn, nrb)
    risk = baselines["纯棘轮"]

    benchmark_close = {}
    benchmark_errors = {}
    for ticker in benchmark_tickers:
        tk = str(ticker).upper()
        label = _benchmark_label(tk)
        try:
            close, meta = _fetch_benchmark_close(tk, cfg, grid)
            version_start_i = _first_valid_price_i(close)
            version = data_version_payload(
                meta,
                used_start=(
                    grid[version_start_i].strftime("%Y-%m-%d")
                    if version_start_i is not None else None
                ),
                used_end=grid[-1].strftime("%Y-%m-%d"),
            )
            benchmark_close[label] = {
                "close": close,
                "source": getattr(meta, "source", "?"),
                "data_version": version if version.get("version_id") else None,
            }
        except Exception as e:
            benchmark_errors[label] = str(e)

    def corr_summary():
        close_df = pd.DataFrame({t: panels[t]["close"] for t in panels}, index=grid)
        ret = close_df.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
        sym_corr = ret.corr()
        pairs = []
        cols = list(sym_corr.columns)
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                v = sym_corr.loc[a, b]
                if pd.notna(v):
                    pairs.append({"pair": f"{a}/{b}", "corr": float(v)})
        pair_vals = [p["corr"] for p in pairs]
        pairs_sorted = sorted(pairs, key=lambda x: x["corr"], reverse=True)
        bench = {}
        for label, item in benchmark_close.items():
            bret = pd.Series(item["close"], index=grid).pct_change(fill_method=None)
            vals = ret.corrwith(bret).dropna()
            bench[label] = {
                "avg": float(vals.mean()) if len(vals) else None,
                "min": float(vals.min()) if len(vals) else None,
                "max": float(vals.max()) if len(vals) else None,
            }
        return {
            "avg_pairwise": float(np.mean(pair_vals)) if pair_vals else None,
            "min_pairwise": float(np.min(pair_vals)) if pair_vals else None,
            "max_pairwise": float(np.max(pair_vals)) if pair_vals else None,
            "top_pairs": pairs_sorted[:5],
            "benchmarks": bench,
            "note": "相关性基于日收益；越接近1，单独个股储备越容易在同一轮下跌中同时被消耗。",
        }

    basket_dd = _drawdown_curve(hold_nav)
    signal_dds = {"篮子DD": basket_dd}
    qqq = benchmark_close.get("纳指100(QQQ)")
    spy = benchmark_close.get("标普500(SPY)")
    if qqq is not None:
        qnav, _ = _run_single_asset_fund(grid, qqq["close"], flows)
        qdd = _drawdown_curve(qnav)
        signal_dds["QQQ DD"] = qdd
    else:
        qdd = None
    if spy is not None:
        snav, _ = _run_single_asset_fund(grid, spy["close"], flows)
        sdd = _drawdown_curve(snav)
    else:
        sdd = None
    if qdd is not None and sdd is not None:
        signal_dds["QQQ/SPY较深DD"] = np.maximum(qdd, sdd)
        signal_dds["篮子/QQQ/SPY较深DD"] = np.maximum(basket_dd, np.maximum(qdd, sdd))
    elif qdd is not None:
        signal_dds["篮子/QQQ较深DD"] = np.maximum(basket_dd, qdd)

    rows = []
    for signal_name, signal_dd in signal_dds.items():
        for w in sleeve_weights:
            nav, eq, stats = _run_crash_sleeve_fund(
                grid, risk_nav, flows, signal_dd, sleeve_weight=float(w),
                thresholds=thresholds, deploy_ratios=deploy_ratios,
                safe_annual=safe_annual)
            m = metric_block(grid, nav, eq, flows, contributed, stats["deployed_amount"])
            xdiff = (m["xirr"] - risk["xirr"]
                     if m["xirr"] is not None and risk["xirr"] is not None else None)
            ddiff = (risk["maxdd"] - m["maxdd"]
                     if risk["maxdd"] is not None and m["maxdd"] is not None else None)
            if xdiff is not None and xdiff >= 0 and ddiff is not None and ddiff > 0:
                verdict = "候选：收益不低且回撤更浅"
            elif ddiff is not None and ddiff > 0:
                verdict = "防守有效但收益成本"
            else:
                verdict = "不优于纯棘轮"
            rows.append({
                "label": f"{float(w):.0%} · {signal_name}",
                "sleeve_weight": float(w),
                "signal": signal_name,
                "metrics": m,
                "stats": stats,
                "xirr_vs_risk": xdiff,
                "dd_relief_vs_risk": ddiff,
                "verdict": verdict,
            })

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def rollup(samples):
        xs = [s.get("xirr_vs_risk") for s in samples]
        dds = [s.get("dd_relief_vs_risk") for s in samples]
        cand = [s["candidate"] for s in samples]
        valid_x = [v for v in xs if v is not None and np.isfinite(v)]
        valid_dd = [v for v in dds if v is not None and np.isfinite(v)]
        windows = len(samples)
        win_rate = (sum(1 for v in valid_x if v >= 0) / len(valid_x)) if valid_x else None
        dd_win_rate = (sum(1 for v in valid_dd if v > 0) / len(valid_dd)) if valid_dd else None
        candidate_rate = (sum(1 for v in cand if v) / windows) if windows else None
        if candidate_rate is not None and candidate_rate >= 0.50:
            verdict = "滚动候选"
        elif dd_win_rate is not None and dd_win_rate >= 0.60:
            verdict = "稳健防守但收益成本"
        else:
            verdict = "滚动不稳健"
        return {"windows": windows,
                "win_rate": win_rate,
                "dd_win_rate": dd_win_rate,
                "candidate_rate": candidate_rate,
                "xirr_vs_risk": {"p10": q(xs, 0.10), "p50": q(xs, 0.50), "p90": q(xs, 0.90)},
                "dd_relief_vs_risk": {"p10": q(dds, 0.10), "p50": q(dds, 0.50), "p90": q(dds, 0.90)},
                "verdict": verdict}

    rolling_samples = {r["label"]: [] for r in rows}
    min_len = max(2, int(float(rolling_min_years) * 252))
    starts = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            starts.append(i)
    starts = starts[::max(1, int(rolling_step_months))]

    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue
        panels2 = {t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
                   for t in alive}
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}
        hold_nav2, _ = _run_fullinvest_fund(grid2, panels2, listing2, last2, caps2, monthly)
        _, risk_nav2, risk_eq2, _, flows2 = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed2 = sum(a for _, a in flows2)
        if contributed2 <= 0:
            continue
        risk2 = metric_block(grid2, risk_nav2, risk_eq2, flows2, contributed2)
        basket_dd2 = _drawdown_curve(hold_nav2)
        qdd2 = _drawdown_curve(_run_single_asset_fund(grid2, qqq["close"][si:], flows2)[0]) if qqq is not None else None
        sdd2 = _drawdown_curve(_run_single_asset_fund(grid2, spy["close"][si:], flows2)[0]) if spy is not None else None
        signal_dds2 = {"篮子DD": basket_dd2}
        if qdd2 is not None:
            signal_dds2["QQQ DD"] = qdd2
        if qdd2 is not None and sdd2 is not None:
            signal_dds2["QQQ/SPY较深DD"] = np.maximum(qdd2, sdd2)
            signal_dds2["篮子/QQQ/SPY较深DD"] = np.maximum(basket_dd2, np.maximum(qdd2, sdd2))
        elif qdd2 is not None:
            signal_dds2["篮子/QQQ较深DD"] = np.maximum(basket_dd2, qdd2)

        for signal_name, signal_dd in signal_dds2.items():
            for w in sleeve_weights:
                label = f"{float(w):.0%} · {signal_name}"
                if label not in rolling_samples:
                    continue
                nav2, eq2, stats2 = _run_crash_sleeve_fund(
                    grid2, risk_nav2, flows2, signal_dd, sleeve_weight=float(w),
                    thresholds=thresholds, deploy_ratios=deploy_ratios,
                    safe_annual=safe_annual)
                m2 = metric_block(grid2, nav2, eq2, flows2, contributed2, stats2["deployed_amount"])
                xdiff = (m2["xirr"] - risk2["xirr"]
                         if m2["xirr"] is not None and risk2["xirr"] is not None else None)
                ddiff = (risk2["maxdd"] - m2["maxdd"]
                         if risk2["maxdd"] is not None and m2["maxdd"] is not None else None)
                rolling_samples[label].append({
                    "xirr_vs_risk": xdiff,
                    "dd_relief_vs_risk": ddiff,
                    "candidate": bool(xdiff is not None and xdiff >= 0
                                      and ddiff is not None and ddiff > 0),
                })

    rolling = {label: rollup(samples) for label, samples in rolling_samples.items()}
    for r in rows:
        r["rolling"] = rolling.get(r["label"])
    rolling_candidates = [label for label, item in rolling.items()
                          if item and item.get("candidate_rate") is not None
                          and item["candidate_rate"] >= 0.50]

    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "baselines": baselines, "rows": rows,
            "correlation": corr_summary(), "benchmark_errors": benchmark_errors,
            "summary": {"candidate_count": sum(1 for r in rows if "候选" in r["verdict"]),
                        "rolling_candidate_count": len(rolling_candidates),
                        "rolling_windows": len(starts),
                        "rolling_min_years": float(rolling_min_years),
                        "rolling_step_months": int(rolling_step_months),
                        "thresholds": [float(x) for x in thresholds],
                        "deploy_ratios": [float(x) for x in deploy_ratios],
                        "safe_annual": float(safe_annual),
                        "status": "research_only",
                        "signal": "独立crash cash sleeve；触发后cash转入纯棘轮风险腿，不消耗个股reserve"}}


# ===========================================================================
# 当前篮子参数扫描（研究层）——core_ratio × 档位 × 投放比例。
#
# 旧 scripts/sweep.py 仍保留命令行用途，但它是早期共同窗口/非 NAV-DD 口径。这里专供
# Dashboard：错峰并入、单位NAV回撤、同现金流、多起点滚动验证，避免把注资或上市时间
# 差异误当策略效果。
# ===========================================================================
def _param_scan_presets(core_ratios=(0.75, 0.85, 0.90, 0.95)):
    tier_sets = [
        {"name": "现行深档", "thresholds": [-0.25, -0.45], "ratios": [0.40, 0.60]},
        {"name": "中深三档", "thresholds": [-0.15, -0.30, -0.45], "ratios": [0.20, 0.35, 0.45]},
        {"name": "后置三档", "thresholds": [-0.20, -0.35, -0.50], "ratios": [0.25, 0.35, 0.40]},
        {"name": "均匀四档", "thresholds": [-0.10, -0.20, -0.30, -0.40], "ratios": [0.25, 0.25, 0.25, 0.25]},
        {"name": "极深两档", "thresholds": [-0.30, -0.50], "ratios": [0.40, 0.60]},
    ]
    out = []
    for core in core_ratios:
        for tiers in tier_sets:
            out.append({
                "core_ratio": float(core),
                "thresholds": list(tiers["thresholds"]),
                "deploy_ratios": list(tiers["ratios"]),
                "tier_name": tiers["name"],
                "label": f"core {core:.0%} · {tiers['name']}",
            })
    return out


def _apply_param_scan_preset(cfg, preset):
    c = copy.deepcopy(cfg)
    p = c.portfolio
    core = float(preset["core_ratio"])
    p.core_ratio = core
    # 扫 core_ratio 时把后续注资核心比例同步过去；注资模式 A/B 留给 TODO 第 7 项。
    p.injection_core_ratio = core
    p.tiers.thresholds = list(preset["thresholds"])
    p.tiers.deploy_ratios = list(preset["deploy_ratios"])
    return c


def run_param_scan_ab(cfg, monthly: float = 0.0, *,
                      core_ratios=(0.75, 0.85, 0.90, 0.95),
                      safe_weight: float | None = None,
                      safe_annual: float = 0.04,
                      rebal_days: int = 21,
                      rebal_band: float = 0.0,
                      rolling_min_years: float = 5.0,
                      rolling_step_months: int = 3,
                      skip_missing: bool = True,
                      strict: bool = False):
    """当前篮子参数扫描：同现金流、NAV-DD、相对当前参数和长期持有比较。"""
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    hold_nav, hold_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    _, cur_nav, cur_eq, cur_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    contributed = sum(a for _, a in flows)

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    def metric_block(grid2, navc, eqc, flows2, contributed2, invested_curve=None,
                     turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows2]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        out = {"final": float(eqc[-1]),
               "mult": float(eqc[-1] / contributed2) if contributed2 else None,
               "xirr": M.xirr(cf),
               "maxdd": M.max_drawdown(navc),
               "sharpe": M.sharpe(ret),
               "sortino": M.sortino(ret),
               "turnover_x": (turnover / contributed2) if contributed2 else None,
               "n_rebal": int(n_rebal)}
        if invested_curve is not None:
            denom = np.where(eqc > 0, eqc, 1)
            out["avg_invested"] = float(np.mean(invested_curve / denom))
        return out

    baselines = {
        "长期持有不动": metric_block(grid, hold_nav, hold_eq, flows, contributed),
        "当前参数": metric_block(grid, cur_nav, cur_eq, flows, contributed, cur_inv),
    }
    if safe_weight > 0:
        def_nav, def_eq, _, turn, nrb = _run_defensive_fund(
            grid, cur_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
        baselines[f"当前参数+防御层(W={safe_weight:.0%})"] = metric_block(
            grid, def_nav, def_eq, flows, contributed, None, turn, nrb)
    hold = baselines["长期持有不动"]
    current = baselines["当前参数"]

    rows = []
    presets = _param_scan_presets(core_ratios)
    for preset in presets:
        c2 = _apply_param_scan_preset(cfg, preset)
        _, nav, eq, inv, flows2 = _run_strategy_fund(
            grid, panels, listing_i, last_i, caps, monthly, c2)
        m = metric_block(grid, nav, eq, flows2, contributed, inv)
        xdiff_cur = (m["xirr"] - current["xirr"]
                     if m["xirr"] is not None and current["xirr"] is not None else None)
        ddiff_cur = (current["maxdd"] - m["maxdd"]
                     if current["maxdd"] is not None and m["maxdd"] is not None else None)
        xdiff_hold = (m["xirr"] - hold["xirr"]
                      if m["xirr"] is not None and hold["xirr"] is not None else None)
        ddiff_hold = (hold["maxdd"] - m["maxdd"]
                      if hold["maxdd"] is not None and m["maxdd"] is not None else None)
        if xdiff_cur is not None and xdiff_cur >= 0 and ddiff_cur is not None and ddiff_cur > 0:
            verdict = "候选：优于当前参数"
        elif xdiff_cur is not None and xdiff_cur > 0:
            verdict = "进攻更强但回撤更深"
        elif ddiff_cur is not None and ddiff_cur > 0:
            verdict = "防守更强但收益成本"
        else:
            verdict = "不优于当前参数"
        row = {
            **preset,
            "metrics": m,
            "xirr_vs_current": xdiff_cur,
            "dd_relief_vs_current": ddiff_cur,
            "xirr_vs_hold": xdiff_hold,
            "dd_relief_vs_hold": ddiff_hold,
            "verdict": verdict,
            "is_current": bool(abs(preset["core_ratio"] - cfg.portfolio.core_ratio) < 1e-9
                               and list(preset["thresholds"]) == list(cfg.portfolio.tiers.thresholds)
                               and list(preset["deploy_ratios"]) == list(cfg.portfolio.tiers.deploy_ratios)),
        }
        rows.append(row)

    valid = [r for r in rows if r["metrics"]["xirr"] is not None]
    best_xirr = max(valid, key=lambda r: r["metrics"]["xirr"]) if valid else None
    best_dd = min(valid, key=lambda r: r["metrics"]["maxdd"]) if valid else None

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def rollup(samples):
        xs = [s.get("xirr_vs_current") for s in samples]
        dds = [s.get("dd_relief_vs_current") for s in samples]
        cand = [s["candidate"] for s in samples]
        valid_x = [v for v in xs if v is not None and np.isfinite(v)]
        valid_dd = [v for v in dds if v is not None and np.isfinite(v)]
        windows = len(samples)
        win_rate = (sum(1 for v in valid_x if v >= 0) / len(valid_x)) if valid_x else None
        dd_win_rate = (sum(1 for v in valid_dd if v > 0) / len(valid_dd)) if valid_dd else None
        candidate_rate = (sum(1 for v in cand if v) / windows) if windows else None
        if candidate_rate is not None and candidate_rate >= 0.50:
            verdict = "滚动候选"
        elif win_rate is not None and win_rate >= 0.60:
            verdict = "滚动进攻"
        elif dd_win_rate is not None and dd_win_rate >= 0.60:
            verdict = "稳健防守但收益成本"
        else:
            verdict = "滚动不稳健"
        return {"windows": windows,
                "win_rate": win_rate,
                "dd_win_rate": dd_win_rate,
                "candidate_rate": candidate_rate,
                "xirr_vs_current": {"p10": q(xs, 0.10), "p50": q(xs, 0.50), "p90": q(xs, 0.90)},
                "dd_relief_vs_current": {"p10": q(dds, 0.10), "p50": q(dds, 0.50), "p90": q(dds, 0.90)},
                "verdict": verdict}

    rolling_samples = {r["label"]: [] for r in rows}
    min_len = max(2, int(float(rolling_min_years) * 252))
    starts = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            starts.append(i)
    starts = starts[::max(1, int(rolling_step_months))]

    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue
        panels2 = {t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
                   for t in alive}
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}
        _, cur_nav2, cur_eq2, cur_inv2, flows_cur2 = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed2 = sum(a for _, a in flows_cur2)
        if contributed2 <= 0:
            continue
        cur2 = metric_block(grid2, cur_nav2, cur_eq2, flows_cur2, contributed2, cur_inv2)
        for preset in presets:
            label = preset["label"]
            c2 = _apply_param_scan_preset(cfg, preset)
            _, nav2, eq2, inv2, flows2 = _run_strategy_fund(
                grid2, panels2, listing2, last2, caps2, monthly, c2)
            m2 = metric_block(grid2, nav2, eq2, flows2, contributed2, inv2)
            xdiff = (m2["xirr"] - cur2["xirr"]
                     if m2["xirr"] is not None and cur2["xirr"] is not None else None)
            ddiff = (cur2["maxdd"] - m2["maxdd"]
                     if cur2["maxdd"] is not None and m2["maxdd"] is not None else None)
            rolling_samples[label].append({
                "xirr_vs_current": xdiff,
                "dd_relief_vs_current": ddiff,
                "candidate": bool(xdiff is not None and xdiff >= 0
                                  and ddiff is not None and ddiff > 0),
            })

    rolling = {label: rollup(samples) for label, samples in rolling_samples.items()}
    for r in rows:
        r["rolling"] = rolling.get(r["label"])
        if r["is_current"]:
            r["verdict"] = "当前参数"
            if r["rolling"]:
                r["rolling"]["verdict"] = "当前基线"
    rolling_candidates = [label for label, item in rolling.items()
                          if item and item.get("candidate_rate") is not None
                          and item["candidate_rate"] >= 0.50]

    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "baselines": baselines, "rows": rows,
            "summary": {"candidate_count": sum(1 for r in rows if "候选" in r["verdict"]),
                        "rolling_candidate_count": len(rolling_candidates),
                        "rolling_windows": len(starts),
                        "rolling_min_years": float(rolling_min_years),
                        "rolling_step_months": int(rolling_step_months),
                        "best_xirr": best_xirr["label"] if best_xirr else None,
                        "best_drawdown": best_dd["label"] if best_dd else None,
                        "current_label": next((r["label"] for r in rows if r["is_current"]), None),
                        "core_ratios": [float(x) for x in core_ratios],
                        "status": "research_only",
                        "signal": "core_ratio 与 injection_core_ratio 同步扫描；注资模式不变"}}


# ===========================================================================
# 注资模式 A/B（研究层）——lump / ladder / all_reserve 在真实定投注资节奏下重测。
#
# 这项直接映射到未来前端“加本金”的执行方式：/api/inject 走 core.engine.apply_injection，
# 因而会受 config.portfolio.injection_mode 影响；/api/scale_up 为保持 74:26 精确落仓，仍刻意
# 使用立即 lump，不参与这里的模式切换。
# ===========================================================================
def _injection_mode_specs(cfg, modes=("lump_core", "ladder_core", "all_reserve")):
    p = cfg.portfolio
    text = {
        "lump_core": (
            "现价核心",
            f"新增本金的 {p.injection_core_ratio:.0%} 买核心，余额进储备；只有单笔核心额超过现有核心 "
            f"{p.injection_ladder_trigger_ratio:.0%} 时才自动分批。"
        ),
        "ladder_core": (
            "分批核心",
            f"新增本金仍按 {p.injection_core_ratio:.0%}/{1 - p.injection_core_ratio:.0%} 拆分，"
            f"但核心部分固定分 {p.injection_ladder_tranches} 批、每 {p.injection_ladder_spacing_days} 个交易日到期买入。"
        ),
        "all_reserve": (
            "全储备",
            "新增本金全部先进入该标的储备金，不主动现价买核心；等待深跌棘轮、战术挂单或后续再平衡触发。"
        ),
    }
    out = []
    seen = set()
    for mode in modes:
        if mode in seen:
            continue
        seen.add(mode)
        short, operation = text.get(mode, (mode, mode))
        out.append({"mode": mode, "label": f"{mode} · {short}", "operation": operation})
    return out


def _apply_injection_mode(cfg, mode: str):
    c = copy.deepcopy(cfg)
    c.portfolio.injection_mode = str(mode)
    return c


def run_injection_mode_ab(cfg, monthly: float = 0.0, *,
                          modes=("lump_core", "ladder_core", "all_reserve"),
                          safe_weight: float | None = None,
                          safe_annual: float = 0.04,
                          rebal_days: int = 21,
                          rebal_band: float = 0.0,
                          rolling_min_years: float = 5.0,
                          rolling_step_months: int = 3,
                          skip_missing: bool = True,
                          strict: bool = False):
    """注资模式 A/B：同篮子、同现金流、同防御层，比较未来新增本金如何进入市场。"""
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    current_mode = str(getattr(cfg.portfolio, "injection_mode", "lump_core"))
    mode_list = list(modes)
    if current_mode not in mode_list:
        mode_list.insert(0, current_mode)
    specs = _injection_mode_specs(cfg, mode_list)

    hold_nav, hold_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    _, cur_risk_nav, cur_risk_eq, cur_risk_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    contributed = sum(a for _, a in flows)

    def metric_block(grid2, navc, eqc, flows2, contributed2,
                     invested_curve=None, turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows2]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        out = {"final": float(eqc[-1]),
               "mult": float(eqc[-1] / contributed2) if contributed2 else None,
               "xirr": M.xirr(cf),
               "maxdd": M.max_drawdown(navc),
               "sharpe": M.sharpe(ret),
               "sortino": M.sortino(ret),
               "turnover_x": (turnover / contributed2) if contributed2 else None,
               "n_rebal": int(n_rebal)}
        if invested_curve is not None:
            denom = np.where(eqc > 0, eqc, 1)
            out["avg_invested"] = float(np.mean(invested_curve / denom))
        return out

    cur_risk_metrics = metric_block(grid, cur_risk_nav, cur_risk_eq, flows, contributed, cur_risk_inv)
    if safe_weight > 0:
        cur_nav, cur_eq, _, cur_turn, cur_nrb = _run_defensive_fund(
            grid, cur_risk_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
        current = metric_block(grid, cur_nav, cur_eq, flows, contributed, None, cur_turn, cur_nrb)
    else:
        cur_nav, cur_eq, current = cur_risk_nav, cur_risk_eq, cur_risk_metrics

    baselines = {
        "长期持有不动": metric_block(grid, hold_nav, hold_eq, flows, contributed),
        f"当前模式风险腿({current_mode})": cur_risk_metrics,
    }
    if safe_weight > 0:
        baselines[f"当前模式+防御层(W={safe_weight:.0%})"] = current

    rows = []
    for spec in specs:
        c2 = _apply_injection_mode(cfg, spec["mode"])
        _, risk_nav, risk_eq, risk_inv, flows2 = _run_strategy_fund(
            grid, panels, listing_i, last_i, caps, monthly, c2)
        risk_m = metric_block(grid, risk_nav, risk_eq, flows2, contributed, risk_inv)
        if safe_weight > 0:
            nav, eq, _, turn, nrb = _run_defensive_fund(
                grid, risk_nav, flows2, safe_annual, safe_weight, rebal_days, rebal_band)
            m = metric_block(grid, nav, eq, flows2, contributed, None, turn, nrb)
        else:
            m = risk_m
        xdiff = (m["xirr"] - current["xirr"]
                 if m["xirr"] is not None and current["xirr"] is not None else None)
        ddiff = (current["maxdd"] - m["maxdd"]
                 if current["maxdd"] is not None and m["maxdd"] is not None else None)
        is_current = spec["mode"] == current_mode
        if is_current:
            verdict = "当前模式"
        elif xdiff is not None and xdiff >= 0 and ddiff is not None and ddiff > 0:
            verdict = "候选：优于当前模式"
        elif xdiff is not None and xdiff > 0:
            verdict = "进攻更强但回撤更深"
        elif ddiff is not None and ddiff > 0:
            verdict = "防守更强但收益成本"
        else:
            verdict = "不优于当前模式"
        rows.append({
            **spec,
            "is_current": is_current,
            "metrics": m,
            "risk_metrics": risk_m,
            "xirr_vs_current": xdiff,
            "dd_relief_vs_current": ddiff,
            "verdict": verdict,
        })

    valid = [r for r in rows if r["metrics"]["xirr"] is not None]
    best_xirr = max(valid, key=lambda r: r["metrics"]["xirr"]) if valid else None
    best_dd = min(valid, key=lambda r: r["metrics"]["maxdd"]) if valid else None

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def rollup(samples):
        xs = [s.get("xirr_vs_current") for s in samples]
        dds = [s.get("dd_relief_vs_current") for s in samples]
        cand = [s["candidate"] for s in samples]
        valid_x = [v for v in xs if v is not None and np.isfinite(v)]
        valid_dd = [v for v in dds if v is not None and np.isfinite(v)]
        windows = len(samples)
        win_rate = (sum(1 for v in valid_x if v >= 0) / len(valid_x)) if valid_x else None
        dd_win_rate = (sum(1 for v in valid_dd if v > 0) / len(valid_dd)) if valid_dd else None
        candidate_rate = (sum(1 for v in cand if v) / windows) if windows else None
        if candidate_rate is not None and candidate_rate >= 0.50:
            verdict = "滚动候选"
        elif win_rate is not None and win_rate >= 0.60:
            verdict = "滚动进攻"
        elif dd_win_rate is not None and dd_win_rate >= 0.60:
            verdict = "稳健防守但收益成本"
        else:
            verdict = "滚动不稳健"
        return {"windows": windows,
                "win_rate": win_rate,
                "dd_win_rate": dd_win_rate,
                "candidate_rate": candidate_rate,
                "xirr_vs_current": {"p10": q(xs, 0.10), "p50": q(xs, 0.50), "p90": q(xs, 0.90)},
                "dd_relief_vs_current": {"p10": q(dds, 0.10), "p50": q(dds, 0.50), "p90": q(dds, 0.90)},
                "verdict": verdict}

    rolling_samples = {r["label"]: [] for r in rows}
    min_len = max(2, int(float(rolling_min_years) * 252))
    starts = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            starts.append(i)
    starts = starts[::max(1, int(rolling_step_months))]

    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue
        panels2 = {t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
                   for t in alive}
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}
        _, cur_risk_nav2, cur_risk_eq2, cur_risk_inv2, flows_cur2 = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed2 = sum(a for _, a in flows_cur2)
        if contributed2 <= 0:
            continue
        if safe_weight > 0:
            cur_nav2, cur_eq2, _, cur_turn2, cur_nrb2 = _run_defensive_fund(
                grid2, cur_risk_nav2, flows_cur2, safe_annual, safe_weight, rebal_days, rebal_band)
            cur2 = metric_block(grid2, cur_nav2, cur_eq2, flows_cur2, contributed2, None,
                                cur_turn2, cur_nrb2)
        else:
            cur2 = metric_block(grid2, cur_risk_nav2, cur_risk_eq2, flows_cur2, contributed2,
                                cur_risk_inv2)
        for spec in specs:
            c2 = _apply_injection_mode(cfg, spec["mode"])
            _, risk_nav2, risk_eq2, risk_inv2, flows2 = _run_strategy_fund(
                grid2, panels2, listing2, last2, caps2, monthly, c2)
            if safe_weight > 0:
                nav2, eq2, _, turn2, nrb2 = _run_defensive_fund(
                    grid2, risk_nav2, flows2, safe_annual, safe_weight, rebal_days, rebal_band)
                m2 = metric_block(grid2, nav2, eq2, flows2, contributed2, None, turn2, nrb2)
            else:
                m2 = metric_block(grid2, risk_nav2, risk_eq2, flows2, contributed2, risk_inv2)
            xdiff = (m2["xirr"] - cur2["xirr"]
                     if m2["xirr"] is not None and cur2["xirr"] is not None else None)
            ddiff = (cur2["maxdd"] - m2["maxdd"]
                     if cur2["maxdd"] is not None and m2["maxdd"] is not None else None)
            rolling_samples[spec["label"]].append({
                "xirr_vs_current": xdiff,
                "dd_relief_vs_current": ddiff,
                "candidate": bool(xdiff is not None and xdiff >= 0
                                  and ddiff is not None and ddiff > 0),
            })

    rolling = {label: rollup(samples) for label, samples in rolling_samples.items()}
    for r in rows:
        r["rolling"] = rolling.get(r["label"])
        if r["is_current"] and r["rolling"]:
            r["rolling"]["verdict"] = "当前基线"
    rolling_candidates = [label for label, item in rolling.items()
                          if item and item.get("candidate_rate") is not None
                          and item["candidate_rate"] >= 0.50]

    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "baselines": baselines, "rows": rows,
            "summary": {"candidate_count": sum(1 for r in rows if "候选" in r["verdict"]),
                        "rolling_candidate_count": len(rolling_candidates),
                        "rolling_windows": len(starts),
                        "rolling_min_years": float(rolling_min_years),
                        "rolling_step_months": int(rolling_step_months),
                        "best_xirr": best_xirr["label"] if best_xirr else None,
                        "best_drawdown": best_dd["label"] if best_dd else None,
                        "current_mode": current_mode,
                        "safe_weight": safe_weight,
                        "status": "research_only",
                        "execution_note": "改 config.portfolio.injection_mode 后会影响 /api/inject；/api/scale_up 为维持 74:26 精确比例仍使用立即 lump。",
                        "signal": "同现金流、同防御层，比较未来新增本金进入风险腿的节奏"}}


def run_tactical_overlay_ab(cfg, monthly: float = 0.0, *,
                            safe_weight: float | None = None,
                            safe_annual: float = 0.04,
                            rebal_days: int = 21,
                            rebal_band: float = 0.0,
                            rolling_min_years: float = 5.0,
                            rolling_step_months: int = 3,
                            skip_missing: bool = True,
                            strict: bool = False):
    """战术挂单 overlay A/B：验证浅回踩固定限价是否值得接入长期执行层。

    战术单只消耗各标的 reserve_cash，不改变核心注资、深跌棘轮和防御层逻辑。
    信号用前一日 close/MA/ATR，成交用当日 open/low，避免未来函数。
    """
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}
    specs = _tactical_ab_specs(cfg)

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    _, base_risk_nav, base_risk_eq, base_risk_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    contributed = sum(a for _, a in flows)

    def metric_block(grid2, navc, eqc, flows2, contributed2,
                     invested_curve=None, turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows2]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        out = {"final": float(eqc[-1]),
               "mult": float(eqc[-1] / contributed2) if contributed2 else None,
               "xirr": M.xirr(cf),
               "maxdd": M.max_drawdown(navc),
               "sharpe": M.sharpe(ret),
               "sortino": M.sortino(ret),
               "turnover_x": (turnover / contributed2) if contributed2 else None,
               "n_rebal": int(n_rebal)}
        if invested_curve is not None:
            denom = np.where(eqc > 0, eqc, 1)
            out["avg_invested"] = float(np.mean(invested_curve / denom))
        return out

    base_risk_metrics = metric_block(grid, base_risk_nav, base_risk_eq, flows,
                                     contributed, base_risk_inv)
    if safe_weight > 0:
        base_nav, base_eq, _, base_turn, base_nrb = _run_defensive_fund(
            grid, base_risk_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
        baseline = metric_block(grid, base_nav, base_eq, flows, contributed, None,
                                base_turn, base_nrb)
    else:
        baseline = base_risk_metrics

    rows = []
    for spec in specs:
        _, risk_nav, risk_eq, risk_inv, flows2, stats = _run_strategy_fund_tactical(
            grid, panels, listing_i, last_i, caps, monthly, cfg, spec)
        risk_m = metric_block(grid, risk_nav, risk_eq, flows2, contributed, risk_inv)
        if safe_weight > 0:
            nav, eq, _, turn, nrb = _run_defensive_fund(
                grid, risk_nav, flows2, safe_annual, safe_weight, rebal_days, rebal_band)
            m = metric_block(grid, nav, eq, flows2, contributed, None, turn, nrb)
        else:
            m = risk_m
        xdiff = (m["xirr"] - baseline["xirr"]
                 if m["xirr"] is not None and baseline["xirr"] is not None else None)
        ddiff = (baseline["maxdd"] - m["maxdd"]
                 if baseline["maxdd"] is not None and m["maxdd"] is not None else None)
        spend_ratio = stats["fill_amount"] / contributed if contributed else None
        if xdiff is not None and xdiff >= 0 and ddiff is not None and ddiff >= -0.001:
            verdict = "候选：收益改善且回撤不劣"
        elif xdiff is not None and xdiff > 0:
            verdict = "进攻有效但回撤更深"
        elif ddiff is not None and ddiff > 0:
            verdict = "更稳但收益成本"
        else:
            verdict = "不优于关闭战术"
        rows.append({
            **spec,
            "metrics": m,
            "risk_metrics": risk_m,
            "stats": {**stats, "spend_ratio": spend_ratio},
            "xirr_vs_baseline": xdiff,
            "dd_relief_vs_baseline": ddiff,
            "verdict": verdict,
        })

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def rollup(samples):
        xs = [s.get("xirr_vs_baseline") for s in samples]
        dds = [s.get("dd_relief_vs_baseline") for s in samples]
        valid_x = [v for v in xs if v is not None and np.isfinite(v)]
        valid_dd = [v for v in dds if v is not None and np.isfinite(v)]
        windows = len(samples)
        win_rate = (sum(1 for v in valid_x if v >= 0) / len(valid_x)) if valid_x else None
        dd_win_rate = (sum(1 for v in valid_dd if v >= 0) / len(valid_dd)) if valid_dd else None
        candidate_rate = (sum(1 for s in samples if s.get("candidate")) / windows) if windows else None
        if candidate_rate is not None and candidate_rate >= 0.50:
            verdict = "滚动候选"
        elif win_rate is not None and win_rate >= 0.60:
            verdict = "滚动进攻"
        elif dd_win_rate is not None and dd_win_rate >= 0.60:
            verdict = "稳健防守但收益成本"
        else:
            verdict = "滚动不稳健"
        return {"windows": windows,
                "win_rate": win_rate,
                "dd_win_rate": dd_win_rate,
                "candidate_rate": candidate_rate,
                "xirr_vs_baseline": {"p10": q(xs, 0.10), "p50": q(xs, 0.50), "p90": q(xs, 0.90)},
                "dd_relief_vs_baseline": {"p10": q(dds, 0.10), "p50": q(dds, 0.50), "p90": q(dds, 0.90)},
                "verdict": verdict}

    rolling_samples = {r["label"]: [] for r in rows}
    min_len = max(2, int(float(rolling_min_years) * 252))
    starts = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            starts.append(i)
    starts = starts[::max(1, int(rolling_step_months))]

    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue
        panels2 = {t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
                   for t in alive}
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}
        _, br_nav2, br_eq2, br_inv2, flows_b2 = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed2 = sum(a for _, a in flows_b2)
        if contributed2 <= 0:
            continue
        if safe_weight > 0:
            b_nav2, b_eq2, _, b_turn2, b_nrb2 = _run_defensive_fund(
                grid2, br_nav2, flows_b2, safe_annual, safe_weight, rebal_days, rebal_band)
            base2 = metric_block(grid2, b_nav2, b_eq2, flows_b2, contributed2, None,
                                 b_turn2, b_nrb2)
        else:
            base2 = metric_block(grid2, br_nav2, br_eq2, flows_b2, contributed2, br_inv2)
        for spec in specs:
            _, r_nav2, r_eq2, r_inv2, flows2, stats2 = _run_strategy_fund_tactical(
                grid2, panels2, listing2, last2, caps2, monthly, cfg, spec)
            if safe_weight > 0:
                nav2, eq2, _, turn2, nrb2 = _run_defensive_fund(
                    grid2, r_nav2, flows2, safe_annual, safe_weight, rebal_days, rebal_band)
                m2 = metric_block(grid2, nav2, eq2, flows2, contributed2, None, turn2, nrb2)
            else:
                m2 = metric_block(grid2, r_nav2, r_eq2, flows2, contributed2, r_inv2)
            xdiff = (m2["xirr"] - base2["xirr"]
                     if m2["xirr"] is not None and base2["xirr"] is not None else None)
            ddiff = (base2["maxdd"] - m2["maxdd"]
                     if base2["maxdd"] is not None and m2["maxdd"] is not None else None)
            rolling_samples[spec["label"]].append({
                "xirr_vs_baseline": xdiff,
                "dd_relief_vs_baseline": ddiff,
                "xirr": m2.get("xirr"),
                "maxdd": m2.get("maxdd"),
                "fills": stats2.get("fills", 0),
                "candidate": bool(xdiff is not None and xdiff >= 0
                                  and ddiff is not None and ddiff >= -0.001
                                  and stats2.get("fills", 0) > 0),
            })

    rolling = {label: rollup(samples) for label, samples in rolling_samples.items()}
    for r in rows:
        r["rolling"] = rolling.get(r["label"])

    current_row = next((r for r in rows if r.get("mode") == "current"), None)
    current_samples = rolling_samples.get(current_row["label"], []) if current_row else []

    def rollup_vs_current(samples, base_samples):
        xs = []
        dds = []
        candidates = []
        for s, b in zip(samples, base_samples):
            sx = s.get("xirr")
            bx = b.get("xirr")
            sd = s.get("maxdd")
            bd = b.get("maxdd")
            xdiff = (sx - bx) if sx is not None and bx is not None else None
            ddiff = (bd - sd) if sd is not None and bd is not None else None
            xs.append(xdiff)
            dds.append(ddiff)
            candidates.append(bool(
                xdiff is not None and xdiff >= 0
                and ddiff is not None and ddiff >= -0.001
                and s.get("fills", 0) > 0
            ))
        valid_x = [v for v in xs if v is not None and np.isfinite(v)]
        valid_dd = [v for v in dds if v is not None and np.isfinite(v)]
        windows = min(len(samples), len(base_samples))
        candidate_rate = (sum(1 for v in candidates if v) / windows) if windows else None
        win_rate = (sum(1 for v in valid_x if v >= 0) / len(valid_x)) if valid_x else None
        dd_win_rate = (sum(1 for v in valid_dd if v >= 0) / len(valid_dd)) if valid_dd else None
        return {
            "windows": windows,
            "win_rate": win_rate,
            "dd_win_rate": dd_win_rate,
            "candidate_rate": candidate_rate,
            "xirr_vs_current": {"p10": q(xs, 0.10), "p50": q(xs, 0.50), "p90": q(xs, 0.90)},
            "dd_relief_vs_current": {"p10": q(dds, 0.10), "p50": q(dds, 0.50), "p90": q(dds, 0.90)},
        }

    current_metrics = (current_row or {}).get("metrics") or {}
    for r in rows:
        m = r.get("metrics") or {}
        xcur = (m.get("xirr") - current_metrics.get("xirr")
                if m.get("xirr") is not None and current_metrics.get("xirr") is not None else None)
        ddcur = (current_metrics.get("maxdd") - m.get("maxdd")
                 if m.get("maxdd") is not None and current_metrics.get("maxdd") is not None else None)
        r["xirr_vs_current_tactical"] = xcur
        r["dd_relief_vs_current_tactical"] = ddcur
        r["rolling_vs_current"] = rollup_vs_current(
            rolling_samples.get(r["label"], []), current_samples) if current_samples else None

        rv = r.get("rolling_vs_current") or {}
        rx = (rv.get("xirr_vs_current") or {}).get("p50")
        rd = (rv.get("dd_relief_vs_current") or {}).get("p50")
        full_ok = xcur is not None and xcur >= 0 and ddcur is not None and ddcur >= -0.001
        rolling_ok = (rv.get("candidate_rate") is not None and rv.get("candidate_rate") >= 0.50
                      and rx is not None and rx >= 0 and rd is not None and rd >= -0.001)
        if r.get("mode") == "current":
            stage = "current"
            verdict2 = "当前实盘配置"
        elif full_ok and rolling_ok:
            stage = "candidate"
            verdict2 = "配置候选：可进入人工替换评审"
        elif (xcur is not None and xcur > 0) or (rv.get("win_rate") is not None and rv.get("win_rate") >= 0.60):
            stage = "watch"
            verdict2 = "配置观察：收益有进步但滚动/回撤不足"
        elif (ddcur is not None and ddcur > 0) or (rv.get("dd_win_rate") is not None and rv.get("dd_win_rate") >= 0.60):
            stage = "watch"
            verdict2 = "配置观察：回撤更浅但收益成本待评估"
        else:
            stage = "reject"
            verdict2 = "不替换当前配置"
        r["promotion_stage"] = stage
        r["promotion_verdict"] = verdict2
        r["promotion_note"] = "仅进入配置评审，不自动写 config 或今日建议。"

    rolling_candidates = [label for label, item in rolling.items()
                          if item and item.get("candidate_rate") is not None
                          and item["candidate_rate"] >= 0.50]

    best_xirr = max(rows, key=lambda r: (r["metrics"]["xirr"] or -999)) if rows else None
    best_score = max(
        rows,
        key=lambda r: ((r["xirr_vs_baseline"] or -999)
                       + min(0.0, r["dd_relief_vs_baseline"] or 0.0) * 0.5)
    ) if rows else None
    promotion_candidates = [r for r in rows if r.get("promotion_stage") == "candidate"]
    promotion_watch = [r for r in rows if r.get("promotion_stage") == "watch"]
    best_promotion = max(
        [r for r in rows if r.get("mode") != "current"],
        key=lambda r: ((r.get("xirr_vs_current_tactical") or -999)
                       + min(0.0, r.get("dd_relief_vs_current_tactical") or 0.0) * 0.5
                       + (((r.get("rolling_vs_current") or {}).get("xirr_vs_current") or {}).get("p50") or -9))
    ) if any(r.get("mode") != "current" for r in rows) else None
    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed,
            "baselines": {
                "关闭战术单风险腿": base_risk_metrics,
                f"关闭战术单+防御层(W={safe_weight:.0%})" if safe_weight > 0 else "关闭战术单": baseline,
            },
            "rows": rows,
            "summary": {"candidate_count": sum(1 for r in rows if "候选" in r["verdict"]),
                        "rolling_candidate_count": len(rolling_candidates),
                        "rolling_windows": len(starts),
                        "rolling_min_years": float(rolling_min_years),
                        "rolling_step_months": int(rolling_step_months),
                        "best_xirr": best_xirr["label"] if best_xirr else None,
                        "best_score": best_score["label"] if best_score else None,
                        "promotion_candidate_count": len(promotion_candidates),
                        "promotion_watch_count": len(promotion_watch),
                        "best_promotion": best_promotion["label"] if best_promotion else None,
                        "safe_weight": safe_weight,
                        "status": "research_only",
                        "signal": "前收/日线锚点 + MA/ATR 固定限价；盘中价只判断是否触发。",
                        "execution_note": "当前仍为研究验证；替换当前 config 需同时通过 vs当前配置的全程、滚动和今日建议差异检查。"}}


# ===========================================================================
# 防御层扫描（B 方向）——篮子 + W% 安全资产（现金/短债，~0 回撤、固定年化）作为
# 永久防御层。机械目标：组合回撤 ≈ (1-W) × 板块回撤，把“压多少回撤 vs 少赚多少”
# 的甜点扫成一条干净曲线，回答“30% 回撤 ↔ X% 年化”。
#
# 实现要点（同源 / 最小改 / 不碰已验证路径）：
#   - 风险腿 = 已验证的棘轮策略单位NAV（直接复用 _run_strategy_fund，零改动）。
#   - 安全腿 = 合成伪资产：每交易日固定收益 safe_annual/252，单调不降 → 回撤≈0。
#   - 两腿按目标权重 W 组合成一只“基金”，申购现金流与策略完全一致（W 只改内部配置、
#     不改外部投入时间表）→ XIRR/终值口径不变；回撤算在组合单位NAV上（真实体验）。
#   - W=0 时组合单位NAV 精确等于策略单位NAV（零回归基线，恒等，已在 sweep 内复用同一数组）。
#   维持 W 的再平衡 = 防御层纪律（独立于棘轮核心的只买不卖）：
#     rebal_days>=1 按固定周期拉回目标；rebal_band>0 仅当现金权重偏离目标≥band 才动
#     （漂移触发，交易次数远少于每日再平衡，机械化最划算）；两者满足其一即触发。
#   信号仍只走 core.engine；防御层是组合层 overlay，未进 compute_ladder。定方案后
#   再把“目标权重 + 偏离判定”移植进 core 做实盘同源（与 C7 同一条路线）。
# ===========================================================================
def _run_defensive_fund(grid, risky_nav, flows, safe_annual: float,
                        w_safe: float, rebal_days: int, rebal_band: float,
                        w_safe_series=None, *, trade_cost_bps: float = 0.0,
                        execution_stats: dict | None = None):
    """把已验证的风险腿单位NAV(risky_nav)与固定收益安全腿，按目标权重组合成一只基金。
    申购现金流复用 flows(=策略的申购：上市cap + 按月注资，与权重无关)。
    w_safe_series=None：目标安全权重恒为 w_safe（静态防御层，与原实现逐位一致）；
    w_safe_series 提供时：每日目标安全权重 = w_safe_series[i]（动态防御层，如 vol-target lite），
      此时只按执行带 rebal_band 漂移触发再平衡（目标每日微动、偏离≥执行带才 snap → 节流换手）。
    返回 (nav, equity, flow_by_index, turnover, n_rebal)。
    turnover = 累计两腿间调拨额；n_rebal = 再平衡发生次数（用于看交易摩擦/机械化成本）。"""
    n = len(grid)
    rr = np.zeros(n)                       # 风险腿日收益（单位NAV口径，与投入额无关）
    for i in range(1, n):
        prev = risky_nav[i - 1]
        rr[i] = (risky_nav[i] / prev - 1.0) if prev > 0 else 0.0
    rs = safe_annual / 252.0               # 安全腿每交易日固定收益（单调 → 回撤≈0）

    flow_by_i = {}
    for i, amt in flows:
        flow_by_i[i] = flow_by_i.get(i, 0.0) + amt

    risky_val = 0.0
    safe_val = 0.0
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    actual_safe_weights = np.zeros(n)
    turnover = 0.0
    cost_paid = 0.0
    n_rebal = 0
    P = int(rebal_days) if (rebal_days and rebal_days >= 1) else 0
    trade_cost = max(0.0, float(trade_cost_bps)) / 10000.0

    for i in range(n):
        if i > 0:                          # 先按当日收益给两腿计值（mark-to-close）
            risky_val *= (1.0 + rr[i])
            safe_val *= (1.0 + rs)
        tv_pre = risky_val + safe_val
        nav_b = (tv_pre / units) if units > 0 else 1.0
        # 当日目标安全权重：动态序列(w_safe_series)优先，否则常数 w_safe。
        # 动态序列=None 时下面每一步都退化为原静态实现（守静态零回归）。
        w_tgt = float(w_safe_series[i]) if w_safe_series is not None else w_safe
        amt = flow_by_i.get(i, 0.0)        # 当日申购：按当日目标权重切分进两腿
        if amt:
            units += amt / nav_b
            risky_val += amt * (1.0 - w_tgt)
            safe_val += amt * w_tgt
        # 维持目标权重的再平衡，决策统一交给 core.engine.compute_defensive_rebalance（实盘同源）：
        #   静态(w_safe_series=None)：周期到点(due, band=0 拉回) 或 rebal_band 漂移触发；
        #   动态(w_safe_series 提供)：目标=当日 w_tgt，仅按执行带 rebal_band 漂移触发
        #     （目标每日微动、偏离≥执行带才 snap → 节流换手；这正是 vol-target lite 的落地方式）。
        # move>0 减仓风险腿/增厚安全腿；move<0 回补风险腿/减薄安全腿（组合总额守恒）。
        if i > 0:
            if w_safe_series is not None:
                move = eng.compute_defensive_rebalance(risky_val, safe_val, w_tgt, rebal_band)
            else:
                due = bool(P and (i % P == 0))
                if due:
                    move = eng.compute_defensive_rebalance(risky_val, safe_val, w_safe, 0.0)
                elif rebal_band > 0:
                    move = eng.compute_defensive_rebalance(risky_val, safe_val, w_safe, rebal_band)
                else:
                    move = None
            if move is not None:
                turnover += abs(move)
                cost = abs(move) * trade_cost
                safe_val += move
                risky_val -= move
                if move > 0:
                    safe_val -= cost
                else:
                    risky_val -= cost
                cost_paid += cost
                n_rebal += 1
        tv = risky_val + safe_val
        equity[i] = tv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
        actual_safe_weights[i] = safe_val / tv if tv > 0 else 0.0
    if execution_stats is not None:
        execution_stats.update({
            "turnover": float(turnover),
            "cost_paid": float(cost_paid),
            "n_rebal": int(n_rebal),
            "trade_cost_bps": float(trade_cost_bps),
            "actual_safe_weight_series": actual_safe_weights,
        })
    return nav, equity, flow_by_i, turnover, n_rebal


def run_defensive_sweep(cfg, monthly: float = 0.0,
                        weights=(0.0, 0.10, 0.20, 0.30, 0.40, 0.50),
                        safe_annual: float = 0.04, rebal_days: int = 21,
                        rebal_band: float = 0.0,
                        skip_missing: bool = True, strict: bool = False):
    """防御层扫描：固定篮子，扫安全资产权重 W → (回撤, XIRR, 终值) 曲线。
    风险腿复用已验证 _run_strategy_fund（跑一次给所有 W 复用）；W=0 即策略基线（恒等）。
    返回 dict：rows=[(w, metrics)...], bench=即时全仓基准, base_maxdd=策略基线回撤, 等。"""
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    # 风险腿（已验证路径）+ 即时全仓基准（参考板块回撤）
    pf, r_nav, r_eq, r_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    b_nav, b_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    contributed = sum(a for _, a in flows)

    def metrics(navc, eqc, turnover=0.0, n_rebal=0):
        cf = [(grid[i].date(), -a) for i, a in flows]
        cf.append((grid[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        return {"mult": float(eqc[-1] / contributed) if contributed else None,
                "final": float(eqc[-1]), "xirr": M.xirr(cf),
                "maxdd": M.max_drawdown(navc), "sharpe": M.sharpe(ret),
                "sortino": M.sortino(ret),
                "turnover_x": (turnover / contributed) if contributed else None,
                "n_rebal": int(n_rebal)}

    rows = []
    for w in weights:
        if w <= 0.0:
            rows.append((w, metrics(r_nav, r_eq)))          # W=0：策略基线（零回归）
        else:
            nav_w, eq_w, _, turn, nrb = _run_defensive_fund(
                grid, r_nav, flows, safe_annual, w, rebal_days, rebal_band)
            rows.append((w, metrics(nav_w, eq_w, turn, nrb)))

    cf = [(grid[i].date(), -a) for i, a in flows]
    cf.append((grid[-1].date(), float(b_eq[-1])))
    bench = {"mult": float(b_eq[-1] / contributed) if contributed else None,
             "final": float(b_eq[-1]), "xirr": M.xirr(cf),
             "maxdd": M.max_drawdown(b_nav)}
    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "rows": rows, "bench": bench,
            "base_maxdd": M.max_drawdown(r_nav), "safe_annual": safe_annual,
            "rebal_days": rebal_days, "rebal_band": rebal_band}


def run_nav_panel(cfg, monthly: float = 0.0, *,
                  safe_weight: float | None = None,
                  safe_annual: float = 0.04,
                  rebal_days: int = 21,
                  rebal_band: float = 0.0,
                  benchmark_tickers=("QQQ", "SPY"),
                  baseline_ticker: str = "QQQ",
                  skip_missing: bool = True,
                  strict: bool = False):
    """Dashboard 专用：输出单位 NAV 曲线与同一现金流下的 XIRR/终值。

    主策略线使用「棘轮风险腿 + W 安全腿」的防御后 NAV；纯棘轮只作为参照线。
    所有回撤/Sharpe/Sortino 都用 NAV，XIRR/终值倍数仍用真实权益与现金流。
    """
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    pf, risk_nav, risk_eq, risk_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    contributed = sum(a for _, a in flows)

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    if safe_weight > 0:
        strategy_nav, strategy_eq, _, turn, nrb = _run_defensive_fund(
            grid, risk_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
    else:
        strategy_nav, strategy_eq, turn, nrb = risk_nav, risk_eq, 0.0, 0

    def metric_block(navc, eqc, invested_curve=None, turnover=0.0, n_rebal=0,
                     flows_override=None):
        used_flows = list(flows_override) if flows_override is not None else flows
        used_contributed = sum(a for _, a in used_flows)
        cf = [(grid[i].date(), -a) for i, a in used_flows]
        cf.append((grid[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        out = {"final": float(eqc[-1]),
               "mult": float(eqc[-1] / used_contributed) if used_contributed else None,
               "xirr": M.xirr(cf),
               "maxdd": M.max_drawdown(navc),
               "sharpe": M.sharpe(ret),
               "sortino": M.sortino(ret),
               "turnover_x": (turnover / used_contributed) if used_contributed else None,
               "n_rebal": int(n_rebal)}
        if invested_curve is not None:
            denom = np.where(eqc > 0, eqc, 1)
            out["avg_invested"] = float(np.mean(invested_curve / denom))
        return out

    strategy_label = f"策略+防御层(W={safe_weight:.0%})" if safe_weight > 0 else "策略"
    curves = {
        strategy_label: {"nav": strategy_nav, "equity": strategy_eq,
                         "metrics": metric_block(strategy_nav, strategy_eq, None, turn, nrb)},
        "纯棘轮": {"nav": risk_nav, "equity": risk_eq,
                   "metrics": metric_block(risk_nav, risk_eq, risk_inv)},
    }

    benchmark_errors = {}
    for ticker in benchmark_tickers:
        tk = str(ticker).upper()
        label = _benchmark_label(tk)
        try:
            bclose, bmeta = _fetch_benchmark_close(tk, cfg, grid)
            run_close, bench_flows, start_i = _benchmark_run_inputs(bclose, flows)
            bnav, beq = _run_single_asset_fund(grid, run_close, bench_flows)
            metrics = metric_block(bnav, beq, flows_override=bench_flows)
            if start_i > 0:
                metrics["start"] = grid[start_i].strftime("%Y-%m-%d")
                metrics["availability_note"] = "基准成立前不回填；此前曲线为空。"
                bnav = bnav.copy()
                beq = beq.copy()
                bnav[:start_i] = np.nan
                beq[:start_i] = np.nan
            curve_item = {"nav": bnav, "equity": beq,
                          "metrics": metrics,
                          "source": getattr(bmeta, "source", "?")}
            version = data_version_payload(
                bmeta,
                used_start=metrics.get("start") or grid[0].strftime("%Y-%m-%d"),
                used_end=grid[-1].strftime("%Y-%m-%d"),
            )
            if version.get("version_id"):
                curve_item["data_version"] = version
            curves[label] = curve_item
        except Exception as e:
            benchmark_errors[label] = str(e)

    baseline_label = _benchmark_label(baseline_ticker)
    if baseline_label not in curves:
        baseline_label = "纳指100(QQQ)" if "纳指100(QQQ)" in curves else strategy_label

    return {"grid": grid, "coverage": coverage, "dropped": dropped,
            "contributed": contributed, "curves": curves,
            "strategy_label": strategy_label, "risk_label": "纯棘轮",
            "baseline_label": baseline_label,
            "safe_weight": safe_weight, "safe_annual": safe_annual,
            "rebal_days": rebal_days, "rebal_band": rebal_band,
            "data_versions": {
                name: item["data_version"]
                for name, item in curves.items() if item.get("data_version")
            },
            "tier_contrib": {
                i: {"amount": sum(f.amount for st in pf.symbols.values()
                                  for f in st.fires if f.tier_index == i),
                    "count": sum(1 for st in pf.symbols.values()
                                 for f in st.fires if f.tier_index == i)}
                for i in sorted({f.tier_index for st in pf.symbols.values() for f in st.fires})
            },
            "benchmark_errors": benchmark_errors}


def run_rolling_start_panel(cfg, monthly: float = 0.0, *,
                            min_years: float = 3.0,
                            safe_weight: float | None = None,
                            safe_annual: float = 0.04,
                            rebal_days: int = 21,
                            rebal_band: float = 0.0,
                            benchmark_tickers=("QQQ", "SPY"),
                            baseline_ticker: str = "QQQ",
                            skip_missing: bool = True,
                            strict: bool = False):
    """每月起点重跑同源 NAV 回测，输出超额收益/回撤改善的分布。

    这里不是简单切全程 NAV 曲线，而是从每个起点重新建一只“基金”：
    已上市标的在窗口首日投入初始 cap，未上市标的等自身上市日错峰并入；
    外部基准复用同一申购现金流，保证 XIRR、终值倍数和 NAV-DD 可比。
    """
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    sl = getattr(cfg, "safe_leg", None)
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    safe_weight = float(safe_weight or 0.0)

    min_len = max(2, int(float(min_years) * 252))
    start_idx = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            start_idx.append(i)

    benchmark_errors = {}
    benchmark_close = {}
    for ticker in benchmark_tickers:
        tk = str(ticker).upper()
        label = _benchmark_label(tk)
        try:
            close, meta = _fetch_benchmark_close(tk, cfg, grid)
            version_start_i = _first_valid_price_i(close)
            version = data_version_payload(
                meta,
                used_start=(
                    grid[version_start_i].strftime("%Y-%m-%d")
                    if version_start_i is not None else None
                ),
                used_end=grid[-1].strftime("%Y-%m-%d"),
            )
            benchmark_close[label] = {
                "close": close,
                "source": getattr(meta, "source", "?"),
                "data_version": version if version.get("version_id") else None,
            }
        except Exception as e:
            benchmark_errors[label] = str(e)

    baseline_label = _benchmark_label(str(baseline_ticker).upper())
    if baseline_label not in benchmark_close and benchmark_close:
        baseline_label = next(iter(benchmark_close.keys()))

    def metric_block(grid2, navc, eqc, flows, contributed, turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        return {"final": float(eqc[-1]),
                "mult": float(eqc[-1] / contributed) if contributed else None,
                "xirr": M.xirr(cf),
                "maxdd": M.max_drawdown(navc),
                "sharpe": M.sharpe(ret),
                "sortino": M.sortino(ret),
                "turnover_x": (turnover / contributed) if contributed else None,
                "n_rebal": int(n_rebal)}

    rows = []
    for si in start_idx:
        base_item = benchmark_close.get(baseline_label)
        if base_item is not None:
            base_px = float(base_item["close"][si])
            if not np.isfinite(base_px) or base_px <= 0:
                continue
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue

        panels2 = {
            t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
            for t in alive
        }
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}

        _, risk_nav, risk_eq, risk_inv, flows = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed = sum(a for _, a in flows)
        if contributed <= 0:
            continue

        if safe_weight > 0:
            strategy_nav, strategy_eq, _, turn, nrb = _run_defensive_fund(
                grid2, risk_nav, flows, safe_annual, safe_weight, rebal_days, rebal_band)
        else:
            strategy_nav, strategy_eq, turn, nrb = risk_nav, risk_eq, 0.0, 0

        strategy = metric_block(grid2, strategy_nav, strategy_eq, flows, contributed, turn, nrb)
        benchmarks = {}
        for label, item in benchmark_close.items():
            first_px = float(item["close"][si])
            if not np.isfinite(first_px) or first_px <= 0:
                continue
            bnav, beq = _run_single_asset_fund(grid2, item["close"][si:], flows)
            benchmarks[label] = metric_block(grid2, bnav, beq, flows, contributed)
            benchmarks[label]["source"] = item["source"]

        baseline = benchmarks.get(baseline_label)
        excess_xirr = None
        dd_relief = None
        if baseline:
            if strategy["xirr"] is not None and baseline["xirr"] is not None:
                excess_xirr = strategy["xirr"] - baseline["xirr"]
            if strategy["maxdd"] is not None and baseline["maxdd"] is not None:
                dd_relief = baseline["maxdd"] - strategy["maxdd"]

        rows.append({
            "start": grid2[0].strftime("%Y-%m-%d"),
            "end": grid2[-1].strftime("%Y-%m-%d"),
            "years": float((grid2[-1] - grid2[0]).days / 365.25),
            "strategy": strategy,
            "benchmarks": benchmarks,
            "baseline": baseline_label if baseline else None,
            "excess_xirr": excess_xirr,
            "dd_relief": dd_relief,
        })

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def qs(vals):
        return {"p10": q(vals, 0.10), "p50": q(vals, 0.50), "p90": q(vals, 0.90)}

    excess = [r["excess_xirr"] for r in rows]
    relief = [r["dd_relief"] for r in rows]
    valid_excess = [v for v in excess if v is not None and np.isfinite(v)]
    valid_relief = [v for v in relief if v is not None and np.isfinite(v)]

    summary = {
        "windows": len(rows),
        "baseline": baseline_label if benchmark_close else None,
        "min_years": float(min_years),
        "strategy_xirr": qs([r["strategy"]["xirr"] for r in rows]),
        "strategy_maxdd": qs([r["strategy"]["maxdd"] for r in rows]),
        "strategy_mult": qs([r["strategy"]["mult"] for r in rows]),
        "benchmark_xirr": qs([
            (r.get("benchmarks", {}).get(baseline_label) or {}).get("xirr")
            for r in rows
        ]),
        "benchmark_maxdd": qs([
            (r.get("benchmarks", {}).get(baseline_label) or {}).get("maxdd")
            for r in rows
        ]),
        "excess_xirr": qs(excess),
        "dd_relief": qs(relief),
        "win_rate": (sum(1 for v in valid_excess if v > 0) / len(valid_excess))
        if valid_excess else None,
        "dd_win_rate": (sum(1 for v in valid_relief if v > 0) / len(valid_relief))
        if valid_relief else None,
    }

    return {"coverage": coverage, "dropped": dropped, "rows": rows, "summary": summary,
            "strategy_label": f"策略+防御层(W={safe_weight:.0%})" if safe_weight > 0 else "策略",
            "safe_weight": safe_weight, "safe_annual": safe_annual,
            "rebal_days": rebal_days, "rebal_band": rebal_band,
            "data_versions": {
                name: item["data_version"]
                for name, item in benchmark_close.items() if item.get("data_version")
            },
            "benchmark_errors": benchmark_errors}


def run_rolling_voltarget_panel(cfg, monthly: float = 0.0, *,
                                min_years: float = 3.0,
                                safe_annual: float = 0.04,
                                target_vol: float = None,
                                base_w: float = None,
                                band: float = None,
                                vol_win: int = None,
                                exec_band: float = None,
                                benchmark_tickers=("QQQ", "SPY"),
                                baseline_ticker: str = "QQQ",
                                skip_missing: bool = True,
                                strict: bool = False):
    """Rolling-start validation for the vol-target defensive overlay.

    This mirrors ``run_rolling_start_panel`` but replaces static W with the
    existing vol-target lite overlay. It is research-only and uses only prior
    realized volatility at each date when deriving the daily target safe weight.
    """
    d = VOLTARGET_DEFAULTS
    target_vol = d["target_vol"] if target_vol is None else target_vol
    base_w = d["base_w"] if base_w is None else base_w
    band = d["band"] if band is None else band
    vol_win = d["vol_win"] if vol_win is None else vol_win
    exec_band = d["exec_band"] if exec_band is None else exec_band

    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    min_len = max(2, int(float(min_years) * 252))
    start_idx = []
    seen_months = set()
    for i, d0 in enumerate(grid):
        key = (int(d0.year), int(d0.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            start_idx.append(i)

    benchmark_errors = {}
    benchmark_close = {}
    for ticker in benchmark_tickers:
        tk = str(ticker).upper()
        label = _benchmark_label(tk)
        try:
            close, meta = _fetch_benchmark_close(tk, cfg, grid)
            version_start_i = _first_valid_price_i(close)
            version = data_version_payload(
                meta,
                used_start=(
                    grid[version_start_i].strftime("%Y-%m-%d")
                    if version_start_i is not None else None
                ),
                used_end=grid[-1].strftime("%Y-%m-%d"),
            )
            benchmark_close[label] = {
                "close": close,
                "source": getattr(meta, "source", "?"),
                "data_version": version if version.get("version_id") else None,
            }
        except Exception as e:
            benchmark_errors[label] = str(e)

    baseline_label = _benchmark_label(str(baseline_ticker).upper())
    if baseline_label not in benchmark_close and benchmark_close:
        baseline_label = next(iter(benchmark_close.keys()))

    def metric_block(grid2, navc, eqc, flows, contributed, turnover=0.0, n_rebal=0):
        cf = [(grid2[i].date(), -a) for i, a in flows]
        cf.append((grid2[-1].date(), float(eqc[-1])))
        ret = M.returns_from_equity(navc)
        return {"final": float(eqc[-1]),
                "mult": float(eqc[-1] / contributed) if contributed else None,
                "xirr": M.xirr(cf),
                "maxdd": M.max_drawdown(navc),
                "sharpe": M.sharpe(ret),
                "sortino": M.sortino(ret),
                "turnover_x": (turnover / contributed) if contributed else None,
                "n_rebal": int(n_rebal)}

    rows = []
    for si in start_idx:
        base_item = benchmark_close.get(baseline_label)
        if base_item is not None:
            base_px = float(base_item["close"][si])
            if not np.isfinite(base_px) or base_px <= 0:
                continue
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si and t in caps]
        if not alive:
            continue

        panels2 = {
            t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
            for t in alive
        }
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}
        caps2 = {t: caps[t] for t in alive}

        _, risk_nav, risk_eq, risk_inv, flows = _run_strategy_fund(
            grid2, panels2, listing2, last2, caps2, monthly, cfg)
        contributed = sum(a for _, a in flows)
        if contributed <= 0:
            continue
        signal_nav, _ = _run_fullinvest_fund(grid2, panels2, listing2, last2, caps2, monthly)
        wser = _vol_target_weight_series(signal_nav, target_vol, base_w, band, vol_win)
        strategy_nav, strategy_eq, _, turn, nrb = _run_defensive_fund(
            grid2, risk_nav, flows, safe_annual, base_w, 0, exec_band, w_safe_series=wser)
        strategy = metric_block(grid2, strategy_nav, strategy_eq, flows, contributed, turn, nrb)
        strategy["avg_safe_weight"] = float(np.mean(wser[1:])) if len(wser) > 1 else float(wser[0])

        benchmarks = {}
        for label, item in benchmark_close.items():
            first_px = float(item["close"][si])
            if not np.isfinite(first_px) or first_px <= 0:
                continue
            bnav, beq = _run_single_asset_fund(grid2, item["close"][si:], flows)
            benchmarks[label] = metric_block(grid2, bnav, beq, flows, contributed)
            benchmarks[label]["source"] = item["source"]

        baseline = benchmarks.get(baseline_label)
        excess_xirr = None
        dd_relief = None
        if baseline:
            if strategy["xirr"] is not None and baseline["xirr"] is not None:
                excess_xirr = strategy["xirr"] - baseline["xirr"]
            if strategy["maxdd"] is not None and baseline["maxdd"] is not None:
                dd_relief = baseline["maxdd"] - strategy["maxdd"]

        rows.append({
            "start": grid2[0].strftime("%Y-%m-%d"),
            "end": grid2[-1].strftime("%Y-%m-%d"),
            "years": float((grid2[-1] - grid2[0]).days / 365.25),
            "strategy": strategy,
            "benchmarks": benchmarks,
            "baseline": baseline_label if baseline else None,
            "excess_xirr": excess_xirr,
            "dd_relief": dd_relief,
        })

    def q(vals, p):
        arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
        return float(np.quantile(arr, p)) if len(arr) else None

    def qs(vals):
        return {"p10": q(vals, 0.10), "p50": q(vals, 0.50), "p90": q(vals, 0.90)}

    excess = [r["excess_xirr"] for r in rows]
    relief = [r["dd_relief"] for r in rows]
    valid_excess = [v for v in excess if v is not None and np.isfinite(v)]
    valid_relief = [v for v in relief if v is not None and np.isfinite(v)]
    summary = {
        "windows": len(rows),
        "baseline": baseline_label if benchmark_close else None,
        "min_years": float(min_years),
        "strategy_xirr": qs([r["strategy"]["xirr"] for r in rows]),
        "strategy_maxdd": qs([r["strategy"]["maxdd"] for r in rows]),
        "strategy_mult": qs([r["strategy"]["mult"] for r in rows]),
        "benchmark_xirr": qs([
            (r.get("benchmarks", {}).get(baseline_label) or {}).get("xirr")
            for r in rows
        ]),
        "benchmark_maxdd": qs([
            (r.get("benchmarks", {}).get(baseline_label) or {}).get("maxdd")
            for r in rows
        ]),
        "avg_safe_weight": qs([r["strategy"].get("avg_safe_weight") for r in rows]),
        "turnover_x": qs([r["strategy"].get("turnover_x") for r in rows]),
        "n_rebal": qs([r["strategy"].get("n_rebal") for r in rows]),
        "excess_xirr": qs(excess),
        "dd_relief": qs(relief),
        "win_rate": (sum(1 for v in valid_excess if v > 0) / len(valid_excess))
        if valid_excess else None,
        "dd_win_rate": (sum(1 for v in valid_relief if v > 0) / len(valid_relief))
        if valid_relief else None,
    }
    return {"coverage": coverage, "dropped": dropped, "rows": rows, "summary": summary,
            "strategy_label": "策略+vol-target动态防御层",
            "safe_annual": safe_annual,
            "benchmark_errors": benchmark_errors,
            "data_versions": {
                name: item["data_version"]
                for name, item in benchmark_close.items() if item.get("data_version")
            },
            "params": {"target_vol": target_vol, "base_w": base_w, "band": band,
                       "vol_win": vol_win, "exec_band": exec_band}}


# ===========================================================================
# A 方向：vol-target lite 动态防御层（把"回撤↔年化"前沿往外推的唯一过样本外的杠杆）。
# 机理：用快波动信号(20d)在静态基线 W 附近微调安全权重——波动飙升(常先于回撤)→ 增厚安全腿、
# 波动平静 → 减薄。快信号是边际来源(尖峰转瞬即逝)，慢信号会错过；换手用"执行带 snap"节流。
# 同源：动态目标权重仍只经 core.engine.compute_defensive_rebalance 决策(实盘据此对篮子+安全腿
# 挂单)，与静态防御层同一条函数。信号取即时全仓基准NAV(b_nav)，非自身overlay → 不自循环。
# 诚实保留：①等权 XSD 上此 overlay 为负 → 边际绑定具体成分；②全在 2018-26 同一牛市区间。
# 下面的固化参数是 2018-26 全程 + 样本外切分(A:18-21 / B:22-26)共同为正中选出的甜点。
# ===========================================================================
VOLTARGET_DEFAULTS = {
    "target_vol": 0.25,   # 年化目标波动（风险仓位 = clip(target_vol/实现波动, 0, 1)）
    "base_w": 0.40,       # 静态基线安全权重（定回撤档；动态在此上下微调）
    "band": 0.15,         # 目标权重钳制带（安全权重 ∈ base ± band，即 [0.25, 0.55]）
    "vol_win": 20,        # 实现波动回看窗（交易日；快信号是边际来源，勿放慢）
    "exec_band": 0.15,    # 执行带（安全权重偏离当日目标 ≥ 此值才 snap）。引擎真实模型(两腿漂移)下
                          # 调出的甜点：0.15 与 0.05 同等边际(+0.7pp全程/样本外两窗+1.9/+1.1)，
                          # 但换手砍半(12.3x vs 28.4x ≈ 每年1.5次)，是纯成本旋钮、不动收益参数。
}


def _vol_target_weight_series(signal_nav, target_vol, base_w, band, vol_win):
    """由信号NAV(基准/价格指数，非自身overlay)算每日目标安全权重(vol-target lite)。
    用 i-1 截止的滚动年化波动决策今日目标(无前视)：
        风险仓位 = clip(target_vol / 实现年化波动, 0, 1)
        目标安全权重 = clip(1 - 风险仓位, base_w - band, base_w + band)
    返回长度 n 的目标安全权重数组（喂给 _run_defensive_fund 的 w_safe_series）。"""
    n = len(signal_nav)
    rets = np.zeros(n)
    rets[1:] = signal_nav[1:] / signal_nav[:-1] - 1.0
    rv = pd.Series(rets).rolling(int(vol_win)).std().to_numpy() * np.sqrt(252.0)
    w = np.empty(n)
    w[0] = base_w
    for i in range(1, n):
        v = rv[i - 1]
        risky_w = 1.0 if (np.isnan(v) or v <= 0) else float(np.clip(target_vol / v, 0.0, 1.0))
        w[i] = float(np.clip(1.0 - risky_w, base_w - band, base_w + band))
    return w


def run_voltarget_sweep(cfg, monthly: float = 0.0, *,
                        static_weights=(0.0, 0.20, 0.30, 0.40, 0.50, 0.60),
                        safe_annual: float = 0.04,
                        target_vol: float = None, base_w: float = None,
                        band: float = None, vol_win: int = None, exec_band: float = None,
                        oos_split: str = "2022-01-01", benchmark_ticker: str = None,
                        skip_missing: bool = True, strict: bool = False):
    """vol-target lite 评估（A 方向）：在引擎真实模型(两腿漂移 + 执行带 snap)下，把动态防御层
    与静态 W 前沿放在【同回撤】口径对比，量化"前沿外推多少 pp"；并按 oos_split 做样本外切分。
    风险腿复用已验证 _run_strategy_fund；信号取即时全仓基准 NAV。参数 None → 用 VOLTARGET_DEFAULTS。"""
    d = VOLTARGET_DEFAULTS
    target_vol = d["target_vol"] if target_vol is None else target_vol
    base_w = d["base_w"] if base_w is None else base_w
    band = d["band"] if band is None else band
    vol_win = d["vol_win"] if vol_win is None else vol_win
    exec_band = d["exec_band"] if exec_band is None else exec_band

    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}
    _, r_nav, r_eq, _, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    b_nav, b_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)
    contributed = sum(a for _, a in flows)
    n = len(grid)

    wser = _vol_target_weight_series(b_nav, target_vol, base_w, band, vol_win)
    avg_w = float(np.mean(wser[1:]))

    # 各静态 W 的全程 (nav, eq)（缓存，供同回撤插值 + OOS 切片复用）
    static = {}
    for w in static_weights:
        if w <= 0.0:
            static[w] = (r_nav, r_eq)
        else:
            nav_w, eq_w, _, _, _ = _run_defensive_fund(grid, r_nav, flows, safe_annual, w, 0, exec_band)
            static[w] = (nav_w, eq_w)
    vt_nav, vt_eq, _, vt_turn, vt_nrebal = _run_defensive_fund(
        grid, r_nav, flows, safe_annual, base_w, 0, exec_band, w_safe_series=wser)

    def block(nav, eq, turn=0.0, nrebal=0):
        cf = [(grid[i].date(), -a) for i, a in flows]
        cf.append((grid[-1].date(), float(eq[-1])))
        ret = M.returns_from_equity(nav)
        return {"maxdd": M.max_drawdown(nav), "xirr": M.xirr(cf),
                "mult": float(eq[-1] / contributed) if contributed else None,
                "final": float(eq[-1]), "sharpe": M.sharpe(ret), "sortino": M.sortino(ret),
                "turnover_x": (turn / contributed) if contributed else None, "n_rebal": int(nrebal)}

    static_rows = [(w, block(*static[w])) for w in static_weights]
    vt_row = block(vt_nav, vt_eq, vt_turn, vt_nrebal)

    def interp_xirr(rows, dd):
        pp = sorted((m["maxdd"], m["xirr"]) for _, m in rows if m["xirr"] is not None)
        if not pp:
            return None
        if dd <= pp[0][0]:
            return pp[0][1]
        if dd >= pp[-1][0]:
            return pp[-1][1]
        for (d0, c0), (d1, c1) in zip(pp, pp[1:]):
            if d0 <= dd <= d1 and d1 > d0:
                f = (dd - d0) / (d1 - d0)
                return c0 + f * (c1 - c0)
        return pp[-1][1]

    vt_excess = None
    base_at_dd = interp_xirr(static_rows, vt_row["maxdd"])
    if vt_row["xirr"] is not None and base_at_dd is not None:
        vt_excess = vt_row["xirr"] - base_at_dd

    # 样本外切分：各窗用单位NAV切片算 (maxdd, CAGR)，同回撤插值看超额（CAGR口径，便于跨窗）
    def seg_dd(nav, a, b):
        seg = nav[a:b]
        if len(seg) == 0:
            return 0.0
        pk = np.maximum.accumulate(seg)
        return float(np.max(1 - seg / np.where(pk > 0, pk, 1)))

    def seg_cagr(nav, a, b):
        seg = nav[a:b]
        if len(seg) < 2 or seg[0] <= 0:
            return None
        yrs = (len(seg) - 1) / 252.0
        return float((seg[-1] / seg[0]) ** (1 / yrs) - 1)

    oos = []
    if oos_split:
        cut = int(grid.searchsorted(pd.Timestamp(oos_split)))
        for lbl, a, b in [(f"A {grid[0].date()}~", 0, cut), (f"B ~{grid[-1].date()}", cut, n)]:
            sf = sorted((seg_dd(static[w][0], a, b), seg_cagr(static[w][0], a, b))
                        for w in static_weights if seg_cagr(static[w][0], a, b) is not None)
            vdd = seg_dd(vt_nav, a, b)
            vcg = seg_cagr(vt_nav, a, b)
            base = None
            if sf:
                if vdd <= sf[0][0]:
                    base = sf[0][1]
                elif vdd >= sf[-1][0]:
                    base = sf[-1][1]
                else:
                    for (d0, c0), (d1, c1) in zip(sf, sf[1:]):
                        if d0 <= vdd <= d1 and d1 > d0:
                            base = c0 + (vdd - d0) / (d1 - d0) * (c1 - c0)
                            break
            oos.append({"win": lbl, "days": b - a, "maxdd": vdd, "cagr": vcg,
                        "static_cagr_at_dd": base,
                        "excess": (vcg - base) if (vcg is not None and base is not None) else None})

    # 外部基准(如纳指100 QQQ)：放上同一(回撤,收益)平面 + 判定"你能否压制它"。
    def interp_w_at_dd(rows, dd):
        """在静态前沿上插值出"回撤=dd 对应的安全权重 W"（回答：基准那个回撤档你该挂多少现金腿）。"""
        pp = sorted((m["maxdd"], w) for w, m in rows)   # 按回撤升序: pp[0]=最浅(W最大), pp[-1]=最深(W最小)
        if dd <= pp[0][0]:
            return pp[0][1]          # 比最浅档还浅 → 取最大W端
        if dd >= pp[-1][0]:
            return pp[-1][1]         # 比最深档还深 → 取最小W端(通常0)
        for (d0, w0), (d1, w1) in zip(pp, pp[1:]):
            if d0 <= dd <= d1 and d1 > d0:
                f = (dd - d0) / (d1 - d0)
                return w0 + f * (w1 - w0)
        return pp[-1][1]

    bench = None
    if benchmark_ticker:
        try:
            bclose, bmeta = _fetch_benchmark_close(benchmark_ticker, cfg, grid)
            bnav, beq = _run_single_asset_fund(grid, bclose, flows)
            bench = block(bnav, beq)
            bench["ticker"] = benchmark_ticker.upper()
            bench["source"] = getattr(bmeta, "source", "?")
            # 战略两问：
            # (A) 比它赚得多？ 满仓篮子(W=0)的 XIRR vs 基准 XIRR
            w0_xirr = next((m["xirr"] for w, m in static_rows if w <= 0.0), None)
            bench["raw_beat"] = (w0_xirr - bench["xirr"]) if (w0_xirr is not None and bench["xirr"] is not None) else None
            # (B) 同回撤压制？ 在基准回撤档，静态前沿能给的 XIRR、对应所需 W、以及 vol-target 是否更优
            bench["static_xirr_at_dd"] = interp_xirr(static_rows, bench["maxdd"])
            bench["w_at_dd"] = interp_w_at_dd(static_rows, bench["maxdd"])
            bench["dominate_gap"] = (bench["static_xirr_at_dd"] - bench["xirr"]) \
                if (bench["static_xirr_at_dd"] is not None and bench["xirr"] is not None) else None
        except Exception as e:
            bench = {"ticker": benchmark_ticker.upper(), "error": str(e)}

    return {"grid": grid, "coverage": coverage, "dropped": dropped, "contributed": contributed,
            "static_rows": static_rows, "vt_row": vt_row, "vt_excess": vt_excess,
            "vt_base_at_dd": base_at_dd, "vt_avg_w": avg_w, "oos": oos, "bench": bench,
            "params": {"target_vol": target_vol, "base_w": base_w, "band": band,
                       "vol_win": vol_win, "exec_band": exec_band, "safe_annual": safe_annual},
            "bench_maxdd": M.max_drawdown(b_nav), "base_maxdd": M.max_drawdown(r_nav)}


def run_basket_voltarget_sweep(cfg, basket, monthly: float = 0.0, *,
                               skip_missing: bool = True, strict: bool = False, **kw):
    """用自定义篮子跑 vol-target lite 评估（symbol 注入与 run_basket_backtest 一致）。"""
    c = copy.deepcopy(cfg)
    c.symbols = _basket_to_symbols(basket, c.portfolio.core_ratio)
    return run_voltarget_sweep(c, monthly=monthly, skip_missing=skip_missing, strict=strict, **kw)


def run_staggered_backtest(cfg, monthly: float = 0.0,
                           skip_missing: bool = True, strict: bool = False
                           ) -> tuple[BacktestResult, list]:
    """错峰起算 + 单位NAV 回测。symbols 来自 cfg（run_basket_backtest 已塞好篮子）。
    返回 (BacktestResult, dropped_tickers)；summary 内含 'coverage' 逐标的覆盖。"""
    series, dropped = _fetch_series(cfg, skip_missing, strict)
    grid, panels, listing_i, last_i, coverage = _build_panels(
        series, cfg.data.start_date, cfg.data.end_date)
    caps = {s.ticker: s.cap_total for s in cfg.symbols if s.ticker in panels}

    pf, s_nav, s_eq, s_inv, flows = _run_strategy_fund(
        grid, panels, listing_i, last_i, caps, monthly, cfg)
    b_nav, b_eq = _run_fullinvest_fund(grid, panels, listing_i, last_i, caps, monthly)

    contributed = sum(amt for _, amt in flows)

    def xirr_of(final_value):
        cf = [(grid[i].date(), -amt) for i, amt in flows]
        cf.append((grid[-1].date(), float(final_value)))
        return M.xirr(cf)

    def block(navc, eqc, invc=None):
        r = {"final": float(eqc[-1]),
             "mult": float(eqc[-1] / contributed) if contributed else None,
             "xirr": xirr_of(eqc[-1]),
             "maxdd": M.max_drawdown(navc)}            # ← 真实回撤：单位净值口径
        ret = M.returns_from_equity(navc)               # 单位净值已剔注资 → 直接算日收益
        r["sharpe"] = M.sharpe(ret)
        r["sortino"] = M.sortino(ret)
        if invc is not None:
            denom = np.where(eqc > 0, eqc, 1)
            r["avg_invested"] = float(np.mean(invc / denom))
        return r

    summary = {
        "days": (grid[-1] - grid[0]).days,
        "contributed": contributed,
        "策略": block(s_nav, s_eq, s_inv),
        "即时全仓·权重": block(b_nav, b_eq),
        "coverage": coverage,
    }
    tier_contrib = {}
    for t, st in pf.symbols.items():
        for f in st.fires:
            tier_contrib.setdefault(f.tier_index, {"amount": 0.0, "count": 0})
            tier_contrib[f.tier_index]["amount"] += f.amount
            tier_contrib[f.tier_index]["count"] += 1
    summary["tier_contrib"] = tier_contrib

    fbi = {}
    for i, amt in flows:
        fbi[i] = fbi.get(i, 0.0) + amt

    res = BacktestResult(dates=grid, strat_equity=s_eq, strat_invested=s_inv,
                         strat_reserve=s_eq - s_inv, flow_by_index=fbi,
                         benchmarks={"即时全仓·权重": b_eq}, portfolio=pf, summary=summary)
    return res, dropped


def build_flow_schedule(dates, initial: dict, monthly: float,
                        monthly_split: dict | None = None) -> tuple[dict, dict]:
    """生成注资时间表。
    initial: {ticker: 初始本金}（t=0 建仓）
    monthly: 每月新增总额（按 cap 权重分到各标的）；monthly_split 可覆盖每只占比
    返回: (per_symbol_flows {ticker:{day_index:amount}}, total_flow_by_index {day_index:amount})
    """
    n = len(dates)
    per = {t: {} for t in initial}
    total = {}
    # 初始
    for t, amt in initial.items():
        per[t][0] = per[t].get(0, 0.0) + amt
        total[0] = total.get(0, 0.0) + amt
    # 每月（每 ~21 交易日）
    if monthly > 0:
        weights = monthly_split or {t: initial[t] / sum(initial.values()) for t in initial}
        for i in range(21, n, 21):
            for t in initial:
                amt = monthly * weights.get(t, 0.0)
                if amt > 0:
                    per[t][i] = per[t].get(i, 0.0) + amt
                    total[i] = total.get(i, 0.0) + amt
    return per, total


def run_backtest(cfg, initial: dict, monthly: float = 0.0,
                 monthly_split: dict | None = None,
                 prepared: tuple | None = None,
                 run_benchmarks: bool = True) -> BacktestResult:
    # prepared=(dates, px) 可复用已抓数据，避免扫描时重复打数据源
    if prepared is not None:
        dates, px = prepared
    else:
        dates, px, _ = _align_prices(cfg)
    n = len(dates)
    high_basis = cfg.portfolio.high_basis  # close / high (本回测用 close 对齐, high 退化为 close)
    per_flows, total_flows = build_flow_schedule(dates, initial, monthly, monthly_split)

    # 初始化各标的状态（t=0 建仓）
    pf = Portfolio(symbols={}, flows=[])
    date0 = dates[0].strftime("%Y-%m-%d")
    for t, amt0 in initial.items():
        st = eng.init_symbol(t, amt0, px["close"][t][0], cfg)
        pf.symbols[t] = st
        pf.flows.append(CashFlow(date=date0, amount=amt0, note="初始建仓"))

    strat_eq = np.zeros(n)
    strat_inv = np.zeros(n)
    strat_res = np.zeros(n)
    inflow_series = np.zeros(n)

    for i in range(n):
        d = dates[i]
        dstr = d.strftime("%Y-%m-%d")
        for t, st in pf.symbols.items():
            c = px["close"][t][i]
            o = px["open"][t][i]
            lo = px["low"][t][i]
            ref = c  # high_basis=close
            # 1) 到期分批核心买入（按当日收盘）
            eng.process_pending(st, c, i)
            # 2) 回测成交：先判当日档位是否触发（用昨日 H，本日 i>0 时 H 已是历史最高）
            if i > 0:
                eng.fire_tiers(st, o, lo, dstr, cfg)
            # 3) 注资（i>0 的计划注入；i==0 的初始已在建仓处理）
            if i > 0 and i in per_flows.get(t, {}):
                amt = per_flows[t][i]
                eng.apply_injection(st, amt, c, i, cfg)
                pf.flows.append(CashFlow(date=dstr, amount=amt, note="注资"))
                inflow_series[i] += amt
            # 4) 收盘后棘轮上调 H + re-arm（影响次日阶梯）
            eng.update_high(st, ref, cfg)
        prices_today = {t: px["close"][t][i] for t in pf.symbols}
        strat_eq[i] = pf.total_value(prices_today)
        strat_inv[i] = pf.total_invested(prices_today)
        strat_res[i] = pf.total_reserve()

    # 基准（扫描时可关，省算力）
    benches = {}
    if run_benchmarks:
        benches = {
            "即时全仓·权重": run_benchmark(px["close"], dates, total_flows, cfg, "fullinvest_cap"),
            "定投DCA·权重": run_benchmark(px["close"], dates, total_flows, cfg, "dca_cap",
                                       dca_days=cfg.portfolio.injection_ladder_spacing_days),
            "即时全仓·等权": run_benchmark(px["close"], dates, total_flows, cfg, "fullinvest_equal"),
        }

    summary = _summarize(dates, strat_eq, strat_inv, inflow_series, pf, benches, total_flows)
    return BacktestResult(dates=dates, strat_equity=strat_eq, strat_invested=strat_inv,
                          strat_reserve=strat_res, flow_by_index=total_flows,
                          benchmarks=benches, portfolio=pf, summary=summary)


def _xirr_for_curve(dates, equity, flow_by_index) -> float | None:
    """构造资金加权现金流：每笔注入为负、期末净值为正。"""
    flows = []
    for i, amt in sorted(flow_by_index.items()):
        flows.append((dates[i].date(), -amt))
    flows.append((dates[-1].date(), float(equity[-1])))
    return M.xirr(flows)


def _summarize(dates, strat_eq, strat_inv, inflow_series, pf, benches, total_flows) -> dict:
    days = (dates[-1] - dates[0]).days
    contributed = sum(total_flows.values())
    out = {"days": days, "contributed": contributed}

    def block(name, eq, invested_curve=None):
        r = {
            "final": float(eq[-1]),
            "mult": float(eq[-1] / contributed) if contributed else None,
            "xirr": _xirr_for_curve(dates, eq, total_flows),
            "maxdd": M.max_drawdown(eq),
        }
        ret = M.returns_from_equity(eq, inflow_series)
        r["sharpe"] = M.sharpe(ret)
        r["sortino"] = M.sortino(ret)
        if invested_curve is not None:
            denom = np.where(eq > 0, eq, 1)
            r["avg_invested"] = float(np.mean(invested_curve / denom))
        return r

    out["策略"] = block("策略", strat_eq, strat_inv)
    for name, eq in benches.items():
        out[name] = block(name, eq)

    # 档位贡献拆解
    tier_contrib = {}
    for t, st in pf.symbols.items():
        for f in st.fires:
            tier_contrib.setdefault(f.tier_index, {"amount": 0.0, "count": 0})
            tier_contrib[f.tier_index]["amount"] += f.amount
            tier_contrib[f.tier_index]["count"] += 1
    out["tier_contrib"] = tier_contrib
    return out
