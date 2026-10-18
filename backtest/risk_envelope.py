"""Fail-closed risk envelope for research-only strategy candidates.

The target screen allows a measured drawdown cost versus 012922, while the
incumbent screen prevents a candidate from materially weakening the current
written strategy.  Maximum drawdown is a loss metric, so its adverse tail is
P90; for ``dd_relief = benchmark_dd - candidate_dd`` the adverse tail is P10.
"""
from __future__ import annotations

from dataclasses import asdict
from math import isfinite
from typing import Any

from core.config import ResearchAdmissionConfig


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _metric(row: dict | None, direct_key: str, distribution_key: str,
            quantile: str) -> float | None:
    if not row:
        return None
    direct = _num(row.get(direct_key))
    if direct is not None:
        return direct
    distribution = row.get("distribution") or {}
    return _num((distribution.get(distribution_key) or {}).get(quantile))


def _quantile(values: list[float], probability: float) -> float | None:
    clean = sorted(
        number for value in values
        if (number := _num(value)) is not None
    )
    if not clean:
        return None
    position = (len(clean) - 1) * float(probability)
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    weight = position - lower
    return float(clean[lower] * (1.0 - weight) + clean[upper] * weight)


def _paired_differences(candidate: dict, incumbent: dict) -> dict:
    incumbent_by_start = {
        str(item.get("start")): item
        for item in incumbent.get("rolling_samples") or []
        if item.get("start")
    }
    xirr_margins = []
    dd_costs = []
    starts = []
    for item in candidate.get("rolling_samples") or []:
        start = str(item.get("start") or "")
        peer = incumbent_by_start.get(start)
        if not peer:
            continue
        candidate_xirr = _num(item.get("xirr"))
        incumbent_xirr = _num(peer.get("xirr"))
        candidate_dd = _num(item.get("maxdd"))
        incumbent_dd = _num(peer.get("maxdd"))
        if None in {candidate_xirr, incumbent_xirr, candidate_dd, incumbent_dd}:
            continue
        starts.append(start)
        xirr_margins.append(candidate_xirr - incumbent_xirr)
        dd_costs.append(candidate_dd - incumbent_dd)
    return {
        "windows": len(starts),
        "starts": starts,
        "xirr_margin_p50": _quantile(xirr_margins, 0.50),
        "xirr_margin_p10": _quantile(xirr_margins, 0.10),
        "dd_cost_p50": _quantile(dd_costs, 0.50),
        "dd_cost_p90": _quantile(dd_costs, 0.90),
    }


def resolve_risk_envelope_policy(value=None) -> ResearchAdmissionConfig:
    if isinstance(value, ResearchAdmissionConfig):
        return value
    nested = getattr(value, "research_admission", None)
    if isinstance(nested, ResearchAdmissionConfig):
        return nested
    if isinstance(value, dict):
        return ResearchAdmissionConfig(**{**ResearchAdmissionConfig().__dict__, **value})
    return ResearchAdmissionConfig()


def _check(name: str, value: float | int | None, threshold: float | int,
           operator: str) -> dict:
    if value is None:
        passed = False
    elif operator == ">=":
        passed = value >= threshold
    elif operator == "<=":
        passed = value <= threshold
    else:
        raise ValueError(f"unsupported risk-envelope operator: {operator}")
    return {
        "name": name,
        "passed": bool(passed),
        "value": value,
        "operator": operator,
        "threshold": threshold,
    }


def evaluate_target_risk_envelope(row: dict | None, *, target: str = "012922",
                                  policy=None) -> dict:
    """Evaluate return evidence and controlled DD cost versus the target."""
    p = resolve_risk_envelope_policy(policy)
    candidate = row or {}
    windows = int(_num(candidate.get("windows")) or 0)
    win_rate = _num(candidate.get("win_rate"))
    excess_p50 = _metric(candidate, "excess_p50", "excess_xirr", "p50")
    relief_p50 = _metric(candidate, "dd_relief_p50", "dd_relief", "p50")
    relief_p10 = _metric(candidate, "dd_relief_p10", "dd_relief", "p10")
    dd_cost_p50 = -relief_p50 if relief_p50 is not None else None
    dd_cost_bad_tail = -relief_p10 if relief_p10 is not None else None

    checks = [
        _check("rolling_windows", windows, p.min_rolling_windows, ">="),
        _check("target_win_rate", win_rate, p.min_target_win_rate, ">="),
        _check("target_excess_xirr_p50", excess_p50, p.min_target_excess_p50, ">="),
        _check("target_dd_cost_p50", dd_cost_p50, p.max_target_dd_cost_p50, "<="),
        _check(
            "target_dd_cost_bad_tail",
            dd_cost_bad_tail,
            p.max_target_dd_cost_bad_tail,
            "<=",
        ),
    ]
    return_checks = checks[:3]
    risk_checks = checks[3:]
    return_passed = all(item["passed"] for item in return_checks)
    risk_passed = all(item["passed"] for item in risk_checks)
    passed = bool(return_passed and risk_passed)

    if not all(item["value"] is not None for item in checks):
        classification = "INSUFFICIENT_EVIDENCE"
        reason = "缺少滚动收益或回撤尾部分位，风险包络按未通过处理。"
    elif not return_passed:
        classification = "RETURN_NOT_ATTRACTIVE"
        reason = f"相对 {target} 的滚动收益证据不足。"
    elif not risk_passed:
        classification = "OUTSIDE_TARGET_ENVELOPE"
        reason = f"相对 {target} 的滚动回撤代价超过研究预算。"
    elif dd_cost_p50 <= 0 and dd_cost_bad_tail <= 0:
        classification = "INSIDE_TARGET_ENVELOPE"
        reason = f"收益证据过线，且滚动回撤中位与坏尾部均不深于 {target}。"
    else:
        classification = "CONTROLLED_ATTACK"
        reason = f"收益证据过线；相对 {target} 更进攻，但回撤代价仍在显式预算内。"

    return {
        "available": all(item["value"] is not None for item in checks),
        "passed": passed,
        "target": str(target or p.target_benchmark).upper(),
        "classification": classification,
        "reason": reason,
        "return_passed": return_passed,
        "risk_passed": risk_passed,
        "metrics": {
            "windows": windows,
            "win_rate": win_rate,
            "excess_xirr_p50": excess_p50,
            "dd_relief_p50": relief_p50,
            "dd_relief_p10": relief_p10,
            "dd_cost_p50": dd_cost_p50,
            "dd_cost_bad_tail": dd_cost_bad_tail,
        },
        "checks": checks,
        "policy": asdict(p),
    }


def evaluate_incumbent_risk_guard(candidate: dict | None,
                                  incumbent: dict | None, *, policy=None) -> dict:
    """Compare candidate P50/P10 return and P50/P90 DD with the incumbent."""
    p = resolve_risk_envelope_policy(policy)
    if not incumbent or not incumbent.get("available"):
        return {
            "available": False,
            "passed": False,
            "reason": (incumbent or {}).get("reason") or "incumbent research unavailable",
            "policy": asdict(p),
        }
    if not candidate:
        return {
            "available": True,
            "passed": False,
            "reason": "no candidate row",
            "policy": asdict(p),
        }

    cand_x50 = _metric(candidate, "xirr_p50", "strategy_xirr", "p50")
    cand_x10 = _metric(candidate, "xirr_p10", "strategy_xirr", "p10")
    cand_dd50 = _metric(candidate, "maxdd_p50", "strategy_maxdd", "p50")
    cand_dd90 = _metric(candidate, "maxdd_p90", "strategy_maxdd", "p90")
    inc_x50 = _metric(incumbent, "xirr_p50", "strategy_xirr", "p50")
    inc_x10 = _metric(incumbent, "xirr_p10", "strategy_xirr", "p10")
    inc_dd50 = _metric(incumbent, "maxdd_p50", "strategy_maxdd", "p50")
    inc_dd90 = _metric(incumbent, "maxdd_p90", "strategy_maxdd", "p90")

    has_sample_evidence = (
        "rolling_samples" in candidate or "rolling_samples" in incumbent
    )
    paired = _paired_differences(candidate, incumbent) if has_sample_evidence else None
    if paired is not None:
        comparison_basis = "paired_rolling_start_deltas"
        x_margin_p50 = paired["xirr_margin_p50"]
        x_margin_p10 = paired["xirr_margin_p10"]
        dd_cost_p50 = paired["dd_cost_p50"]
        dd_cost_p90 = paired["dd_cost_p90"]
    else:
        comparison_basis = "quantile_difference_legacy_fallback"
        x_margin_p50 = cand_x50 - inc_x50 if cand_x50 is not None and inc_x50 is not None else None
        x_margin_p10 = cand_x10 - inc_x10 if cand_x10 is not None and inc_x10 is not None else None
        dd_cost_p50 = cand_dd50 - inc_dd50 if cand_dd50 is not None and inc_dd50 is not None else None
        dd_cost_p90 = cand_dd90 - inc_dd90 if cand_dd90 is not None and inc_dd90 is not None else None
    checks = []
    if paired is not None:
        checks.append(_check(
            "paired_rolling_windows",
            paired["windows"],
            p.min_rolling_windows,
            ">=",
        ))
    checks.extend([
        _check(
            "xirr_margin_p50_vs_incumbent",
            x_margin_p50,
            p.min_incumbent_xirr_margin_p50,
            ">=",
        ),
        _check(
            "xirr_margin_p10_vs_incumbent",
            x_margin_p10,
            p.min_incumbent_xirr_margin_p10,
            ">=",
        ),
        _check(
            "dd_cost_p50_vs_incumbent",
            dd_cost_p50,
            p.max_incumbent_dd_cost_p50,
            "<=",
        ),
        _check(
            "dd_cost_p90_vs_incumbent",
            dd_cost_p90,
            p.max_incumbent_dd_cost_p90,
            "<=",
        ),
    ])
    available = all(item["value"] is not None for item in checks)
    passed = bool(available and all(item["passed"] for item in checks))
    reason = (
        "candidate is within the incumbent P50 and adverse-tail risk budget"
        if passed
        else "candidate fails the incumbent P50 or adverse-tail risk budget"
    )
    return {
        "available": available,
        "passed": passed,
        "reason": reason,
        "comparison_basis": comparison_basis,
        "paired_evidence": paired,
        "candidate": {
            "basket": candidate.get("basket"),
            "defense_mode": candidate.get("defense_mode"),
            "safe_weight": candidate.get("safe_weight"),
            "xirr_p50": cand_x50,
            "xirr_p10": cand_x10,
            "maxdd_p50": cand_dd50,
            "maxdd_p90": cand_dd90,
        },
        "incumbent": incumbent,
        "margins": {
            "xirr_p50_vs_incumbent": x_margin_p50,
            "xirr_p10_vs_incumbent": x_margin_p10,
            "dd_relief_p50_vs_incumbent": -dd_cost_p50 if dd_cost_p50 is not None else None,
            "dd_relief_p90_vs_incumbent": -dd_cost_p90 if dd_cost_p90 is not None else None,
            "dd_cost_p50_vs_incumbent": dd_cost_p50,
            "dd_cost_p90_vs_incumbent": dd_cost_p90,
        },
        "thresholds": {
            "min_xirr_margin": p.min_incumbent_xirr_margin_p50,
            "min_dd_margin": -p.max_incumbent_dd_cost_p50,
            "min_xirr_margin_p50": p.min_incumbent_xirr_margin_p50,
            "min_xirr_margin_p10": p.min_incumbent_xirr_margin_p10,
            "max_dd_cost_p50": p.max_incumbent_dd_cost_p50,
            "max_dd_cost_p90": p.max_incumbent_dd_cost_p90,
        },
        "checks": checks,
        "policy": asdict(p),
    }


def evaluate_candidate_risk_envelope(candidate: dict | None,
                                     incumbent: dict | None, *,
                                     target: str = "012922", policy=None) -> dict:
    p = resolve_risk_envelope_policy(policy)
    target_gate = evaluate_target_risk_envelope(candidate, target=target, policy=p)
    incumbent_gate = evaluate_incumbent_risk_guard(candidate, incumbent, policy=p)
    passed = bool(target_gate["passed"] and incumbent_gate["passed"])
    if not target_gate["passed"]:
        stage = "TARGET_BLOCKED"
        reason = target_gate["reason"]
    elif not incumbent_gate["passed"]:
        stage = "INCUMBENT_BLOCKED"
        reason = incumbent_gate["reason"]
    else:
        stage = "RISK_SCREEN_PASSED"
        reason = "target and incumbent risk-envelope checks passed; live connection remains disabled"
    return {
        "research_only": True,
        "live_connected": False,
        "passed": passed,
        "stage": stage,
        "reason": reason,
        "target": target_gate,
        "incumbent": incumbent_gate,
        "policy": asdict(p),
    }
