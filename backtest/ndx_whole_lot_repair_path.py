"""Research-only continuous whole-lot path with conditional local repair.

The frozen legacy path remains unchanged.  At each existing rebalance date this
module first computes that path's floor allocation and fee-only cash repair.  A
floor/ceil projection is consulted only when the resulting holdings fail the
unchanged five daily risk constraints.  Tickers, target weights, prices,
capital, thresholds, and schedule are never searched or changed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from backtest.ndx_whole_lot_rebalance import (
    NdxWholeLotRebalanceError,
    simulate_continuous_whole_lot_rebalance,
)
from backtest.ndx_whole_lot_repair_diagnostic import project_whole_lot_rebalance


class NdxWholeLotRepairPathError(ValueError):
    """Raised when the conditional repair path contract is invalid."""


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise NdxWholeLotRepairPathError(f"{field} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxWholeLotRepairPathError(f"{field} must be finite numeric") from exc
    if not math.isfinite(result):
        raise NdxWholeLotRepairPathError(f"{field} must be finite numeric")
    return result


def _strict_session_date(value: Any, field: str) -> pd.Timestamp:
    if isinstance(value, str) and _ISO_DATE.fullmatch(value) is None:
        raise NdxWholeLotRepairPathError(f"{field} must be an exact YYYY-MM-DD date")
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxWholeLotRepairPathError(f"{field} is not a session date") from exc
    if (
        pd.isna(result)
        or result.tz is not None
        or result != result.normalize()
    ):
        raise NdxWholeLotRepairPathError(
            f"{field} must be a timezone-naive midnight session date"
        )
    return result


def _risk_snapshot(
    notionals: Mapping[str, float],
    *,
    risk_chain_by_ticker: Mapping[str, str],
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict[str, Any]:
    invested = float(sum(notionals.values()))
    if invested <= 0:
        return {
            "top1": 1.0,
            "top3": 1.0,
            "minimum_single_weight": 0.0,
            "effective_n": 0.0,
            "risk_chain_top1": 1.0,
            "constraints_passed": False,
            "failure_reasons": ["ZERO_INVESTED_NOTIONAL"],
        }
    weights = {ticker: value / invested for ticker, value in notionals.items()}
    ordered = sorted(weights.values(), reverse=True)
    chain_weights: dict[str, float] = {}
    for ticker, weight in weights.items():
        chain = risk_chain_by_ticker[ticker]
        chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
    effective_n = 1.0 / sum(value * value for value in ordered)
    checks = {
        "MAX_SINGLE_WEIGHT": ordered[0] <= max_single_weight + 1e-9,
        "MIN_SINGLE_WEIGHT": ordered[-1] >= min_single_weight - 1e-9,
        "SECURITY_TOP3_WEIGHT": sum(ordered[:3]) <= top_weight_cap + 1e-9,
        "MINIMUM_EFFECTIVE_N": effective_n
        >= minimum_effective_n_ratio * len(weights) - 1e-9,
        "RISK_CHAIN_TOP1_WEIGHT": max(chain_weights.values())
        <= risk_chain_top1_cap + 1e-9,
    }
    return {
        "top1": ordered[0],
        "top3": sum(ordered[:3]),
        "minimum_single_weight": ordered[-1],
        "effective_n": effective_n,
        "risk_chain_top1": max(chain_weights.values()),
        "constraints_passed": all(checks.values()),
        "failure_reasons": [name for name, passed in checks.items() if not passed],
    }


def _daily_risk_audit(
    prices: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    tickers: list[str],
    risk_chain_by_ticker: Mapping[str, str],
    portfolio_cash_usd: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict[str, Any]:
    by_day = {
        pd.Timestamp(row["rebalance_date"]).normalize(): row
        for row in ledger.to_dict("records")
    }
    shares = {ticker: 0 for ticker in tickers}
    cash = portfolio_cash_usd
    values: list[float] = []
    failures: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    zero_share_count = 0
    for raw_date, row in prices.iterrows():
        date = pd.Timestamp(raw_date).normalize()
        if date in by_day:
            record = by_day[date]
            parsed: dict[str, int] = {}
            for part in str(record["shares"]).split(";"):
                ticker, raw_quantity = part.split(":", 1)
                parsed[ticker] = int(raw_quantity)
            if sorted(parsed) != tickers:
                raise NdxWholeLotRepairPathError("rebalance ledger shares changed")
            shares = parsed
            cash = _finite(record["posttrade_cash_usd"], "posttrade cash")
        marks = {ticker: float(row[ticker]) for ticker in tickers}
        notionals = {ticker: shares[ticker] * marks[ticker] for ticker in tickers}
        snapshot = _risk_snapshot(
            notionals,
            risk_chain_by_ticker=risk_chain_by_ticker,
            max_single_weight=max_single_weight,
            min_single_weight=min_single_weight,
            top_weight_cap=top_weight_cap,
            minimum_effective_n_ratio=minimum_effective_n_ratio,
            risk_chain_top1_cap=risk_chain_top1_cap,
        )
        reasons = list(snapshot["failure_reasons"])
        if any(quantity == 0 for quantity in shares.values()):
            reasons.append("ZERO_SHARE")
            zero_share_count += 1
        if cash < 0:
            reasons.append("NEGATIVE_CASH")
        if reasons:
            reason_counts.update(reasons)
            failures.append(
                {
                    "session_date": date.date().isoformat(),
                    "failure_reasons": reasons,
                    "top1_weight": snapshot["top1"],
                    "minimum_single_weight": snapshot["minimum_single_weight"],
                    "top3_weight": snapshot["top3"],
                    "effective_n": snapshot["effective_n"],
                    "risk_chain_top1_weight": snapshot["risk_chain_top1"],
                    "cash_usd": cash,
                }
            )
        values.append(cash + sum(notionals.values()))
    series = pd.Series(values, index=prices.index, dtype=float)
    corrected = pd.Series([portfolio_cash_usd, *values], dtype=float)
    return {
        "session_count": len(series),
        "failure_session_count": len(failures),
        "failure_reason_counts": dict(sorted(reason_counts.items())),
        "failure_sessions": failures,
        "zero_share_session_count": zero_share_count,
        "legacy_drawdown_without_initial_capital_peak": float(
            (1.0 - series / series.cummax()).max()
        ),
        "corrected_drawdown_with_initial_capital_peak": float(
            (1.0 - corrected / corrected.cummax()).max()
        ),
        "first_session_value_after_trade_and_fees_usd": float(series.iloc[0]),
        "terminal_value_usd": float(series.iloc[-1]),
    }


def _result_boundary() -> dict[str, Any]:
    return {
        "research_only": True,
        "research_track": "portfolio_optimization_execution_diagnostic",
        "mechanism": "CONDITIONAL_FLOOR_CEIL_REPAIR_ON_EXISTING_REBALANCE_DATES",
        "candidate_set_changed": False,
        "target_weights_changed": False,
        "rebalance_cadence_changed": False,
        "risk_thresholds_changed": False,
        "portfolio_cash_changed": False,
        "transaction_cost_changed": False,
        "issuer_uniqueness_checked": False,
        "portfolio_optimality_claimed": False,
        "full_integer_space_infeasibility_claimed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def simulate_conditional_whole_lot_repair_path(
    prices: pd.DataFrame,
    schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    *,
    risk_chain_by_ticker: Mapping[str, str],
    portfolio_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
    max_repair_evaluations: int = 262_144,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Replay the fixed schedule, repairing only failed legacy rebalance actions."""

    items = [
        (_strict_session_date(date, "rebalance date"), dict(weights))
        for date, weights in schedule
    ]
    contract = {
        "portfolio_cash_usd": _finite(portfolio_cash_usd, "portfolio_cash_usd"),
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
    }
    if (
        contract["portfolio_cash_usd"] <= 0
        or not 0
        <= contract["minimum_cash_buffer_usd"]
        < contract["portfolio_cash_usd"]
        or contract["transaction_cost_bps"] < 0
        or not 0
        <= contract["min_single_weight"]
        <= contract["max_single_weight"]
        <= 1
        or not 0 <= contract["top_weight_cap"] <= 1
        or not 0 <= contract["minimum_effective_n_ratio"] <= 1
        or not 0 <= contract["risk_chain_top1_cap"] <= 1
    ):
        raise NdxWholeLotRepairPathError("continuous repair contract is invalid")
    if (
        isinstance(max_repair_evaluations, bool)
        or not isinstance(max_repair_evaluations, int)
        or max_repair_evaluations <= 0
    ):
        raise NdxWholeLotRepairPathError(
            "max_repair_evaluations must be a positive integer"
        )
    if not items:
        raise NdxWholeLotRepairPathError("rebalance schedule must be nonempty")
    schedule_dates = [date for date, _ in items]
    if (
        schedule_dates != sorted(schedule_dates)
        or len(set(schedule_dates)) != len(schedule_dates)
    ):
        raise NdxWholeLotRepairPathError(
            "rebalance session dates must be unique and ascending"
        )
    tickers = sorted(items[0][1])
    if (
        not tickers
        or any(
            not isinstance(ticker, str)
            or not ticker
            or ticker != ticker.strip()
            for ticker in tickers
        )
        or any(sorted(weights) != tickers for _, weights in items)
    ):
        raise NdxWholeLotRepairPathError("rebalance ticker set changed")
    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.hasnans
        or prices.index.tz is not None
        or prices.index.has_duplicates
        or not prices.index.is_monotonic_increasing
        or any(date != date.normalize() for date in prices.index)
        or prices.columns.has_duplicates
        or any(
            not isinstance(column, str)
            or not column
            or column != column.strip()
            for column in prices.columns
        )
    ):
        raise NdxWholeLotRepairPathError(
            "price coordinates must be unique ascending naive session dates and columns"
        )
    if set(risk_chain_by_ticker) != set(tickers) or any(
        not isinstance(risk_chain_by_ticker[ticker], str)
        or not risk_chain_by_ticker[ticker]
        or risk_chain_by_ticker[ticker] != risk_chain_by_ticker[ticker].strip()
        for ticker in tickers
    ):
        raise NdxWholeLotRepairPathError("risk-chain evidence is invalid")
    normalized_items = []
    for date, weights in items:
        values = {ticker: _finite(weights[ticker], f"weight[{ticker}]") for ticker in tickers}
        if any(value <= 0 for value in values.values()):
            raise NdxWholeLotRepairPathError("target weights must be positive")
        total = sum(values.values())
        if (
            not math.isfinite(total)
            or not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-8)
        ):
            raise NdxWholeLotRepairPathError("target weights must sum to one")
        normalized_items.append(
            (date, {ticker: values[ticker] / total for ticker in tickers})
        )

    try:
        legacy_summary, legacy_ledger = simulate_continuous_whole_lot_rebalance(
            prices,
            items,
            risk_chain_by_ticker=risk_chain_by_ticker,
            **contract,
        )
    except NdxWholeLotRebalanceError as exc:
        raise NdxWholeLotRepairPathError(str(exc)) from exc
    path = prices.loc[items[0][0]:, tickers].copy()
    if bool(legacy_ledger["constraints_passed"].all()):
        audit = _daily_risk_audit(
            path,
            legacy_ledger,
            tickers=tickers,
            risk_chain_by_ticker=risk_chain_by_ticker,
            portfolio_cash_usd=contract["portfolio_cash_usd"],
            max_single_weight=contract["max_single_weight"],
            min_single_weight=contract["min_single_weight"],
            top_weight_cap=contract["top_weight_cap"],
            minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
            risk_chain_top1_cap=contract["risk_chain_top1_cap"],
        )
        status = (
            "COMPLETE_RISK_CONSTRAINTS_PRESERVED"
            if audit["failure_session_count"] == 0
            else "COMPLETE_WITH_DAILY_MARK_TO_MARKET_RISK_FAILURES"
        )
        return (
            {
                **_result_boundary(),
                "status": status,
                "search_complete": True,
                "summary": legacy_summary,
                "daily_risk_audit": audit,
                "repair_events": [],
                "repair_invocation_count": 0,
                "successful_repair_count": 0,
                "unresolved_rebalance_count": 0,
                "execution_eligible": audit["failure_session_count"] == 0,
                "legacy_no_trigger_path_reused_exactly": True,
            },
            legacy_ledger,
        )

    cash = contract["portfolio_cash_usd"]
    buffer = contract["minimum_cash_buffer_usd"]
    fee_rate = contract["transaction_cost_bps"] / 10_000.0
    shares = {ticker: 0 for ticker in tickers}
    schedule_by_date = dict(normalized_items)
    ledger_rows: list[dict[str, Any]] = []
    repair_events: list[dict[str, Any]] = []
    values: list[float] = []
    minimum_cash = cash
    total_cost = 0.0
    total_trade_notional = 0.0
    share_change_count = 0
    initial_shares = ""
    successful_repairs = 0
    unresolved = 0
    constraints_all_days = True
    for date, row in path.iterrows():
        marks = {ticker: float(row[ticker]) for ticker in tickers}
        if date in schedule_by_date:
            weights = schedule_by_date[date]
            previous_shares = dict(shares)
            previous_cash = cash
            pretrade_equity = cash + sum(
                shares[ticker] * marks[ticker] for ticker in tickers
            )
            investable = max(0.0, pretrade_equity - buffer)
            desired = {
                ticker: int(
                    math.floor(investable * weights[ticker] / marks[ticker])
                )
                for ticker in tickers
            }

            def projected_cash(target: Mapping[str, int]) -> tuple[float, float, float]:
                buy = sum(
                    max(0, target[ticker] - previous_shares[ticker]) * marks[ticker]
                    for ticker in tickers
                )
                sell = sum(
                    max(0, previous_shares[ticker] - target[ticker]) * marks[ticker]
                    for ticker in tickers
                )
                fees = (buy + sell) * fee_rate
                return previous_cash + sell - buy - fees, buy + sell, fees

            after_cash, traded, fees = projected_cash(desired)
            while after_cash < buffer - 1e-9:
                reducible = [
                    ticker
                    for ticker in tickers
                    if desired[ticker] > previous_shares[ticker]
                ]
                if not reducible:
                    raise NdxWholeLotRepairPathError(
                        "transaction costs breach cash buffer"
                    )
                reduce_ticker = max(
                    reducible, key=lambda name: (marks[name], name)
                )
                desired[reduce_ticker] -= 1
                after_cash, traded, fees = projected_cash(desired)
            legacy_notionals = {
                ticker: desired[ticker] * marks[ticker] for ticker in tickers
            }
            legacy_snapshot = _risk_snapshot(
                legacy_notionals,
                risk_chain_by_ticker=risk_chain_by_ticker,
                max_single_weight=contract["max_single_weight"],
                min_single_weight=contract["min_single_weight"],
                top_weight_cap=contract["top_weight_cap"],
                minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
                risk_chain_top1_cap=contract["risk_chain_top1_cap"],
            )
            action = "LEGACY_FLOOR_ACTION_RETAINED"
            projection_status = "NOT_INVOKED_LEGACY_ACTION_PASSED"
            if not legacy_snapshot["constraints_passed"]:
                projection = project_whole_lot_rebalance(
                    current_shares=previous_shares,
                    current_cash_usd=previous_cash,
                    prices=marks,
                    target_weights=weights,
                    risk_chain_by_ticker=risk_chain_by_ticker,
                    minimum_cash_buffer_usd=buffer,
                    transaction_cost_bps=contract["transaction_cost_bps"],
                    max_single_weight=contract["max_single_weight"],
                    min_single_weight=contract["min_single_weight"],
                    top_weight_cap=contract["top_weight_cap"],
                    minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
                    risk_chain_top1_cap=contract["risk_chain_top1_cap"],
                    max_evaluations=max_repair_evaluations,
                )
                projection_status = projection["status"]
                event = {
                    "rebalance_date": date.date().isoformat(),
                    "legacy_failure_reasons": list(
                        legacy_snapshot["failure_reasons"]
                    ),
                    "legacy_candidate_shares": dict(desired),
                    "legacy_candidate_posttrade_cash_usd": after_cash,
                    "projection_status": projection_status,
                    "search_complete": projection["search_complete"],
                    "search_space_size": projection["search_space_size"],
                    "evaluations_completed": projection["evaluations_completed"],
                    "full_integer_space_infeasibility_claimed": False,
                }
                if projection_status == "RESEARCH_SEARCH_BUDGET_EXHAUSTED":
                    event["action"] = "NO_ACTION_PATH_INCOMPLETE"
                    repair_events.append(event)
                    return (
                        {
                            **_result_boundary(),
                            "status": "INCOMPLETE_REPAIR_SEARCH_BUDGET_EXHAUSTED",
                            "search_complete": False,
                            "summary": None,
                            "daily_risk_audit": None,
                            "repair_events": repair_events,
                            "repair_invocation_count": len(repair_events),
                            "successful_repair_count": successful_repairs,
                            "unresolved_rebalance_count": unresolved,
                            "execution_eligible": False,
                            "legacy_no_trigger_path_reused_exactly": False,
                            "stopped_before_rebalance_date": date.date().isoformat(),
                        },
                        pd.DataFrame(ledger_rows),
                    )
                if projection["feasible_projection_found"]:
                    desired = dict(projection["projected_shares"])
                    after_cash = projection["posttrade_cash_usd"]
                    traded = projection["traded_notional_usd"]
                    fees = projection["transaction_cost_usd"]
                    action = "FLOOR_CEIL_REPAIR_APPLIED"
                    successful_repairs += 1
                    event["projected_shares"] = dict(desired)
                    event["projected_posttrade_cash_usd"] = after_cash
                else:
                    action = "LEGACY_FAILED_ACTION_RETAINED_UNRESOLVED"
                    unresolved += 1
                event["action"] = action
                repair_events.append(event)
            changes = sum(
                desired[ticker] != previous_shares[ticker] for ticker in tickers
            )
            share_change_count += changes
            shares = desired
            cash = after_cash
            total_trade_notional += traded
            total_cost += fees
            notionals = {
                ticker: shares[ticker] * marks[ticker] for ticker in tickers
            }
            snapshot = _risk_snapshot(
                notionals,
                risk_chain_by_ticker=risk_chain_by_ticker,
                max_single_weight=contract["max_single_weight"],
                min_single_weight=contract["min_single_weight"],
                top_weight_cap=contract["top_weight_cap"],
                minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
                risk_chain_top1_cap=contract["risk_chain_top1_cap"],
            )
            if not initial_shares:
                initial_shares = ";".join(
                    f"{ticker}:{shares[ticker]}" for ticker in tickers
                )
            ledger_rows.append(
                {
                    "rebalance_date": date.date().isoformat(),
                    "pretrade_equity_usd": pretrade_equity,
                    "posttrade_cash_usd": cash,
                    "traded_notional_usd": traded,
                    "transaction_cost_usd": fees,
                    "changed_ticker_count": changes,
                    "shares": ";".join(
                        f"{ticker}:{shares[ticker]}" for ticker in tickers
                    ),
                    "top1": snapshot["top1"],
                    "top3": snapshot["top3"],
                    "effective_n": snapshot["effective_n"],
                    "risk_chain_top1": snapshot["risk_chain_top1"],
                    "constraints_passed": snapshot["constraints_passed"],
                }
            )
        notionals = {ticker: shares[ticker] * marks[ticker] for ticker in tickers}
        snapshot = _risk_snapshot(
            notionals,
            risk_chain_by_ticker=risk_chain_by_ticker,
            max_single_weight=contract["max_single_weight"],
            min_single_weight=contract["min_single_weight"],
            top_weight_cap=contract["top_weight_cap"],
            minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
            risk_chain_top1_cap=contract["risk_chain_top1_cap"],
        )
        constraints_all_days &= bool(snapshot["constraints_passed"])
        minimum_cash = min(minimum_cash, cash)
        values.append(cash + sum(notionals.values()))

    ledger = pd.DataFrame(ledger_rows)
    records = ledger.to_dict("records")
    trace_hash = hashlib.sha256(
        json.dumps(
            records, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    values_series = pd.Series(values, index=path.index, dtype=float)
    summary = {
        "whole_lot_rebalance_count": len(ledger),
        "whole_lot_initial_shares": initial_shares,
        "whole_lot_terminal_shares": ";".join(
            f"{ticker}:{shares[ticker]}" for ticker in tickers
        ),
        "whole_lot_share_change_count": share_change_count,
        "whole_lot_total_trade_notional_usd": total_trade_notional,
        "whole_lot_total_transaction_cost_usd": total_cost,
        "whole_lot_min_cash_usd": minimum_cash,
        "whole_lot_cash_buffer_preserved": minimum_cash >= buffer - 1e-9,
        "whole_lot_constraints_preserved_all_days": constraints_all_days,
        "whole_lot_terminal_value_usd": float(values_series.iloc[-1]),
        "whole_lot_path_return_net": float(
            values_series.iloc[-1] / contract["portfolio_cash_usd"] - 1.0
        ),
        "whole_lot_path_max_drawdown": float(
            (1.0 - values_series / values_series.cummax()).max()
        ),
        "whole_lot_rebalance_trace_sha256": trace_hash,
        "whole_lot_execution_mode": (
            "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES_"
            "WITH_CONDITIONAL_FLOOR_CEIL_REPAIR"
        ),
    }
    audit = _daily_risk_audit(
        path,
        ledger,
        tickers=tickers,
        risk_chain_by_ticker=risk_chain_by_ticker,
        portfolio_cash_usd=contract["portfolio_cash_usd"],
        max_single_weight=contract["max_single_weight"],
        min_single_weight=contract["min_single_weight"],
        top_weight_cap=contract["top_weight_cap"],
        minimum_effective_n_ratio=contract["minimum_effective_n_ratio"],
        risk_chain_top1_cap=contract["risk_chain_top1_cap"],
    )
    if unresolved:
        status = "COMPLETE_WITH_UNRESOLVED_REBALANCE_FAILURES"
    elif audit["failure_session_count"]:
        status = "COMPLETE_WITH_DAILY_MARK_TO_MARKET_RISK_FAILURES"
    else:
        status = "COMPLETE_RISK_CONSTRAINTS_PRESERVED"
    return (
        {
            **_result_boundary(),
            "status": status,
            "search_complete": True,
            "summary": summary,
            "daily_risk_audit": audit,
            "repair_events": repair_events,
            "repair_invocation_count": len(repair_events),
            "successful_repair_count": successful_repairs,
            "unresolved_rebalance_count": unresolved,
            "execution_eligible": audit["failure_session_count"] == 0
            and unresolved == 0,
            "legacy_no_trigger_path_reused_exactly": False,
        },
        ledger,
    )


__all__ = [
    "NdxWholeLotRepairPathError",
    "simulate_conditional_whole_lot_repair_path",
]
