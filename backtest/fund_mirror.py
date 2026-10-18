"""Mirror a target fund's disclosed holdings into the US ratchet research layer."""
from __future__ import annotations

import copy
from datetime import timedelta
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
    run_rolling_start_panel,
)
from backtest.preference import _admission_note, _cfg_for_basket, parse_safe_weights
from backtest.weights import bounded_proportional_weights
from core import engine as eng
from data.fetch import get_bars
from data.funds import get_fund_nav
from data.fund_holdings import get_fund_holding_history, get_fund_holdings
from data.versioning import data_version_payload, modeled_availability_manifest


def _parse_float_list(raw: str | Iterable[float]) -> list[float]:
    if isinstance(raw, str):
        vals = []
        for part in raw.replace("，", ",").replace(";", ",").split(","):
            txt = part.strip()
            if not txt:
                continue
            vals.append(float(txt.rstrip("%")) / (100.0 if txt.endswith("%") else 1.0))
        return vals
    return [float(x) for x in raw]


def _research_cfg(cfg, local_only: bool):
    c = copy.deepcopy(cfg)
    if local_only:
        c.data.fallback_chain = ["local_cache"]
    return c


def _weights_from_holdings(rows, mode: str, top_n: int) -> dict[str, float]:
    us = rows[
        (rows["asset_class"] == "US")
        & rows["ticker"].notna()
        & rows["nav_weight"].notna()
        & (rows["nav_weight"].astype(float) > 0)
    ].copy()
    if top_n and top_n > 0:
        us = us.sort_values("nav_weight", ascending=False).head(int(top_n))
    if us.empty:
        return {}
    tickers = [str(t).upper().strip() for t in us["ticker"].tolist()]
    if mode == "equal":
        return {t: 1.0 / len(tickers) for t in tickers}
    raw = {str(r["ticker"]).upper().strip(): float(r["nav_weight"]) for _, r in us.iterrows()}
    total = sum(raw.values())
    return {t: w / total for t, w in raw.items() if total > 0}


def _holding_records(df) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        item = {}
        for k, v in r.items():
            if hasattr(v, "item"):
                v = v.item()
            if isinstance(v, float) and not np.isfinite(v):
                v = None
            item[k] = v
        rows.append(item)
    return rows


def _coverage(df) -> dict:
    total = float(df["nav_weight"].dropna().astype(float).sum()) if "nav_weight" in df else 0.0
    by_class = {}
    for name, g in df.groupby("asset_class"):
        by_class[str(name)] = float(g["nav_weight"].dropna().astype(float).sum())
    us = by_class.get("US", 0.0)
    return {
        "reported_nav_weight": total,
        "us_nav_weight": us,
        "us_share_of_reported": (us / total) if total > 0 else None,
        "by_asset_class": by_class,
    }


def _eval_row(base_cfg, weights: dict[str, float], *, label: str,
              construction: str, weight_mode: str, total_cap: float,
              monthly: float, safe_weight: float, core_ratio: float,
              target: str, min_years: float) -> dict:
    cfg2 = copy.deepcopy(base_cfg)
    cfg2.portfolio.core_ratio = float(core_ratio)
    cfg2.portfolio.injection_core_ratio = float(core_ratio)
    bt_cfg = _cfg_for_basket(cfg2, weights, total_cap)
    roll = run_rolling_start_panel(
        bt_cfg,
        monthly=float(monthly),
        min_years=float(min_years),
        safe_weight=float(safe_weight),
        safe_annual=0.04,
        rebal_days=21,
        rebal_band=0.15,
        benchmark_tickers=("QQQ", "SPY", target),
        baseline_ticker=target,
        skip_missing=True,
    )
    s = roll["summary"]
    ex = s.get("excess_xirr") or {}
    dd = s.get("dd_relief") or {}
    sx = s.get("strategy_xirr") or {}
    sd = s.get("strategy_maxdd") or {}
    row = {
        "basket": label,
        "construction": construction,
        "weight_mode": weight_mode,
        "defense_mode": "static_safe_weight",
        "tickers": list(weights.keys()),
        "weights": weights,
        "n": len(weights),
        "safe_weight": float(safe_weight),
        "core_ratio": float(core_ratio),
        "windows": s.get("windows"),
        "win_rate": s.get("win_rate"),
        "dd_win_rate": s.get("dd_win_rate"),
        "excess_p50": ex.get("p50"),
        "excess_p10": ex.get("p10"),
        "excess_p90": ex.get("p90"),
        "dd_relief_p50": dd.get("p50"),
        "dd_relief_p10": dd.get("p10"),
        "dd_relief_p90": dd.get("p90"),
        "xirr_p50": sx.get("p50"),
        "maxdd_p50": sd.get("p50"),
        "range": [roll["rows"][0]["start"], roll["rows"][-1]["start"]] if roll.get("rows") else None,
        "benchmark_errors": roll.get("benchmark_errors", {}),
        "dropped": roll.get("dropped", []),
        "coverage": roll.get("coverage", []),
    }
    row["admission"] = _admission_note(row, target)
    return row


def _best_rows(rows: list[dict]) -> dict:
    valid = [r for r in rows if r.get("windows")]
    if not valid:
        return {}
    return {
        "best_return": max(valid, key=lambda r: (r.get("win_rate") or -1, r.get("excess_p50") or -9)),
        "best_balanced": max(valid, key=lambda r: (
            (r.get("excess_p50") or -9) - max(0.0, -(r.get("dd_relief_p50") or 0.0)) * 0.35,
            r.get("win_rate") or -1,
        )),
        "best_drawdown": max(valid, key=lambda r: (
            r.get("dd_relief_p50") if r.get("dd_relief_p50") is not None else -9,
            r.get("excess_p50") or -9,
        )),
    }


def run_fund_mirror_research(cfg, fund_code: str = "012922", *,
                             report_date: str | None = None,
                             total_cap: float = 37000.0,
                             monthly: float = 3000.0,
                             target_benchmark: str = "012922",
                             min_years: float = 3.0,
                             top_n: int = 10,
                             safe_weights: str | Iterable[float] = "0,0.14,0.26,0.40",
                             core_ratios: str | Iterable[float] = "0.90,0.95",
                             include_equal: bool = True,
                             local_only: bool = False) -> dict:
    c = _research_cfg(cfg, local_only=False)
    holdings, meta = get_fund_holdings(
        fund_code, c, report_date=report_date, local_only=local_only, top_line=max(20, int(top_n) * 3)
    )
    if local_only:
        c.data.fallback_chain = ["local_cache"]

    target = str(target_benchmark or fund_code).upper()
    rows = []
    modes = [("fund_weight", "按基金披露占净值比例归一到 US 子集")]
    if include_equal:
        modes.append(("equal", "US 子集等权，仅作对照"))
    for mode, construction in modes:
        weights = _weights_from_holdings(holdings, mode, top_n)
        if not weights:
            continue
        for cr in _parse_float_list(core_ratios):
            for sw in parse_safe_weights(safe_weights):
                rows.append(_eval_row(
                    c, weights,
                    label=f"{fund_code}_{mode}_top{top_n}",
                    construction=construction,
                    weight_mode=mode,
                    total_cap=float(total_cap),
                    monthly=float(monthly),
                    safe_weight=float(sw),
                    core_ratio=float(cr),
                    target=target,
                    min_years=float(min_years),
                ))
    rows = sorted(
        rows,
        key=lambda r: (
            r.get("win_rate") or -1,
            r.get("excess_p50") or -9,
            r.get("dd_relief_p50") or -9,
        ),
        reverse=True,
    )
    holdings_version = data_version_payload(
        meta,
        used_rows=len(holdings),
        used_report_date=meta.report_date,
    )
    target_version = {}
    if len(target) == 6 and target.isdigit():
        target_nav, target_meta = get_fund_nav(target, c, local_only=local_only)
        target_version = data_version_payload(
            target_meta,
            used_rows=len(target_nav),
            used_start=target_nav.index[0].strftime("%Y-%m-%d"),
            used_end=target_nav.index[-1].strftime("%Y-%m-%d"),
        )
    data_manifest = {
        "schema_version": 1,
        "fund_code": str(fund_code),
        "latest_holdings_hindsight": True,
        "holdings_report": holdings_version,
        "target_nav": target_version,
    }
    return {
        "summary": {
            "research_only": True,
            "does_change_today_advice": False,
            "latest_holdings_hindsight": True,
            "method": "target_fund_latest_us_holdings_mirror",
            "fund_code": str(fund_code),
            "fund_name": meta.fund_name,
            "report_date": meta.report_date,
            "holdings_source": meta.source,
            "data_versions": {
                "holdings_report": holdings_version.get("version_id"),
                "target_nav": target_version.get("version_id"),
            },
            "target_benchmark": target,
            "total_cap": float(total_cap),
            "monthly": float(monthly),
            "min_years": float(min_years),
            "top_n": int(top_n),
            "safe_weights": parse_safe_weights(safe_weights),
            "core_ratios": _parse_float_list(core_ratios),
            "coverage": _coverage(holdings),
            "best": _best_rows(rows),
            "note": "仅镜像基金最新披露持仓中的 US ticker 子集；不是基金完整历史持仓回放，不改变今日建议。",
        },
        "holdings": _holding_records(holdings),
        "data_manifest": data_manifest,
        "rows": rows,
    }


def _parse_int_list(raw: str | Iterable[int], default: tuple[int, ...] = (6,)) -> list[int]:
    if raw is None:
        return list(default)
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace(";", ",").split(",")
        vals = [int(float(p.strip())) for p in parts if p.strip()]
    else:
        vals = [int(x) for x in raw]
    vals = sorted({x for x in vals if x > 0})
    return vals or list(default)


def _parse_mode_list(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return ["fund_weight", "capped_fund_weight", "score_risk"]
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace(";", ",").split(",")
    else:
        parts = list(raw)
    out = []
    seen = set()
    aliases = {
        "fund": "fund_weight",
        "cap": "capped_fund_weight",
        "capped": "capped_fund_weight",
        "risk": "score_risk",
        "score": "score_risk",
    }
    for p in parts:
        mode = aliases.get(str(p or "").strip().lower(), str(p or "").strip().lower())
        if mode and mode not in seen:
            seen.add(mode)
            out.append(mode)
    return out or ["fund_weight", "capped_fund_weight", "score_risk"]


def _q(vals, p: float) -> float | None:
    arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
    return float(np.quantile(arr, p)) if len(arr) else None


def _qs(vals) -> dict:
    return {"p10": _q(vals, 0.10), "p50": _q(vals, 0.50), "p90": _q(vals, 0.90)}


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


def _metrics_asof(series: Mapping[str, pd.DataFrame], tickers: Iterable[str],
                  asof: pd.Timestamp, *, lookback_days: int = 756) -> pd.DataFrame:
    rows = []
    asof_date = pd.Timestamp(asof)
    for ticker in tickers:
        df = series.get(str(ticker).upper())
        if df is None:
            continue
        hist = df["Close"][df.index < asof_date].dropna()
        if len(hist) < 126:
            continue
        days = min(int(lookback_days), max(1, len(hist) - 1))
        rows.append({
            "ticker": str(ticker).upper(),
            "ret_1y": _ret(hist, 252),
            "ret_3y": _ret(hist, days),
            "vol_3y": _ann_vol(hist, days),
            "dd_3y": _maxdd(hist, days),
            "asof_date": hist.index[-1].strftime("%Y-%m-%d"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.set_index("ticker", drop=False)
    df["attack_score"] = (
        _rank_pct(df["ret_3y"]) * 0.50
        + _rank_pct(df["ret_1y"]) * 0.25
        + _rank_pct(df["dd_3y"], higher=False) * 0.15
        + _rank_pct(df["vol_3y"], higher=False) * 0.10
    )
    return df


def _capped_weights(raw: Mapping[str, float], max_weight: float, min_weight: float) -> dict[str, float]:
    s = pd.Series({str(k).upper(): float(v) for k, v in raw.items() if float(v) > 0})
    if s.empty:
        return {}
    w = bounded_proportional_weights(
        s,
        max_weight=float(max_weight),
        min_weight=float(min_weight),
    )
    return {t: float(v) for t, v in w.items()}


def _report_weights(report_df: pd.DataFrame, mode: str, top_n: int,
                    series: Mapping[str, pd.DataFrame], asof: pd.Timestamp,
                    *, max_weight: float, min_weight: float) -> tuple[dict[str, float], dict]:
    us = report_df[
        (report_df["asset_class"] == "US")
        & report_df["ticker"].notna()
        & report_df["nav_weight"].notna()
        & (report_df["nav_weight"].astype(float) > 0)
    ].copy()
    us = us.sort_values("nav_weight", ascending=False)
    if int(top_n) > 0:
        us = us.head(int(top_n))
    if us.empty:
        return {}, {"reason": "no_us_holdings"}

    raw = {str(r["ticker"]).upper().strip(): float(r["nav_weight"]) for _, r in us.iterrows()}
    tickers = list(raw)
    total = sum(raw.values())
    base = {t: w / total for t, w in raw.items()} if total > 0 else {}

    if mode == "equal":
        weights = {t: 1.0 / len(tickers) for t in tickers}
    elif mode == "fund_weight":
        weights = base
    elif mode == "capped_fund_weight":
        weights = _capped_weights(base, max_weight, min_weight)
    elif mode == "score_risk":
        metrics = _metrics_asof(series, tickers, asof)
        vol = pd.to_numeric(metrics.get("vol_3y", pd.Series(dtype=float)), errors="coerce")
        median_vol = float(vol.dropna().median()) if len(vol.dropna()) else 0.45
        raw2 = {}
        for t in tickers:
            score = 0.50
            v = median_vol
            if not metrics.empty and t in metrics.index:
                score = float(metrics.loc[t, "attack_score"])
                vv = metrics.loc[t, "vol_3y"]
                if vv is not None and np.isfinite(vv):
                    v = float(vv)
            raw2[t] = (max(0.001, base.get(t, 0.0)) ** 0.70) * \
                (max(0.05, score) ** 0.60) / (max(0.15, v) ** 0.35)
        weights = _capped_weights(raw2, max_weight, min_weight)
    else:
        return {}, {"reason": f"unknown_weight_mode:{mode}"}

    return weights, {
        "report_date": str(us["report_date"].iloc[0]) if "report_date" in us else None,
        "selected_nav_weight": float(total),
        "us_nav_weight": float(report_df.loc[report_df["asset_class"] == "US", "nav_weight"].dropna().astype(float).sum()),
        "reported_nav_weight": float(report_df["nav_weight"].dropna().astype(float).sum()),
        "tickers": tickers,
        "weight_mode": mode,
        "max_weight": max(weights.values()) if weights else None,
    }


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
        meta[ticker] = {"source": m.source, "start": m.start, "end": m.end, "rows": m.rows}
    return series, meta, errors


def _history_with_availability(history: pd.DataFrame, availability_delay_days: int) -> pd.DataFrame:
    if int(availability_delay_days) < 0:
        raise ValueError("availability_delay_days must be >= 0")
    h = history.copy()
    h["report_ts"] = pd.to_datetime(h["report_date"])
    h["available_ts"] = h["report_ts"] + pd.to_timedelta(int(availability_delay_days), unit="D")
    h["available_date"] = h["available_ts"].dt.strftime("%Y-%m-%d")
    return h


def _available_report(history: pd.DataFrame, asof: pd.Timestamp) -> tuple[str | None, pd.DataFrame | None]:
    h = history[history["available_ts"] <= pd.Timestamp(asof)]
    if h.empty:
        return None, None
    rd = str(h["report_date"].max())
    selected = h[h["report_date"].astype(str) == rd].copy()
    if (selected["available_ts"] > pd.Timestamp(asof)).any():
        raise RuntimeError(f"future disclosure selected: report={rd} asof={pd.Timestamp(asof).date()}")
    return rd, selected


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (int(b.year) - int(a.year)) * 12 + (int(b.month) - int(a.month))


def _rebalance_indexes(grid: pd.DatetimeIndex, rebalance_months: int) -> list[int]:
    months = max(1, int(rebalance_months))
    out = [0]
    last = pd.Timestamp(grid[0])
    seen = {(int(last.year), int(last.month))}
    for i, d in enumerate(grid[1:], start=1):
        key = (int(d.year), int(d.month))
        if key in seen:
            continue
        seen.add(key)
        cur = pd.Timestamp(d)
        if _months_between(last, cur) >= months:
            out.append(i)
            last = cur
    return out


def _monthly_start_indexes(grid: pd.DatetimeIndex, min_len: int, step_months: int) -> list[int]:
    out = []
    seen = set()
    for i, d in enumerate(grid):
        key = (int(d.year), int(d.month))
        if key in seen:
            continue
        seen.add(key)
        if len(grid) - i >= min_len:
            out.append(i)
    return out[::max(1, int(step_months))]


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
        total += st.shares * float(panels[st.ticker][field][idx])
    return total


def _selection_churn(prev: set[str] | None, current: set[str]) -> float | None:
    if prev is None or not prev or not current:
        return None
    return 1.0 - len(prev & current) / max(len(prev), len(current))


def _active_quarterly_mirror_risk_leg(cfg, grid: pd.DatetimeIndex,
                                      panels: Mapping[str, dict],
                                      listing_i: Mapping[str, int],
                                      last_i: Mapping[str, int],
                                      history: pd.DataFrame,
                                      series: Mapping[str, pd.DataFrame],
                                      mode: str,
                                      top_n: int,
                                      total_cap: float,
                                      monthly: float,
                                      *,
                                      max_weight: float,
                                      min_weight: float,
                                      rebalance_months: int,
                                      trade_cost_bps: float,
                                      rebalance_same_report: bool) -> tuple[np.ndarray, np.ndarray, list[tuple[int, float]], dict]:
    n = len(grid)
    symbols = {}
    entry_i: dict[str, int] = {}
    units = 0.0
    cash_pool = 0.0
    nav = np.zeros(n)
    equity = np.zeros(n)
    flows: list[tuple[int, float]] = []
    rebalance_set = set(_rebalance_indexes(grid, rebalance_months))
    trade_cost = max(0.0, float(trade_cost_bps)) / 10000.0
    turnover = 0.0
    cost_paid = 0.0
    failed_rebalances = 0
    rebalance_count = 0
    selections = []
    last_report: str | None = None
    prev_selection: set[str] | None = None

    def active_symbols_at(idx: int) -> list[str]:
        return [t for t in symbols if listing_i.get(t, 0) <= idx <= last_i.get(t, n - 1)]

    for i in range(n):
        tv_pre = _symbols_value_at(symbols, panels, i, "close") if symbols else cash_pool
        nav_b = (tv_pre / units) if units > 0 else 1.0
        if i == 0:
            units += float(total_cap) / nav_b
            flows.append((i, float(total_cap)))
            cash_pool += float(total_cap)

        if i in rebalance_set:
            report_date, report_df = _available_report(history, pd.Timestamp(grid[i]))
            should_rebalance = report_df is not None and (rebalance_same_report or report_date != last_report)
            if should_rebalance:
                weights, info = _report_weights(
                    report_df, mode, int(top_n), series, pd.Timestamp(grid[i]),
                    max_weight=float(max_weight), min_weight=float(min_weight)
                )
                alive = [
                    t for t in weights
                    if t in panels and listing_i.get(t, n + 1) <= i <= last_i.get(t, -1)
                ]
                weight_sum = sum(float(weights.get(t, 0.0)) for t in alive)
                if len(alive) < 2 or weight_sum <= 0:
                    failed_rebalances += 1
                else:
                    had_symbols = bool(symbols)
                    gross_value = _symbols_value_at(symbols, panels, i, "open") if had_symbols else cash_pool
                    sell_notional = _symbols_market_value_at(symbols, panels, i, "open") if had_symbols else 0.0
                    core_buy_notional = gross_value * float(cfg.portfolio.core_ratio) if had_symbols else 0.0
                    traded = sell_notional + core_buy_notional
                    cost = traded * trade_cost
                    deployable = max(0.0, gross_value - cost)
                    turnover += traded
                    cost_paid += cost
                    symbols = {}
                    entry_i = {}
                    cash_pool = 0.0
                    for t in alive:
                        w = float(weights.get(t, 0.0)) / weight_sum
                        px = float(panels[t]["open"][i])
                        if px <= 0 or not np.isfinite(px):
                            continue
                        symbols[t] = eng.init_symbol(t, deployable * w, px, cfg)
                        entry_i[t] = i
                    cur = set(symbols)
                    if cur:
                        selections.append({
                            "date": grid[i].strftime("%Y-%m-%d"),
                            "report_date": report_date,
                            "available_date": str(report_df["available_date"].iloc[0]),
                            "mode": mode,
                            "top_n": int(top_n),
                            "tickers": sorted(cur),
                            "weights": {t: float(weights[t]) for t in sorted(cur) if t in weights},
                            "selected_nav_weight": info.get("selected_nav_weight"),
                            "us_nav_weight": info.get("us_nav_weight"),
                            "reported_nav_weight": info.get("reported_nav_weight"),
                            "max_weight": info.get("max_weight"),
                            "churn": _selection_churn(prev_selection, cur),
                            "turnover": traded,
                            "cost": cost,
                        })
                        prev_selection = cur
                        last_report = report_date
                        rebalance_count += 1
                    else:
                        failed_rebalances += 1

        if not symbols:
            equity[i] = cash_pool
            nav[i] = (cash_pool / units) if units > 0 else 1.0
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
        "avg_n_selected": float(np.mean([len(s.get("tickers") or []) for s in selections])) if selections else None,
        "max_weight_p50": _q([s.get("max_weight") for s in selections], 0.50),
        "report_count": len({s.get("report_date") for s in selections}),
        "selections": selections,
    }
    return nav, equity, flows, stats


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


def _quarterly_rollup(mode: str, top_n: int, core_ratio: float, safe_weight: float,
                      samples: list[dict], target: str, *,
                      rebalance_months: int, trade_cost_bps: float) -> dict:
    excess = [s.get("excess_xirr") for s in samples]
    relief = [s.get("dd_relief") for s in samples]
    valid_excess = [v for v in excess if v is not None and np.isfinite(v)]
    valid_relief = [v for v in relief if v is not None and np.isfinite(v)]
    tickers = sorted({t for s in samples for t in (s.get("tickers_observed") or [])})
    row = {
        "basket": f"quarterly_{mode}_top{int(top_n)}",
        "construction": "012922 historical disclosed US holdings, point-in-time by availability date",
        "weight_mode": mode,
        "defense_mode": "static_safe_weight",
        "top_n": int(top_n),
        "core_ratio": float(core_ratio),
        "safe_weight": float(safe_weight),
        "rebalance_months": int(rebalance_months),
        "trade_cost_bps": float(trade_cost_bps),
        "n": _q([s.get("avg_n_selected") for s in samples], 0.50),
        "tickers_observed": tickers,
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
        "turnover_x_p50": _q([s.get("strategy", {}).get("turnover_x") for s in samples], 0.50),
        "selection_churn_p50": _q([s.get("selection_churn_p50") for s in samples], 0.50),
        "report_count_p50": _q([s.get("report_count") for s in samples], 0.50),
        "range": [samples[0]["start"], samples[-1]["start"]] if samples else None,
        "distribution": {
            "strategy_xirr": _qs([s.get("strategy", {}).get("xirr") for s in samples]),
            "strategy_maxdd": _qs([s.get("strategy", {}).get("maxdd") for s in samples]),
            "benchmark_xirr": _qs([s.get("benchmark", {}).get("xirr") for s in samples]),
            "benchmark_maxdd": _qs([s.get("benchmark", {}).get("maxdd") for s in samples]),
            "excess_xirr": _qs(excess),
            "dd_relief": _qs(relief),
        },
    }
    row["admission"] = _admission_note(row, target)
    return row


def _history_coverage(history: pd.DataFrame) -> list[dict]:
    rows = []
    for rd, g in history.groupby("report_date"):
        total = float(g["nav_weight"].dropna().astype(float).sum())
        us = float(g.loc[g["asset_class"] == "US", "nav_weight"].dropna().astype(float).sum())
        us_tickers = [
            str(t).upper() for t in g.loc[g["asset_class"] == "US"].sort_values("nav_weight", ascending=False)["ticker"].tolist()
        ]
        rows.append({
            "report_date": str(rd),
            "available_date": (
                str(g["available_date"].dropna().iloc[0])
                if "available_date" in g and not g["available_date"].dropna().empty else None
            ),
            "reported_nav_weight": total,
            "us_nav_weight": us,
            "us_count": len(us_tickers),
            "top_us": us_tickers[:10],
        })
    return sorted(rows, key=lambda x: x["report_date"], reverse=True)


def run_fund_quarterly_mirror_research(cfg, fund_code: str = "012922", *,
                                       total_cap: float = 37000.0,
                                       monthly: float = 3000.0,
                                       target_benchmark: str = "012922",
                                       min_years: float = 3.0,
                                       start_year: int | None = None,
                                       end_year: int | None = None,
                                       top_ns: str | Iterable[int] = "4,6,8",
                                       weight_modes: str | Iterable[str] | None = None,
                                       safe_weights: str | Iterable[float] = "0.26,0.34,0.40",
                                       core_ratios: str | Iterable[float] = "0.90,0.95",
                                       max_weight: float = 0.30,
                                       min_weight: float = 0.04,
                                       availability_delay_days: int = 30,
                                       rebalance_months: int = 3,
                                       rebalance_same_report: bool = False,
                                       trade_cost_bps: float = 10.0,
                                       step_months: int = 3,
                                       max_windows: int = 0,
                                       local_only: bool = False,
                                       include_samples: bool = False) -> dict:
    """Point-in-time mirror of historical quarterly fund holdings.

    The active report is the latest disclosed report with
    ``report_date + availability_delay_days <= rebalance_date``.  This avoids
    using current/latest holdings for older windows.
    """
    c = _research_cfg(cfg, local_only=False)
    history, holding_meta = get_fund_holding_history(
        fund_code,
        c,
        start_year=start_year,
        end_year=end_year,
        local_only=local_only,
        top_line=100,
    )
    report_dates = sorted({str(value)[:10] for value in history["report_date"].dropna().tolist()})
    availability_manifest = modeled_availability_manifest(
        report_dates, int(availability_delay_days)
    )
    holdings_version = data_version_payload(
        holding_meta,
        used_rows=len(history),
        used_report_start=report_dates[0] if report_dates else None,
        used_report_end=report_dates[-1] if report_dates else None,
        used_report_count=len(report_dates),
    )
    if local_only:
        c.data.fallback_chain = ["local_cache"]
    history = _history_with_availability(history, int(availability_delay_days))
    us_tickers = sorted({
        str(t).upper().strip()
        for t in history.loc[history["asset_class"] == "US", "ticker"].dropna().tolist()
        if str(t).strip()
    })
    if not us_tickers:
        raise ValueError(f"{fund_code} 历史持仓中没有可映射的 US ticker")

    series, price_meta, price_errors = _load_series(c, us_tickers)
    if not series:
        raise ValueError("基金 US 持仓没有任何可用美股行情；请检查缓存或关闭 local_only")

    grid, panels, listing_i, last_i, coverage = _build_panels(series, c.data.start_date, c.data.end_date)
    target = str(target_benchmark or fund_code).upper().strip()
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
    starts = []
    for si in _monthly_start_indexes(grid, min_len, int(step_months)):
        px = float(target_close[si])
        if np.isfinite(px) and px > 0:
            starts.append(si)
    if max_windows and max_windows > 0:
        starts = starts[:int(max_windows)]

    top_n_list = _parse_int_list(top_ns, default=(6,))
    modes = _parse_mode_list(weight_modes)
    sw_list = parse_safe_weights(safe_weights)
    cr_list = _parse_float_list(core_ratios)
    samples_by_key: dict[tuple[str, int, float, float], list[dict]] = {
        (mode, int(top_n), float(cr), float(sw)): []
        for mode in modes for top_n in top_n_list for cr in cr_list for sw in sw_list
    }
    skipped = []
    selection_audit = []

    for si in starts:
        grid2 = grid[si:]
        alive = [t for t in panels if last_i[t] >= si]
        if len(alive) < 2:
            skipped.append({"start": grid[si].strftime("%Y-%m-%d"), "reason": "可交易 US 持仓不足"})
            continue
        panels2 = {
            t: {k: np.asarray(v[si:], dtype=float) for k, v in panels[t].items()}
            for t in alive
        }
        listing2 = {t: max(0, listing_i[t] - si) for t in alive}
        last2 = {t: last_i[t] - si for t in alive}

        for cr in cr_list:
            cfg2 = copy.deepcopy(c)
            cfg2.portfolio.core_ratio = float(cr)
            cfg2.portfolio.injection_core_ratio = float(cr)
            for mode in modes:
                for top_n in top_n_list:
                    try:
                        risk_nav, risk_eq, flows, stats = _active_quarterly_mirror_risk_leg(
                            cfg2, grid2, panels2, listing2, last2, history, series,
                            mode, int(top_n), float(total_cap), float(monthly),
                            max_weight=float(max_weight),
                            min_weight=float(min_weight),
                            rebalance_months=int(rebalance_months),
                            trade_cost_bps=float(trade_cost_bps),
                            rebalance_same_report=bool(rebalance_same_report),
                        )
                    except Exception as e:
                        skipped.append({
                            "start": grid[si].strftime("%Y-%m-%d"),
                            "mode": mode,
                            "top_n": int(top_n),
                            "core_ratio": float(cr),
                            "reason": str(e),
                        })
                        continue
                    contributed = sum(a for _, a in flows)
                    if contributed <= 0 or not len(flows):
                        continue
                    bnav, beq = _run_single_asset_fund(grid2, target_close[si:], flows)
                    benchmark = _metric_block(grid2, bnav, beq, flows, contributed)
                    selections = stats.get("selections") or []
                    selection_audit.extend(selections)
                    tickers_observed = sorted({t for s in selections for t in s.get("tickers", [])})
                    for sw in sw_list:
                        if float(sw) > 0:
                            strategy_nav, strategy_eq, _, safe_turn, nrb = _run_defensive_fund(
                                grid2, risk_nav, flows, 0.04, float(sw), 21, 0.15)
                        else:
                            strategy_nav, strategy_eq, safe_turn, nrb = risk_nav, risk_eq, 0.0, 0
                        strategy = _metric_block(
                            grid2, strategy_nav, strategy_eq, flows, contributed,
                            turnover=float(stats.get("turnover") or 0.0) + float(safe_turn or 0.0),
                            n_rebal=int(nrb) + int(stats.get("rebalance_count") or 0),
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
                            "basket": f"quarterly_{mode}_top{int(top_n)}",
                            "weight_mode": mode,
                            "top_n": int(top_n),
                            "core_ratio": float(cr),
                            "safe_weight": float(sw),
                            "tickers_observed": tickers_observed,
                            "avg_n_selected": stats.get("avg_n_selected"),
                            "selection_churn_p50": stats.get("selection_churn_p50"),
                            "report_count": stats.get("report_count"),
                            "strategy": strategy,
                            "benchmark": benchmark,
                            "baseline": target_label,
                            "excess_xirr": excess,
                            "dd_relief": relief,
                        }
                        if include_samples:
                            sample["selections"] = selections
                        samples_by_key[(mode, int(top_n), float(cr), float(sw))].append(sample)

    rows = [
        _quarterly_rollup(mode, top_n, cr, sw, samples, target,
                          rebalance_months=int(rebalance_months),
                          trade_cost_bps=float(trade_cost_bps))
        for (mode, top_n, cr, sw), samples in samples_by_key.items()
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
    best = _best_rows(rows)
    future_violations = [
        selection for selection in selection_audit
        if str(selection.get("available_date") or "9999-12-31") > str(selection.get("date") or "")
    ]
    if future_violations:
        raise RuntimeError(f"point-in-time disclosure guard failed: {future_violations[:3]}")
    data_manifest = {
        "schema_version": 1,
        "fund_code": str(fund_code),
        "holdings_history": holdings_version,
        "target_nav": target_version,
        "availability": availability_manifest,
        "point_in_time_guard": {
            "rule": "available_date <= rebalance_date",
            "checked_selection_count": len(selection_audit),
            "violation_count": 0,
            "passed": True,
        },
    }
    out = {
        "summary": {
            "research_only": True,
            "does_change_today_advice": False,
            "latest_holdings_hindsight": False,
            "method": "target_fund_quarterly_us_holdings_point_in_time",
            "fund_code": str(fund_code),
            "fund_name": holding_meta.fund_name,
            "latest_report_date": holding_meta.report_date,
            "holdings_source": holding_meta.source,
            "target_benchmark": target,
            "target_label": target_label,
            "target_source": getattr(target_meta, "source", "?"),
            "data_versions": {
                "holdings_history": holdings_version.get("version_id"),
                "target_nav": target_version.get("version_id"),
            },
            "total_cap": float(total_cap),
            "monthly": float(monthly),
            "min_years": float(min_years),
            "start_count": len(starts),
            "top_ns": top_n_list,
            "weight_modes": modes,
            "safe_weights": sw_list,
            "core_ratios": cr_list,
            "max_weight": float(max_weight),
            "min_weight": float(min_weight),
            "availability_delay_days": int(availability_delay_days),
            "rebalance_months": int(rebalance_months),
            "rebalance_same_report": bool(rebalance_same_report),
            "trade_cost_bps": float(trade_cost_bps),
            "step_months": int(step_months),
            "us_ticker_count": len(us_tickers),
            "available_ticker_count": len(series),
            "best": best,
            "note": "历史季度持仓按可获得日期点时回放；只镜像 US ticker 子集，不写 config/state，不改变今日建议。",
        },
        "history_coverage": _history_coverage(history),
        "price_coverage": coverage,
        "price_meta": price_meta,
        "data_manifest": data_manifest,
        "dropped": price_errors,
        "skipped": skipped[:100],
        "rows": rows,
    }
    if include_samples:
        out["samples"] = [sample for _, samples in samples_by_key.items() for sample in samples]
    return out
