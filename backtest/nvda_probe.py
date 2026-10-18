"""Fail-closed contract helpers for the NVDA two-arm probe preregistration."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml


class NvdaProbePlanError(ValueError):
    """Raised when a probe plan diverges from its narrow preregistered scope."""


def _hash_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_probe_plan(plan: Mapping[str, Any], *, cfg, state) -> dict[str, Any]:
    errors: list[str] = []
    if int(plan.get("schema_version") or 0) != 1:
        errors.append("schema_version must be 1")
    if plan.get("research_only") is not True:
        errors.append("probe plan must remain research_only")
    if plan.get("live_config_mutation_allowed") is not False:
        errors.append("live config mutation must be disabled")
    if plan.get("return_data_read") is not False:
        errors.append("preregistration cannot read returns")

    control = plan.get("control_arm") or {}
    probe = plan.get("probe_arm") or {}
    evaluation = plan.get("evaluation") or {}
    guards = plan.get("portfolio_guards") or {}
    nvda = state.symbols.get("NVDA") if state is not None else None
    if nvda is None:
        errors.append("data/state.json must contain NVDA")
    if not math.isclose(float(control.get("bear_reserve_ratio", -1)), 0.0, abs_tol=1e-12):
        errors.append("control arm must preserve BEAR=0")
    if not math.isclose(float(cfg.tactical_orders.bear_reserve_ratio), 0.0, abs_tol=1e-12):
        errors.append("production config no longer matches control BEAR=0")
    if probe.get("budget_source") != "external_new_money_only":
        errors.append("probe budget must be external new money")
    if probe.get("core_or_ratchet_budget_reuse_allowed") is not False:
        errors.append("probe cannot reuse core or ratchet budget")
    if probe.get("existing_position_sale_allowed") is not False:
        errors.append("probe cannot sell existing holdings")
    if int(probe.get("fixed_order_lots") or 0) != 1:
        errors.append("probe must use exactly one lot per order")
    if int(probe.get("lot_size") or 0) != int(cfg.execution.lot_size):
        errors.append("probe lot size must match ExecutionConfig")
    if bool(probe.get("allow_fractional")) != bool(cfg.execution.allow_fractional):
        errors.append("fractional-share rule must match ExecutionConfig")
    if int(probe.get("cooldown_trading_days") or 0) != 20:
        errors.append("cooldown must be locked at 20 trading days")
    if int(probe.get("review_cycle_months") or 0) != 6:
        errors.append("review cycle must be locked at six months")
    if int(probe.get("order_lifetime_sessions") or 0) != 1:
        errors.append("probe order must expire after one session")
    if probe.get("eligible_regime") != "BEAR":
        errors.append("probe arm only addresses the BEAR abstention gap")
    if probe.get("chase_policy") != "never_raise_or_replace_unfilled_order":
        errors.append("unfilled probe orders must never be chased")

    single_cap = float(probe.get("single_order_notional_cap") or 0.0)
    total_cap = float(probe.get("total_notional_cap_per_review_cycle") or 0.0)
    state_h = float(nvda.H) if nvda is not None else 0.0
    if single_cap <= 0 or not math.isclose(single_cap, total_cap, abs_tol=0.005):
        errors.append("single and cycle notional caps must be the same positive one-lot cap")
    if state_h > 0 and not math.isclose(single_cap, state_h, abs_tol=0.005):
        errors.append("notional cap must remain hash-bound to registered NVDA.H")
    if guards.get("post_probe_single_name_not_above_incumbent_top1") is not True:
        errors.append("single-name incumbent Top1 guard is required")
    if guards.get("risk_chain_increment_not_above_one_capped_lot") is not True:
        errors.append("risk-chain increment must be capped at one registered lot")
    if int(evaluation.get("minimum_independent_signal_cohorts") or 0) < 12:
        errors.append("at least 12 independent fresh cohorts are required")
    if evaluation.get("promotion_before_fresh_oos_allowed") is not False:
        errors.append("promotion before fresh OOS must be forbidden")
    if errors:
        raise NvdaProbePlanError("; ".join(errors))

    caps = [float(symbol.cap_total) for symbol in cfg.symbols]
    total = sum(caps)
    incumbent_top1 = max(caps) / total
    nvda_weight = next(float(s.cap_total) for s in cfg.symbols if s.ticker == "NVDA") / total
    semi_tickers = {"NVDA", "TXN", "ASML", "CDNS", "TSM", "MU"}
    semi_cap = sum(float(s.cap_total) for s in cfg.symbols if s.ticker in semi_tickers)
    post_total = total + total_cap
    return {
        "passed": True,
        "plan_sha256": _hash_json(plan),
        "registered_nvda_h": state_h,
        "single_order_notional_cap": single_cap,
        "incumbent_risk_cap_total": total,
        "incumbent_top1": incumbent_top1,
        "incumbent_nvda_weight": nvda_weight,
        "incumbent_semiconductor_chain_weight": semi_cap / total,
        "maximum_post_probe_nvda_weight": (next(float(s.cap_total) for s in cfg.symbols if s.ticker == "NVDA") + total_cap) / post_total,
        "maximum_post_probe_semiconductor_chain_weight": (semi_cap + total_cap) / post_total,
        "execution_lot_size": float(cfg.execution.lot_size),
        "allow_fractional": bool(cfg.execution.allow_fractional),
    }


def load_probe_plan(path: str | Path, *, cfg, state) -> tuple[dict[str, Any], dict[str, Any]]:
    source = Path(path)
    try:
        plan = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise NvdaProbePlanError(f"cannot read probe plan: {exc}") from exc
    if not isinstance(plan, dict):
        raise NvdaProbePlanError("probe plan root must be a mapping")
    return plan, validate_probe_plan(plan, cfg=cfg, state=state)


def arm_rows(plan: Mapping[str, Any], audit: Mapping[str, Any]) -> pd.DataFrame:
    probe = plan["probe_arm"]
    return pd.DataFrame([
        {
            "arm_id": plan["control_arm"]["arm_id"],
            "arm_role": "control",
            "budget_source": "production_reserve_rule",
            "bear_action": "WAIT",
            "order_lots": 0,
            "single_order_cap": 0.0,
            "cycle_total_cap": 0.0,
            "cooldown_trading_days": 0,
            "order_lifetime_sessions": 0,
            "promotion_status": "FORWARD_WATCH_ONLY",
        },
        {
            "arm_id": probe["arm_id"],
            "arm_role": "probe",
            "budget_source": probe["budget_source"],
            "bear_action": "PLACE_ONE_SESSION_LIMIT_IF_ALL_GUARDS_PASS",
            "order_lots": int(probe["fixed_order_lots"]),
            "single_order_cap": float(probe["single_order_notional_cap"]),
            "cycle_total_cap": float(probe["total_notional_cap_per_review_cycle"]),
            "cooldown_trading_days": int(probe["cooldown_trading_days"]),
            "order_lifetime_sessions": int(probe["order_lifetime_sessions"]),
            "promotion_status": "FORWARD_WATCH_ONLY",
        },
    ])


def metric_rows(plan: Mapping[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "metric": metric,
            "value": None,
            "status": "NOT_AVAILABLE_UNTIL_FRESH_OOS",
            "reason": "预注册不读取收益；至少6个月且12个独立前向信号队列后才计算",
        }
        for metric in plan["evaluation"]["required_metrics"]
    ])

