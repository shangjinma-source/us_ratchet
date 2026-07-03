"""收益与风险指标。

核心：持续注资下用资金加权收益率（XIRR）为主，时间加权（CAGR）为辅。
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np


def _to_date(s) -> date:
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s)[:10])


def xirr(flows: list[tuple], guess: float = 0.1) -> float | None:
    """资金加权收益率。flows: [(date, amount), ...]，注入为负、期末价值为正。
    Newton 法求解 Σ cf/(1+r)^(days/365)=0；失败回退二分。"""
    if len(flows) < 2:
        return None
    d0 = _to_date(flows[0][0])
    times = [( _to_date(d) - d0).days / 365.0 for d, _ in flows]
    amts = [a for _, a in flows]
    if not (any(a > 0 for a in amts) and any(a < 0 for a in amts)):
        return None

    def npv(r):
        return sum(a / (1 + r) ** t for a, t in zip(amts, times))

    def dnpv(r):
        return sum(-t * a / (1 + r) ** (t + 1) for a, t in zip(amts, times))

    r = guess
    for _ in range(100):
        f = npv(r)
        df = dnpv(r)
        if abs(df) < 1e-12:
            break
        step = f / df
        r -= step
        if r <= -0.9999:
            r = -0.99
        if abs(step) < 1e-8:
            return r
    # 回退二分
    lo, hi = -0.99, 10.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-7:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def cagr(equity: np.ndarray, days: int) -> float | None:
    """时间加权年化（基于净值曲线首尾，注资会失真，仅作辅助）。"""
    if len(equity) < 2 or equity[0] <= 0 or days <= 0:
        return None
    years = days / 365.0
    if years <= 0:
        return None
    return (equity[-1] / equity[0]) ** (1 / years) - 1


def max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / np.where(peak > 0, peak, 1)
    return float(np.max(dd))


def sharpe(daily_ret: np.ndarray, rf_annual: float = 0.0) -> float | None:
    if len(daily_ret) < 2:
        return None
    rf_d = rf_annual / 252
    ex = daily_ret - rf_d
    sd = ex.std(ddof=1)
    if sd == 0:
        return None
    return float(ex.mean() / sd * math.sqrt(252))


def sortino(daily_ret: np.ndarray, rf_annual: float = 0.0) -> float | None:
    if len(daily_ret) < 2:
        return None
    rf_d = rf_annual / 252
    ex = daily_ret - rf_d
    downside = ex[ex < 0]
    dd = downside.std(ddof=1) if len(downside) > 1 else 0.0
    if dd == 0:
        return None
    return float(ex.mean() / dd * math.sqrt(252))


def returns_from_equity(equity: np.ndarray, external_flows: np.ndarray | None = None) -> np.ndarray:
    """由净值序列算日收益。external_flows[t]=当日注入（应剔除，避免注资被当成上涨）。"""
    eq = np.asarray(equity, dtype=float)
    prev = eq[:-1]
    cur = eq[1:]
    if external_flows is not None:
        cur = cur - external_flows[1:]   # 当日净值里减去当日注入
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(prev > 0, cur / prev - 1, 0.0)
    return r
