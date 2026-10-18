"""Research-only whole-share convergence preview for future new money.

This module is deliberately independent from the P4 admission chain and from
broker persistence.  The simulation kernel accepts only explicit, synthetic or
already-sanitized inputs.  The public wrapper remains fail-closed until a
separate canonical P4 adapter is implemented; caller supplied booleans or
mappings can never unlock it.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping


class NdxDynamicShadowNewMoneyPreviewError(ValueError):
    """Raised when a research preview input is ambiguous or unsafe."""


_CURRENT_KEYS = {"security_id", "issuer_id", "ticker", "quantity"}
_TARGET_KEYS = {"security_id", "issuer_id", "ticker", "target_weight"}
_PRICE_KEYS = {
    "security_id", "issuer_id", "ticker", "price_usd", "session_date", "observed_at",
}
_FIXED_TRANSACTION_COST_BPS = 10.0
_FIXED_MINIMUM_CASH_BUFFER_USD = 100.0
_IMPROVEMENT_EPSILON = 1e-12
_DEFAULT_MAX_ITERATIONS = 100_000
_DEFAULT_MAX_CANDIDATE_EVALUATIONS = 1_000_000
_HARD_MAX_ITERATIONS = 1_000_000
_HARD_MAX_CANDIDATE_EVALUATIONS = 10_000_000


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise NdxDynamicShadowNewMoneyPreviewError(f"{field} cannot be boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowNewMoneyPreviewError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise NdxDynamicShadowNewMoneyPreviewError(f"{field} must be finite")
    return number


def _session_date(value: Any, field: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxDynamicShadowNewMoneyPreviewError(
            f"{field} must be an ISO date"
        ) from exc
    if parsed.isoformat() != text:
        raise NdxDynamicShadowNewMoneyPreviewError(f"{field} must be canonical YYYY-MM-DD")
    return text


def _timestamp(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NdxDynamicShadowNewMoneyPreviewError(
            f"{field} must be a timezone-aware ISO timestamp"
        ) from exc
    if "T" not in text or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NdxDynamicShadowNewMoneyPreviewError(
            f"{field} must be a timezone-aware ISO timestamp"
        )
    return parsed.astimezone(timezone.utc)


def _identity(raw: Mapping[str, Any], label: str) -> tuple[str, str, str]:
    security_id = str(raw.get("security_id") or "").strip()
    issuer_id = str(raw.get("issuer_id") or "").strip()
    ticker = str(raw.get("ticker") or "").upper().strip()
    if not security_id or not issuer_id or not ticker:
        raise NdxDynamicShadowNewMoneyPreviewError(f"{label} identity is incomplete")
    return security_id, issuer_id, ticker


def _exact_keys(raw: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(raw) != expected:
        raise NdxDynamicShadowNewMoneyPreviewError(f"{label} schema is not exact")


def _identity_index(
    rows: Iterable[Mapping[str, Any]], *, expected_keys: set[str], label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    issuers: set[str] = set()
    tickers: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise NdxDynamicShadowNewMoneyPreviewError(f"{label} row must be a mapping")
        _exact_keys(raw, expected_keys, label)
        security_id, issuer_id, ticker = _identity(raw, label)
        if security_id in result or issuer_id in issuers or ticker in tickers:
            raise NdxDynamicShadowNewMoneyPreviewError(
                f"{label} contains a duplicate security, issuer, or ticker identity"
            )
        result[security_id] = dict(raw, security_id=security_id, issuer_id=issuer_id, ticker=ticker)
        issuers.add(issuer_id)
        tickers.add(ticker)
    return result


def _shape(notionals: Mapping[str, float]) -> dict[str, float]:
    positive = [float(value) for value in notionals.values() if float(value) > 0]
    total = sum(positive)
    if total <= 0:
        return {"top1_weight": 0.0, "top3_weight": 0.0, "effective_n": 0.0}
    weights = sorted((value / total for value in positive), reverse=True)
    return {
        "top1_weight": weights[0],
        "top3_weight": sum(weights[:3]),
        "effective_n": 1.0 / sum(weight * weight for weight in weights),
    }


def _issuer_notionals(
    quantities: Mapping[str, int], identities: Mapping[str, Mapping[str, Any]],
    prices: Mapping[str, float],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for security_id, quantity in quantities.items():
        issuer_id = str(identities[security_id]["issuer_id"])
        result[issuer_id] = result.get(issuer_id, 0.0) + quantity * prices[security_id]
    return result


def _tracking_error(
    quantities: Mapping[str, int], cash_usd: float, identities: Mapping[str, Mapping[str, Any]],
    prices: Mapping[str, float], target_weights: Mapping[str, float],
) -> float:
    notionals = {
        security_id: quantities.get(security_id, 0) * prices[security_id]
        for security_id in identities
    }
    total_equity = sum(notionals.values()) + cash_usd
    if not math.isfinite(total_equity) or total_equity < 0:
        raise NdxDynamicShadowNewMoneyPreviewError("preview equity cannot be negative")
    if total_equity == 0:
        return sum(abs(weight) for weight in target_weights.values())
    security_error = sum(
        abs(notionals[security_id] / total_equity - target_weights.get(security_id, 0.0))
        for security_id in identities
    )
    return security_error + abs(cash_usd / total_equity)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _search_budget(value: Any, field: str, *, hard_maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NdxDynamicShadowNewMoneyPreviewError(f"{field} must be a positive integer")
    if value > hard_maximum:
        raise NdxDynamicShadowNewMoneyPreviewError(f"{field} exceeds the research safety limit")
    return value


def simulate_research_new_money_preview(
    current_holdings: Iterable[Mapping[str, Any]],
    target_holdings: Iterable[Mapping[str, Any]],
    prices: Iterable[Mapping[str, Any]],
    *,
    new_money_usd: float,
    valuation_session_date: str,
    valuation_timestamp: str,
    transaction_cost_bps: float = _FIXED_TRANSACTION_COST_BPS,
    minimum_cash_buffer_usd: float = _FIXED_MINIMUM_CASH_BUFFER_USD,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    max_candidate_evaluations: int = _DEFAULT_MAX_CANDIDATE_EVALUATIONS,
) -> dict[str, Any]:
    """Simulate a deterministic buy-only whole-share convergence path.

    At each step the kernel considers one additional share of every affordable
    target security and takes the share that produces the largest strict
    reduction in target L1 error.  The error includes residual new-money cash
    and frozen non-target holdings as zero-target assets.  This is a transparent
    execution heuristic, not a portfolio optimizer or a candidate admission.
    """

    session_date = _session_date(valuation_session_date, "valuation_session_date")
    valuation_instant = _timestamp(valuation_timestamp, "valuation_timestamp")
    if date.fromisoformat(session_date) > valuation_instant.date():
        raise NdxDynamicShadowNewMoneyPreviewError(
            "valuation session cannot be after the UTC observation date"
        )
    new_money = _finite_number(new_money_usd, "new_money_usd")
    bps = _finite_number(transaction_cost_bps, "transaction_cost_bps")
    buffer_usd = _finite_number(minimum_cash_buffer_usd, "minimum_cash_buffer_usd")
    if new_money < 0:
        raise NdxDynamicShadowNewMoneyPreviewError("new_money_usd cannot be negative")
    if bps != _FIXED_TRANSACTION_COST_BPS or buffer_usd != _FIXED_MINIMUM_CASH_BUFFER_USD:
        raise NdxDynamicShadowNewMoneyPreviewError("P5 cost and cash-buffer contract changed")
    iteration_budget = _search_budget(
        max_iterations, "max_iterations", hard_maximum=_HARD_MAX_ITERATIONS,
    )
    evaluation_budget = _search_budget(
        max_candidate_evaluations, "max_candidate_evaluations",
        hard_maximum=_HARD_MAX_CANDIDATE_EVALUATIONS,
    )

    current = _identity_index(current_holdings, expected_keys=_CURRENT_KEYS, label="current holding")
    targets = _identity_index(target_holdings, expected_keys=_TARGET_KEYS, label="target holding")
    if not targets:
        raise NdxDynamicShadowNewMoneyPreviewError("dynamic target portfolio is empty")
    price_rows = _identity_index(prices, expected_keys=_PRICE_KEYS, label="price")
    all_security_ids = set(current) | set(targets)
    if set(price_rows) != all_security_ids:
        raise NdxDynamicShadowNewMoneyPreviewError("prices must exactly cover current and target securities")

    all_identities: dict[str, dict[str, Any]] = {}
    issuer_to_security: dict[str, str] = {}
    ticker_to_security: dict[str, str] = {}
    for source in (current, targets):
        for security_id, row in source.items():
            prior = all_identities.get(security_id)
            identity = {key: row[key] for key in ("security_id", "issuer_id", "ticker")}
            if prior is not None and prior != identity:
                raise NdxDynamicShadowNewMoneyPreviewError("current/target security identity changed")
            if row["issuer_id"] in issuer_to_security and issuer_to_security[row["issuer_id"]] != security_id:
                raise NdxDynamicShadowNewMoneyPreviewError(
                    "multiple securities for one issuer are not supported by this preview"
                )
            if row["ticker"] in ticker_to_security and ticker_to_security[row["ticker"]] != security_id:
                raise NdxDynamicShadowNewMoneyPreviewError("ticker maps to multiple securities")
            all_identities[security_id] = identity
            issuer_to_security[row["issuer_id"]] = security_id
            ticker_to_security[row["ticker"]] = security_id

    quantities: dict[str, int] = {security_id: 0 for security_id in all_security_ids}
    for security_id, row in current.items():
        quantity_value = row["quantity"]
        if isinstance(quantity_value, bool) or not isinstance(quantity_value, int) or quantity_value < 0:
            raise NdxDynamicShadowNewMoneyPreviewError("current quantities must be non-negative integers")
        quantities[security_id] = quantity_value

    target_weights: dict[str, float] = {}
    for security_id, row in targets.items():
        weight = _finite_number(row["target_weight"], f"target_weight for {security_id}")
        if weight <= 0:
            raise NdxDynamicShadowNewMoneyPreviewError("target weights must be positive")
        target_weights[security_id] = weight
    if not math.isclose(sum(target_weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise NdxDynamicShadowNewMoneyPreviewError("target weights must sum to one")

    price_by_security: dict[str, float] = {}
    for security_id, row in price_rows.items():
        identity = all_identities[security_id]
        if any(row[key] != identity[key] for key in ("security_id", "issuer_id", "ticker")):
            raise NdxDynamicShadowNewMoneyPreviewError("price identity does not match holdings")
        if _session_date(row["session_date"], f"price session for {security_id}") != session_date:
            raise NdxDynamicShadowNewMoneyPreviewError("prices are not from one valuation session")
        if _timestamp(row["observed_at"], f"price timestamp for {security_id}") != valuation_instant:
            raise NdxDynamicShadowNewMoneyPreviewError("prices are not from one observation instant")
        price = _finite_number(row["price_usd"], f"price for {security_id}")
        if price <= 0:
            raise NdxDynamicShadowNewMoneyPreviewError("prices must be positive")
        price_by_security[security_id] = price

    before_quantities = dict(quantities)
    remaining_cash = new_money
    accumulated_fees = 0.0
    starting_error = _tracking_error(
        quantities, remaining_cash, all_identities, price_by_security, target_weights,
    )
    current_error = starting_error
    buy_shares = {security_id: 0 for security_id in targets}
    completed_iterations = 0
    candidate_evaluations = 0
    search_budget_exhausted = False

    while True:
        if completed_iterations >= iteration_budget:
            search_budget_exhausted = True
            break
        proposals: list[tuple[float, str, float, float]] = []
        for security_id in sorted(targets):
            if candidate_evaluations >= evaluation_budget:
                search_budget_exhausted = True
                break
            candidate_evaluations += 1
            price = price_by_security[security_id]
            fee = price * bps / 10_000.0
            cash_cost = price + fee
            if not math.isfinite(fee) or not math.isfinite(cash_cost):
                raise NdxDynamicShadowNewMoneyPreviewError("whole-share cash cost overflowed")
            if remaining_cash - cash_cost < buffer_usd - 1e-9:
                continue
            candidate_quantities = dict(quantities)
            candidate_quantities[security_id] += 1
            candidate_cash = remaining_cash - cash_cost
            candidate_error = _tracking_error(
                candidate_quantities, candidate_cash, all_identities,
                price_by_security, target_weights,
            )
            improvement = current_error - candidate_error
            if improvement > _IMPROVEMENT_EPSILON:
                proposals.append((-improvement, security_id, candidate_error, cash_cost))
        if search_budget_exhausted:
            break
        if not proposals:
            break
        _, security_id, candidate_error, cash_cost = min(proposals)
        quantities[security_id] += 1
        buy_shares[security_id] += 1
        remaining_cash -= cash_cost
        accumulated_fees += price_by_security[security_id] * bps / 10_000.0
        current_error = candidate_error
        completed_iterations += 1

    before_notionals = {
        security_id: before_quantities[security_id] * price_by_security[security_id]
        for security_id in sorted(all_security_ids)
    }
    after_notionals = {
        security_id: quantities[security_id] * price_by_security[security_id]
        for security_id in sorted(all_security_ids)
    }
    buy_plan = []
    position_changes = []
    for security_id in sorted(all_security_ids):
        identity = all_identities[security_id]
        purchased = buy_shares.get(security_id, 0)
        price = price_by_security[security_id]
        row = {
            **identity,
            "target_weight": target_weights.get(security_id, 0.0),
            "quantity_before": before_quantities[security_id],
            "buy_shares": purchased,
            "sell_shares": 0,
            "quantity_after": quantities[security_id],
            "reference_price_usd": price,
            "market_value_before_usd": before_notionals[security_id],
            "market_value_after_usd": after_notionals[security_id],
            "non_target_frozen": security_id not in targets,
        }
        position_changes.append(row)
        if purchased:
            gross = purchased * price
            fee = gross * bps / 10_000.0
            buy_plan.append({
                **identity,
                "action": "RESEARCH_PREVIEW_BUY",
                "shares": purchased,
                "sell_shares": 0,
                "reference_price_usd": price,
                "gross_notional_usd": gross,
                "estimated_fee_usd": fee,
                "cash_cost_usd": gross + fee,
                "orders_created": False,
            })

    gross_buy_notional = sum(row["gross_notional_usd"] for row in buy_plan)
    buy_cash_cost = gross_buy_notional + accumulated_fees
    current_stock_value = sum(before_notionals.values())
    final_stock_value = sum(after_notionals.values())
    before_issuer = _issuer_notionals(
        before_quantities, all_identities, price_by_security,
    )
    after_issuer = _issuer_notionals(quantities, all_identities, price_by_security)
    normalized_inputs = {
        "current_holdings": [current[key] for key in sorted(current)],
        "target_holdings": [targets[key] for key in sorted(targets)],
        "prices": [price_rows[key] for key in sorted(price_rows)],
        "new_money_usd": new_money,
        "valuation_session_date": session_date,
        "valuation_timestamp_utc": valuation_instant.isoformat(),
        "transaction_cost_bps": bps,
        "minimum_cash_buffer_usd": buffer_usd,
        "max_iterations": iteration_budget,
        "max_candidate_evaluations": evaluation_budget,
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_new_money_research_preview",
        "status": (
            "RESEARCH_SEARCH_BUDGET_EXHAUSTED"
            if search_budget_exhausted else (
                "RESEARCH_PREVIEW_STRICT_CONVERGENCE_PATH"
                if buy_plan else "RESEARCH_PREVIEW_NO_STRICTLY_IMPROVING_AFFORDABLE_WHOLE_SHARE"
            )
        ),
        "valuation_session_date": session_date,
        "valuation_timestamp_utc": valuation_instant.isoformat(),
        "target_k": len(targets),
        "buy_action_count": len(buy_plan),
        "target_k_is_not_buy_action_count": True,
        "algorithm": (
            "DETERMINISTIC_ONE_SHARE_GREEDY_MAX_STRICT_L1_IMPROVEMENT_"
            "INCLUDING_CASH_AND_FROZEN_NON_TARGETS"
        ),
        "algorithm_is_portfolio_optimizer": False,
        "portfolio_optimality_claimed": False,
        "candidate_admission_performed": False,
        "target_selection_performed": False,
        "research_track": "migration_control",
        "upstream_target_research_track": "portfolio_optimization",
        "migration_control_included": True,
        "research_only": True,
        "execution_eligible": False,
        "risk_limit_status": "RISK_LIMIT_POLICY_NOT_SUPPLIED_NOT_EXECUTION_ELIGIBLE",
        "broker_activity_requirement_used": False,
        "forced_cash_deployment": False,
        "orders_created": False,
        "config_changed": False,
        "state_changed": False,
        "broker_snapshot_changed": False,
        "today_advice_changed": False,
        "new_money_usd": new_money,
        "minimum_cash_buffer_usd": buffer_usd,
        "transaction_cost_bps": bps,
        "gross_buy_notional_usd": gross_buy_notional,
        "estimated_fees_usd": accumulated_fees,
        "new_money_cash_used_usd": buy_cash_cost,
        "uninvested_new_money_usd": remaining_cash,
        "cash_buffer_preserved": remaining_cash >= buffer_usd - 1e-9,
        "current_stock_value_usd": current_stock_value,
        "final_stock_value_usd": final_stock_value,
        "initial_total_equity_usd": current_stock_value + new_money,
        "final_total_equity_usd": final_stock_value + remaining_cash,
        "fee_only_equity_reduction_usd": accumulated_fees,
        "target_l1_error_before": starting_error,
        "target_l1_error_after": current_error,
        "target_l1_strictly_improved": current_error < starting_error - _IMPROVEMENT_EPSILON,
        "search_complete": not search_budget_exhausted,
        "search_budget": {
            "max_iterations": iteration_budget,
            "max_candidate_evaluations": evaluation_budget,
            "completed_iterations": completed_iterations,
            "candidate_evaluations": candidate_evaluations,
            "budget_exhausted": search_budget_exhausted,
            "budget_is_portfolio_policy": False,
            "budget_is_target_cardinality_limit": False,
            "budget_may_truncate_preview": True,
        },
        "security_shape_before": _shape(before_notionals),
        "security_shape_after": _shape(after_notionals),
        "issuer_shape_before": _shape(before_issuer),
        "issuer_shape_after": _shape(after_issuer),
        "buy_plan": buy_plan,
        "position_changes": position_changes,
        "input_fingerprint_sha256": _canonical_hash(normalized_inputs),
    }
    payload["preview_id"] = "p5-research-preview:" + _canonical_hash(payload)[:24]
    return payload


def build_new_money_preview(*, admission_authority: Any = None) -> dict[str, Any]:
    """Fail closed until a canonical, rebuildable P4 adapter is implemented."""

    if admission_authority is not None:
        raise NdxDynamicShadowNewMoneyPreviewError(
            "caller-supplied admission authority is not accepted"
        )
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_new_money_preview_readiness",
        "status": "BLOCKED_NO_CANONICAL_P4_ADMISSION_ADAPTER",
        "blockers": [
            "CANONICAL_P4_ADMISSION_ADAPTER_NOT_IMPLEMENTED",
            "CANONICAL_EXECUTION_IDENTITY_AND_PRICE_EVIDENCE_NOT_AVAILABLE",
        ],
        "plan_rows": [],
        "eligible_candidate_ids": [],
        "caller_supplied_admission_authority_accepted": False,
        "synthetic_research_kernel_available": True,
        "research_track": "migration_control",
        "upstream_target_research_track": "portfolio_optimization",
        "migration_control_included": True,
        "orders_created": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


__all__ = [
    "NdxDynamicShadowNewMoneyPreviewError",
    "build_new_money_preview",
    "simulate_research_new_money_preview",
]
