"""Research-rule admission gate.

The backtest engine can rank many ideas, but only this module decides whether a
research row is merely informative, a candidate, or close enough to consider for
live execution.  It is intentionally pure so API routes and checks can reuse the
same standard without touching live orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


STAGE_LABELS = {
    "show": "仅展示",
    "candidate": "可作为候选",
    "eligible": "可进入今日建议",
    "defer": "应延后",
}


@dataclass(frozen=True)
class AdmissionProfile:
    name: str
    benchmark: str
    x_field: str
    dd_field: str
    rolling_x_field: str | None = None
    rolling_dd_field: str | None = None
    min_xirr: float = 0.0
    min_dd: float = 0.0
    min_candidate_rate: float = 0.60
    min_win_rate: float = 0.55
    min_dd_win_rate: float = 0.55
    min_p50_xirr: float = 0.0
    min_p50_dd: float = 0.0
    p10_xirr_floor: float = -0.02
    p10_dd_floor: float = -0.02
    market_mode: str = "informational"  # informational / structural / downshift / tactical / crash
    live_block: str = ""
    allow_live_entry: bool = False
    requires_today_diff: bool = True


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}%"


def _market_label(market: dict | None) -> tuple[str, str]:
    if not market:
        return "UNKNOWN", "未知"
    regime = str(market.get("regime") or "UNKNOWN")
    label = str(market.get("label") or {
        "BULL": "牛市",
        "NEUTRAL": "震荡",
        "BEAR": "熊市/破趋势",
        "UNKNOWN": "未知",
    }.get(regime, regime))
    return regime, label


def _market_check(profile: AdmissionProfile, market: dict | None) -> dict:
    regime, label = _market_label(market)
    mode = profile.market_mode
    if mode in {"informational", "structural"}:
        passed = True
        detail = "结构性规则，不用市场阶段放大个股信号"
    elif mode == "downshift":
        passed = regime in {"NEUTRAL", "BEAR"}
        detail = "仅在震荡/破趋势阶段才有今日压制意义"
    elif mode == "tactical":
        passed = regime in {"BULL", "NEUTRAL"}
        detail = "熊市/破趋势阶段不应放大战术浅层买入"
    elif mode == "crash":
        passed = regime == "BEAR"
        detail = "只有破趋势阶段才有接入崩盘储备的紧迫性"
    else:
        passed = False
        detail = "未知市场适用规则"
    return {
        "name": "当前市场",
        "passed": bool(passed),
        "value": label,
        "threshold": detail,
    }


def _roll_dist(row: dict, field: str) -> dict:
    roll = row.get("rolling") or {}
    dist = roll.get(field) or {}
    return {
        "p10": _num(dist.get("p10")),
        "p50": _num(dist.get("p50")),
        "p90": _num(dist.get("p90")),
    }


def evaluate_admission(row: dict, profile: AdmissionProfile,
                       market: dict | None = None) -> dict:
    """Evaluate one research row against the live-admission standard."""
    x = _num(row.get(profile.x_field))
    dd = _num(row.get(profile.dd_field))
    roll = row.get("rolling") or {}
    candidate_rate = _num(roll.get("candidate_rate"))
    win_rate = _num(roll.get("win_rate"))
    dd_win_rate = _num(roll.get("dd_win_rate"))
    rolling_x_field = profile.rolling_x_field or profile.x_field
    rolling_dd_field = profile.rolling_dd_field or profile.dd_field
    x_dist = _roll_dist(row, rolling_x_field)
    dd_dist = _roll_dist(row, rolling_dd_field)
    checks = []

    def add(name: str, passed: bool, value: str, threshold: str) -> None:
        checks.append({
            "name": name,
            "passed": bool(passed),
            "value": value,
            "threshold": threshold,
        })

    is_current = bool(row.get("is_current"))
    add("全程收益", x is not None and x >= profile.min_xirr,
        _pct(x, 2), f">= {_pct(profile.min_xirr, 2)} vs {profile.benchmark}")
    add("NAV-DD", dd is not None and dd >= profile.min_dd,
        _pct(dd, 1), f">= {_pct(profile.min_dd, 1)}")
    add("滚动候选率", candidate_rate is not None and candidate_rate >= profile.min_candidate_rate,
        _pct(candidate_rate, 0), f">= {_pct(profile.min_candidate_rate, 0)}")
    add("滚动胜率", win_rate is not None and win_rate >= profile.min_win_rate,
        _pct(win_rate, 0), f">= {_pct(profile.min_win_rate, 0)}")
    add("滚动DD胜率", dd_win_rate is not None and dd_win_rate >= profile.min_dd_win_rate,
        _pct(dd_win_rate, 0), f">= {_pct(profile.min_dd_win_rate, 0)}")
    add("滚动P50", (x_dist["p50"] is not None and x_dist["p50"] >= profile.min_p50_xirr
                 and dd_dist["p50"] is not None and dd_dist["p50"] >= profile.min_p50_dd),
        f"收益 {_pct(x_dist['p50'], 2)} / DD {_pct(dd_dist['p50'], 1)}",
        f"收益 >= {_pct(profile.min_p50_xirr, 2)} 且 DD >= {_pct(profile.min_p50_dd, 1)}")
    add("滚动P10护栏",
        (x_dist["p10"] is not None and x_dist["p10"] >= profile.p10_xirr_floor
         and dd_dist["p10"] is not None and dd_dist["p10"] >= profile.p10_dd_floor),
        f"收益 {_pct(x_dist['p10'], 2)} / DD {_pct(dd_dist['p10'], 1)}",
        f"收益 >= {_pct(profile.p10_xirr_floor, 2)} 且 DD >= {_pct(profile.p10_dd_floor, 1)}")
    checks.append({
        "name": "滚动P90",
        "passed": True,
        "value": f"收益 {_pct(x_dist['p90'], 2)} / DD {_pct(dd_dist['p90'], 1)}",
        "threshold": "信息项",
    })
    market_check = _market_check(profile, market)
    checks.append(market_check)
    add("今天影响", not profile.requires_today_diff,
        "已知" if not profile.requires_today_diff else "未计算",
        "接入前必须对比今日建议是否变化")

    failed = [c for c in checks if not c["passed"] and c["name"] != "今天影响"]
    history_ok = all(c["passed"] for c in checks if c["name"] in {"全程收益", "NAV-DD"})
    rolling_ok = all(c["passed"] for c in checks if c["name"] in {
        "滚动候选率", "滚动胜率", "滚动DD胜率", "滚动P50", "滚动P10护栏"
    })
    market_ok = bool(market_check["passed"])

    if is_current:
        stage = "show"
        reasons = ["当前基线本身不作为替换规则。"]
    elif profile.live_block:
        stage = "defer"
        reasons = [profile.live_block]
    elif not history_ok:
        stage = "show"
        reasons = [f"{c['name']}未达标：{c['value']}，要求 {c['threshold']}"
                   for c in failed[:3]]
    elif not rolling_ok:
        stage = "defer"
        reasons = [f"{c['name']}未达标：{c['value']}，要求 {c['threshold']}"
                   for c in failed[:3]]
    elif not market_ok:
        stage = "defer"
        reasons = [f"当前市场不适用：{market_check['value']}，{market_check['threshold']}"]
    elif profile.requires_today_diff:
        stage = "candidate"
        reasons = ["历史与滚动验证通过；接入前还要做今日建议差异检查。"]
    elif profile.allow_live_entry:
        stage = "eligible"
        reasons = ["准入条件通过，可进入今日建议评审。"]
    else:
        stage = "candidate"
        reasons = ["准入条件通过，但该规则仍需人工确认后改配置或开关。"]

    if stage != "eligible":
        reasons.append("未接入今日建议。")

    return {
        "profile": profile.name,
        "stage": stage,
        "label": STAGE_LABELS[stage],
        "benchmark": profile.benchmark,
        "connected_today": False,
        "checks": checks,
        "rolling_distribution": {
            profile.x_field: x_dist,
            profile.dd_field: dd_dist,
        },
        "reasons": reasons,
        "summary": "；".join(reasons[:2]),
    }


def apply_admissions(rows: list[dict], profile: AdmissionProfile,
                     market: dict | None = None) -> dict:
    """Attach admission decisions to rows and return a summary."""
    counts = {k: 0 for k in STAGE_LABELS}
    for row in rows:
        decision = evaluate_admission(row, profile, market)
        row["admission"] = decision
        counts[decision["stage"]] += 1
    return {
        "counts": counts,
        "criteria": {
            "benchmark": profile.benchmark,
            "min_xirr": profile.min_xirr,
            "min_dd": profile.min_dd,
            "min_candidate_rate": profile.min_candidate_rate,
            "min_win_rate": profile.min_win_rate,
            "min_dd_win_rate": profile.min_dd_win_rate,
            "p10_xirr_floor": profile.p10_xirr_floor,
            "p10_dd_floor": profile.p10_dd_floor,
            "requires_today_diff": profile.requires_today_diff,
        },
        "market": {
            "regime": _market_label(market)[0],
            "label": _market_label(market)[1],
        },
    }
