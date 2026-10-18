"""Research-only conditional whole-lot repair for dynamic security-id paths.

The frozen dynamic engine remains the baseline.  This version preserves its
decision/execution coordinates, nominal execution and valuation channels,
security/issuer identity semantics, target sets, target weights, and bilateral
transaction costs.  A bounded floor/ceil projection is attempted only when the
baseline whole-lot action is not executable or violates one of the five fixed
risk checks at the execution price.

This is an execution diagnostic, not a portfolio selector, admission gate,
live allocator, order generator, or proof over the full integer share space.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from backtest import ndx_dynamic_whole_lot_path as legacy
from backtest.ndx_whole_lot_repair_diagnostic import (
    NdxWholeLotRepairDiagnosticError,
    project_whole_lot_rebalance,
)


class NdxDynamicWholeLotRepairPathError(ValueError):
    """Raised when the versioned dynamic repair contract is invalid."""


_TOLERANCE = 1e-8
_REPAIR_EVENT_COLUMNS = [
    "rebalance_sequence",
    "decision_date",
    "execution_date",
    "trigger_reasons",
    "projection_status",
    "search_complete",
    "search_space_size",
    "evaluations_completed",
    "removed_sell_notional_usd",
    "removed_transaction_cost_usd",
]


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise NdxDynamicWholeLotRepairPathError(f"{field} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotRepairPathError(
            f"{field} must be finite numeric"
        ) from exc
    if not math.isfinite(result):
        raise NdxDynamicWholeLotRepairPathError(f"{field} must be finite numeric")
    return result


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _strict_session_date(value: Any, field: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotRepairPathError(f"invalid {field}: {value!r}") from exc
    if pd.isna(result) or result.tzinfo is not None or result != result.normalize():
        raise NdxDynamicWholeLotRepairPathError(
            f"{field} must be a timezone-naive midnight session date"
        )
    if isinstance(value, str) and value != result.date().isoformat():
        raise NdxDynamicWholeLotRepairPathError(
            f"{field} string must use exact YYYY-MM-DD form"
        )
    return result


def _strict_price_index(frame: Any, field: str) -> None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise NdxDynamicWholeLotRepairPathError(f"{field} must be a nonempty DataFrame")
    dates = [_strict_session_date(value, f"{field} index") for value in frame.index]
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise NdxDynamicWholeLotRepairPathError(
            f"{field} session dates must be unique and ascending"
        )
    columns = list(frame.columns)
    if any(
        not isinstance(column, str)
        or not column
        or column != column.strip().upper()
        for column in columns
    ) or len(set(columns)) != len(columns):
        raise NdxDynamicWholeLotRepairPathError(
            f"{field} ticker columns must be canonical, nonempty, and unique"
        )


def _risk_snapshot(
    shares: Mapping[str, int],
    marks: Mapping[str, float],
    chains: Mapping[str, str],
    *,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict[str, Any]:
    if not shares or set(shares) != set(marks) or set(shares) != set(chains):
        raise NdxDynamicWholeLotRepairPathError(
            "risk snapshot identity sets must be nonempty and identical"
        )
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in shares.values()):
        return {
            "checks": {
                "MAX_SINGLE_WEIGHT": False,
                "MIN_SINGLE_WEIGHT": False,
                "SECURITY_TOP3_WEIGHT": False,
                "MINIMUM_EFFECTIVE_N": False,
                "RISK_CHAIN_TOP1_WEIGHT": False,
            },
            "all_passed": False,
            "actual_weights": {},
            "top1_weight": None,
            "minimum_single_weight": None,
            "top3_weight": None,
            "effective_n": None,
            "risk_chain_top1_weight": None,
        }
    notionals = {
        security_id: int(shares[security_id]) * float(marks[security_id])
        for security_id in shares
    }
    invested = sum(notionals.values())
    if not math.isfinite(invested) or invested <= 0:
        raise NdxDynamicWholeLotRepairPathError("risk snapshot invested value is invalid")
    weights = {
        security_id: notional / invested for security_id, notional in notionals.items()
    }
    ordered = sorted(weights.values(), reverse=True)
    effective_n = 1.0 / sum(value * value for value in ordered)
    chain_weights: dict[str, float] = {}
    for security_id, weight in weights.items():
        chain = chains[security_id]
        chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
    checks = {
        "MAX_SINGLE_WEIGHT": ordered[0] <= max_single_weight + 1e-9,
        "MIN_SINGLE_WEIGHT": ordered[-1] >= min_single_weight - 1e-9,
        "SECURITY_TOP3_WEIGHT": sum(ordered[:3]) <= top_weight_cap + 1e-9,
        "MINIMUM_EFFECTIVE_N": effective_n
        >= minimum_effective_n_ratio * len(ordered) - 1e-9,
        "RISK_CHAIN_TOP1_WEIGHT": max(chain_weights.values())
        <= risk_chain_top1_cap + 1e-9,
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "actual_weights": dict(sorted(weights.items())),
        "top1_weight": ordered[0],
        "minimum_single_weight": ordered[-1],
        "top3_weight": sum(ordered[:3]),
        "effective_n": effective_n,
        "risk_chain_top1_weight": max(chain_weights.values()),
    }


def _normalise_contract(
    items: list[dict[str, Any]],
    *,
    risk_chains_by_decision: Mapping[str, Mapping[str, str]],
    initial_cash_usd: Any,
    minimum_cash_buffer_usd: Any,
    transaction_cost_bps: Any,
    max_single_weight: Any,
    min_single_weight: Any,
    top_weight_cap: Any,
    minimum_effective_n_ratio: Any,
    risk_chain_top1_cap: Any,
    max_repair_evaluations: Any,
) -> dict[str, Any]:
    decision_dates = [item["decision_date"].date().isoformat() for item in items]
    if len(set(decision_dates)) != len(decision_dates):
        raise NdxDynamicWholeLotRepairPathError(
            "schedule decision dates must be unique for risk-chain evidence"
        )
    if not isinstance(risk_chains_by_decision, Mapping) or set(
        risk_chains_by_decision
    ) != set(decision_dates):
        raise NdxDynamicWholeLotRepairPathError(
            "risk_chains_by_decision must cover exactly the scheduled decision dates"
        )
    chains_by_decision: dict[str, dict[str, str]] = {}
    for item, decision_date in zip(items, decision_dates):
        raw = risk_chains_by_decision[decision_date]
        if not isinstance(raw, Mapping) or set(raw) != set(item["targets"]):
            raise NdxDynamicWholeLotRepairPathError(
                f"risk chains for {decision_date} must cover exactly that decision's targets"
            )
        current: dict[str, str] = {}
        for security_id in sorted(raw):
            chain = raw[security_id]
            if (
                not isinstance(chain, str)
                or not chain
                or chain != chain.strip()
            ):
                raise NdxDynamicWholeLotRepairPathError(
                    "risk-chain identities must be canonical nonempty strings"
                )
            current[security_id] = chain
        chains_by_decision[decision_date] = current
    if (
        isinstance(max_repair_evaluations, bool)
        or not isinstance(max_repair_evaluations, int)
        or max_repair_evaluations <= 0
    ):
        raise NdxDynamicWholeLotRepairPathError(
            "max_repair_evaluations must be a positive integer"
        )
    contract = {
        "initial_cash_usd": _finite(initial_cash_usd, "initial_cash_usd"),
        "minimum_cash_buffer_usd": _finite(
            minimum_cash_buffer_usd, "minimum_cash_buffer_usd"
        ),
        "transaction_cost_bps": _finite(
            transaction_cost_bps, "transaction_cost_bps"
        ),
        "max_single_weight": _finite(max_single_weight, "max_single_weight"),
        "min_single_weight": _finite(min_single_weight, "min_single_weight"),
        "top_weight_cap": _finite(top_weight_cap, "top_weight_cap"),
        "minimum_effective_n_ratio": _finite(
            minimum_effective_n_ratio, "minimum_effective_n_ratio"
        ),
        "risk_chain_top1_cap": _finite(
            risk_chain_top1_cap, "risk_chain_top1_cap"
        ),
        "max_repair_evaluations": max_repair_evaluations,
        "risk_chains_by_decision": chains_by_decision,
    }
    if (
        contract["initial_cash_usd"] <= 0
        or contract["minimum_cash_buffer_usd"] < 0
        or contract["minimum_cash_buffer_usd"] >= contract["initial_cash_usd"]
        or contract["transaction_cost_bps"] < 0
        or not (
            0
            <= contract["min_single_weight"]
            <= contract["max_single_weight"]
            <= 1
        )
        or not 0 <= contract["top_weight_cap"] <= 1
        or not 0 <= contract["minimum_effective_n_ratio"] <= 1
        or not 0 <= contract["risk_chain_top1_cap"] <= 1
    ):
        raise NdxDynamicWholeLotRepairPathError(
            "dynamic conditional-repair execution contract is invalid"
        )
    return contract


def _daily_risk_audit(
    path: pd.DataFrame,
    valuation_prices: pd.DataFrame,
    *,
    chains_by_execution_date: Mapping[pd.Timestamp, Mapping[str, str]],
    contract: Mapping[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    active_chains: dict[str, str] = {}
    for row in path.to_dict("records"):
        date = pd.Timestamp(row["date"])
        if date in chains_by_execution_date:
            active_chains = dict(chains_by_execution_date[date])
        holdings = json.loads(str(row["holdings"]))
        active = sorted(holdings)
        if set(active_chains) != set(active):
            raise NdxDynamicWholeLotRepairPathError(
                "daily risk-chain evidence does not match active security identities"
            )
        marks = {
            security_id: legacy._price_at(
                valuation_prices, date, str(holdings[security_id]["ticker"])
            )
            for security_id in active
        }
        snapshot = _risk_snapshot(
            {security_id: int(holdings[security_id]["shares"]) for security_id in active},
            marks,
            {security_id: active_chains[security_id] for security_id in active},
            max_single_weight=contract["max_single_weight"],
            min_single_weight=contract["min_single_weight"],
            top_weight_cap=contract["top_weight_cap"],
            minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
            risk_chain_top1_cap=contract["risk_chain_top1_cap"],
        )
        failures = sorted(key for key, passed in snapshot["checks"].items() if not passed)
        rows.append({
            "session_date": date.date().isoformat(),
            "is_rebalance_session": date in chains_by_execution_date,
            "all_constraints_passed": snapshot["all_passed"],
            "failure_reasons": _json(failures),
            "top1_weight": snapshot["top1_weight"],
            "minimum_single_weight": snapshot["minimum_single_weight"],
            "top3_weight": snapshot["top3_weight"],
            "effective_n": snapshot["effective_n"],
            "risk_chain_top1_weight": snapshot["risk_chain_top1_weight"],
        })
    return pd.DataFrame(rows)


def _result(
    *,
    status: str,
    search_complete: bool,
    path_complete: bool,
    legacy_exact_reuse: bool,
    summary: dict[str, Any] | None,
    rebalances: pd.DataFrame | None,
    trades: pd.DataFrame | None,
    path: pd.DataFrame | None,
    repair_events: pd.DataFrame,
    daily_risk: pd.DataFrame | None,
) -> dict[str, Any]:
    summary_invariants_passed = bool(
        isinstance(summary, Mapping)
        and summary.get("cash_buffer_preserved") is True
        and summary.get("cash_conservation_passed") is True
        and summary.get("accounting_invariant_passed") is True
        and summary.get("whole_share_invariant_passed") is True
    )
    daily_risk_passed = bool(
        isinstance(daily_risk, pd.DataFrame)
        and not daily_risk.empty
        and "all_constraints_passed" in daily_risk.columns
        and daily_risk["all_constraints_passed"].map(lambda value: value is True).all()
    )
    execution_eligible = bool(
        search_complete
        and path_complete
        and summary_invariants_passed
        and daily_risk_passed
    )
    return {
        "status": status,
        "research_only": True,
        "research_track": "portfolio_optimization_execution_diagnostic",
        "algorithm_is_portfolio_optimizer": False,
        "candidate_set_changed": False,
        "target_weights_changed": False,
        "rebalance_schedule_changed": False,
        "legacy_exact_reuse": legacy_exact_reuse,
        "conditional_repair_enabled": True,
        "repair_search_space": "PER_TARGET_SECURITY_FLOOR_OR_CEIL_ONLY_AFTER_MANDATORY_EXITS",
        "search_complete": search_complete,
        "path_complete": path_complete,
        "execution_eligible": execution_eligible,
        "execution_eligible_is_research_diagnostic_only": True,
        "execution_eligibility_requires_full_daily_risk_path": True,
        "summary": summary,
        "rebalances": rebalances,
        "trades": trades,
        "path": path,
        "repair_events": repair_events,
        "daily_risk": daily_risk,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
        "full_integer_space_infeasibility_claimed": False,
    }


def simulate_dynamic_security_id_conditional_repair_path(
    prices: pd.DataFrame,
    schedule: Iterable[Mapping[str, Any]],
    *,
    execution_prices: pd.DataFrame | None = None,
    require_separate_execution_prices: bool = True,
    require_next_session_execution: bool = True,
    require_issuer_trace: bool = True,
    risk_chains_by_decision: Mapping[str, Mapping[str, str]],
    initial_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float = 10.0,
    valuation_end_date: Any,
    max_single_weight: float = 0.45,
    min_single_weight: float = 0.05,
    top_weight_cap: float = 0.80,
    minimum_effective_n_ratio: float = 0.70,
    risk_chain_top1_cap: float = 0.55,
    max_repair_evaluations: int = 262_144,
) -> dict[str, Any]:
    """Replay a dynamic identity path and conditionally repair execution lots."""

    if (
        execution_prices is None
        or require_separate_execution_prices is not True
        or require_next_session_execution is not True
        or require_issuer_trace is not True
    ):
        raise NdxDynamicWholeLotRepairPathError(
            "dynamic repair requires separate execution prices, next-session execution, "
            "and a complete issuer trace"
        )
    try:
        schedule_rows = list(schedule)
    except TypeError as exc:
        raise NdxDynamicWholeLotRepairPathError("schedule must be iterable") from exc
    _strict_price_index(prices, "valuation prices")
    if execution_prices is not None:
        _strict_price_index(execution_prices, "execution prices")
    for sequence, raw_item in enumerate(schedule_rows, start=1):
        if not isinstance(raw_item, Mapping):
            raise NdxDynamicWholeLotRepairPathError(
                f"rebalance {sequence}: schedule item must be a mapping"
            )
        _strict_session_date(raw_item.get("decision_date"), "decision_date")
        _strict_session_date(raw_item.get("execution_date"), "execution_date")
        raw_targets = raw_item.get("targets")
        if not isinstance(raw_targets, Mapping) or not raw_targets:
            raise NdxDynamicWholeLotRepairPathError(
                f"rebalance {sequence}: targets must be a nonempty mapping"
            )
        for security_id, raw_target in raw_targets.items():
            if (
                not isinstance(security_id, str)
                or not security_id
                or security_id != security_id.strip()
                or not isinstance(raw_target, Mapping)
            ):
                raise NdxDynamicWholeLotRepairPathError(
                    f"rebalance {sequence}: security identities must be canonical strings"
                )
            ticker = raw_target.get("ticker")
            issuer_id = raw_target.get("issuer_id")
            if (
                not isinstance(ticker, str)
                or not ticker
                or ticker != ticker.strip().upper()
                or not isinstance(issuer_id, str)
                or not issuer_id
                or issuer_id != issuer_id.strip()
            ):
                raise NdxDynamicWholeLotRepairPathError(
                    f"rebalance {sequence}: ticker and issuer identities must be canonical"
                )
            _finite(raw_target.get("target_weight"), "target_weight")
    strict_end_date = _strict_session_date(valuation_end_date, "valuation_end_date")
    try:
        frame = legacy._normalise_prices(prices)
        execution_frame = (
            legacy._normalise_prices(execution_prices)
            if execution_prices is not None
            else frame
        )
        items = legacy._normalise_schedule(schedule_rows)
        legacy._validate_schedule_identity_and_execution_guards(
            items,
            valuation_prices=frame,
            separate_execution_prices_supplied=execution_prices is not None,
            require_separate_execution_prices=require_separate_execution_prices,
            require_next_session_execution=require_next_session_execution,
            require_issuer_trace=require_issuer_trace,
        )
        end_date = legacy._date(strict_end_date, field="valuation_end_date")
    except legacy.NdxDynamicWholeLotPathError as exc:
        raise NdxDynamicWholeLotRepairPathError(str(exc)) from exc
    contract = _normalise_contract(
        items,
        risk_chains_by_decision=risk_chains_by_decision,
        initial_cash_usd=initial_cash_usd,
        minimum_cash_buffer_usd=minimum_cash_buffer_usd,
        transaction_cost_bps=transaction_cost_bps,
        max_single_weight=max_single_weight,
        min_single_weight=min_single_weight,
        top_weight_cap=top_weight_cap,
        minimum_effective_n_ratio=minimum_effective_n_ratio,
        risk_chain_top1_cap=risk_chain_top1_cap,
        max_repair_evaluations=max_repair_evaluations,
    )
    first_execution = items[0]["execution_date"]
    last_execution = items[-1]["execution_date"]
    if end_date < last_execution:
        raise NdxDynamicWholeLotRepairPathError(
            "valuation_end_date must not precede the final execution date"
        )
    execution_dates = {item["execution_date"] for item in items}
    if (
        end_date not in frame.index
        or not execution_dates.issubset(set(execution_frame.index))
    ):
        raise NdxDynamicWholeLotRepairPathError(
            "an execution or valuation date is absent from prices"
        )
    path_prices = frame.loc[first_execution:end_date].copy()
    if path_prices.empty:
        raise NdxDynamicWholeLotRepairPathError("no prices inside the valuation interval")
    chains_by_execution_date = {
        item["execution_date"]: contract["risk_chains_by_decision"][
            item["decision_date"].date().isoformat()
        ]
        for item in items
    }

    # Preserve the frozen engine byte-for-byte whenever all of its execution
    # actions pass the new execution-date risk checks.
    try:
        baseline = legacy.simulate_dynamic_security_id_whole_lot_path(
            prices,
            schedule_rows,
            execution_prices=execution_prices,
            require_separate_execution_prices=require_separate_execution_prices,
            require_next_session_execution=require_next_session_execution,
            require_issuer_trace=require_issuer_trace,
            initial_cash_usd=initial_cash_usd,
            minimum_cash_buffer_usd=minimum_cash_buffer_usd,
            transaction_cost_bps=transaction_cost_bps,
            valuation_end_date=valuation_end_date,
        )
    except (OverflowError, ValueError) as exc:
        if not isinstance(exc, legacy.NdxDynamicWholeLotPathError):
            raise NdxDynamicWholeLotRepairPathError(
                "legacy target share coordinate overflowed"
            ) from exc
        if not any(
            marker in str(exc)
            for marker in (
                "target is not executable as positive whole lots",
                "costs breach buffer and positive lots cannot be preserved",
            )
        ):
            raise NdxDynamicWholeLotRepairPathError(str(exc)) from exc
        baseline = None
    if baseline is not None:
        baseline_summary, baseline_rebalances, baseline_trades, baseline_path = baseline
        baseline_actions_pass = True
        for row in baseline_rebalances.to_dict("records"):
            date = pd.Timestamp(row["execution_date"])
            holdings = json.loads(str(row["holdings"]))
            active = sorted(holdings)
            marks = {
                security_id: legacy._price_at(
                    execution_frame, date, str(holdings[security_id]["ticker"])
                )
                for security_id in active
            }
            snapshot = _risk_snapshot(
                {security_id: int(holdings[security_id]["shares"]) for security_id in active},
                marks,
                {security_id: chains_by_execution_date[date][security_id] for security_id in active},
                max_single_weight=contract["max_single_weight"],
                min_single_weight=contract["min_single_weight"],
                top_weight_cap=contract["top_weight_cap"],
                minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
                risk_chain_top1_cap=contract["risk_chain_top1_cap"],
            )
            baseline_actions_pass = baseline_actions_pass and snapshot["all_passed"]
        if baseline_actions_pass:
            daily_risk = _daily_risk_audit(
                baseline_path,
                frame,
                chains_by_execution_date=chains_by_execution_date,
                contract=contract,
            )
            return _result(
                status="COMPLETE_LEGACY_EXACT_REUSE",
                search_complete=True,
                path_complete=True,
                legacy_exact_reuse=True,
                summary=baseline_summary,
                rebalances=baseline_rebalances,
                trades=baseline_trades,
                path=baseline_path,
                repair_events=pd.DataFrame(columns=_REPAIR_EVENT_COLUMNS),
                daily_risk=daily_risk,
            )

    cash = contract["initial_cash_usd"]
    buffer = contract["minimum_cash_buffer_usd"]
    fee_rate = contract["transaction_cost_bps"] / 10_000.0
    holdings: dict[str, dict[str, Any]] = {}
    rebalances: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    repair_events: list[dict[str, Any]] = []
    schedule_by_date = {item["execution_date"]: item for item in items}
    total_buy = total_sell = total_fees = 0.0
    maximum_accounting_error = maximum_cash_error = 0.0
    minimum_cash = cash

    for date in path_prices.index:
        if date in schedule_by_date:
            item = schedule_by_date[date]
            targets = item["targets"]
            decision_chains = contract["risk_chains_by_decision"][
                item["decision_date"].date().isoformat()
            ]
            current_ids = set(holdings)
            target_ids = set(targets)
            added_ids = sorted(target_ids - current_ids)
            removed_ids = sorted(current_ids - target_ids)
            continued_ids = sorted(current_ids & target_ids)
            renamed_ids = sorted(
                security_id
                for security_id in continued_ids
                if holdings[security_id]["ticker"] != targets[security_id]["ticker"]
            )
            marks: dict[str, float] = {}
            try:
                for security_id in sorted(current_ids | target_ids):
                    ticker = (
                        targets[security_id]["ticker"]
                        if security_id in target_ids
                        else holdings[security_id]["ticker"]
                    )
                    marks[security_id] = legacy._price_at(execution_frame, date, ticker)
            except legacy.NdxDynamicWholeLotPathError as exc:
                raise NdxDynamicWholeLotRepairPathError(str(exc)) from exc
            cash_before = cash
            pretrade_equity = cash_before + sum(
                int(holding["shares"]) * marks[security_id]
                for security_id, holding in holdings.items()
            )
            investable = pretrade_equity - buffer
            if not math.isfinite(investable) or investable <= 0:
                raise NdxDynamicWholeLotRepairPathError(
                    f"rebalance {item['sequence']}: no capital above cash buffer"
                )
            desired: dict[str, int] = {}
            for security_id in sorted(target_ids):
                raw_target = (
                    investable
                    * float(targets[security_id]["target_weight"])
                    / marks[security_id]
                )
                if not math.isfinite(raw_target):
                    raise NdxDynamicWholeLotRepairPathError(
                        f"rebalance {item['sequence']}: target share coordinate overflowed"
                    )
                desired[security_id] = int(math.floor(raw_target))

            def projected_cash(target_shares: Mapping[str, int]) -> tuple[float, float, float, float]:
                buy_notional = sell_notional = 0.0
                for security_id in sorted(current_ids | target_ids):
                    before = int(holdings.get(security_id, {}).get("shares", 0))
                    after = int(target_shares.get(security_id, 0))
                    difference = after - before
                    if difference > 0:
                        buy_notional += difference * marks[security_id]
                    elif difference < 0:
                        sell_notional += -difference * marks[security_id]
                fees = (buy_notional + sell_notional) * fee_rate
                return cash_before + sell_notional - buy_notional - fees, buy_notional, sell_notional, fees

            trigger_reasons: list[str] = []
            if any(value < 1 for value in desired.values()):
                trigger_reasons.append("ZERO_TARGET_SHARE")
            else:
                after_cash, buy_notional, sell_notional, fees = projected_cash(desired)
                while after_cash < buffer - _TOLERANCE:
                    reducible = [security_id for security_id, value in desired.items() if value > 1]
                    if not reducible:
                        trigger_reasons.append("CASH_BUFFER")
                        break
                    security_id = max(
                        reducible,
                        key=lambda candidate: (marks[candidate], candidate),
                    )
                    desired[security_id] -= 1
                    after_cash, buy_notional, sell_notional, fees = projected_cash(desired)
                if not trigger_reasons:
                    snapshot = _risk_snapshot(
                        desired,
                        {security_id: marks[security_id] for security_id in target_ids},
                        {security_id: decision_chains[security_id] for security_id in target_ids},
                        max_single_weight=contract["max_single_weight"],
                        min_single_weight=contract["min_single_weight"],
                        top_weight_cap=contract["top_weight_cap"],
                        minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
                        risk_chain_top1_cap=contract["risk_chain_top1_cap"],
                    )
                    trigger_reasons.extend(
                        sorted(key for key, passed in snapshot["checks"].items() if not passed)
                    )

            if trigger_reasons:
                removed_sell = sum(
                    int(holdings[security_id]["shares"]) * marks[security_id]
                    for security_id in removed_ids
                )
                removed_fee = removed_sell * fee_rate
                projection_cash = cash_before + removed_sell - removed_fee
                try:
                    projection = project_whole_lot_rebalance(
                        current_shares={
                            security_id: int(holdings.get(security_id, {}).get("shares", 0))
                            for security_id in sorted(target_ids)
                        },
                        current_cash_usd=projection_cash,
                        prices={security_id: marks[security_id] for security_id in sorted(target_ids)},
                        target_weights={
                            security_id: float(targets[security_id]["target_weight"])
                            for security_id in sorted(target_ids)
                        },
                        risk_chain_by_ticker={
                            security_id: decision_chains[security_id]
                            for security_id in sorted(target_ids)
                        },
                        minimum_cash_buffer_usd=buffer,
                        transaction_cost_bps=contract["transaction_cost_bps"],
                        max_single_weight=contract["max_single_weight"],
                        min_single_weight=contract["min_single_weight"],
                        top_weight_cap=contract["top_weight_cap"],
                        minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
                        risk_chain_top1_cap=contract["risk_chain_top1_cap"],
                        max_evaluations=contract["max_repair_evaluations"],
                    )
                except NdxWholeLotRepairDiagnosticError as exc:
                    raise NdxDynamicWholeLotRepairPathError(str(exc)) from exc
                event = {
                    "rebalance_sequence": int(item["sequence"]),
                    "decision_date": item["decision_date"].date().isoformat(),
                    "execution_date": date.date().isoformat(),
                    "trigger_reasons": _json(trigger_reasons),
                    "projection_status": projection["status"],
                    "search_complete": bool(projection["search_complete"]),
                    "search_space_size": int(projection["search_space_size"]),
                    "evaluations_completed": int(projection["evaluations_completed"]),
                    "removed_sell_notional_usd": removed_sell,
                    "removed_transaction_cost_usd": removed_fee,
                }
                repair_events.append(event)
                if not projection["search_complete"] or not projection["feasible_projection_found"]:
                    status = (
                        "RESEARCH_SEARCH_BUDGET_EXHAUSTED"
                        if not projection["search_complete"]
                        else "NO_FEASIBLE_PROJECTION_IN_COMPLETE_FLOOR_CEIL_NEIGHBORHOOD"
                    )
                    return _result(
                        status=status,
                        search_complete=bool(projection["search_complete"]),
                        path_complete=False,
                        legacy_exact_reuse=False,
                        summary=None,
                        rebalances=None,
                        trades=None,
                        path=None,
                        repair_events=pd.DataFrame(repair_events, columns=_REPAIR_EVENT_COLUMNS),
                        daily_risk=None,
                    )
                desired = {
                    security_id: int(value)
                    for security_id, value in projection["projected_shares"].items()
                }
                after_cash = float(projection["posttrade_cash_usd"])
                buy_notional = float(projection["buy_notional_usd"])
                sell_notional = removed_sell + float(projection["sell_notional_usd"])
                fees = removed_fee + float(projection["transaction_cost_usd"])
            else:
                after_cash, buy_notional, sell_notional, fees = projected_cash(desired)

            for security_id in renamed_ids:
                trades.append({
                    "rebalance_sequence": int(item["sequence"]),
                    "decision_date": item["decision_date"].date().isoformat(),
                    "execution_date": date.date().isoformat(),
                    "security_id": security_id,
                    "event_type": "RENAME_NO_TRADE",
                    "action": "NONE",
                    "before_ticker": holdings[security_id]["ticker"],
                    "after_ticker": targets[security_id]["ticker"],
                    "trade_ticker": "",
                    "shares_before": int(holdings[security_id]["shares"]),
                    "shares_after": int(holdings[security_id]["shares"]),
                    "share_delta": 0,
                    "price_usd": marks[security_id],
                    "notional_usd": 0.0,
                    "transaction_cost_usd": 0.0,
                })
            for security_id in sorted(current_ids | target_ids):
                before = int(holdings.get(security_id, {}).get("shares", 0))
                after = int(desired.get(security_id, 0))
                delta = after - before
                if delta == 0:
                    continue
                ticker = (
                    targets[security_id]["ticker"]
                    if security_id in target_ids
                    else holdings[security_id]["ticker"]
                )
                notional = abs(delta) * marks[security_id]
                trades.append({
                    "rebalance_sequence": int(item["sequence"]),
                    "decision_date": item["decision_date"].date().isoformat(),
                    "execution_date": date.date().isoformat(),
                    "security_id": security_id,
                    "event_type": "ECONOMIC_TRADE",
                    "action": "BUY" if delta > 0 else "SELL",
                    "before_ticker": str(holdings.get(security_id, {}).get("ticker", "")),
                    "after_ticker": str(targets.get(security_id, {}).get("ticker", "")),
                    "trade_ticker": ticker,
                    "shares_before": before,
                    "shares_after": after,
                    "share_delta": delta,
                    "price_usd": marks[security_id],
                    "notional_usd": notional,
                    "transaction_cost_usd": notional * fee_rate,
                })
            new_holdings = {
                security_id: {
                    "ticker": targets[security_id]["ticker"],
                    "issuer_id": targets[security_id]["issuer_id"],
                    "shares": int(desired[security_id]),
                }
                for security_id in sorted(target_ids)
            }
            posttrade_equity = after_cash + sum(
                int(new_holdings[security_id]["shares"]) * marks[security_id]
                for security_id in new_holdings
            )
            cash_error = abs(
                after_cash - (cash_before + sell_notional - buy_notional - fees)
            )
            accounting_error = abs(posttrade_equity - (pretrade_equity - fees))
            cash_tolerance = legacy._amount_tolerance(
                after_cash, cash_before, buy_notional, sell_notional, fees
            )
            accounting_tolerance = legacy._amount_tolerance(
                posttrade_equity, pretrade_equity, fees
            )
            if cash_error > cash_tolerance or accounting_error > accounting_tolerance:
                raise NdxDynamicWholeLotRepairPathError(
                    f"rebalance {item['sequence']}: self-financing accounting invariant failed"
                )
            cash = after_cash
            holdings = new_holdings
            minimum_cash = min(minimum_cash, cash)
            total_buy += buy_notional
            total_sell += sell_notional
            total_fees += fees
            maximum_cash_error = max(maximum_cash_error, cash_error)
            maximum_accounting_error = max(maximum_accounting_error, accounting_error)
            rebalances.append({
                "rebalance_sequence": int(item["sequence"]),
                "decision_date": item["decision_date"].date().isoformat(),
                "execution_date": date.date().isoformat(),
                "target_k": len(target_ids),
                "pretrade_k": len(current_ids),
                "posttrade_k": len(holdings),
                "added_security_ids": _json(added_ids),
                "removed_security_ids": _json(removed_ids),
                "continued_security_ids": _json(continued_ids),
                "renamed_security_ids": _json(renamed_ids),
                "target_weights": _json({
                    security_id: targets[security_id]["target_weight"]
                    for security_id in sorted(target_ids)
                }),
                "holdings": _json(holdings),
                "cash_before_usd": cash_before,
                "cash_after_usd": cash,
                "pretrade_equity_usd": pretrade_equity,
                "posttrade_equity_usd": posttrade_equity,
                "buy_notional_usd": buy_notional,
                "sell_notional_usd": sell_notional,
                "transaction_cost_usd": fees,
                "cash_conservation_error_usd": cash_error,
                "accounting_error_usd": accounting_error,
            })

        try:
            daily_marks = {
                security_id: legacy._price_at(path_prices, date, holding["ticker"])
                for security_id, holding in holdings.items()
            }
        except legacy.NdxDynamicWholeLotPathError as exc:
            raise NdxDynamicWholeLotRepairPathError(str(exc)) from exc
        holdings_value = sum(
            int(holdings[security_id]["shares"]) * daily_marks[security_id]
            for security_id in holdings
        )
        path_rows.append({
            "date": date.date().isoformat(),
            "cash_usd": cash,
            "holdings_value_usd": holdings_value,
            "total_value_usd": cash + holdings_value,
            "holding_count": len(holdings),
            "active_security_ids": _json(sorted(holdings)),
            "active_tickers": _json(sorted(holding["ticker"] for holding in holdings.values())),
            "holdings": _json(holdings),
        })

    rebalance_frame = pd.DataFrame(rebalances)
    trade_frame = pd.DataFrame(trades)
    path_frame = pd.DataFrame(path_rows)
    trace_payload = {
        "rebalances": rebalance_frame.to_dict("records"),
        "trades": trade_frame.to_dict("records"),
        "path": path_frame.to_dict("records"),
    }
    trace_hash = hashlib.sha256(_json(trace_payload).encode("utf-8")).hexdigest()
    terminal_value = float(path_frame.iloc[-1]["total_value_usd"])
    path_values = path_frame["total_value_usd"].astype(float)
    path_nav = pd.concat(
        [
            pd.Series([1.0]),
            (path_values / contract["initial_cash_usd"]).reset_index(drop=True),
        ],
        ignore_index=True,
    )
    elapsed_sessions = max(1, len(path_frame))
    k_path = [int(item["target_k"]) for item in rebalances]
    summary = {
        "portfolio_track": "portfolio_optimization",
        "migration_control_assumption_used": False,
        "dynamic_cardinality_enabled": True,
        "security_identity_key": "security_id",
        "issuer_identity_trace_available": all(
            bool(target.get("issuer_id"))
            for item in items
            for target in item["targets"].values()
        ),
        "ticker_rename_execution": "ZERO_TRADE_ZERO_FEE_IDENTITY_CONTINUATION",
        "dynamic_whole_lot_execution_mode": (
            "SECURITY_ID_CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_"
            + (
                "SEPARATE_EXECUTION_AND_VALUATION_PRICES"
                if execution_prices is not None
                else "REAL_CLOSES"
            )
        ),
        "separate_execution_price_channel": execution_prices is not None,
        "separate_execution_price_required": bool(require_separate_execution_prices),
        "next_session_execution_required": bool(require_next_session_execution),
        "issuer_trace_required": bool(require_issuer_trace),
        "valuation_start_date": first_execution.date().isoformat(),
        "valuation_end_date": end_date.date().isoformat(),
        "maximum_price_date_used": path_prices.index.max().date().isoformat(),
        "future_prices_after_cutoff_ignored": True,
        "transaction_cost_bps": contract["transaction_cost_bps"],
        "transaction_cost_sides": "BUY_AND_SELL",
        "rebalance_count": len(rebalances),
        "k_path": k_path,
        "minimum_target_k": min(k_path),
        "maximum_target_k": max(k_path),
        "total_buy_notional_usd": total_buy,
        "total_sell_notional_usd": total_sell,
        "total_transaction_cost_usd": total_fees,
        "minimum_cash_usd": minimum_cash,
        "cash_buffer_preserved": minimum_cash >= buffer - _TOLERANCE,
        "cash_conservation_max_error_usd": maximum_cash_error,
        "cash_conservation_passed": True,
        "accounting_max_error_usd": maximum_accounting_error,
        "accounting_invariant_passed": True,
        "whole_share_invariant_passed": all(
            isinstance(holding["shares"], int) and holding["shares"] >= 1
            for holding in holdings.values()
        ),
        "terminal_cash_usd": cash,
        "terminal_value_usd": terminal_value,
        "path_return_net": terminal_value / contract["initial_cash_usd"] - 1.0,
        "path_annualized_return_net": (
            (terminal_value / contract["initial_cash_usd"])
            ** (252.0 / elapsed_sessions)
            - 1.0
        ),
        "path_max_drawdown": float((1.0 - path_nav / path_nav.cummax()).max()),
        "path_trading_session_count": len(path_frame),
        "dynamic_whole_lot_trace_sha256": trace_hash,
        "promotion_allowed": False,
    }
    daily_risk = _daily_risk_audit(
        path_frame,
        frame,
        chains_by_execution_date=chains_by_execution_date,
        contract=contract,
    )
    return _result(
        status="COMPLETE_WITH_CONDITIONAL_REPAIR",
        search_complete=True,
        path_complete=True,
        legacy_exact_reuse=False,
        summary=summary,
        rebalances=rebalance_frame,
        trades=trade_frame,
        path=path_frame,
        repair_events=pd.DataFrame(repair_events, columns=_REPAIR_EVENT_COLUMNS),
        daily_risk=daily_risk,
    )


__all__ = [
    "NdxDynamicWholeLotRepairPathError",
    "simulate_dynamic_security_id_conditional_repair_path",
]
