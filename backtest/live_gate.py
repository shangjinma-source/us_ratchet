"""Read-only live admission gate for dynamic preference baskets.

The preference/universe research layer can produce attractive baskets, but that
does not mean the live ratchet engine may use them.  This module turns a
research result into an explicit preflight decision:

* historical and rolling evidence,
* current market applicability,
* whether today's advice would change,
* and a config diff preview that is deliberately marked as not applicable.

It never writes config/state and never generates executable orders.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

from backtest.engine import run_rolling_start_panel
from backtest.preference import PREFERRED_MAX_HOLDINGS, run_preference_portfolio_research
from backtest.risk_envelope import (
    evaluate_candidate_risk_envelope,
    evaluate_incumbent_risk_guard,
    resolve_risk_envelope_policy,
)


STAGE_RANK = {"eligible": 3, "candidate": 2, "defer": 1, "show": 0}


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _stage(row: dict) -> str:
    return str((row.get("admission") or {}).get("stage") or "show")


def _stage_label(row: dict) -> str:
    return str((row.get("admission") or {}).get("label") or _stage(row))


def _stage_reason(row: dict) -> str:
    adm = row.get("admission") or {}
    return str(adm.get("reason") or adm.get("summary") or "")


def _holding_count(row: dict) -> int:
    n = _num(row.get("n"))
    if n is not None:
        return int(round(n))
    return len(row.get("tickers") or [])


def _row_sort_key(row: dict) -> tuple:
    n = _holding_count(row)
    return (
        STAGE_RANK.get(_stage(row), -1),
        _num(row.get("win_rate")) or -9.0,
        _num(row.get("excess_p50")) or -9.0,
        1 if 0 < n <= PREFERRED_MAX_HOLDINGS else 0,
        -n if n > 0 else -999,
        _num(row.get("dd_relief_p50")) or -9.0,
        -(_num(row.get("maxdd_p50")) or 9.0),
    )


def _row_summary(row: dict) -> dict:
    return {
        "basket": row.get("basket"),
        "defense_mode": row.get("defense_mode"),
        "safe_weight": row.get("safe_weight"),
        "avg_safe_weight_p50": row.get("avg_safe_weight_p50"),
        "n": row.get("n"),
        "compact_preferred": 0 < _holding_count(row) <= PREFERRED_MAX_HOLDINGS,
        "tickers": list(row.get("tickers") or []),
        "weights": row.get("weights") or {},
        "windows": row.get("windows"),
        "win_rate": row.get("win_rate"),
        "dd_win_rate": row.get("dd_win_rate"),
        "excess_p50": row.get("excess_p50"),
        "excess_p10": row.get("excess_p10"),
        "dd_relief_p50": row.get("dd_relief_p50"),
        "dd_relief_p10": row.get("dd_relief_p10"),
        "xirr_p10": row.get("xirr_p10"),
        "xirr_p50": row.get("xirr_p50"),
        "maxdd_p90": row.get("maxdd_p90"),
        "maxdd_p50": row.get("maxdd_p50"),
        "range": row.get("range"),
        "data_versions": row.get("data_versions") or {},
        "admission": row.get("admission") or {},
    }


def _roll_summary_for_guard(roll: dict) -> dict:
    s = roll.get("summary") or {}
    sx = s.get("strategy_xirr") or {}
    sd = s.get("strategy_maxdd") or {}
    bx = s.get("benchmark_xirr") or {}
    bd = s.get("benchmark_maxdd") or {}
    ex = s.get("excess_xirr") or {}
    dd = s.get("dd_relief") or {}
    return {
        "windows": s.get("windows"),
        "win_rate": s.get("win_rate"),
        "dd_win_rate": s.get("dd_win_rate"),
        "xirr_p10": sx.get("p10"),
        "xirr_p50": sx.get("p50"),
        "xirr_p90": sx.get("p90"),
        "maxdd_p10": sd.get("p10"),
        "maxdd_p50": sd.get("p50"),
        "maxdd_p90": sd.get("p90"),
        "excess_p50": ex.get("p50"),
        "dd_relief_p50": dd.get("p50"),
        "distribution": {
            "strategy_xirr": sx,
            "strategy_maxdd": sd,
            "benchmark_xirr": bx,
            "benchmark_maxdd": bd,
            "excess_xirr": ex,
            "dd_relief": dd,
        },
        "rolling_samples": [
            {
                "start": item.get("start"),
                "end": item.get("end"),
                "xirr": (item.get("strategy") or {}).get("xirr"),
                "maxdd": (item.get("strategy") or {}).get("maxdd"),
            }
            for item in roll.get("rows") or []
        ],
        "range": [roll["rows"][0]["start"], roll["rows"][-1]["start"]] if roll.get("rows") else None,
        "benchmark_errors": roll.get("benchmark_errors", {}),
        "data_versions": roll.get("data_versions", {}),
    }


def _incumbent_research(cfg, monthly: float, target_benchmark: str,
                        min_years: float,
                        incumbent_basis: str = "caller_cfg") -> dict:
    if cfg is None:
        return {"available": False, "reason": "cfg unavailable"}
    target = str(target_benchmark or "012922").upper().strip()
    safe_weight = float(getattr(getattr(cfg, "safe_leg", None), "target_weight", 0.0) or 0.0)
    roll = run_rolling_start_panel(
        cfg,
        monthly=float(monthly),
        min_years=float(min_years),
        safe_weight=safe_weight,
        safe_annual=0.04,
        rebal_days=21,
        rebal_band=float(getattr(getattr(cfg, "safe_leg", None), "exec_band", 0.15) or 0.15),
        benchmark_tickers=("QQQ", "SPY", target),
        baseline_ticker=target,
        skip_missing=True,
    )
    out = _roll_summary_for_guard(roll)
    out.update({
        "available": True,
        "label": f"current_config+defense(W={safe_weight:.0%})",
        "target_benchmark": target,
        "safe_weight": safe_weight,
        "basis": str(incumbent_basis or "caller_cfg"),
    })
    return out


def _evaluate_incumbent_guard(best: dict | None, incumbent: dict | None,
                              policy=None) -> dict:
    return evaluate_incumbent_risk_guard(best, incumbent, policy=policy)


def _stage_counts(rows: list[dict]) -> dict[str, int]:
    counts = {"eligible": 0, "candidate": 0, "defer": 0, "show": 0}
    for row in rows:
        st = _stage(row)
        counts[st] = counts.get(st, 0) + 1
    return counts


def _current_caps(cfg) -> dict[str, float]:
    out = {}
    for sym in getattr(cfg, "symbols", []) or []:
        out[str(sym.ticker).upper()] = float(sym.cap_total)
    return out


def _config_diff_preview(cfg, row: dict | None, total_cap: float) -> dict:
    if not row:
        return {"should_apply": False, "symbols": [], "removed": []}

    weights = {str(t).upper(): float(w) for t, w in (row.get("weights") or {}).items()}
    current = _current_caps(cfg) if cfg is not None else {}
    core_ratio = float(getattr(getattr(cfg, "portfolio", None), "core_ratio", 0.90) or 0.90)
    symbols = []
    for ticker, weight in sorted(weights.items(), key=lambda kv: kv[1], reverse=True):
        cap = float(total_cap) * weight
        old = current.get(ticker, 0.0)
        if old <= 0:
            status = "add"
        elif abs(old - cap) <= max(1.0, cap * 0.01):
            status = "keep"
        else:
            status = "resize"
        symbols.append({
            "ticker": ticker,
            "weight": weight,
            "cap_total": cap,
            "current_cap_total": old,
            "delta_cap_total": cap - old,
            "core_target": cap * core_ratio,
            "reserve_quota": cap * (1.0 - core_ratio),
            "status": status,
        })

    removed = [
        {"ticker": ticker, "current_cap_total": cap}
        for ticker, cap in sorted(current.items())
        if ticker not in weights
    ]
    safe_target = row.get("safe_weight")
    if row.get("defense_mode") == "voltarget":
        safe_target = "dynamic_voltarget"
    return {
        "should_apply": False,
        "reason": "Preview only. Live config/state writes are blocked until the full gate passes.",
        "defense_mode": row.get("defense_mode"),
        "safe_weight_target": safe_target,
        "total_cap": float(total_cap),
        "core_ratio": core_ratio,
        "symbols": symbols,
        "removed": removed,
    }


def _market_summary(market: dict | None) -> dict:
    if not market:
        return {
            "regime": "UNKNOWN",
            "label": "unknown",
            "applicable": False,
            "rule": "Market phase was not supplied; live connection remains blocked.",
        }
    regime = str(market.get("regime") or "UNKNOWN")
    return {
        "regime": regime,
        "label": str(market.get("label") or regime),
        "applicable": regime in {"BULL", "NEUTRAL", "BEAR"},
        "rule": "Market layer may only reduce buy aggressiveness; it cannot promote a research basket into live advice.",
        "detail": market.get("rule"),
    }


def evaluate_preference_live_gate(research: dict, cfg=None,
                                  market: dict | None = None) -> dict:
    """Summarize whether a preference-basket research result may affect live advice."""
    rows = list(research.get("rows") or [])
    ranked = sorted(rows, key=_row_sort_key, reverse=True)
    best = ranked[0] if ranked else None
    eligible = [r for r in ranked if _stage(r) == "eligible"]
    candidates = [r for r in ranked if _stage(r) == "candidate"]
    total_cap = float((research.get("summary") or {}).get("total_cap") or 0.0)
    summary = research.get("summary") or {}
    holding_pref = summary.get("holding_preference") or {
        "preferred_max_holdings": PREFERRED_MAX_HOLDINGS,
        "rule": "同等证据下优先精简篮子。",
    }
    best_compact = ((summary.get("best") or {}).get("best_compact"))
    incumbent = (research.get("summary") or {}).get("incumbent_guard")
    policy = resolve_risk_envelope_policy(cfg)
    target_benchmark = str(summary.get("target_benchmark") or policy.target_benchmark).upper()
    risk_envelope = evaluate_candidate_risk_envelope(
        best,
        incumbent,
        target=target_benchmark,
        policy=policy,
    )
    guard = risk_envelope["incumbent"]

    if not rows:
        decision = "NO_RESEARCH"
        live_stage = "blocked"
        blockers = ["No research rows were produced."]
    elif not eligible:
        decision = "BLOCKED_BY_ADMISSION"
        live_stage = "blocked"
        if best:
            blockers = [
                f"Best row is {_stage_label(best)}: {_stage_reason(best)}",
                "No basket passed both return and drawdown admission versus the target benchmark.",
            ]
        else:
            blockers = ["No basket passed admission."]
    elif not guard.get("passed"):
        decision = "BLOCKED_BY_INCUMBENT"
        live_stage = "blocked"
        blockers = [
            guard.get("reason") or "Candidate failed incumbent guard.",
            "Dynamic candidates must be no worse than the current written config before any live connection.",
        ]
    else:
        decision = "RESEARCH_CANDIDATE_ONLY"
        live_stage = "blocked"
        blockers = [
            "At least one basket passed the first admission screen, but live connection is still disabled.",
            "Required next checks are point-in-time walk-forward, sample-out validation, and today's advice diff.",
        ]

    history = {
        "improved_return": bool(best and (_num(best.get("excess_p50")) or -9.0) > 0),
        "drawdown_ok": bool(risk_envelope["target"].get("risk_passed")),
        "incumbent_guard_passed": bool(guard.get("passed")),
        "risk_envelope_passed": bool(risk_envelope.get("passed")),
        "drawdown_tradeoff": risk_envelope["target"].get("metrics"),
        "best": _row_summary(best) if best else None,
        "eligible_count": len(eligible),
        "candidate_count": len(candidates),
        "stage_counts": _stage_counts(rows),
        "holding_preference": holding_pref,
        "best_compact": _row_summary(best_compact) if best_compact else None,
    }

    return {
        "research_only": True,
        "live_connected": False,
        "does_change_today_advice": False,
        "decision": decision,
        "live_stage": live_stage,
        "target_benchmark": (research.get("summary") or {}).get("target_benchmark"),
        "history": history,
        "risk_envelope": risk_envelope,
        "incumbent_guard": guard,
        "current_market": _market_summary(market),
        "today": {
            "would_change_advice": False,
            "reason": "The dynamic basket gate is read-only; /api/state and config.yaml are unchanged.",
            "changes": [],
        },
        "blockers": blockers,
        "next_validation": [
            "Require the configured target DD-cost envelope on rolling starts, including the adverse tail.",
            "Require the incumbent guard on XIRR P50/P10 and maximum-drawdown P50/P90.",
            f"Prefer compact baskets with <= {PREFERRED_MAX_HOLDINGS} holdings when evidence is otherwise comparable.",
            "Run sample-out or expanding-window validation; do not tune on the same 2022-2026 slice only.",
            "Replay dynamic weight selection with /api/preference_walkforward before any config write.",
            "Compute a today-advice diff and require manual approval before changing live rules.",
        ],
        "config_diff_preview": _config_diff_preview(cfg, best, total_cap),
        "top_rows": [_row_summary(r) for r in ranked[:5]],
        "summary": {
            "ticker_count": (research.get("summary") or {}).get("ticker_count"),
            "group_count": (research.get("summary") or {}).get("group_count"),
            "evaluation_count": len(rows),
            "include_voltarget": (research.get("summary") or {}).get("include_voltarget"),
            "risk_envelope_policy": risk_envelope.get("policy"),
        },
    }


def run_preference_live_gate(cfg, tickers: str | Iterable[str] = "",
                             groups: str | Mapping[str, Iterable[str]] | None = None,
                             *,
                             total_cap: float = 37000.0,
                             monthly: float = 3000.0,
                             target_benchmark: str = "012922",
                             min_years: float = 3.0,
                             safe_weights: str | Iterable[float] = "0,0.14,0.26",
                             include_voltarget: bool = False,
                             voltarget_top_k: int = 4,
                             local_only: bool = True,
                             market: dict | None = None,
                             incumbent_basis: str = "caller_cfg",
                             include_research: bool = False) -> dict:
    """Run preference research and return the read-only live gate decision."""
    research = run_preference_portfolio_research(
        cfg,
        tickers=tickers,
        groups=groups,
        total_cap=total_cap,
        monthly=monthly,
        target_benchmark=target_benchmark,
        min_years=min_years,
        safe_weights=safe_weights,
        include_voltarget=include_voltarget,
        voltarget_top_k=voltarget_top_k,
        local_only=local_only,
    )
    try:
        incumbent = _incumbent_research(
            cfg,
            monthly=float(monthly),
            target_benchmark=target_benchmark,
            min_years=float(min_years),
            incumbent_basis=incumbent_basis,
        )
    except Exception as e:
        incumbent = {"available": False, "reason": repr(e)}
    research.setdefault("summary", {})["incumbent_guard"] = incumbent
    research["summary"]["incumbent_basis"] = str(incumbent_basis or "caller_cfg")
    gate = evaluate_preference_live_gate(research, cfg=cfg, market=market)
    if include_research:
        gate["research"] = research
    return gate
