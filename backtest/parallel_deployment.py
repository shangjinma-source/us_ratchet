"""Read-only capital deployment for an existing approved target book.

The strategy chooses names and amounts from account-truth gaps and execution
constraints. Broker activity requirements are deliberately absent: they must
never create, suppress, split, or time an investment action.
"""
from __future__ import annotations

import hashlib
import json
from math import floor, isfinite
from typing import Iterable, Mapping


def _number(value, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if isfinite(result) else default


def _fee(notional: float, fee_bps: float, min_fee: float) -> float:
    if notional <= 0:
        return 0.0
    return max(min_fee, notional * fee_bps / 10000.0)


def _order_cash_cost(lots: int, unit_notional: float,
                     fee_bps: float, min_fee: float) -> float:
    notional = max(0, int(lots)) * unit_notional
    return notional + _fee(notional, fee_bps, min_fee)


def _finalize_plan(payload: dict) -> dict:
    """Attach a deterministic identity to the complete mechanical draft."""
    canonical = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    out = dict(payload)
    out["plan_id"] = f"core-deployment:{hashlib.sha256(canonical).hexdigest()[:20]}"
    out["plan_identity_rule"] = (
        "相同账户缺口、报价、现金、整股与费用输入生成相同草案 ID；任一输入变化都会生成新 ID。"
    )
    return out


def build_parallel_deployment_plan(
    position_gaps: Iterable[Mapping],
    price_by_ticker: Mapping[str, float],
    *,
    cash_usd: float,
    broker_confirmed: bool,
    broker_snapshot_as_of: str | None = None,
    broker_account_fingerprint: str | None = None,
    excluded_tickers: Iterable[str] = (),
    max_names: int = 4,
    lot_size: int = 1,
    fee_bps: float = 0.0,
    min_fee: float = 0.0,
) -> dict:
    """Allocate cash across strategy-ranked gaps as whole-lot review lines.

    This is a mechanical deployment draft for the current approved target book,
    not a dynamic-k portfolio conclusion. A recently reported exit is excluded
    until the strategy explicitly produces a new entry decision, preventing an
    account sync from being interpreted as an instruction to buy it straight
    back.
    """
    cash = max(0.0, _number(cash_usd))
    name_limit = max(1, int(max_names or 1))
    lot = max(1, int(lot_size or 1))
    bps = max(0.0, _number(fee_bps))
    minimum_fee = max(0.0, _number(min_fee))
    excluded = {str(ticker or "").upper().strip() for ticker in excluded_tickers}

    candidates = []
    excluded_rows = []
    for raw in position_gaps:
        ticker = str(raw.get("ticker") or "").upper().strip()
        gap = max(0.0, _number(raw.get("gap_amount")))
        price = _number(price_by_ticker.get(ticker))
        explicitly_ineligible = raw.get("core_deployment_eligible") is False
        if ticker in excluded or explicitly_ineligible:
            excluded_rows.append({
                "ticker": ticker,
                "reason": (
                    "RECENTLY_REPORTED_EXIT_REQUIRES_NEW_STRATEGY_ENTRY_SIGNAL"
                    if ticker in excluded else
                    "POSITION_GAP_NOT_ELIGIBLE_FOR_CORE_DEPLOYMENT"
                ),
            })
            continue
        if not ticker or gap <= 0.01 or price <= 0 or bool(raw.get("frozen")):
            continue
        unit_notional = price * lot
        max_lots_by_gap = floor((gap + 1e-9) / unit_notional)
        if max_lots_by_gap <= 0:
            continue
        candidates.append({
            "ticker": ticker,
            "position_kind": str(raw.get("position_kind") or ""),
            "target_amount": round(max(0.0, _number(raw.get("target_amount"))), 2),
            "real_market_value": round(max(0.0, _number(raw.get("real_market_value"))), 2),
            "gap_amount": round(gap, 2),
            "gap_ratio": max(0.0, _number(raw.get("gap_ratio"))),
            "gap_rank": int(_number(raw.get("gap_rank"), 999)),
            "price": price,
            "unit_notional": unit_notional,
            "max_lots_by_gap": max_lots_by_gap,
            "lots_assigned": 0,
        })
    candidates.sort(key=lambda row: (
        -row["gap_ratio"], -row["gap_amount"], row["gap_rank"], row["ticker"]
    ))

    base = {
        "version": 3,
        "lane": "core_capital_deployment",
        "portfolio_role": "current_approved_core_gap_only",
        "portfolio_optimization_role": "separate_dynamic_k_research_track",
        "migration_control_included": False,
        "broker_activity_requirement_used": False,
        "cash_usd": round(cash, 2),
        "broker_confirmed": bool(broker_confirmed),
        "broker_snapshot_as_of": broker_snapshot_as_of,
        "broker_account_fingerprint": broker_account_fingerprint,
        "max_names": name_limit,
        "lot_size": lot,
        "allow_fractional": False,
        "fee_bps": bps,
        "min_fee": minimum_fee,
        "excluded_tickers": sorted(excluded),
        "excluded_rows": excluded_rows,
        "orders_created": False,
        "state_changed": False,
        "config_changed": False,
        "today_advice_changed": False,
        "promotion_allowed": False,
        "research_or_execution_draft": "READ_ONLY_EXECUTION_DRAFT",
        "selection_rule": (
            "按真实缺口比例、缺口金额和稳定 ticker 顺序选择本批最多 max_names 个可买整股标的；"
            "先保证每个入选标的一手，再按剩余缺口最大者分配额外整股。"
        ),
    }
    if cash <= 0:
        return _finalize_plan({
            **base, "status": "NEEDS_CASH_INPUT", "lines": [],
            "cash_deployed": 0.0, "cash_remaining": round(cash, 2),
        })
    if not candidates:
        return _finalize_plan({
            **base, "status": "NO_AFFORDABLE_WHOLE_LOT", "lines": [],
            "cash_deployed": 0.0, "cash_remaining": round(cash, 2),
        })

    remaining = cash
    selected = []
    for row in candidates:
        if len(selected) >= name_limit:
            break
        first_lot_cost = _order_cash_cost(1, row["unit_notional"], bps, minimum_fee)
        if first_lot_cost <= remaining + 1e-9:
            row["lots_assigned"] = 1
            selected.append(row)
            remaining -= first_lot_cost
    if not selected:
        return _finalize_plan({
            **base, "status": "NO_AFFORDABLE_WHOLE_LOT", "lines": [],
            "cash_deployed": 0.0, "cash_remaining": round(cash, 2),
        })

    while True:
        affordable = []
        for row in selected:
            lots = row["lots_assigned"]
            if lots >= row["max_lots_by_gap"]:
                continue
            incremental_cost = (
                _order_cash_cost(lots + 1, row["unit_notional"], bps, minimum_fee)
                - _order_cash_cost(lots, row["unit_notional"], bps, minimum_fee)
            )
            if incremental_cost <= remaining + 1e-9:
                affordable.append((row, incremental_cost))
        if not affordable:
            break
        affordable.sort(key=lambda pair: (
            -(pair[0]["gap_amount"] - pair[0]["lots_assigned"] * pair[0]["unit_notional"]),
            -pair[0]["gap_ratio"], pair[0]["ticker"]
        ))
        row, incremental_cost = affordable[0]
        row["lots_assigned"] += 1
        remaining -= incremental_cost

    lines = []
    for row in selected:
        shares = row["lots_assigned"] * lot
        notional = shares * row["price"]
        fee = _fee(notional, bps, minimum_fee)
        lines.append({
            "ticker": row["ticker"],
            "shares": shares,
            "reference_price": round(row["price"], 4),
            "notional": round(notional, 2),
            "estimated_fee": round(fee, 2),
            "cash_cost": round(notional + fee, 2),
            "gap_before": row["gap_amount"],
            "gap_after": round(max(0.0, row["gap_amount"] - notional), 2),
            "position_kind": row["position_kind"],
            "reason": "按当前已批准目标的真实持仓缺口部署；与券商交易考核无关。",
        })
    deployed = sum(float(row["cash_cost"]) for row in lines)
    result = {
        **base,
        "status": "READY_FOR_USER_REVIEW" if broker_confirmed else "ACCOUNT_CONFIRMATION_REQUIRED",
        "lines": lines,
        "strategy_selected_name_count": len(lines),
        "cash_deployed": round(deployed, 2),
        "cash_remaining": round(max(0.0, cash - deployed), 2),
        "deployment_ratio": round(deployed / cash, 6) if cash > 0 else 0.0,
        "account_confirmation_note": (
            "券商持仓已由用户确认，可进入逐笔人工复核。"
            if broker_confirmed else
            "当前券商快照未在本会话确认；草案仅供测算，不能视为可下单。"
        ),
        "boundary_note": (
            "本通道只沿当前已批准目标的真实缺口部署现金；不宣称原目标是动态 k 最优答案，"
            "也不使用 migration_control 的动作作为目标持仓数。"
        ),
    }
    return _finalize_plan(result)


__all__ = ["build_parallel_deployment_plan"]
