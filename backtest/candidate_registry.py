"""Normalize research outputs into a read-only promotion candidate registry.

This module deliberately does not run research and never writes config/state.
API routes pass already computed research results here so the frontend can show
one compact view of "what improved, why it is not live, and what validation is
next" without wiring research outputs into executable advice.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np


STAGES = ("rejected", "watch", "config_candidate", "live_eligible")
STAGE_LABELS = {
    "rejected": "未通过",
    "watch": "观察项",
    "config_candidate": "配置候选",
    "live_eligible": "可接实盘",
}
STAGE_RANK = {name: i for i, name in enumerate(STAGES)}


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _p(value, digits: int = 2) -> str:
    x = _num(value)
    if x is None:
        return "-"
    return f"{x * 100:+.{digits}f}pct"


def _pct(value, digits: int = 0) -> str:
    x = _num(value)
    if x is None:
        return "-"
    return f"{x * 100:.{digits}f}%"


def _metric_summary(xirr_delta, dd_delta, benchmark: str) -> str:
    x = _num(xirr_delta)
    dd = _num(dd_delta)
    parts = []
    if x is not None:
        parts.append(f"相对{benchmark} XIRR {_p(x, 2)}")
    if dd is not None:
        direction = "更浅" if dd >= 0 else "更深"
        parts.append(f"回撤{direction} {abs(dd) * 100:.1f}pct")
    return "；".join(parts) if parts else "暂无可比指标"


def _rolling_summary(row: dict, *, x_field: str = "excess_p50",
                     dd_field: str = "dd_relief_p50",
                     win_field: str = "win_rate") -> dict:
    return {
        "windows": row.get("windows"),
        "win_rate": row.get(win_field),
        "xirr_p50": row.get(x_field),
        "dd_relief_p50": row.get(dd_field),
        "range": row.get("range"),
        "summary": (
            f"窗口 {row.get('windows') or '-'}；胜率 {_pct(row.get(win_field), 0)}；"
            f"XIRR中位 {_p(row.get(x_field), 2)}；回撤改善 {_p(row.get(dd_field), 1)}"
        ),
    }


def _stage_from_admission(admission: dict | None, *,
                          cap_at_watch: bool = False) -> str:
    stage = str((admission or {}).get("stage") or "show")
    if stage == "eligible":
        return "watch" if cap_at_watch else "config_candidate"
    if stage == "candidate":
        return "watch"
    return "rejected"


def _stage_from_config_row(row: dict) -> str:
    admission = row.get("admission") or {}
    if admission.get("stage") == "eligible":
        return "config_candidate"
    verdict = str(row.get("verdict") or "")
    rolling = row.get("rolling") or {}
    if "候选" in verdict or admission.get("stage") == "candidate":
        return "watch"
    if _num(rolling.get("candidate_rate")) is not None and float(rolling["candidate_rate"]) >= 0.50:
        return "watch"
    if (_num(row.get("xirr_vs_current")) or -9.0) > 0 or (
        _num(row.get("dd_relief_vs_current")) or -9.0
    ) > 0:
        return "watch"
    return "rejected"


def _base_candidate(name: str, source: str, stage: str, *,
                    historical_result: dict | None = None,
                    rolling_result: dict | None = None,
                    vs_current_config: dict | None = None,
                    vs_012922: dict | None = None,
                    drawdown_tradeoff: str = "",
                    today_advice_impact: dict | None = None,
                    why_not_live: str = "",
                    next_validation: list[str] | None = None,
                    detail: dict | None = None) -> dict:
    stage = stage if stage in STAGE_LABELS else "rejected"
    return {
        "name": name,
        "source": source,
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "historical_result": historical_result or {"summary": "暂无历史结果"},
        "rolling_result": rolling_result or {"summary": "暂无滚动验证"},
        "vs_current_config": vs_current_config or {"summary": "尚未对照当前配置"},
        "vs_012922": vs_012922 or {"summary": "此来源不直接对标 012922"},
        "drawdown_tradeoff": drawdown_tradeoff or "暂无回撤权衡结论",
        "today_advice_impact": today_advice_impact or {
            "would_change": False,
            "summary": "不改变今日建议。",
            "changes": [],
        },
        "why_not_live": why_not_live or "未通过完整准入，不接入 config.yaml 或 /api/state。",
        "next_validation": next_validation or ["继续保持 research only。"],
        "detail": detail or {},
    }


def _pick_best_by_admission(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    return max(
        rows,
        key=lambda r: (
            STAGE_RANK.get(_stage_from_admission(r.get("admission")), 0),
            _num(r.get("win_rate")) or -1.0,
            _num(r.get("excess_p50")) or -9.0,
            _num(r.get("dd_relief_p50")) or -9.0,
        ),
    )


def _from_preference_gate(gate: dict | None) -> dict | None:
    if not gate:
        return None
    history = gate.get("history") or {}
    best = history.get("best") or {}
    if gate.get("live_connected"):
        stage = "live_eligible"
    elif gate.get("decision") == "RESEARCH_CANDIDATE_ONLY":
        stage = "config_candidate"
    elif history.get("improved_return"):
        stage = "watch"
    else:
        stage = "rejected"
    blockers = [str(x) for x in (gate.get("blockers") or []) if x]
    guard = gate.get("incumbent_guard") or {}
    margins = guard.get("margins") or {}
    return _base_candidate(
        name="动态自选篮子 live gate",
        source="dynamic_basket_live_gate",
        stage=stage,
        historical_result={
            "summary": _metric_summary(best.get("excess_p50"), best.get("dd_relief_p50"), "012922"),
            "best": best,
            "eligible_count": history.get("eligible_count"),
            "stage_counts": history.get("stage_counts"),
        },
        rolling_result=_rolling_summary(best) if best else {"summary": "没有可用候选行"},
        vs_current_config={
            "passed": guard.get("passed"),
            "summary": guard.get("reason") or "当前配置守门未完成",
            "xirr_p50_vs_incumbent": margins.get("xirr_p50_vs_incumbent"),
            "dd_relief_p50_vs_incumbent": margins.get("dd_relief_p50_vs_incumbent"),
            "incumbent": guard.get("incumbent"),
        },
        vs_012922={
            "summary": _metric_summary(best.get("excess_p50"), best.get("dd_relief_p50"), "012922"),
            "target_benchmark": gate.get("target_benchmark"),
        },
        drawdown_tradeoff=_metric_summary(best.get("excess_p50"), best.get("dd_relief_p50"), "012922"),
        today_advice_impact=gate.get("today") or {
            "would_change": False,
            "summary": "动态篮子准入是只读预检；今日建议不变。",
            "changes": [],
        },
        why_not_live="；".join(blockers) if blockers else "动态篮子没有通过完整 live gate。",
        next_validation=list(gate.get("next_validation") or []),
        detail={
            "decision": gate.get("decision"),
            "current_market": gate.get("current_market"),
            "config_diff_preview": gate.get("config_diff_preview"),
        },
    )


def _from_tactical_ab(ab: dict | None) -> dict | None:
    if not ab:
        return None
    rows = [
        r for r in (ab.get("rows") or [])
        if str(r.get("mode") or "") != "current"
    ]
    if not rows:
        return None
    best = max(
        rows,
        key=lambda r: (
            {"candidate": 3, "watch": 2, "reject": 1}.get(str(r.get("promotion_stage")), 0),
            _num(r.get("xirr_vs_current_tactical")) or -9.0,
            _num(((r.get("rolling_vs_current") or {}).get("xirr_vs_current") or {}).get("p50")) or -9.0,
        ),
    )
    promo_stage = str(best.get("promotion_stage") or "reject")
    stage = {
        "candidate": "config_candidate",
        "watch": "watch",
        "reject": "rejected",
    }.get(promo_stage, "rejected")
    rv = best.get("rolling_vs_current") or {}
    rx = rv.get("xirr_vs_current") or {}
    rd = rv.get("dd_relief_vs_current") or {}
    return _base_candidate(
        name=f"战术限价候选：{best.get('label') or best.get('mode')}",
        source="tactical_overlay_ab",
        stage=stage,
        historical_result={
            "summary": _metric_summary(best.get("xirr_vs_baseline"), best.get("dd_relief_vs_baseline"), "关闭战术单"),
            "metrics": best.get("metrics") or {},
            "stats": best.get("stats") or {},
        },
        rolling_result={
            "windows": rv.get("windows"),
            "candidate_rate": rv.get("candidate_rate"),
            "xirr_p50_vs_current": rx.get("p50"),
            "dd_relief_p50_vs_current": rd.get("p50"),
            "summary": (
                f"vs当前滚动候选率 {_pct(rv.get('candidate_rate'), 0)}；"
                f"XIRR中位 {_p(rx.get('p50'), 2)}；回撤改善 {_p(rd.get('p50'), 1)}"
            ),
        },
        vs_current_config={
            "summary": _metric_summary(best.get("xirr_vs_current_tactical"),
                                       best.get("dd_relief_vs_current_tactical"), "当前战术配置"),
            "xirr_vs_current": best.get("xirr_vs_current_tactical"),
            "dd_relief_vs_current": best.get("dd_relief_vs_current_tactical"),
            "promotion_verdict": best.get("promotion_verdict"),
        },
        drawdown_tradeoff=_metric_summary(best.get("xirr_vs_current_tactical"),
                                          best.get("dd_relief_vs_current_tactical"), "当前战术配置"),
        today_advice_impact={
            "would_change": False,
            "summary": "不会替换当前 tactical_orders；今日战术限价仍按现行 5/20+ATR 生成。",
            "changes": [],
        },
        why_not_live=best.get("promotion_verdict") or "未通过 vs 当前配置的替换评审。",
        next_validation=[
            "继续复核 vs 当前配置的全程和滚动窗口。",
            "进入配置候选后再做今日建议差异检查。",
            "人工确认后才允许改 tactical_orders。",
        ],
        detail={"mode": best.get("mode"), "operation": best.get("operation")},
    )


def _from_config_ab(ab: dict | None, *, source: str, name: str,
                    current_label: str) -> dict | None:
    if not ab:
        return None
    rows = [r for r in (ab.get("rows") or []) if not r.get("is_current")]
    if not rows:
        return None
    best = max(
        rows,
        key=lambda r: (
            STAGE_RANK.get(_stage_from_config_row(r), 0),
            _num(r.get("xirr_vs_current")) or -9.0,
            _num(r.get("dd_relief_vs_current")) or -9.0,
        ),
    )
    stage = _stage_from_config_row(best)
    rolling = best.get("rolling") or {}
    rx = rolling.get("xirr_vs_current") or {}
    rd = rolling.get("dd_relief_vs_current") or {}
    label = best.get("label") or best.get("mode") or name
    return _base_candidate(
        name=f"{name}：{label}",
        source=source,
        stage=stage,
        historical_result={
            "summary": _metric_summary(best.get("xirr_vs_current"),
                                       best.get("dd_relief_vs_current"), current_label),
            "metrics": best.get("metrics") or {},
            "verdict": best.get("verdict"),
        },
        rolling_result={
            "windows": rolling.get("windows"),
            "candidate_rate": rolling.get("candidate_rate"),
            "xirr_p50_vs_current": rx.get("p50"),
            "dd_relief_p50_vs_current": rd.get("p50"),
            "summary": (
                f"滚动候选率 {_pct(rolling.get('candidate_rate'), 0)}；"
                f"XIRR中位 {_p(rx.get('p50'), 2)}；回撤改善 {_p(rd.get('p50'), 1)}"
            ),
        },
        vs_current_config={
            "summary": _metric_summary(best.get("xirr_vs_current"),
                                       best.get("dd_relief_vs_current"), current_label),
            "xirr_vs_current": best.get("xirr_vs_current"),
            "dd_relief_vs_current": best.get("dd_relief_vs_current"),
        },
        drawdown_tradeoff=_metric_summary(best.get("xirr_vs_current"),
                                          best.get("dd_relief_vs_current"), current_label),
        today_advice_impact={
            "would_change": False,
            "summary": "未写 config.yaml；今日建议仍由当前配置生成。",
            "changes": [],
        },
        why_not_live=(
            (best.get("admission") or {}).get("reason")
            or best.get("verdict")
            or "缺少今日建议差异检查和人工确认。"
        ),
        next_validation=[
            "A/B 结果需继续通过多起点滚动验证。",
            "若进入配置候选，先输出今日建议 diff。",
            "人工确认后才允许改 config.yaml。",
        ],
        detail={"row": {k: best.get(k) for k in ("label", "mode", "operation", "verdict")}},
    )


def _from_benchmark_rows(result: dict | None, *, source: str, title: str,
                         cap_at_watch: bool = False,
                         why: str = "") -> dict | None:
    if not result:
        return None
    rows = result.get("rows") or []
    best = None
    summary_best = ((result.get("summary") or {}).get("best") or {})
    for key in ("best_compact", "best_balanced", "best_return"):
        candidate = summary_best.get(key)
        if candidate:
            best = candidate
            break
    if not best:
        best = _pick_best_by_admission(rows)
    if not best:
        return None
    stage = _stage_from_admission(best.get("admission"), cap_at_watch=cap_at_watch)
    return _base_candidate(
        name=f"{title}：{best.get('basket') or best.get('label') or 'best'}",
        source=source,
        stage=stage,
        historical_result={
            "summary": _metric_summary(best.get("excess_p50"), best.get("dd_relief_p50"), "012922"),
            "best": best,
        },
        rolling_result=_rolling_summary(best),
        vs_012922={
            "summary": _metric_summary(best.get("excess_p50"), best.get("dd_relief_p50"), "012922"),
            "win_rate": best.get("win_rate"),
            "dd_win_rate": best.get("dd_win_rate"),
        },
        drawdown_tradeoff=_metric_summary(best.get("excess_p50"), best.get("dd_relief_p50"), "012922"),
        today_advice_impact={
            "would_change": False,
            "summary": "研究结果不接入 /api/state，不生成限价单。",
            "changes": [],
        },
        why_not_live=why or (best.get("admission") or {}).get("reason") or "未通过完整实盘准入。",
        next_validation=[
            "点时验证必须继续通过，禁止使用未来披露或未来涨幅。",
            "通过后再做当前配置对照和今日建议差异检查。",
        ],
        detail={"summary": result.get("summary") or {}},
    )


def _finalize(rows: list[dict], *, source_errors: dict[str, str] | None = None,
              market: dict | None = None, execution: dict | None = None,
              include_heavy: bool = False, computed: bool = True,
              as_of: str | None = None, note: str | None = None) -> dict:
    rows = [c for c in rows if c]
    rows.sort(
        key=lambda c: (
            STAGE_RANK.get(c["stage"], 0),
            _num((c.get("vs_current_config") or {}).get("xirr_vs_current")) or -9.0,
            _num((c.get("vs_012922") or {}).get("win_rate")) or -1.0,
        ),
        reverse=True,
    )
    counts = {stage: 0 for stage in STAGES}
    for row in rows:
        counts[row["stage"]] = counts.get(row["stage"], 0) + 1
    highest = rows[0]["stage"] if rows else "rejected"
    summary = {
        "research_only": True,
        "does_change_today_advice": False,
        "as_of": as_of or date.today().isoformat(),
        "include_heavy": bool(include_heavy),
        "computed": bool(computed),
        "candidate_count": len(rows),
        "stage_counts": counts,
        "highest_stage": highest,
        "highest_stage_label": STAGE_LABELS.get(highest, highest),
        "current_market": market,
        "execution_summary": (execution or {}).get("summary"),
        "summary": note or (
            "候选库只读：显示观察项和配置候选，不写 config.yaml，"
            "不接入 /api/state，也不改变今日建议。"
        ),
    }
    return {
        "summary": summary,
        "candidates": rows,
        "source_errors": source_errors or {},
        "stage_labels": STAGE_LABELS,
    }


def build_static_candidate_registry(*, market: dict | None = None,
                                    execution: dict | None = None,
                                    as_of: str | None = None) -> dict:
    """Fast dashboard summary from the latest recorded research conclusions.

    The full API can recompute sources on demand.  This fast view exists so the
    execution dashboard is not blocked by multi-minute research jobs.
    """
    rows = [
        _base_candidate(
            name="动态 top4/top6 自选篮子",
            source="dynamic_basket_live_gate",
            stage="rejected",
            historical_result={
                "summary": "静态 top4_attack_score_risk 跑赢率 100%，超额 XIRR P50 +6.98pct。",
            },
            rolling_result={
                "summary": "点时 top4_score_risk 跑赢率 0%，超额 XIRR P50 -35.40pct。",
            },
            vs_current_config={
                "summary": "未通过当前写死配置守门；不能接入 config 或今日建议。",
            },
            vs_012922={
                "summary": "静态收益强，但 DD 中位比 012922 深约 24.5pct。",
            },
            drawdown_tradeoff="收益侧有 hindsight 吸引力，但点时失效且回撤显著更深。",
            why_not_live="点时 walk-forward 失败，静态强势主要来自 hindsight。",
            next_validation=[
                "继续 top4/top6 点时验证。",
                "先通过当前配置对照，再做今日建议 diff。",
            ],
        ),
        _base_candidate(
            name="战术限价：open_gap",
            source="tactical_overlay_ab",
            stage="watch",
            historical_result={"summary": "最接近替换当前 5/20+ATR，但收益小幅落后。"},
            rolling_result={"summary": "季度滚动复核替换候选仍为 0。"},
            vs_current_config={"summary": "当前 5/20+ATR 仍是最佳 XIRR / 最佳综合。"},
            drawdown_tradeoff="可观察开盘缺口成交质量，但不足以替换当前战术限价。",
            why_not_live="未通过 vs 当前配置的全程和滚动替换门槛。",
            next_validation=["继续记录成交质量。", "若进入配置候选，再做今日建议差异检查。"],
        ),
        _base_candidate(
            name="012922 最新披露 US 持仓镜像",
            source="fund_mirror_research",
            stage="watch",
            historical_result={"summary": "最新持仓 hindsight 收益吸引，core=95%、W=0 超额 XIRR P50 约 +37.81pct。"},
            rolling_result={"summary": "历史季度点时镜像严格测试全部跑输。"},
            vs_012922={"summary": "最新镜像 DD 中位仍明显深于 012922。"},
            drawdown_tradeoff="收益强来自最新持仓 hindsight，回撤和点时复刻不达标。",
            why_not_live="不能简单复制 012922 最新或历史 US 子集。",
            next_validation=["继续季度披露点时验证。", "禁止使用未来披露。"],
        ),
        _base_candidate(
            name="注资模式：ladder_core",
            source="injection_ab",
            stage="watch",
            historical_result={"summary": "回撤仅小幅改善，收益有轻微成本。"},
            rolling_result={"summary": "滚动中位 DD 改善约 0.20pct，XIRR 少约 0.18pct。"},
            vs_current_config={"summary": "当前 lump_core 仍是收益最优。"},
            drawdown_tradeoff="轻微防守，但改善幅度不足以改执行方式。",
            why_not_live="不值得为了很小的回撤改善牺牲核心入场效率。",
            next_validation=["只有出现配置候选后才做 today diff。"],
        ),
        _base_candidate(
            name="参数扫描：保守深档微调",
            source="param_scan",
            stage="watch",
            historical_result={"summary": "极深两档回撤略浅，但全程 XIRR 小幅落后。"},
            rolling_result={"summary": "改善幅度属于保守微调，不足以自动改配置。"},
            vs_current_config={"summary": "当前参数并不差，未出现可靠替换。"},
            drawdown_tradeoff="回撤改善很小，收益成本也很小；适合观察，不适合自动替换。",
            why_not_live="缺少足够大的收益/回撤优势和今日建议差异检查。",
            next_validation=["继续多起点验证。", "候选进入 config_candidate 后再输出 today diff。"],
        ),
        _base_candidate(
            name="点时动态篮子 walk-forward",
            source="preference_walkforward",
            stage="rejected",
            historical_result={"summary": "只使用起点前历史选股后，默认形态超额中位为负。"},
            rolling_result={"summary": "当前自选科技池 17 个真实起点跑赢率为 0%。"},
            vs_012922={"summary": "未通过收益侧准入。"},
            drawdown_tradeoff="没有收益补偿，不能接受更深回撤。",
            why_not_live="点时动态选股没有外推静态 hindsight 优势。",
            next_validation=["增加稳健评分前，继续 research only。"],
        ),
        _base_candidate(
            name="012922 历史季度 US 持仓点时镜像",
            source="fund_quarterly_mirror_research",
            stage="rejected",
            historical_result={"summary": "严格 3 年季度起点和 2 年月度敏感性全部跑输。"},
            rolling_result={"summary": "0 天延迟、每月重调、0 成本、W=0 的进攻上限也未跑赢。"},
            vs_012922={"summary": "跑赢率 0%，超额 XIRR P50 约 -37pct 左右。"},
            drawdown_tradeoff="既没有稳定超额，也承担更深 DD。",
            why_not_live="复制历史 US 子集不是接近 012922 的有效方向。",
            next_validation=["只保留为研究参照，不进入配置候选。"],
        ),
    ]
    return _finalize(
        rows,
        market=market,
        execution=execution,
        computed=False,
        as_of=as_of,
        note="快速候选摘要基于上一轮已记录研究结论；点“完整候选库”可重新计算来源。",
    )


def build_candidate_registry(*,
                             preference_gate: dict | None = None,
                             tactical_ab: dict | None = None,
                             param_scan: dict | None = None,
                             injection_ab: dict | None = None,
                             preference_walkforward: dict | None = None,
                             preference_rebalance: dict | None = None,
                             fund_mirror: dict | None = None,
                             fund_quarterly: dict | None = None,
                             source_errors: dict[str, str] | None = None,
                             market: dict | None = None,
                             execution: dict | None = None,
                             include_heavy: bool = False,
                             as_of: str | None = None) -> dict:
    """Build the read-only registry from already computed source results."""
    candidates = [
        _from_preference_gate(preference_gate),
        _from_tactical_ab(tactical_ab),
        _from_config_ab(param_scan, source="param_scan", name="参数扫描", current_label="当前参数"),
        _from_config_ab(injection_ab, source="injection_ab", name="注资模式", current_label="当前注资模式"),
    ]
    if include_heavy:
        candidates.extend([
            _from_benchmark_rows(
                preference_walkforward,
                source="preference_walkforward",
                title="点时动态篮子",
                why="点时 walk-forward 未稳定跑赢；未通过前不生成限价单。",
            ),
            _from_benchmark_rows(
                preference_rebalance,
                source="preference_rebalance",
                title="低频主动重选",
                why="主动重选涉及卖出/重建，需更高准入；当前只作研究。",
            ),
            _from_benchmark_rows(
                fund_mirror,
                source="fund_mirror_research",
                title="012922 最新持仓镜像",
                cap_at_watch=True,
                why="最新披露持仓属于 hindsight 镜像；必须等待历史季度点时镜像通过。",
            ),
            _from_benchmark_rows(
                fund_quarterly,
                source="fund_quarterly_mirror_research",
                title="012922 季度点时镜像",
                why="历史季度点时镜像未稳定跑赢，不能复制到实盘。",
            ),
        ])
    return _finalize(
        candidates,
        source_errors=source_errors,
        market=market,
        execution=execution,
        include_heavy=include_heavy,
        computed=True,
        as_of=as_of,
    )
