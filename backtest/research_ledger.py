"""Fail-closed governance ledger for strategy research candidates.

Research sources may use different verdicts, metrics, and validation depth.
This module preserves each source verdict as ``source_stage`` and applies one
shared promotion policy.  It never writes config/state and never confirms a
candidate on behalf of the user.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


LEDGER_SCHEMA_VERSION = 1
STAGES = ("rejected", "watch", "config_candidate", "live_eligible")
STAGE_LABELS = {
    "rejected": "未通过",
    "watch": "观察项",
    "config_candidate": "配置候选",
    "live_eligible": "可接实盘",
}
STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}


@dataclass(frozen=True)
class SourcePolicy:
    hypothesis: str
    data_sources: tuple[str, ...]
    change_scope: tuple[str, ...]
    point_in_time_status: str
    point_in_time_passed: bool
    sample_out_status: str = "not_validated"
    sample_out_passed: bool = False
    target_required: bool = True
    risk_envelope_required: bool = False


SOURCE_POLICIES = {
    "dynamic_basket_live_gate": SourcePolicy(
        hypothesis="动态精简科技篮子可在不突破 012922 与现有配置风险预算的前提下提高长期收益。",
        data_sources=("美股日线", "012922 净值", "当前策略配置/状态"),
        change_scope=("symbols", "cap_total", "safe_leg"),
        point_in_time_status="static_selection_not_point_in_time",
        point_in_time_passed=False,
        risk_envelope_required=True,
    ),
    "tactical_overlay_ab": SourcePolicy(
        hypothesis="替代战术限价可以改善浅层成交效率，同时不削弱当前 5/20+ATR 的收益回撤表现。",
        data_sources=("美股 OHLC 日线", "当前 tactical_orders"),
        change_scope=("tactical_orders",),
        point_in_time_status="validated_previous_day_signal_next_day_fill",
        point_in_time_passed=True,
        target_required=False,
    ),
    "param_scan": SourcePolicy(
        hypothesis="有限的核心比例和深跌档位调整可改善当前棘轮的收益回撤组合。",
        data_sources=("美股日线", "当前 portfolio 参数"),
        change_scope=("portfolio.core_ratio", "portfolio.tiers"),
        point_in_time_status="fixed_rule_no_future_signal",
        point_in_time_passed=True,
        target_required=False,
    ),
    "injection_ab": SourcePolicy(
        hypothesis="替代注资分配方式可在保留核心入场效率的同时降低组合回撤。",
        data_sources=("美股日线", "当前 injection 配置"),
        change_scope=("portfolio.injection_core_ratio", "portfolio.inject_skip_core_near_high"),
        point_in_time_status="fixed_rule_no_future_signal",
        point_in_time_passed=True,
        target_required=False,
    ),
    "preference_walkforward": SourcePolicy(
        hypothesis="仅使用每个起点之前的数据重选 top4/top6 后，动态篮子仍能稳定接近或超过 012922。",
        data_sources=("点时美股日线", "012922 净值"),
        change_scope=("symbols", "cap_total"),
        point_in_time_status="validated_expanding_or_rolling_selection",
        point_in_time_passed=True,
        sample_out_status="walk_forward_internal_oos_only",
        sample_out_passed=False,
    ),
    "preference_rebalance": SourcePolicy(
        hypothesis="低频点时重选在计入换手和交易成本后仍能提供可复现的收益回撤改善。",
        data_sources=("点时美股日线", "012922 净值", "交易成本假设"),
        change_scope=("symbols", "cap_total", "rebalance_rule"),
        point_in_time_status="validated_point_in_time_reselection",
        point_in_time_passed=True,
        sample_out_status="walk_forward_internal_oos_only",
        sample_out_passed=False,
    ),
    "fund_mirror_research": SourcePolicy(
        hypothesis="012922 最新披露的美股子集可作为高收益候选，但必须证明结果不是最新持仓 hindsight。",
        data_sources=("012922 最新持仓披露", "美股日线", "012922 净值"),
        change_scope=("symbols", "cap_total", "safe_leg"),
        point_in_time_status="failed_latest_holdings_hindsight",
        point_in_time_passed=False,
        risk_envelope_required=True,
    ),
    "fund_quarterly_mirror_research": SourcePolicy(
        hypothesis="仅在披露可用日后使用季度美股持仓，仍可复现 012922 的风险收益特征。",
        data_sources=("012922 历史季度持仓", "建模披露可用日", "美股日线", "012922 净值"),
        change_scope=("symbols", "cap_total", "rebalance_rule"),
        point_in_time_status="modeled_delay_actual_publication_unverified",
        point_in_time_passed=False,
        risk_envelope_required=True,
    ),
    "ndx_competition": SourcePolicy(
        hypothesis="纳指100历史成分股可在严格点时约束下竞争出兼顾收益、回撤与集中度的个股组合。",
        data_sources=(
            "Nasdaq 官方当前成分",
            "QQQ SEC N-PORT 历史点时持仓",
            "版本化美股 OHLC 日线",
            "QQQ/012922/当前配置基准",
        ),
        change_scope=("symbols", "cap_total", "rebalance_rule", "safe_leg"),
        point_in_time_status="validated_sec_filing_availability_proxy_event_timing_not_exact",
        point_in_time_passed=True,
        sample_out_status="pre_registered_train_validation_failed",
        sample_out_passed=False,
        risk_envelope_required=True,
    ),
}


DEFAULT_POLICY = SourcePolicy(
    hypothesis="该研究候选需要证明相对当前策略具有可复现且风险受控的改进。",
    data_sources=("未登记研究源",),
    change_scope=("unknown",),
    point_in_time_status="unverified",
    point_in_time_passed=False,
)


def _source_policy(source: str) -> SourcePolicy:
    return SOURCE_POLICIES.get(str(source or ""), DEFAULT_POLICY)


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _collect_version_ids(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 9:
        return []
    found = []
    if isinstance(value, dict):
        version_id = value.get("version_id")
        if isinstance(version_id, str) and version_id.strip():
            found.append(version_id.strip())
        for nested in value.values():
            found.extend(_collect_version_ids(nested, depth=depth + 1))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found.extend(_collect_version_ids(nested, depth=depth + 1))
    return sorted(set(found))


def _is_real_summary(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not any(marker in text for marker in ("暂无", "尚未", "未完成", "不直接对标"))


def _check(check_id: str, label: str, passed: bool, evidence: Any,
           *, required: bool = True) -> dict:
    return {
        "id": check_id,
        "label": label,
        "required": bool(required),
        "passed": bool(passed) if required else True,
        "status": ("passed" if passed else "missing_or_failed") if required else "not_applicable",
        "evidence": evidence,
    }


def _research_window(candidate: dict) -> dict:
    rolling = candidate.get("rolling_result") or {}
    historical = candidate.get("historical_result") or {}
    best = historical.get("best") or {}
    range_value = rolling.get("range") or best.get("range")
    windows = rolling.get("windows") or best.get("windows")
    if not range_value:
        detail_summary = (candidate.get("detail") or {}).get("summary") or {}
        range_value = detail_summary.get("range") or detail_summary.get("common_range")
    return {
        "range": range_value,
        "windows": windows,
        "documented": bool(range_value and windows),
    }


def _override(candidate: dict, name: str, default_status: str,
              default_passed: bool) -> tuple[str, bool, Any]:
    override = (candidate.get("governance_evidence") or {}).get(name) or {}
    if override:
        return (
            str(override.get("status") or default_status),
            bool(override.get("passed")),
            override.get("evidence"),
        )
    return default_status, bool(default_passed), None


def _normalize_rollback(candidate: dict, policy: SourcePolicy) -> dict:
    supplied = candidate.get("rollback_protocol") or {}
    return {
        "required_before_live": True,
        "prepared": bool(supplied.get("prepared")),
        "change_scope": list(supplied.get("change_scope") or policy.change_scope),
        "old_config_snapshot_id": supplied.get("old_config_snapshot_id"),
        "replacement_reason": supplied.get("replacement_reason"),
        "old_vs_new_today_available": bool(supplied.get("old_vs_new_today_available")),
        "rule": "实盘替换前必须保留旧配置摘要；替换后继续展示旧配置 vs 新配置的今日建议。",
    }


def _normalize_confirmation(candidate: dict) -> dict:
    supplied = candidate.get("user_confirmation") or {}
    confirmed = bool(supplied.get("confirmed"))
    confirmed_at = supplied.get("confirmed_at")
    confirmation_id = supplied.get("confirmation_id")
    return {
        "required": True,
        "confirmed": confirmed,
        "confirmed_at": confirmed_at,
        "confirmation_id": confirmation_id,
        "valid": bool(confirmed and confirmed_at and confirmation_id),
        "rule": "live_eligible 只生成可读 diff；必须用户明确确认后才能修改配置。",
    }


def enrich_ledger_entry(candidate: dict, *, computed: bool) -> dict:
    entry = copy.deepcopy(candidate)
    source = str(entry.get("source") or "unknown")
    policy = _source_policy(source)
    source_stage = str(entry.get("stage") or "rejected")
    if source_stage not in STAGE_RANK:
        source_stage = "rejected"

    versions = _collect_version_ids(entry)
    window = _research_window(entry)
    point_status, point_passed, point_detail = _override(
        entry,
        "point_in_time",
        policy.point_in_time_status,
        policy.point_in_time_passed,
    )
    oos_status, oos_passed, oos_detail = _override(
        entry,
        "sample_out",
        policy.sample_out_status,
        policy.sample_out_passed,
    )
    target = entry.get("vs_012922") or {}
    incumbent = entry.get("vs_current_config") or {}
    detail = entry.get("detail") or {}
    risk_envelope = detail.get("risk_envelope") or {}
    if not risk_envelope:
        risk_envelope = ((entry.get("historical_result") or {}).get("best") or {}).get(
            "risk_envelope"
        ) or {}
    target_passed = _is_real_summary(target.get("summary"))
    if "passed" in target:
        target_passed = target_passed and bool(target.get("passed"))
    incumbent_passed = bool(incumbent.get("passed"))
    if "passed" not in incumbent:
        incumbent_passed = (
            STAGE_RANK[source_stage] >= STAGE_RANK["config_candidate"]
            and _is_real_summary(incumbent.get("summary"))
        )
    risk_passed = bool(risk_envelope.get("passed"))
    if not policy.risk_envelope_required:
        risk_passed = (
            STAGE_RANK[source_stage] >= STAGE_RANK["config_candidate"]
            and _is_real_summary(entry.get("drawdown_tradeoff"))
        )

    today = entry.get("today_advice_impact") or {}
    today_evaluated = bool(today.get("evaluated"))
    rollback = _normalize_rollback(entry, policy)
    confirmation = _normalize_confirmation(entry)

    checks = [
        _check("hypothesis", "研究假设", bool(policy.hypothesis), policy.hypothesis),
        _check("data_source", "数据源登记", bool(policy.data_sources), list(policy.data_sources)),
        _check("data_version", "数据版本", bool(versions), versions),
        _check("backtest_window", "回测窗口", window["documented"], window),
        _check("point_in_time", "点时约束", point_passed, {
            "status": point_status,
            "detail": point_detail,
        }),
        _check("sample_out", "样本外验证", oos_passed, {
            "status": oos_status,
            "detail": oos_detail,
        }),
        _check(
            "vs_012922",
            "相对 012922",
            target_passed,
            target,
            required=policy.target_required,
        ),
        _check("vs_current", "相对当前配置", incumbent_passed, incumbent),
        _check(
            "risk_gate",
            "风险准入",
            risk_passed,
            risk_envelope or entry.get("drawdown_tradeoff"),
        ),
        _check("today_diff", "今日建议差异", today_evaluated, today),
        _check(
            "rollback",
            "回滚协议",
            bool(
                rollback["prepared"]
                and rollback["old_config_snapshot_id"]
                and rollback["replacement_reason"]
                and rollback["old_vs_new_today_available"]
            ),
            rollback,
        ),
    ]
    config_check_ids = {
        "hypothesis", "data_source", "data_version", "backtest_window",
        "point_in_time", "sample_out", "vs_012922", "vs_current", "risk_gate",
    }
    live_check_ids = config_check_ids | {"today_diff", "rollback"}
    config_ready = all(
        check["passed"] for check in checks if check["id"] in config_check_ids
    )
    live_ready = all(
        check["passed"] for check in checks if check["id"] in live_check_ids
    )

    if source_stage == "rejected":
        governed_stage = "rejected"
    elif STAGE_RANK[source_stage] < STAGE_RANK["config_candidate"]:
        governed_stage = "watch"
    elif not config_ready:
        governed_stage = "watch"
    elif source_stage == "config_candidate" or not live_ready:
        governed_stage = "config_candidate"
    else:
        governed_stage = "live_eligible"

    apply_allowed = bool(
        governed_stage == "live_eligible" and confirmation["valid"]
    )
    failed = [check for check in checks if check["required"] and not check["passed"]]
    applicable = [check for check in checks if check["required"]]
    score = (
        sum(1 for check in applicable if check["passed"]) / len(applicable)
        if applicable else 0.0
    )
    evidence_grade = "complete" if score == 1.0 else "partial" if score >= 0.55 else "insufficient"

    candidate_key = str(entry.get("candidate_key") or source)
    identity = {"source": source, "candidate_key": candidate_key}
    entry_id = f"strategy_candidate:{source}:{_json_hash(identity)[:12]}"
    ledger_content = {
        "identity": identity,
        "source_stage": source_stage,
        "governed_stage": governed_stage,
        "version_ids": versions,
        "window": window,
        "checks": [(check["id"], check["status"]) for check in checks],
    }
    content_hash = _json_hash(ledger_content)

    entry.update({
        "source_stage": source_stage,
        "source_stage_label": STAGE_LABELS[source_stage],
        "stage": governed_stage,
        "stage_label": STAGE_LABELS[governed_stage],
        "hypothesis": policy.hypothesis,
        "data_provenance": {
            "declared_sources": list(policy.data_sources),
            "version_ids": versions,
            "versioned": bool(versions),
            "computed_now": bool(computed),
        },
        "research_window": window,
        "point_in_time": {
            "status": point_status,
            "passed": point_passed,
            "detail": point_detail,
        },
        "sample_out": {
            "status": oos_status,
            "passed": oos_passed,
            "detail": oos_detail,
        },
        "rollback_protocol": rollback,
        "user_confirmation": confirmation,
        "promotion": {
            "policy": "fail_closed_v1",
            "source_stage": source_stage,
            "governed_stage": governed_stage,
            "downgraded": STAGE_RANK[governed_stage] < STAGE_RANK[source_stage],
            "config_ready": config_ready,
            "live_ready": live_ready,
            "apply_allowed": apply_allowed,
            "confirmation_valid": confirmation["valid"],
            "evidence_score": score,
            "evidence_grade": evidence_grade,
            "checks": checks,
            "blockers": [check["label"] for check in failed],
            "next_required_checks": [check["id"] for check in failed],
            "apply_blockers": (
                ([] if governed_stage == "live_eligible" else ["live_eligible"])
                + ([] if confirmation["valid"] else ["explicit_user_confirmation"])
            ),
            "rule": "治理层只能维持或降低研究源阶段，不能提高；用户确认前禁止应用。",
        },
        "ledger": {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "entry_id": entry_id,
            "content_sha256": content_hash,
        },
    })
    return entry


def finalize_research_ledger(candidates: list[dict], *, computed: bool) -> tuple[list[dict], dict]:
    entries = [enrich_ledger_entry(candidate, computed=computed) for candidate in candidates]
    stage_counts = {stage: 0 for stage in STAGES}
    source_stage_counts = {stage: 0 for stage in STAGES}
    for entry in entries:
        stage_counts[entry["stage"]] += 1
        source_stage_counts[entry["source_stage"]] += 1
    ledger_id = "strategy_research_ledger:" + _json_hash([
        entry["ledger"]["content_sha256"] for entry in entries
    ])[:16]
    summary = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger_id,
        "entry_count": len(entries),
        "stage_counts": stage_counts,
        "source_stage_counts": source_stage_counts,
        "downgraded_count": sum(1 for entry in entries if entry["promotion"]["downgraded"]),
        "config_ready_count": sum(1 for entry in entries if entry["promotion"]["config_ready"]),
        "live_ready_count": sum(1 for entry in entries if entry["promotion"]["live_ready"]),
        "apply_allowed_count": sum(1 for entry in entries if entry["promotion"]["apply_allowed"]),
        "policy": {
            "name": "fail_closed_v1",
            "stages": list(STAGES),
            "config_candidate_requires": [
                "hypothesis", "data_source", "data_version", "backtest_window",
                "point_in_time", "sample_out", "vs_012922", "vs_current", "risk_gate",
            ],
            "live_eligible_additionally_requires": ["today_diff", "rollback"],
            "apply_additionally_requires": ["explicit_user_confirmation"],
            "automatic_config_write": False,
        },
    }
    return entries, summary


def source_policy_payloads() -> dict:
    return {source: asdict(policy) for source, policy in SOURCE_POLICIES.items()}
