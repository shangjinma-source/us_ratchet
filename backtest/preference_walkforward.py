"""Point-in-time walk-forward research for grouped preference baskets.

This module is research-only.  It answers the missing question between a static
candidate basket and live execution: if the basket had been selected only from
history available at each rolling start, would it still beat the target
benchmark without taking materially deeper drawdown?
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from backtest import metrics as M
from backtest.engine import (
    _benchmark_label,
    _build_panels,
    _fetch_benchmark_close,
    _first_valid_price_i,
    _run_defensive_fund,
    _run_single_asset_fund,
    _run_strategy_fund,
)
from core import engine as eng
from data.versioning import data_version_payload
from backtest.preference import (
    COMPACT_TOP_NS,
    DEFAULT_GROUP,
    PREFERRED_MAX_HOLDINGS,
    _admission_note,
    _group_balanced,
    _group_counts,
    _weights_for,
    parse_preference_groups,
    parse_safe_weights,
)
from data.fetch import get_bars


DEFAULT_WALKFORWARD_MODES = (
    "top4_score_risk",
    "top6_score_risk",
    "top8_score_risk",
    "group_balanced_top4_score_risk",
    "group_balanced_top6_score_risk",
    "group_balanced_top8_score_risk",
    "all_score_risk",
)

DEFAULT_REBALANCE_MONTHS = (6, 12)


@dataclass(frozen=True)
class WalkForwardChoice:
    mode: str
    tickers: tuple[str, ...]
    weights: dict[str, float]
    construction: str
    weight_mode: str
    asof_date: str | None


def parse_walkforward_modes(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_WALKFORWARD_MODES)
    if isinstance(raw, str):
        parts = re.split(r"[,，;\s]+", raw.strip())
    else:
        parts = list(raw)
    out: list[str] = []
    seen = set()
    for part in parts:
        mode = str(part or "").strip().lower()
        if not mode:
            continue
        mode = mode.replace("attack_", "")
        mode = mode.replace("risk_weight", "score_risk")
        if mode not in seen:
            seen.add(mode)
            out.append(mode)
    return out or list(DEFAULT_WALKFORWARD_MODES)


def _research_cfg(cfg, local_only: bool):
    c = copy.deepcopy(cfg)
    if local_only:
        c.data.fallback_chain = ["local_cache"]
    return c


def _load_series(cfg, tickers: Iterable[str]) -> tuple[dict[str, pd.DataFrame], dict[str, dict], dict[str, str]]:
    series: dict[str, pd.DataFrame] = {}
    meta: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for ticker in sorted({str(t).upper().strip() for t in tickers if str(t).strip()}):
        try:
            df, m = get_bars(ticker, cfg)
        except Exception as e:
            errors[ticker] = str(e)
            continue
        series[ticker] = df[["Open", "High", "Low", "Close"]].copy()
        meta[ticker] = {
            "source": m.source,
            "start": m.start,
            "end": m.end,
            "rows": m.rows,
        }
    return series, meta, errors


def _ret(close: pd.Series, days: int) -> float | None:
    s = close.dropna()
    if len(s) <= days:
        return None
    first = float(s.iloc[-days - 1])
    last = float(s.iloc[-1])
    return last / first - 1.0 if first > 0 else None


def _ann_vol(close: pd.Series, days: int) -> float | None:
    r = close.dropna().pct_change(fill_method=None).dropna().tail(days)
    if len(r) < 60:
        return None
    return float(r.std(ddof=1) * np.sqrt(252.0))


def _maxdd(close: pd.Series, days: int) -> float | None:
    s = close.dropna().tail(days)
    if len(s) < 2:
        return None
    arr = s.to_numpy(dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = np.where(peak > 0, (peak - arr) / peak, 0.0)
    return float(np.nanmax(dd))


def _rank_pct(s: pd.Series, higher: bool = True) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    if not higher:
        x = -x
    return x.rank(pct=True).fillna(0.0)


def _metrics_asof(series: Mapping[str, pd.DataFrame], asof: pd.Timestamp,
                  *, lookback_days: int, min_history_days: int) -> pd.DataFrame:
    rows = []
    asof_date = pd.Timestamp(asof)
    for ticker, df in series.items():
        close = df["Close"]
        hist = close[close.index < asof_date].dropna()
        if len(hist) < int(min_history_days):
            continue
        days = min(int(lookback_days), max(1, len(hist) - 1))
        rows.append({
            "ticker": ticker,
            "ret_1y": _ret(hist, 252),
            "ret_3y": _ret(hist, days),
            "vol_3y": _ann_vol(hist, days),
            "dd_3y": _maxdd(hist, days),
            "history_days": int(len(hist)),
            "asof_date": hist.index[-1].strftime("%Y-%m-%d") if len(hist) else None,
            "error": None,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.set_index("ticker", drop=False)
    score = (
        _rank_pct(df["ret_3y"]) * 0.55
        + _rank_pct(df["ret_1y"]) * 0.25
        + _rank_pct(df["dd_3y"], higher=False) * 0.12
        + _rank_pct(df["vol_3y"], higher=False) * 0.08
    )
    df["attack_score"] = score
    return df


def _parse_top_n(mode: str) -> int | None:
    m = re.search(r"top(\d+)", mode)
    return int(m.group(1)) if m else None


def _choice_for_mode(mode: str, metrics: pd.DataFrame,
                     groups: Mapping[str, list[str]]) -> WalkForwardChoice | None:
    if metrics.empty:
        return None
    ranked = metrics.sort_values("attack_score", ascending=False)["ticker"].tolist()
    weight_mode = "equal" if mode.endswith("_equal") else "score_risk"

    if mode.startswith("all_"):
        tickers = ranked
        construction = "点时自选池全量"
    elif mode.startswith("group_balanced_top"):
        n = _parse_top_n(mode)
        if n is None or len(ranked) < n:
            return None
        tickers = _group_balanced(ranked, groups, metrics, n)
        construction = f"点时分组覆盖后按 attack_score 取前 {n}"
    elif mode.startswith("top"):
        n = _parse_top_n(mode)
        if n is None or len(ranked) < n:
            return None
        tickers = ranked[:n]
        construction = f"点时按 attack_score 取前 {n}"
    else:
        return None

    if len(tickers) < 2:
        return None
    if weight_mode == "equal":
        weights = {t: 1.0 / len(tickers) for t in tickers}
    else:
        weights = _weights_for(tickers, metrics, "score_risk")
    asof_date = None
    if "asof_date" in metrics and len(tickers):
        vals = [metrics.loc[t, "asof_date"] for t in tickers if t in metrics.index]
        vals = [v for v in vals if isinstance(v, str)]
        asof_date = max(vals) if vals else None
    return WalkForwardChoice(
        mode=mode,
        tickers=tuple(tickers),
        weights={t: float(weights[t]) for t in tickers if t in weights and float(weights[t]) > 0},
        construction=construction,
        weight_mode=weight_mode,
        asof_date=asof_date,
    )


def _monthly_start_indexes(grid: pd.DatetimeIndex, min_len: int, step_months: int) -> list[int]:
    start_idx = []
    seen_months = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        if len(grid) - i >= min_len:
            start_idx.append(i)
    step = max(1, int(step_months))
    return start_idx[::step]


def _metric_block(grid, navc, eqc, flows, contributed, turnover=0.0, n_rebal=0) -> dict:
    cf = [(grid[i].date(), -a) for i, a in flows]
    cf.append((grid[-1].date(), float(eqc[-1])))
    ret = M.returns_from_equity(navc)
    return {
        "final": float(eqc[-1]),
        "mult": float(eqc[-1] / contributed) if contributed else None,
        "xirr": M.xirr(cf),
        "maxdd": M.max_drawdown(navc),
        "sharpe": M.sharpe(ret),
        "sortino": M.sortino(ret),
        "turnover_x": (turnover / contributed) if contributed else None,
        "n_rebal": int(n_rebal),
    }


def _q(vals, p: float) -> float | None:
    arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
    return float(np.quantile(arr, p)) if len(arr) else None


def _qs(vals) -> dict:
    return {"p10": _q(vals, 0.10), "p50": _q(vals, 0.50), "p90": _q(vals, 0.90)}


def _selection_churn(prev: set[str] | None, current: set[str]) -> float | None:
    if prev is None or not prev or not current:
        return None
    return 1.0 - len(prev & current) / max(len(prev), len(current))


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (int(b.year) - int(a.year)) * 12 + (int(b.month) - int(a.month))


def _rebalance_indexes(grid: pd.DatetimeIndex, rebalance_months: int) -> list[int]:
    months = max(1, int(rebalance_months))
    out = [0]
    last = pd.Timestamp(grid[0])
    seen_months = {(int(last.year), int(last.month))}
    for i, d in enumerate(grid[1:], start=1):
        key = (int(d.year), int(d.month))
        if key in seen_months:
            continue
        seen_months.add(key)
        cur = pd.Timestamp(d)
        if _months_between(last, cur) >= months:
            out.append(i)
            last = cur
    return out


def _state_total_at(st, panels: Mapping[str, dict], idx: int, field: str = "close") -> float:
    px = float(panels[st.ticker][field][idx])
    return st.shares * px + st.reserve_cash + getattr(st, "pending_core_cash", 0.0)


def _symbols_value_at(symbols: Mapping[str, object], panels: Mapping[str, dict],
                      idx: int, field: str = "close") -> float:
    return sum(_state_total_at(st, panels, idx, field) for st in symbols.values())


def _symbols_market_value_at(symbols: Mapping[str, object], panels: Mapping[str, dict],
                             idx: int, field: str = "open") -> float:
    total = 0.0
    for st in symbols.values():
        px = float(panels[st.ticker][field][idx])
        total += st.shares * px
    return total


def _active_rotation_risk_leg(cfg, grid: pd.DatetimeIndex,
                              panels: Mapping[str, dict],
                              listing_i: Mapping[str, int],
                              last_i: Mapping[str, int],
                              series: Mapping[str, pd.DataFrame],
                              groups: Mapping[str, list[str]],
                              mode: str,
                              total_cap: float,
                              monthly: float,
                              *,
                              lookback_days: int,
                              min_history_days: int,
                              rebalance_months: int,
                              trade_cost_bps: float) -> tuple[np.ndarray, np.ndarray, list[tuple[int, float]], dict]:
    """Run an active-rotation risk sleeve.

    This is intentionally conservative research logic: at each rebalance date it
    liquidates the existing risk sleeve at the open, pays a cost on traded
    notional, then restarts ratchet states for the newly selected basket.  It is
    not a live-equivalent rule and must not be wired into /api/state.
    """
    n = len(grid)
    symbols = {}
    entry_i: dict[str, int] = {}
    units = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    flows: list[tuple[int, float]] = []
    rebalance_set = set(_rebalance_indexes(grid, rebalance_months))
    trade_cost = max(0.0, float(trade_cost_bps)) / 10000.0
    turnover = 0.0
    cost_paid = 0.0
    rebalance_count = 0
    failed_rebalances = 0
    selections = []
    prev_selection: set[str] | None = None

    def choose(abs_i: int) -> WalkForwardChoice | None:
        metrics = _metrics_asof(series, grid[abs_i], lookback_days=lookback_days,
                                 min_history_days=min_history_days)
        return _choice_for_mode(mode, metrics, groups)

    def active_symbols_at(idx: int) -> list[str]:
        return [t for t in symbols if listing_i.get(t, 0) <= idx <= last_i.get(t, n - 1)]

    for i in range(n):
        # External subscription happens before the day's allocation decision.
        tv_pre = _symbols_value_at(symbols, panels, i, "close") if symbols else 0.0
        nav_b = (tv_pre / units) if units > 0 else 1.0
        if i == 0:
            units += float(total_cap) / nav_b
            flows.append((i, float(total_cap)))

        if i in rebalance_set:
            choice = choose(i)
            if choice is None:
                failed_rebalances += 1
            else:
                alive = [t for t in choice.tickers if t in panels and last_i.get(t, -1) >= i]
                weight_sum = sum(choice.weights.get(t, 0.0) for t in alive)
                if len(alive) < 2 or weight_sum <= 0:
                    failed_rebalances += 1
                else:
                    had_symbols = bool(symbols)
                    gross_value = (
                        _symbols_value_at(symbols, panels, i, "open")
                        if had_symbols else float(total_cap)
                    )
                    sell_notional = _symbols_market_value_at(symbols, panels, i, "open") if had_symbols else 0.0
                    # Restarting ratchet states buys the new core sleeve; reserve is cash.
                    core_buy_notional = gross_value * float(cfg.portfolio.core_ratio) if had_symbols else 0.0
                    traded = sell_notional + core_buy_notional
                    cost = traded * trade_cost
                    deployable = max(0.0, gross_value - cost)
                    turnover += traded
                    cost_paid += cost
                    symbols = {}
                    entry_i = {}
                    for t in alive:
                        w = float(choice.weights.get(t, 0.0)) / weight_sum
                        px = float(panels[t]["open"][i])
                        if px <= 0 or not np.isfinite(px):
                            continue
                        symbols[t] = eng.init_symbol(t, deployable * w, px, cfg)
                        entry_i[t] = i
                    cur_selection = set(symbols)
                    selections.append({
                        "date": grid[i].strftime("%Y-%m-%d"),
                        "mode": mode,
                        "tickers": sorted(cur_selection),
                        "churn": _selection_churn(prev_selection, cur_selection),
                        "turnover": traded,
                        "cost": cost,
                    })
                    prev_selection = cur_selection
                    rebalance_count += 1

        if not symbols:
            equity[i] = equity[i - 1] if i > 0 else float(total_cap)
            nav[i] = (equity[i] / units) if units > 0 else 1.0
            continue

        dstr = grid[i].strftime("%Y-%m-%d")
        alive_held = active_symbols_at(i)
        monthly_due = (monthly > 0 and i > 0 and i % 21 == 0 and bool(alive_held))
        if monthly_due:
            tv_now = _symbols_value_at(symbols, panels, i, "close")
            nav_before_flow = (tv_now / units) if units > 0 else nav[i - 1] if i > 0 else 1.0
            units += float(monthly) / nav_before_flow
            flows.append((i, float(monthly)))

        wsum = sum(max(0.0, symbols[t].cap_total) for t in alive_held)
        for t in list(symbols):
            if not (listing_i.get(t, 0) <= i <= last_i.get(t, n - 1)):
                continue
            st = symbols[t]
            close = float(panels[t]["close"][i])
            open_ = float(panels[t]["open"][i])
            low = float(panels[t]["low"][i])
            eng.process_pending(st, close, i)
            if i > entry_i.get(t, i):
                eng.fire_tiers(st, open_, low, dstr, cfg)
            if monthly_due and wsum > 0:
                eng.apply_injection(st, float(monthly) * st.cap_total / wsum, close, i, cfg)
            eng.update_high(st, close, cfg)

        tv = _symbols_value_at(symbols, panels, i, "close")
        equity[i] = tv
        nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)

    stats = {
        "rebalance_months": int(rebalance_months),
        "trade_cost_bps": float(trade_cost_bps),
        "turnover": float(turnover),
        "cost_paid": float(cost_paid),
        "rebalance_count": int(rebalance_count),
        "failed_rebalances": int(failed_rebalances),
        "selection_churn_p50": _q([s.get("churn") for s in selections], 0.50),
        "selections": selections,
    }
    return nav, equity, flows, stats


def _rollup(mode: str, safe_weight: float, samples: list[dict],
            target: str, groups: Mapping[str, list[str]]) -> dict:
    excess = [s.get("excess_xirr") for s in samples]
    relief = [s.get("dd_relief") for s in samples]
    valid_excess = [v for v in excess if v is not None and np.isfinite(v)]
    valid_relief = [v for v in relief if v is not None and np.isfinite(v)]
    tickers = sorted({t for s in samples for t in (s.get("tickers") or [])})
    row = {
        "basket": mode,
        "construction": samples[0].get("construction") if samples else mode,
        "weight_mode": samples[0].get("weight_mode") if samples else None,
        "defense_mode": "static_safe_weight",
        "safe_weight": float(safe_weight),
        "n": float(np.mean([len(s.get("tickers") or []) for s in samples])) if samples else 0,
        "tickers_observed": tickers,
        "group_counts": _group_counts(tickers, groups),
        "windows": len(samples),
        "win_rate": (sum(1 for v in valid_excess if v > 0) / len(valid_excess)) if valid_excess else None,
        "dd_win_rate": (sum(1 for v in valid_relief if v > 0) / len(valid_relief)) if valid_relief else None,
        "excess_p50": _q(excess, 0.50),
        "excess_p10": _q(excess, 0.10),
        "excess_p90": _q(excess, 0.90),
        "dd_relief_p50": _q(relief, 0.50),
        "dd_relief_p10": _q(relief, 0.10),
        "dd_relief_p90": _q(relief, 0.90),
        "xirr_p50": _q([s.get("strategy", {}).get("xirr") for s in samples], 0.50),
        "maxdd_p50": _q([s.get("strategy", {}).get("maxdd") for s in samples], 0.50),
        "selection_churn_p50": _q([s.get("selection_churn") for s in samples], 0.50),
        "max_weight_p50": _q([s.get("max_weight") for s in samples], 0.50),
        "range": [samples[0]["start"], samples[-1]["start"]] if samples else None,
    }
    row["distribution"] = {
        "strategy_xirr": _qs([s.get("strategy", {}).get("xirr") for s in samples]),
        "strategy_maxdd": _qs([s.get("strategy", {}).get("maxdd") for s in samples]),
        "benchmark_xirr": _qs([s.get("benchmark", {}).get("xirr") for s in samples]),
        "benchmark_maxdd": _qs([s.get("benchmark", {}).get("maxdd") for s in samples]),
        "excess_xirr": _qs(excess),
        "dd_relief": _qs(relief),
    }
    row["admission"] = _admission_note(row, target)
    return row


def _best_rows(rows: list[dict]) -> dict:
    valid = [r for r in rows if r.get("windows")]
    if not valid:
        return {}
    best_return = max(valid, key=lambda r: (r.get("win_rate") or -1, r.get("excess_p50") or -9))
    best_balanced = max(valid, key=lambda r: (
        (r.get("excess_p50") or -9) - max(0.0, -(r.get("dd_relief_p50") or 0.0)) * 0.35,
        r.get("win_rate") or -1,
    ))
    best_drawdown = max(valid, key=lambda r: (
        r.get("dd_relief_p50") if r.get("dd_relief_p50") is not None else -9,
        r.get("excess_p50") or -9,
    ))
    compact = [r for r in valid if float(r.get("n") or 999) <= PREFERRED_MAX_HOLDINGS]
    best_compact = max(compact, key=lambda r: (
        r.get("win_rate") or -1,
        r.get("excess_p50") or -9,
        r.get("dd_relief_p50") or -9,
        -float(r.get("n") or 999),
    )) if compact else None
    return {
        "best_return": best_return,
        "best_balanced": best_balanced,
        "best_drawdown": best_drawdown,
        "best_compact": best_compact,
    }


def _rebalance_rollup(mode: str, rebalance_months: int, safe_weight: float,
                      trade_cost_bps: float, samples: list[dict],
                      target: str, groups: Mapping[str, list[str]]) -> dict:
    excess = [s.get("excess_xirr") for s in samples]
    relief = [s.get("dd_relief") for s in samples]
    valid_excess = [v for v in excess if v is not None and np.isfinite(v)]
    valid_relief = [v for v in relief if v is not None and np.isfinite(v)]
    tickers = sorted({t for s in samples for t in (s.get("tickers_observed") or [])})
    row = {
        "basket": f"{mode}_rebalance_{int(rebalance_months)}m",
        "base_mode": mode,
        "construction": f"点时动态重选；每 {int(rebalance_months)} 个月在自选池内重建风险腿",
        "weight_mode": "score_risk" if mode.endswith("score_risk") else "equal",
        "defense_mode": "active_rebalance_static_safe_weight",
        "safe_weight": float(safe_weight),
        "active_rebalance": True,
        "rebalance_months": int(rebalance_months),
        "trade_cost_bps": float(trade_cost_bps),
        "n": _q([s.get("avg_n_selected") for s in samples], 0.50),
        "tickers_observed": tickers,
        "group_counts": _group_counts(tickers, groups),
        "windows": len(samples),
        "win_rate": (sum(1 for v in valid_excess if v > 0) / len(valid_excess)) if valid_excess else None,
        "dd_win_rate": (sum(1 for v in valid_relief if v > 0) / len(valid_relief)) if valid_relief else None,
        "excess_p50": _q(excess, 0.50),
        "excess_p10": _q(excess, 0.10),
        "excess_p90": _q(excess, 0.90),
        "dd_relief_p50": _q(relief, 0.50),
        "dd_relief_p10": _q(relief, 0.10),
        "dd_relief_p90": _q(relief, 0.90),
        "xirr_p50": _q([s.get("strategy", {}).get("xirr") for s in samples], 0.50),
        "maxdd_p50": _q([s.get("strategy", {}).get("maxdd") for s in samples], 0.50),
        "selection_churn_p50": _q([s.get("selection_churn_p50") for s in samples], 0.50),
        "rotation_turnover_x_p50": _q([s.get("rotation_turnover_x") for s in samples], 0.50),
        "rotation_cost_x_p50": _q([s.get("rotation_cost_x") for s in samples], 0.50),
        "rebalance_count_p50": _q([s.get("rebalance_count") for s in samples], 0.50),
        "range": [samples[0]["start"], samples[-1]["start"]] if samples else None,
    }
    row["distribution"] = {
        "strategy_xirr": _qs([s.get("strategy", {}).get("xirr") for s in samples]),
        "strategy_maxdd": _qs([s.get("strategy", {}).get("maxdd") for s in samples]),
        "benchmark_xirr": _qs([s.get("benchmark", {}).get("xirr") for s in samples]),
        "benchmark_maxdd": _qs([s.get("benchmark", {}).get("maxdd") for s in samples]),
        "excess_xirr": _qs(excess),
        "dd_relief": _qs(relief),
    }
    row["admission"] = _admission_note(row, target)
    return row


def run_preference_rebalance_research(cfg, tickers: str | Iterable[str] = "",
                                      groups: str | Mapping[str, Iterable[str]] | None = None,
                                      *,
                                      total_cap: float = 37000.0,
                                      monthly: float = 3000.0,
                                      target_benchmark: str = "012922",
                                      min_years: float = 3.0,
                                      lookback_years: float = 3.0,
                                      min_history_years: float = 2.0,
                                      safe_weights: str | Iterable[float] = "0,0.26",
                                      modes: str | Iterable[str] | None = None,
                                      rebalance_months: str | Iterable[int] = DEFAULT_REBALANCE_MONTHS,
                                      trade_cost_bps: float = 10.0,
                                      safe_annual: float = 0.04,
                                      rebal_days: int = 21,
                                      rebal_band: float = 0.15,
                                      step_months: int = 1,
                                      max_windows: int = 0,
                                      local_only: bool = True,
                                      include_samples: bool = False) -> dict:
    """Evaluate active point-in-time basket reselection with turnover costs."""
    c = _research_cfg(cfg, local_only)
    group_map, requested = parse_preference_groups(groups, tickers)
    if not requested:
        raise ValueError("请提供 --tickers 或 --groups；主动轮换研究不默认扫描全部缓存。")

    series, meta, errors = _load_series(c, requested)
    if not series:
        raise ValueError("候选池没有任何可用行情；请检查 ticker 或关闭 local_only 后取数")

    grid, panels, listing_i, last_i, coverage = _build_panels(series, c.data.start_date, c.data.end_date)
    target = str(target_benchmark or "012922").upper().strip()
    target_label = _benchmark_label(target)
    target_close, target_meta = _fetch_benchmark_close(target, c, grid)
    target_start_i = _first_valid_price_i(target_close)
    target_version = data_version_payload(
        target_meta,
        used_start=(
            grid[target_start_i].strftime("%Y-%m-%d")
            if target_start_i is not None else None
        ),
        used_end=grid[-1].strftime("%Y-%m-%d"),
    )

    min_len = max(2, int(float(min_years) * 252))
    lookback_days = max(63, int(float(lookback_years) * 252))
    min_history_days = max(63, int(float(min_history_years) * 252))
    starts = []
    for si in _monthly_start_indexes(grid, min_len, step_months):
        px = float(target_close[si])
        if not np.isfinite(px) or px <= 0:
            continue
        starts.append(si)
    if max_windows and max_windows > 0:
        starts = starts[:int(max_windows)]

    mode_list = parse_walkforward_modes(modes)
    weights = parse_safe_weights(safe_weights)
    if isinstance(rebalance_months, str):
        rb_months = [
            int(float(p)) for p in re.split(r"[,，;\s]+", rebalance_months.strip())
            if p.strip()
        ]
    else:
        rb_months = [int(x) for x in rebalance_months]
    rb_months = sorted({max(1, int(x)) for x in rb_months}) or list(DEFAULT_REBALANCE_MONTHS)

    samples_by_key: dict[tuple[str, int, float], list[dict]] = {
        (mode, rb, float(w)): [] for mode in mode_list for rb in rb_months for w in weights
    }
    skipped = []
    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si]
        if len(alive) < 2:
            skipped.append({"start": grid[si].strftime("%Y-%m-%d"), "reason": "窗口内可交易标的不足"})
            continue
        panels2 = {
            t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
            for t in alive
        }
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}

        for mode in mode_list:
            for rb in rb_months:
                try:
                    risk_nav, risk_eq, flows, stats = _active_rotation_risk_leg(
                        c, grid2, panels2, listing2, last2, series, group_map, mode,
                        float(total_cap), float(monthly),
                        lookback_days=lookback_days,
                        min_history_days=min_history_days,
                        rebalance_months=rb,
                        trade_cost_bps=float(trade_cost_bps),
                    )
                except Exception as e:
                    skipped.append({"start": grid[si].strftime("%Y-%m-%d"),
                                    "mode": mode, "rebalance_months": rb,
                                    "reason": str(e)})
                    continue
                contributed = sum(a for _, a in flows)
                if contributed <= 0 or not len(flows):
                    continue
                bnav, beq = _run_single_asset_fund(grid2, target_close[si:], flows)
                benchmark = _metric_block(grid2, bnav, beq, flows, contributed)
                selections = stats.get("selections") or []
                tickers_observed = sorted({t for s in selections for t in s.get("tickers", [])})
                avg_n = float(np.mean([len(s.get("tickers") or []) for s in selections])) if selections else None
                for w in weights:
                    if float(w) > 0:
                        strategy_nav, strategy_eq, _, safe_turn, nrb = _run_defensive_fund(
                            grid2, risk_nav, flows, float(safe_annual), float(w),
                            int(rebal_days), float(rebal_band))
                    else:
                        strategy_nav, strategy_eq, safe_turn, nrb = risk_nav, risk_eq, 0.0, 0
                    strategy = _metric_block(
                        grid2, strategy_nav, strategy_eq, flows, contributed,
                        turnover=float(stats.get("turnover") or 0.0) + float(safe_turn or 0.0),
                        n_rebal=int(nrb),
                    )
                    excess = None
                    relief = None
                    if strategy["xirr"] is not None and benchmark["xirr"] is not None:
                        excess = strategy["xirr"] - benchmark["xirr"]
                    if strategy["maxdd"] is not None and benchmark["maxdd"] is not None:
                        relief = benchmark["maxdd"] - strategy["maxdd"]
                    sample = {
                        "start": grid2[0].strftime("%Y-%m-%d"),
                        "end": grid2[-1].strftime("%Y-%m-%d"),
                        "years": float((grid2[-1] - grid2[0]).days / 365.25),
                        "basket": mode,
                        "rebalance_months": int(rb),
                        "safe_weight": float(w),
                        "tickers_observed": tickers_observed,
                        "avg_n_selected": avg_n,
                        "selection_churn_p50": stats.get("selection_churn_p50"),
                        "rotation_turnover_x": (float(stats.get("turnover") or 0.0) / contributed)
                        if contributed else None,
                        "rotation_cost_x": (float(stats.get("cost_paid") or 0.0) / contributed)
                        if contributed else None,
                        "rebalance_count": stats.get("rebalance_count"),
                        "strategy": strategy,
                        "benchmark": benchmark,
                        "baseline": target_label,
                        "excess_xirr": excess,
                        "dd_relief": relief,
                    }
                    if include_samples:
                        sample["selections"] = selections
                    samples_by_key[(mode, int(rb), float(w))].append(sample)

    rows = [
        _rebalance_rollup(mode, rb, w, float(trade_cost_bps), samples, target, group_map)
        for (mode, rb, w), samples in samples_by_key.items()
        if samples
    ]
    rows = sorted(
        rows,
        key=lambda r: (
            r.get("win_rate") or -1,
            r.get("excess_p50") or -9,
            r.get("dd_relief_p50") or -9,
        ),
        reverse=True,
    )
    out = {
        "summary": {
            "research_only": True,
            "does_change_today_advice": False,
            "method": "preference_active_rebalance_walkforward",
            "target_benchmark": target,
            "target_label": target_label,
            "target_source": getattr(target_meta, "source", "?"),
            "data_versions": {"target_nav": target_version.get("version_id")},
            "total_cap": float(total_cap),
            "monthly": float(monthly),
            "min_years": float(min_years),
            "lookback_years": float(lookback_years),
            "min_history_years": float(min_history_years),
            "step_months": int(step_months),
            "start_count": len(starts),
            "ticker_count": len(requested),
            "available_ticker_count": len(series),
            "group_count": len(group_map),
            "modes": mode_list,
            "safe_weights": weights,
            "rebalance_months": rb_months,
            "trade_cost_bps": float(trade_cost_bps),
            "holding_preference": {
                "preferred_max_holdings": PREFERRED_MAX_HOLDINGS,
                "tested_top_ns": list(COMPACT_TOP_NS),
                "rule": "低频重选默认同时验证 top4/top6/top8；同等证据下优先精简篮子。",
            },
            "best": _best_rows(rows),
            "note": "持有期内点时重选并扣内部调仓成本；主动卖出/重建仅为研究，不改变今日建议。",
        },
        "groups": [{"name": name, "tickers": vals} for name, vals in group_map.items()],
        "coverage": coverage,
        "meta": meta,
        "data_manifest": {"schema_version": 1, "target_nav": target_version},
        "dropped": errors,
        "rows": rows,
        "skipped": skipped[:100],
    }
    if include_samples:
        out["samples"] = [
            sample for _, samples in samples_by_key.items() for sample in samples
        ]
    return out


def run_preference_walkforward_research(cfg, tickers: str | Iterable[str] = "",
                                        groups: str | Mapping[str, Iterable[str]] | None = None,
                                        *,
                                        total_cap: float = 37000.0,
                                        monthly: float = 3000.0,
                                        target_benchmark: str = "012922",
                                        min_years: float = 3.0,
                                        lookback_years: float = 3.0,
                                        min_history_years: float = 2.0,
                                        safe_weights: str | Iterable[float] = "0,0.26",
                                        modes: str | Iterable[str] | None = None,
                                        safe_annual: float = 0.04,
                                        rebal_days: int = 21,
                                        rebal_band: float = 0.15,
                                        step_months: int = 1,
                                        max_windows: int = 0,
                                        local_only: bool = True,
                                        include_samples: bool = False) -> dict:
    """Run point-in-time basket selection at each rolling start.

    Selection inputs are restricted to prices before the start date.  The
    selected basket is then handed to the existing ratchet NAV engine for that
    window.  This is not a live execution rule and does not write config/state.
    """
    c = _research_cfg(cfg, local_only)
    group_map, requested = parse_preference_groups(groups, tickers)
    if not requested:
        raise ValueError("请提供 --tickers 或 --groups；点时回放不默认扫描全部缓存。")

    series, meta, errors = _load_series(c, requested)
    if not series:
        raise ValueError("候选池没有任何可用行情；请检查 ticker 或关闭 local_only 后取数")

    grid, panels, listing_i, last_i, coverage = _build_panels(series, c.data.start_date, c.data.end_date)
    target = str(target_benchmark or "012922").upper().strip()
    target_label = _benchmark_label(target)
    target_close, target_meta = _fetch_benchmark_close(target, c, grid)
    target_start_i = _first_valid_price_i(target_close)
    target_version = data_version_payload(
        target_meta,
        used_start=(
            grid[target_start_i].strftime("%Y-%m-%d")
            if target_start_i is not None else None
        ),
        used_end=grid[-1].strftime("%Y-%m-%d"),
    )

    min_len = max(2, int(float(min_years) * 252))
    lookback_days = max(63, int(float(lookback_years) * 252))
    min_history_days = max(63, int(float(min_history_years) * 252))
    starts = []
    for si in _monthly_start_indexes(grid, min_len, step_months):
        px = float(target_close[si])
        if not np.isfinite(px) or px <= 0:
            continue
        metrics = _metrics_asof(series, grid[si], lookback_days=lookback_days,
                                 min_history_days=min_history_days)
        if not metrics.empty:
            starts.append((si, metrics))
    if max_windows and max_windows > 0:
        starts = starts[:int(max_windows)]

    mode_list = parse_walkforward_modes(modes)
    weights = parse_safe_weights(safe_weights)
    samples_by_key: dict[tuple[str, float], list[dict]] = {
        (mode, float(w)): [] for mode in mode_list for w in weights
    }
    prev_tickers: dict[tuple[str, float], set[str] | None] = {k: None for k in samples_by_key}
    skipped = []

    for si, metrics in starts:
        grid2 = grid[si:]
        for mode in mode_list:
            choice = _choice_for_mode(mode, metrics, group_map)
            if choice is None:
                skipped.append({"start": grid[si].strftime("%Y-%m-%d"), "mode": mode,
                                "reason": "可用历史或入选数量不足"})
                continue
            alive = [t for t in choice.tickers if t in panels and last_i[t] >= si]
            if len(alive) < 2:
                skipped.append({"start": grid[si].strftime("%Y-%m-%d"), "mode": mode,
                                "reason": "窗口内可交易标的不足"})
                continue
            weight_sum = sum(choice.weights.get(t, 0.0) for t in alive)
            if weight_sum <= 0:
                continue
            caps = {t: float(total_cap) * float(choice.weights.get(t, 0.0)) / weight_sum for t in alive}
            panels2 = {
                t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
                for t in alive
            }
            listing2 = {t: max(0, listing_i[t] - si) for t in alive}
            last2 = {t: last_i[t] - si for t in alive}

            _, risk_nav, risk_eq, risk_inv, flows = _run_strategy_fund(
                grid2, panels2, listing2, last2, caps, float(monthly), c)
            contributed = sum(a for _, a in flows)
            if contributed <= 0:
                continue

            bnav, beq = _run_single_asset_fund(grid2, target_close[si:], flows)
            benchmark = _metric_block(grid2, bnav, beq, flows, contributed)

            for w in weights:
                key = (mode, float(w))
                if float(w) > 0:
                    strategy_nav, strategy_eq, _, turn, nrb = _run_defensive_fund(
                        grid2, risk_nav, flows, float(safe_annual), float(w),
                        int(rebal_days), float(rebal_band))
                else:
                    strategy_nav, strategy_eq, turn, nrb = risk_nav, risk_eq, 0.0, 0
                strategy = _metric_block(grid2, strategy_nav, strategy_eq, flows,
                                         contributed, turn, nrb)
                excess = None
                relief = None
                if strategy["xirr"] is not None and benchmark["xirr"] is not None:
                    excess = strategy["xirr"] - benchmark["xirr"]
                if strategy["maxdd"] is not None and benchmark["maxdd"] is not None:
                    relief = benchmark["maxdd"] - strategy["maxdd"]
                cur_set = set(alive)
                sample = {
                    "start": grid2[0].strftime("%Y-%m-%d"),
                    "end": grid2[-1].strftime("%Y-%m-%d"),
                    "years": float((grid2[-1] - grid2[0]).days / 365.25),
                    "asof_date": choice.asof_date,
                    "basket": mode,
                    "construction": choice.construction,
                    "weight_mode": choice.weight_mode,
                    "safe_weight": float(w),
                    "tickers": alive,
                    "weights": {t: caps[t] / float(total_cap) for t in alive},
                    "group_counts": _group_counts(alive, group_map),
                    "max_weight": max(caps[t] / float(total_cap) for t in alive),
                    "selection_churn": _selection_churn(prev_tickers.get(key), cur_set),
                    "strategy": strategy,
                    "benchmark": benchmark,
                    "baseline": target_label,
                    "excess_xirr": excess,
                    "dd_relief": relief,
                }
                samples_by_key[key].append(sample)
                prev_tickers[key] = cur_set

    rows = [
        _rollup(mode, w, samples, target, group_map)
        for (mode, w), samples in samples_by_key.items()
        if samples
    ]
    rows = sorted(
        rows,
        key=lambda r: (
            r.get("win_rate") or -1,
            r.get("excess_p50") or -9,
            r.get("dd_relief_p50") or -9,
        ),
        reverse=True,
    )
    out = {
        "summary": {
            "research_only": True,
            "does_change_today_advice": False,
            "method": "preference_point_in_time_walkforward",
            "target_benchmark": target,
            "target_label": target_label,
            "target_source": getattr(target_meta, "source", "?"),
            "data_versions": {"target_nav": target_version.get("version_id")},
            "total_cap": float(total_cap),
            "monthly": float(monthly),
            "min_years": float(min_years),
            "lookback_years": float(lookback_years),
            "min_history_years": float(min_history_years),
            "step_months": int(step_months),
            "start_count": len(starts),
            "ticker_count": len(requested),
            "available_ticker_count": len(series),
            "group_count": len(group_map),
            "modes": mode_list,
            "safe_weights": weights,
            "holding_preference": {
                "preferred_max_holdings": PREFERRED_MAX_HOLDINGS,
                "tested_top_ns": list(COMPACT_TOP_NS),
                "rule": "点时选篮子默认同时验证 top4/top6/top8；同等证据下优先精简篮子。",
            },
            "best": _best_rows(rows),
            "note": "每个起点只用起点前价格历史选篮子；不写 config/state，不改变今日建议。",
        },
        "groups": [{"name": name, "tickers": vals} for name, vals in group_map.items()],
        "coverage": coverage,
        "meta": meta,
        "data_manifest": {"schema_version": 1, "target_nav": target_version},
        "dropped": errors,
        "rows": rows,
        "skipped": skipped[:100],
    }
    if include_samples:
        out["samples"] = [
            sample for _, samples in samples_by_key.items() for sample in samples
        ]
    return out
