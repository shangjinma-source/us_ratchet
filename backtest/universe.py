"""Universe diagnostics and dynamic basket research.

This is a research layer, not a live execution rule.  It asks a different
question from the ratchet engine: given a user-supplied technology stock pool,
which names look suitable for a concentrated long-term sleeve, and what weight
shape should be tested before touching config.yaml?
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from backtest.engine import run_nav_panel, run_rolling_start_panel
from backtest import metrics as M
from core.config import Symbol
from data.fetch import get_bars


DEFAULT_EXCLUDED = {"QQQ", "SPY", "SGOV", "SMH", "XSD"}


def cached_universe(cache_dir: str | Path = "data/cache",
                    exclude: Iterable[str] = DEFAULT_EXCLUDED) -> list[str]:
    path = Path(cache_dir)
    excluded = {str(x).upper() for x in exclude}
    if not path.exists():
        return []
    return sorted(p.stem.upper() for p in path.glob("*.csv")
                  if p.stem.upper() not in excluded)


def parse_tickers(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace(";", ",").replace("\n", ",").split(",")
    else:
        parts = list(raw)
    out = []
    seen = set()
    for p in parts:
        tk = str(p or "").upper().strip()
        if not tk or tk in seen:
            continue
        seen.add(tk)
        out.append(tk)
    return out


def _research_cfg(cfg, local_only: bool):
    c = copy.deepcopy(cfg)
    if local_only:
        c.data.fallback_chain = ["local_cache"]
    return c


def _ret(close: pd.Series, days: int) -> float | None:
    s = close.dropna()
    if len(s) <= days:
        return None
    first = float(s.iloc[-days - 1])
    last = float(s.iloc[-1])
    return last / first - 1.0 if first > 0 else None


def _cagr(close: pd.Series) -> float | None:
    s = close.dropna()
    if len(s) < 2:
        return None
    years = (s.index[-1] - s.index[0]).days / 365.25
    if years <= 0 or float(s.iloc[0]) <= 0:
        return None
    return float(s.iloc[-1] / s.iloc[0]) ** (1.0 / years) - 1.0


def _ann_vol(close: pd.Series, days: int) -> float | None:
    r = close.dropna().pct_change(fill_method=None).dropna()
    if len(r) < max(20, min(days, 60)):
        return None
    r = r.tail(days)
    sd = float(r.std(ddof=1))
    return sd * np.sqrt(252.0) if sd > 0 else None


def _maxdd(close: pd.Series, days: int | None = None) -> float | None:
    s = close.dropna()
    if days is not None:
        s = s.tail(days)
    if len(s) < 2:
        return None
    return M.max_drawdown(s.to_numpy(dtype=float))


def _ma(close: pd.Series, days: int) -> float | None:
    s = close.dropna()
    if len(s) < days:
        return None
    return float(s.tail(days).mean())


def _corr_beta(close: pd.Series, bench: pd.Series, days: int) -> tuple[float | None, float | None]:
    joined = pd.concat([close, bench], axis=1, join="inner").dropna()
    if len(joined) < 80:
        return None, None
    rets = joined.pct_change(fill_method=None).dropna().tail(days)
    if len(rets) < 60:
        return None, None
    a = rets.iloc[:, 0]
    b = rets.iloc[:, 1]
    corr = float(a.corr(b))
    var = float(b.var(ddof=1))
    beta = float(a.cov(b) / var) if var > 0 else None
    return corr if np.isfinite(corr) else None, beta if beta is not None and np.isfinite(beta) else None


def _rank_pct(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = values.astype(float)
    if not higher_is_better:
        s = -s
    ranked = s.rank(pct=True)
    return ranked.fillna(0.0)


def _capped_weights(raw: pd.Series, max_weight: float, min_weight: float) -> pd.Series:
    raw = raw.clip(lower=0.0)
    if float(raw.sum()) <= 0:
        raw = pd.Series(1.0, index=raw.index)
    w = raw / raw.sum()
    cap = max(float(max_weight), 1.0 / max(1, len(w)))
    for _ in range(20):
        over = w > cap
        if not bool(over.any()):
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        under = ~over
        if not bool(under.any()) or float(w[under].sum()) <= 0:
            break
        w[under] += w[under] / float(w[under].sum()) * excess

    floor = float(min_weight)
    if floor > 0 and floor * len(w) < 1.0:
        below = w < floor
        if bool(below.any()):
            need = float((floor - w[below]).sum())
            donors = ~below
            available = float((w[donors] - floor).clip(lower=0.0).sum())
            if available >= need and available > 0:
                w[below] = floor
                take = (w[donors] - floor).clip(lower=0.0)
                w[donors] -= take / float(take.sum()) * need
    return w / w.sum()


def _symbols_from_weight_map(weight_map: dict[str, float], total_cap: float,
                             core_ratio: float) -> list[Symbol]:
    syms = [
        Symbol(ticker=t, cap_total=float(total_cap) * float(w))
        for t, w in weight_map.items()
        if float(w) > 0
    ]
    total = sum(s.cap_total for s in syms)
    for s in syms:
        s.weight = s.cap_total / total if total > 0 else 0.0
        s.core_target = s.cap_total * core_ratio
        s.reserve_quota = s.cap_total * (1.0 - core_ratio)
    return syms


def _metric_block_from_panel(res: dict, label_hint: str) -> dict | None:
    curves = res.get("curves") or {}
    if label_hint in curves:
        return curves[label_hint].get("metrics")
    for name, item in curves.items():
        if label_hint in name:
            return item.get("metrics")
    return None


def _rolling_target_summary(res: dict) -> dict:
    rows = res.get("rows") or []
    summary = res.get("summary") or {}
    return {
        "baseline": summary.get("baseline"),
        "windows": summary.get("windows"),
        "win_rate": summary.get("win_rate"),
        "dd_win_rate": summary.get("dd_win_rate"),
        "excess_xirr": summary.get("excess_xirr"),
        "dd_relief": summary.get("dd_relief"),
        "strategy_xirr": summary.get("strategy_xirr"),
        "strategy_maxdd": summary.get("strategy_maxdd"),
        "range": [rows[0]["start"], rows[-1]["start"]] if rows else None,
        "benchmark_errors": res.get("benchmark_errors", {}),
    }


def run_universe_research(cfg, tickers: str | Iterable[str], *,
                          total_cap: float = 37000.0,
                          monthly: float = 3000.0,
                          top_n: int = 8,
                          min_history_years: float = 2.0,
                          max_weight: float = 0.22,
                          min_weight: float = 0.04,
                          max_pair_corr: float = 0.92,
                          drawdown_budget: float = 0.35,
                          local_only: bool = True,
                          include_backtest: bool = True,
                          benchmark_tickers=("QQQ", "SPY", "012922", "SMH", "XSD"),
                          target_benchmark: str = "012922",
                          target_min_years: float = 3.0) -> dict:
    """Rank a candidate universe and build a capped risk-balanced basket.

    The scoring uses only price history available through the data layer:
    momentum, realized risk, trend, and diversification.  It deliberately avoids
    black-box optimization and does not write config/state.
    """
    c = _research_cfg(cfg, local_only)
    requested = parse_tickers(tickers)
    if not requested:
        requested = cached_universe(c.cache_dir)
    requested = [t for t in requested if t not in {"SGOV"}]

    series: dict[str, pd.Series] = {}
    meta = {}
    errors = {}
    for ticker in sorted(set(requested) | {str(x).upper() for x in benchmark_tickers}):
        if len(ticker) == 6 and ticker.isdigit():
            if ticker in requested:
                errors[ticker] = "基金代码不能作为美股候选标的"
            continue
        try:
            df, m = get_bars(ticker, c)
        except Exception as e:
            errors[ticker] = str(e)
            continue
        series[ticker] = df["Close"].copy()
        meta[ticker] = {
            "source": m.source,
            "start": m.start,
            "end": m.end,
            "rows": m.rows,
        }

    candidates = [t for t in requested if t in series]
    if not candidates:
        raise ValueError("候选池没有任何可用行情；请检查 ticker 或关闭 local_only 后取数")

    close_df = pd.DataFrame({t: series[t] for t in candidates}).sort_index()
    trailing_returns = close_df.pct_change(fill_method=None).tail(756)
    corr = trailing_returns.corr(min_periods=60)
    qqq = series.get("QQQ")
    spy = series.get("SPY")

    rows = []
    for t in candidates:
        close = series[t].dropna()
        years = (close.index[-1] - close.index[0]).days / 365.25 if len(close) > 1 else 0.0
        r1 = _ret(close, 252)
        r3 = _ret(close, 756)
        vol1 = _ann_vol(close, 252)
        vol3 = _ann_vol(close, 756)
        dd3 = _maxdd(close, 756)
        dd_all = _maxdd(close)
        ma50 = _ma(close, 50)
        ma200 = _ma(close, 200)
        last = float(close.iloc[-1])
        corr_qqq, beta_qqq = _corr_beta(close, qqq, 756) if qqq is not None else (None, None)
        corr_spy, beta_spy = _corr_beta(close, spy, 756) if spy is not None else (None, None)
        qret = _ret(qqq, 252) if qqq is not None else None
        peers = corr.loc[t].drop(labels=[t], errors="ignore").dropna() if t in corr.index else pd.Series(dtype=float)
        avg_peer_corr = float(peers.mean()) if len(peers) else None
        daily = close.pct_change(fill_method=None).dropna().tail(756)
        sharpe = (float(daily.mean() / daily.std(ddof=1) * np.sqrt(252.0))
                  if len(daily) > 30 and float(daily.std(ddof=1)) > 0 else None)
        rows.append({
            "ticker": t,
            "history_years": float(years),
            "last": last,
            "ret_1y": r1,
            "ret_3y": r3,
            "cagr_all": _cagr(close),
            "ann_vol_1y": vol1,
            "ann_vol_3y": vol3,
            "maxdd_3y": dd3,
            "maxdd_all": dd_all,
            "sharpe_3y": sharpe,
            "ma50": ma50,
            "ma200": ma200,
            "above_ma200": bool(ma200 is not None and last >= ma200),
            "ma50_above_ma200": bool(ma50 is not None and ma200 is not None and ma50 >= ma200),
            "corr_qqq_3y": corr_qqq,
            "beta_qqq_3y": beta_qqq,
            "corr_spy_3y": corr_spy,
            "beta_spy_3y": beta_spy,
            "rel_qqq_1y": (r1 - qret if r1 is not None and qret is not None else None),
            "avg_peer_corr_3y": avg_peer_corr,
            "source": meta.get(t, {}).get("source"),
            "start": meta.get(t, {}).get("start"),
            "end": meta.get(t, {}).get("end"),
        })

    df = pd.DataFrame(rows).set_index("ticker")
    trend = (
        df["above_ma200"].astype(float) * 0.60
        + df["ma50_above_ma200"].astype(float) * 0.40
    )
    mom = (
        _rank_pct(df["ret_1y"]) * 0.45
        + _rank_pct(df["ret_3y"]) * 0.35
        + _rank_pct(df["rel_qqq_1y"]) * 0.20
    )
    risk = (
        _rank_pct(df["ann_vol_3y"], higher_is_better=False) * 0.45
        + _rank_pct(df["maxdd_3y"], higher_is_better=False) * 0.35
        + _rank_pct(df["sharpe_3y"]) * 0.20
    )
    diversifier = _rank_pct(df["avg_peer_corr_3y"], higher_is_better=False)
    df["score"] = (mom * 0.42 + risk * 0.25 + trend * 0.18 + diversifier * 0.15).clip(0, 1)
    df["eligible"] = df["history_years"] >= float(min_history_years)

    ranked = df.sort_values(["eligible", "score"], ascending=[False, False])
    target_n = max(1, min(int(top_n), len(ranked)))
    selected_names: list[str] = []
    skipped_similar = []
    for t, row in ranked.iterrows():
        if len(selected_names) >= target_n:
            break
        if not bool(row.get("eligible")):
            continue
        similar_to = None
        for kept in selected_names:
            try:
                cv = float(corr.loc[t, kept])
            except Exception:
                cv = np.nan
            if np.isfinite(cv) and cv >= float(max_pair_corr):
                similar_to = {"kept": kept, "corr": cv}
                break
        if similar_to:
            skipped_similar.append({"skipped": t, **similar_to})
            continue
        selected_names.append(t)
    for t, _ in ranked.iterrows():
        if len(selected_names) >= target_n:
            break
        if t not in selected_names:
            selected_names.append(t)
    selected = ranked.loc[selected_names]

    vol = selected["ann_vol_3y"].fillna(selected["ann_vol_1y"]).fillna(selected["ann_vol_3y"].median())
    vol = vol.fillna(0.35).clip(lower=0.12)
    raw_weight = (selected["score"].clip(lower=0.05) ** 1.35) / vol
    weights = _capped_weights(raw_weight, max_weight=max_weight, min_weight=min_weight)
    selected = selected.copy()
    selected["weight"] = weights
    selected["cap_total"] = selected["weight"] * float(total_cap)

    selected_corr = close_df[list(selected.index)].pct_change(fill_method=None).tail(756).corr(min_periods=60)
    pair_vals = []
    for i, a in enumerate(selected_corr.columns):
        for b in selected_corr.columns[i + 1:]:
            v = selected_corr.loc[a, b]
            if pd.notna(v):
                pair_vals.append(float(v))
    avg_pair_corr = float(np.mean(pair_vals)) if pair_vals else None
    avg_qqq_corr = float(selected["corr_qqq_3y"].dropna().mean()) if selected["corr_qqq_3y"].notna().any() else None

    backtest = None
    safe_weight_estimate = None
    if include_backtest:
        current_res = run_nav_panel(
            c, monthly=float(monthly),
            safe_weight=(c.safe_leg.target_weight if c.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21,
            rebal_band=(c.safe_leg.exec_band if c.safe_leg else 0.0),
            benchmark_tickers=benchmark_tickers,
            skip_missing=True)
        current_strategy = (
            _metric_block_from_panel(current_res, "策略+防御层")
            or _metric_block_from_panel(current_res, "策略")
        )
        current_pure = _metric_block_from_panel(current_res, "纯棘轮")

        bt_cfg = copy.deepcopy(c)
        weight_map = {t: float(w) for t, w in selected["weight"].items()}
        bt_cfg.symbols = _symbols_from_weight_map(
            weight_map, float(total_cap), bt_cfg.portfolio.core_ratio)
        res = run_nav_panel(
            bt_cfg, monthly=float(monthly),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21,
            rebal_band=(bt_cfg.safe_leg.exec_band if bt_cfg.safe_leg else 0.0),
            benchmark_tickers=benchmark_tickers,
            skip_missing=True)
        strategy = _metric_block_from_panel(res, "策略+防御层") or _metric_block_from_panel(res, "策略")
        pure = _metric_block_from_panel(res, "纯棘轮")
        pure_dd = pure.get("maxdd") if pure else None
        if pure_dd and pure_dd > 0 and drawdown_budget > 0:
            safe_weight_estimate = float(np.clip(1.0 - float(drawdown_budget) / float(pure_dd), 0.0, 0.65))
        backtest = {
            "range": [
                res["grid"][0].strftime("%Y-%m-%d"),
                res["grid"][-1].strftime("%Y-%m-%d"),
            ] if len(res.get("grid", [])) else None,
            "strategy": strategy,
            "pure_ratchet": pure,
            "current_config": {
                "range": [
                    current_res["grid"][0].strftime("%Y-%m-%d"),
                    current_res["grid"][-1].strftime("%Y-%m-%d"),
                ] if len(current_res.get("grid", [])) else None,
                "strategy": current_strategy,
                "pure_ratchet": current_pure,
            },
            "benchmarks": {
                k: v.get("metrics") for k, v in (res.get("curves") or {}).items()
                if k not in {"纯棘轮"} and "策略" not in k
            },
            "benchmark_errors": res.get("benchmark_errors", {}),
            "safe_weight_current": res.get("safe_weight"),
            "safe_weight_estimate_for_budget": safe_weight_estimate,
        }
        if target_benchmark:
            target = str(target_benchmark).upper()
            target_tickers = tuple(dict.fromkeys(("QQQ", "SPY", target)))
            current_roll = run_rolling_start_panel(
                c, monthly=float(monthly),
                min_years=float(target_min_years),
                safe_weight=(c.safe_leg.target_weight if c.safe_leg else 0.0),
                safe_annual=0.04, rebal_days=21,
                rebal_band=(c.safe_leg.exec_band if c.safe_leg else 0.0),
                benchmark_tickers=target_tickers,
                baseline_ticker=target,
                skip_missing=True)
            reco_roll = run_rolling_start_panel(
                bt_cfg, monthly=float(monthly),
                min_years=float(target_min_years),
                safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
                safe_annual=0.04, rebal_days=21,
                rebal_band=(bt_cfg.safe_leg.exec_band if bt_cfg.safe_leg else 0.0),
                benchmark_tickers=target_tickers,
                baseline_ticker=target,
                skip_missing=True)
            backtest["target_rolling"] = {
                "target": target,
                "min_years": float(target_min_years),
                "current_config": _rolling_target_summary(current_roll),
                "recommended": _rolling_target_summary(reco_roll),
            }

    if avg_pair_corr is None:
        fit = "数据不足，暂不能判断相关性。"
    elif avg_pair_corr >= 0.70:
        fit = "高相关科技篮子：个股储备难以显著抗跌，回撤控制应主要靠组合防御层和权重上限。"
    elif avg_pair_corr >= 0.50:
        fit = "中高相关科技篮子：适合进攻 sleeve，但不要期待棘轮储备单独压住板块级回撤。"
    else:
        fit = "相关性较分散：个股层棘轮更可能产生差异化补仓价值，但仍需滚动验证。"

    selected_rows = selected.reset_index().sort_values("weight", ascending=False)
    all_rows = df.reset_index().sort_values("score", ascending=False)
    return {
        "requested": requested,
        "used": candidates,
        "dropped": {k: v for k, v in errors.items() if k in requested},
        "ranking": all_rows.to_dict(orient="records"),
        "selected": selected_rows.to_dict(orient="records"),
        "basket": [
            {"ticker": r["ticker"], "weight": float(r["weight"]),
             "cap_total": round(float(r["cap_total"]), 2)}
            for r in selected_rows.to_dict(orient="records")
        ],
        "summary": {
            "method": "price_only_momentum_risk_trend_diversification",
            "score_weights": {
                "momentum": 0.42,
                "risk": 0.25,
                "trend": 0.18,
                "diversification": 0.15,
            },
            "top_n": int(top_n),
            "total_cap": float(total_cap),
            "min_history_years": float(min_history_years),
            "max_weight": float(max_weight),
            "min_weight": float(min_weight),
            "max_pair_corr": float(max_pair_corr),
            "avg_pairwise_corr_3y": avg_pair_corr,
            "avg_corr_qqq_3y": avg_qqq_corr,
            "strategy_fit": fit,
            "safe_weight_estimate_for_budget": safe_weight_estimate,
            "drawdown_budget": float(drawdown_budget),
            "research_only": True,
            "note": "仅用价格历史，不含基本面/估值/财报质量；不能直接写回实盘配置。",
        },
        "skipped_similar": skipped_similar,
        "backtest": backtest,
    }
