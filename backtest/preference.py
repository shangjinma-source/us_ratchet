"""Preference-universe portfolio research.

This module is deliberately research-only. It borrows only the watchlist
organization pattern from a grouped self-selected workflow: tickers can be
grouped by theme, then deterministic basket families are rolled against a
target benchmark. It does not adapt any grid/limit-order strategy, and it never
writes config/state.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from backtest.engine import run_rolling_start_panel, run_rolling_voltarget_panel
from backtest.universe import cached_universe, parse_tickers
from core.config import Symbol
from data.fetch import get_bars


DEFAULT_GROUP = "未分组"
PREFERRED_MAX_HOLDINGS = 6
COMPACT_TOP_NS = (4, 6, 8)


@dataclass(frozen=True)
class BasketSpec:
    name: str
    tickers: tuple[str, ...]
    weights: tuple[tuple[str, float], ...]
    construction: str
    weight_mode: str

    def weight_map(self) -> dict[str, float]:
        return {t: float(w) for t, w in self.weights}


def _dedupe(items: Iterable[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        tk = str(item or "").upper().strip()
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out


def parse_preference_groups(groups: str | Mapping[str, Iterable[str]] | None = None,
                            tickers: str | Iterable[str] | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """Parse grouped user watchlists and return ``(groups, ticker_universe)``."""
    parsed: dict[str, list[str]] = {}
    if isinstance(groups, Mapping):
        for name, vals in groups.items():
            key = str(name or DEFAULT_GROUP).strip() or DEFAULT_GROUP
            parsed[key] = _dedupe(vals)
    else:
        raw = str(groups or "").strip()
        if raw:
            for block in re.split(r"[;\n]+", raw):
                block = block.strip()
                if not block:
                    continue
                if "=" in block:
                    name, body = block.split("=", 1)
                elif ":" in block:
                    name, body = block.split(":", 1)
                else:
                    name, body = DEFAULT_GROUP, block
                key = name.strip() or DEFAULT_GROUP
                parts = re.split(r"[\s,，|/]+", body)
                parsed[key] = _dedupe([p for p in parts if p.strip()])

    explicit = parse_tickers(tickers or "")
    if not parsed:
        parsed[DEFAULT_GROUP] = explicit
    else:
        grouped = {t for vals in parsed.values() for t in vals}
        extras = [t for t in explicit if t not in grouped]
        if extras:
            parsed.setdefault(DEFAULT_GROUP, []).extend(extras)
            parsed[DEFAULT_GROUP] = _dedupe(parsed[DEFAULT_GROUP])

    cleaned = {str(k): _dedupe(v) for k, v in parsed.items() if _dedupe(v)}
    universe = _dedupe(t for vals in cleaned.values() for t in vals)
    return cleaned, universe


def parse_safe_weights(raw: str | Iterable[float]) -> list[float]:
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace(";", ",").split(",")
        vals = []
        for part in parts:
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


def _ret(close: pd.Series, days: int) -> float | None:
    s = close.dropna()
    if len(s) <= days:
        return None
    first = float(s.iloc[-days - 1])
    last = float(s.iloc[-1])
    return last / first - 1.0 if first > 0 else None


def _maxdd(close: pd.Series, days: int) -> float | None:
    s = close.dropna().tail(days)
    if len(s) < 2:
        return None
    arr = s.to_numpy(dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = np.where(peak > 0, (peak - arr) / peak, 0.0)
    return float(np.nanmax(dd))


def _ann_vol(close: pd.Series, days: int) -> float | None:
    r = close.dropna().pct_change(fill_method=None).dropna().tail(days)
    if len(r) < 60:
        return None
    return float(r.std(ddof=1) * np.sqrt(252.0))


def _rank_pct(s: pd.Series, higher: bool = True) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    if not higher:
        x = -x
    return x.rank(pct=True).fillna(0.0)


def _load_metrics(cfg, tickers: list[str]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        try:
            df, meta = get_bars(ticker, cfg)
        except Exception as e:
            rows.append({"ticker": ticker, "error": str(e)})
            continue
        close = df["Close"].copy()
        rows.append({
            "ticker": ticker,
            "ret_1y": _ret(close, 252),
            "ret_3y": _ret(close, 756),
            "vol_3y": _ann_vol(close, 756),
            "dd_3y": _maxdd(close, 756),
            "source": meta.source,
            "error": None,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("ret_1y", "ret_3y", "vol_3y", "dd_3y", "source", "error"):
        if col not in df:
            df[col] = np.nan
    df = df.set_index("ticker", drop=False)
    score = (
        _rank_pct(df["ret_3y"]) * 0.55
        + _rank_pct(df["ret_1y"]) * 0.25
        + _rank_pct(df["dd_3y"], higher=False) * 0.12
        + _rank_pct(df["vol_3y"], higher=False) * 0.08
    )
    df["attack_score"] = score
    return df


def _capped_weights(raw: pd.Series, max_weight: float, min_weight: float) -> pd.Series:
    raw = raw.astype(float).clip(lower=0.0)
    if float(raw.sum()) <= 0:
        raw = pd.Series(1.0, index=raw.index)
    w = raw / float(raw.sum())
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
    return w / float(w.sum())


def _weights_for(tickers: list[str], metrics: pd.DataFrame, mode: str) -> dict[str, float]:
    tickers = _dedupe(tickers)
    if not tickers:
        return {}
    if mode == "equal":
        return {t: 1.0 / len(tickers) for t in tickers}

    m = metrics.reindex(tickers)
    score = pd.to_numeric(m["attack_score"], errors="coerce").fillna(0.0).clip(lower=0.05)
    vol = pd.to_numeric(m["vol_3y"], errors="coerce")
    median_vol = float(vol.dropna().median()) if len(vol.dropna()) else 0.45
    vol = vol.fillna(median_vol).clip(lower=0.15)
    raw = score / vol
    max_w = 0.28 if len(tickers) >= 6 else 0.40
    min_w = 0.04 if len(tickers) >= 6 else 0.08
    w = _capped_weights(raw, max_w, min_w)
    return {t: float(w.loc[t]) for t in tickers}


def _make_spec(name: str, tickers: list[str], metrics: pd.DataFrame,
               construction: str, weight_mode: str) -> BasketSpec:
    weights = _weights_for(tickers, metrics, weight_mode)
    ordered = [t for t in tickers if t in weights]
    return BasketSpec(
        name=name,
        tickers=tuple(ordered),
        weights=tuple((t, weights[t]) for t in ordered),
        construction=construction,
        weight_mode=weight_mode,
    )


def _group_by_ticker(groups: Mapping[str, list[str]]) -> dict[str, str]:
    out = {}
    for name, items in groups.items():
        for t in items:
            out.setdefault(t, name)
    return out


def _group_balanced(ranked: list[str], groups: Mapping[str, list[str]],
                    metrics: pd.DataFrame, n: int) -> list[str]:
    t_to_group = _group_by_ticker(groups)
    live_groups = {}
    for g, items in groups.items():
        live = [t for t in items if t in ranked]
        if live:
            live_groups[g] = live
    if not live_groups:
        return ranked[:n]

    selected: list[str] = []
    counts = {g: 0 for g in live_groups}
    group_order = sorted(
        live_groups,
        key=lambda g: max(float(metrics.loc[t, "attack_score"]) for t in live_groups[g]),
        reverse=True,
    )
    for g in group_order:
        pick = next((t for t in ranked if t in live_groups[g] and t not in selected), None)
        if pick:
            selected.append(pick)
            counts[g] += 1
        if len(selected) >= n:
            return selected[:n]

    max_per_group = max(2, int(math.ceil(n / max(1, len(live_groups))) + 1))
    for t in ranked:
        if t in selected:
            continue
        g = t_to_group.get(t, DEFAULT_GROUP)
        if g in counts and counts[g] >= max_per_group:
            continue
        selected.append(t)
        if g in counts:
            counts[g] += 1
        if len(selected) >= n:
            break
    return selected[:n]


def _candidate_baskets(cfg, tickers: list[str], groups: Mapping[str, list[str]],
                       metrics: pd.DataFrame) -> list[BasketSpec]:
    valid = metrics
    if "error" in valid:
        valid = valid[valid["error"].isna()]
    if valid.empty:
        return []

    baskets: list[BasketSpec] = []
    current = [s.ticker for s in cfg.symbols if s.ticker in valid.index]
    if current:
        total = sum(float(s.cap_total) for s in cfg.symbols if s.ticker in current)
        weights = tuple(
            (s.ticker, float(s.cap_total) / total)
            for s in cfg.symbols
            if s.ticker in current and total > 0
        )
        baskets.append(BasketSpec("current_config", tuple(current), weights,
                                  "当前 config.yaml 标的与 cap_total", "config_cap"))

    valid_tickers = [t for t in tickers if t in valid.index]
    baskets.append(_make_spec("all_equal", valid_tickers, metrics,
                              "用户自选池全量等权", "equal"))
    baskets.append(_make_spec("all_score_risk", valid_tickers, metrics,
                              "用户自选池按进攻分/波动配权", "score_risk"))

    for field in ("ret_3y", "attack_score"):
        ranked = valid.sort_values(field, ascending=False)["ticker"].tolist()
        for n in COMPACT_TOP_NS:
            if len(ranked) >= n:
                picked = ranked[:n]
                baskets.append(_make_spec(f"top{n}_{field}_equal", picked, metrics,
                                          f"按 {field} 排名前 {n} 等权", "equal"))
                baskets.append(_make_spec(f"top{n}_{field}_risk", picked, metrics,
                                          f"按 {field} 排名前 {n}，进攻分/波动配权", "score_risk"))

    ranked_score = valid.sort_values("attack_score", ascending=False)["ticker"].tolist()
    for n in COMPACT_TOP_NS:
        if len(ranked_score) >= n:
            picked = _group_balanced(ranked_score, groups, metrics, n)
            baskets.append(_make_spec(f"group_balanced_top{n}_equal", picked, metrics,
                                      f"自选分组至少覆盖后按 attack_score 填满前 {n} 等权", "equal"))
            baskets.append(_make_spec(f"group_balanced_top{n}_risk", picked, metrics,
                                      f"自选分组至少覆盖后按 attack_score 填满前 {n}，进攻分/波动配权", "score_risk"))

    unique: list[BasketSpec] = []
    seen = set()
    for b in baskets:
        key = (b.tickers, b.weights)
        if b.tickers and key not in seen:
            seen.add(key)
            unique.append(b)
    return unique


def _cfg_for_basket(base_cfg, weights: Mapping[str, float], total_cap: float):
    cfg = copy.deepcopy(base_cfg)
    cfg.symbols = [
        Symbol(ticker=t, cap_total=float(total_cap) * float(w))
        for t, w in weights.items()
        if float(w) > 0
    ]
    total = sum(s.cap_total for s in cfg.symbols)
    for s in cfg.symbols:
        s.weight = s.cap_total / total if total > 0 else 0.0
        s.core_target = s.cap_total * cfg.portfolio.core_ratio
        s.reserve_quota = s.cap_total * (1.0 - cfg.portfolio.core_ratio)
    return cfg


def _group_counts(tickers: Iterable[str], groups: Mapping[str, list[str]]) -> dict[str, int]:
    t_to_group = _group_by_ticker(groups)
    out: dict[str, int] = {}
    for t in tickers:
        g = t_to_group.get(t, DEFAULT_GROUP)
        out[g] = out.get(g, 0) + 1
    return out


def _admission_note(row: dict, target: str) -> dict:
    windows = int(row.get("windows") or 0)
    win = row.get("win_rate")
    excess = row.get("excess_p50")
    dd = row.get("dd_relief_p50")
    if windows < 6:
        return {"stage": "defer", "label": "样本不足", "reason": "012922可用窗口太少，不能作为准入依据。"}
    if win is None or excess is None or win < 0.50 or excess <= 0:
        return {"stage": "defer", "label": "收益未过关", "reason": f"滚动跑赢 {target} 的胜率或超额中位不足。"}
    if dd is not None and dd < 0:
        return {"stage": "candidate", "label": "收益候选", "reason": f"收益侧过关，但回撤中位仍深于 {target}，不能接实盘。"}
    if (win or 0) >= 0.60 and (excess or 0) > 0:
        return {"stage": "eligible", "label": "可继续验证", "reason": "收益和回撤初筛均过线，但仍需样本外/动态权重验证。"}
    return {"stage": "show", "label": "仅展示", "reason": "结果不够稳定，只用于观察。"}


def _evaluate(base_cfg, basket: BasketSpec, safe_weight: float,
              total_cap: float, monthly: float, target: str,
              min_years: float, groups: Mapping[str, list[str]]) -> dict:
    cfg = base_cfg if basket.name == "current_config" else _cfg_for_basket(base_cfg, basket.weight_map(), total_cap)
    roll = run_rolling_start_panel(
        cfg, monthly=float(monthly), min_years=float(min_years),
        safe_weight=float(safe_weight),
        safe_annual=0.04, rebal_days=21, rebal_band=0.15,
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
        "basket": basket.name,
        "construction": basket.construction,
        "weight_mode": basket.weight_mode,
        "defense_mode": "static_safe_weight",
        "tickers": list(basket.tickers),
        "weights": basket.weight_map(),
        "group_counts": _group_counts(basket.tickers, groups),
        "n": len(basket.tickers),
        "safe_weight": float(safe_weight),
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
    }
    row["admission"] = _admission_note(row, target)
    return row


def _evaluate_voltarget(base_cfg, basket: BasketSpec, total_cap: float,
                        monthly: float, target: str, min_years: float,
                        groups: Mapping[str, list[str]]) -> dict:
    cfg = base_cfg if basket.name == "current_config" else _cfg_for_basket(base_cfg, basket.weight_map(), total_cap)
    roll = run_rolling_voltarget_panel(
        cfg, monthly=float(monthly), min_years=float(min_years),
        safe_annual=0.04,
        benchmark_tickers=("QQQ", "SPY", target),
        baseline_ticker=target,
        skip_missing=True,
    )
    s = roll["summary"]
    ex = s.get("excess_xirr") or {}
    dd = s.get("dd_relief") or {}
    sx = s.get("strategy_xirr") or {}
    sd = s.get("strategy_maxdd") or {}
    avg_w = s.get("avg_safe_weight") or {}
    turn = s.get("turnover_x") or {}
    row = {
        "basket": basket.name,
        "construction": basket.construction,
        "weight_mode": basket.weight_mode,
        "defense_mode": "voltarget",
        "tickers": list(basket.tickers),
        "weights": basket.weight_map(),
        "group_counts": _group_counts(basket.tickers, groups),
        "n": len(basket.tickers),
        "safe_weight": None,
        "avg_safe_weight_p50": avg_w.get("p50"),
        "turnover_x_p50": turn.get("p50"),
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
        "voltarget_params": roll.get("params", {}),
    }
    row["admission"] = _admission_note(row, target)
    return row


def _metric_records(metrics: pd.DataFrame, groups: Mapping[str, list[str]]) -> list[dict]:
    t_to_group = _group_by_ticker(groups)
    rows = []
    if metrics.empty:
        return rows
    for _, r in metrics.sort_values("attack_score", ascending=False).iterrows():
        item = {}
        for k, v in r.items():
            if pd.isna(v):
                item[k] = None
            elif isinstance(v, (np.floating, float)):
                item[k] = float(v)
            else:
                item[k] = v
        item["group"] = t_to_group.get(item.get("ticker"), DEFAULT_GROUP)
        rows.append(item)
    return rows


def _best_rows(rows: list[dict]) -> dict:
    valid = [r for r in rows if r.get("windows")]
    if not valid:
        return {}
    best_return = max(valid, key=lambda r: (r.get("win_rate") or -1, r.get("excess_p50") or -9))
    best_balanced = max(valid, key=lambda r: (
        (r.get("excess_p50") or -9) - max(0.0, -(r.get("dd_relief_p50") or 0.0)) * 0.35,
        r.get("win_rate") or -1,
    ))
    best_drawdown = max(valid, key=lambda r: (r.get("dd_relief_p50") if r.get("dd_relief_p50") is not None else -9))
    compact = [r for r in valid if int(r.get("n") or 999) <= PREFERRED_MAX_HOLDINGS]
    best_compact = max(compact, key=lambda r: (
        r.get("win_rate") or -1,
        r.get("excess_p50") or -9,
        r.get("dd_relief_p50") or -9,
        -int(r.get("n") or 999),
    )) if compact else None
    return {
        "best_return": best_return,
        "best_balanced": best_balanced,
        "best_drawdown": best_drawdown,
        "best_compact": best_compact,
    }


def run_preference_portfolio_research(cfg, tickers: str | Iterable[str] = "",
                                      groups: str | Mapping[str, Iterable[str]] | None = None,
                                      *,
                                      total_cap: float = 37000.0,
                                      monthly: float = 3000.0,
                                      target_benchmark: str = "012922",
                                      min_years: float = 3.0,
                                      safe_weights: str | Iterable[float] = "0,0.14,0.26",
                                      include_voltarget: bool = False,
                                      voltarget_top_k: int = 4,
                                      local_only: bool = True) -> dict:
    """Evaluate grouped user preference baskets against the target benchmark."""
    c = _research_cfg(cfg, local_only)
    group_map, requested = parse_preference_groups(groups, tickers)
    if not requested:
        requested = cached_universe(c.cache_dir)
        group_map = {DEFAULT_GROUP: requested}
    if not requested:
        raise ValueError("没有可用候选 ticker；请提供 --tickers 或 --groups")

    target = str(target_benchmark or "012922").upper().strip()
    metrics = _load_metrics(c, requested)
    baskets = _candidate_baskets(c, requested, group_map, metrics)
    if not baskets:
        raise ValueError("候选池没有任何可用行情；请检查 ticker 或关闭 local_only 后取数")
    weights = parse_safe_weights(safe_weights)
    rows = []
    for basket in baskets:
        for w in weights:
            rows.append(_evaluate(c, basket, w, total_cap, monthly, target, min_years, group_map))
    if include_voltarget:
        by_name = {b.name: b for b in baskets}
        leaders = sorted(
            [r for r in rows if r.get("safe_weight") == 0],
            key=lambda r: (r.get("win_rate") or -1, r.get("excess_p50") or -9),
            reverse=True,
        )
        for r in leaders[:max(0, int(voltarget_top_k))]:
            basket = by_name.get(r["basket"])
            if basket is not None:
                rows.append(_evaluate_voltarget(c, basket, total_cap, monthly, target, min_years, group_map))
    rows = sorted(
        rows,
        key=lambda r: (
            r.get("win_rate") or -1,
            r.get("excess_p50") or -9,
            r.get("dd_relief_p50") or -9,
        ),
        reverse=True,
    )
    return {
        "summary": {
            "research_only": True,
            "does_change_today_advice": False,
            "method": "grouped_preference_basket_rolling_ab",
            "target_benchmark": target,
            "min_years": float(min_years),
            "total_cap": float(total_cap),
            "monthly": float(monthly),
            "ticker_count": len(requested),
            "group_count": len(group_map),
            "basket_count": len(baskets),
            "evaluation_count": len(rows),
            "safe_weights": weights,
            "include_voltarget": bool(include_voltarget),
            "voltarget_top_k": int(voltarget_top_k),
            "holding_preference": {
                "preferred_max_holdings": PREFERRED_MAX_HOLDINGS,
                "tested_top_ns": list(COMPACT_TOP_NS),
                "rule": "同等证据下优先 top4/top6 精简篮子；不因少持仓牺牲已验证的收益/回撤准入。",
            },
            "best": _best_rows(rows),
            "note": "只验证自选池/分组下的组合形态；不生成限价单，不写 config/state，不改变今日建议。",
        },
        "groups": [{"name": name, "tickers": vals} for name, vals in group_map.items()],
        "metrics": _metric_records(metrics, group_map),
        "baskets": [
            {
                "name": b.name,
                "construction": b.construction,
                "weight_mode": b.weight_mode,
                "tickers": list(b.tickers),
                "weights": b.weight_map(),
                "group_counts": _group_counts(b.tickers, group_map),
            }
            for b in baskets
        ],
        "rows": rows,
    }
