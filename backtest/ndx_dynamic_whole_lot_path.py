"""Dynamic-cardinality, security-identity whole-lot portfolio path engine.

This module is deliberately independent from the fixed-composition whole-lot
engine.  It models the ``portfolio_optimization`` research track: target
cardinality, security composition, ticker labels, and weights may all change at
each rebalance while cash and integer shares remain continuous.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


class NdxDynamicWholeLotPathError(ValueError):
    """Raised when the dynamic execution contract cannot be proved valid."""


_TOLERANCE = 1e-8


def _amount_tolerance(*values: float) -> float:
    """Scale the audit tolerance without masking economically material errors."""
    return max(_TOLERANCE, 1e-12 * max([1.0, *(abs(float(value)) for value in values)]))


def _date(value: Any, *, field: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotPathError(f"invalid {field}: {value!r}") from exc
    if pd.isna(result):
        raise NdxDynamicWholeLotPathError(f"invalid {field}: {value!r}")
    if result.tzinfo is not None:
        result = result.tz_convert(None)
    return result.normalize()


def _normalise_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise NdxDynamicWholeLotPathError("prices must be a nonempty DataFrame")
    try:
        index = pd.DatetimeIndex(pd.to_datetime(prices.index, errors="raise"))
    except (TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotPathError("price index contains invalid dates") from exc
    if index.tz is not None:
        index = index.tz_convert(None)
    index = index.normalize()
    if index.has_duplicates:
        raise NdxDynamicWholeLotPathError("price index dates must be unique")
    if not index.is_monotonic_increasing:
        raise NdxDynamicWholeLotPathError("price index must be sorted")
    columns = [str(column).strip().upper() for column in prices.columns]
    if any(not column for column in columns) or len(set(columns)) != len(columns):
        raise NdxDynamicWholeLotPathError("price ticker columns must be nonempty and unique")
    result = prices.copy()
    result.index = index
    result.columns = columns
    return result


def _normalise_targets(raw_targets: Any, *, sequence: int) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_targets, Mapping) or not raw_targets:
        raise NdxDynamicWholeLotPathError(
            f"rebalance {sequence}: targets must be a nonempty security_id mapping"
        )
    result: dict[str, dict[str, Any]] = {}
    seen_tickers: set[str] = set()
    seen_issuers: set[str] = set()
    issuer_trace_mode: bool | None = None
    for raw_security_id, raw_target in raw_targets.items():
        security_id = str(raw_security_id).strip()
        if not security_id or security_id in result:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: target security_id must be nonempty and unique"
            )
        if not isinstance(raw_target, Mapping):
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: invalid target for {security_id}"
            )
        ticker = str(raw_target.get("ticker") or "").strip().upper()
        if not ticker:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: ticker missing for {security_id}"
            )
        if ticker in seen_tickers:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: ticker {ticker} maps to multiple security_ids"
            )
        issuer_id = str(raw_target.get("issuer_id") or "").strip()
        has_issuer = bool(issuer_id)
        if issuer_trace_mode is None:
            issuer_trace_mode = has_issuer
        elif issuer_trace_mode != has_issuer:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: issuer_id trace must be complete or entirely omitted"
            )
        if issuer_id and issuer_id in seen_issuers:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: issuer_id {issuer_id} appears more than once"
            )
        try:
            weight = float(raw_target.get("target_weight"))
        except (TypeError, ValueError) as exc:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: invalid weight for {security_id}"
            ) from exc
        if not math.isfinite(weight) or weight <= 0:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: target weights must be positive finite"
            )
        result[security_id] = {
            "ticker": ticker,
            "issuer_id": issuer_id,
            "target_weight": weight,
        }
        seen_tickers.add(ticker)
        if issuer_id:
            seen_issuers.add(issuer_id)
    total_weight = sum(float(target["target_weight"]) for target in result.values())
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise NdxDynamicWholeLotPathError(
            f"rebalance {sequence}: target weight total must be positive finite"
        )
    for target in result.values():
        target["target_weight"] = float(target["target_weight"]) / total_weight
    return result


def _normalise_schedule(
    schedule: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    try:
        raw_items = list(schedule)
    except TypeError as exc:
        raise NdxDynamicWholeLotPathError("schedule must be iterable") from exc
    if not raw_items:
        raise NdxDynamicWholeLotPathError("rebalance schedule must be nonempty")
    items: list[dict[str, Any]] = []
    for sequence, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, Mapping):
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: schedule item must be a mapping"
            )
        decision_date = _date(raw_item.get("decision_date"), field="decision_date")
        execution_date = _date(raw_item.get("execution_date"), field="execution_date")
        if decision_date >= execution_date:
            raise NdxDynamicWholeLotPathError(
                f"rebalance {sequence}: decision_date must precede execution_date"
            )
        items.append({
            "sequence": sequence,
            "decision_date": decision_date,
            "execution_date": execution_date,
            "targets": _normalise_targets(raw_item.get("targets"), sequence=sequence),
        })
    execution_dates = [item["execution_date"] for item in items]
    if execution_dates != sorted(execution_dates):
        raise NdxDynamicWholeLotPathError("execution dates must be sorted")
    if len(set(execution_dates)) != len(execution_dates):
        raise NdxDynamicWholeLotPathError("execution dates must be unique")
    return items


def _validate_schedule_identity_and_execution_guards(
    items: list[dict[str, Any]],
    *,
    valuation_prices: pd.DataFrame,
    separate_execution_prices_supplied: bool,
    require_separate_execution_prices: bool,
    require_next_session_execution: bool,
    require_issuer_trace: bool,
) -> None:
    if require_separate_execution_prices and not separate_execution_prices_supplied:
        raise NdxDynamicWholeLotPathError(
            "a separate execution price channel is required"
        )
    issuer_by_security: dict[str, str] = {}
    for item in items:
        for security_id, target in item["targets"].items():
            issuer_id = str(target.get("issuer_id") or "")
            if require_issuer_trace and not issuer_id:
                raise NdxDynamicWholeLotPathError("a complete issuer_id trace is required")
            if issuer_id:
                previous = issuer_by_security.setdefault(security_id, issuer_id)
                if previous != issuer_id:
                    raise NdxDynamicWholeLotPathError(
                        f"security_id {security_id} changed issuer_id across periods"
                    )
        if require_next_session_execution:
            later = valuation_prices.index[valuation_prices.index > item["decision_date"]]
            if len(later) == 0 or later[0] != item["execution_date"]:
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: execution is not the first session after decision"
                )


def _price_at(prices: pd.DataFrame, date: pd.Timestamp, ticker: str) -> float:
    if ticker not in prices.columns:
        raise NdxDynamicWholeLotPathError(
            f"required price column missing for {ticker} on {date.date()}"
        )
    try:
        value = float(prices.at[date, ticker])
    except (KeyError, TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotPathError(
            f"required price missing for {ticker} on {date.date()}"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise NdxDynamicWholeLotPathError(
            f"required price must be positive finite for {ticker} on {date.date()}"
        )
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def simulate_dynamic_security_id_whole_lot_path(
    prices: pd.DataFrame,
    schedule: Iterable[Mapping[str, Any]],
    *,
    execution_prices: pd.DataFrame | None = None,
    require_separate_execution_prices: bool = False,
    require_next_session_execution: bool = False,
    require_issuer_trace: bool = False,
    initial_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float = 10.0,
    valuation_end_date: Any,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Simulate a self-financing dynamic portfolio through an explicit cutoff.

    Target holdings are keyed by stable ``security_id``.  A ticker-label change
    for the same identity carries its shares without a sale or purchase.  A
    genuine identity exit and entry are economic sell and buy legs and each is
    charged the configured transaction-cost rate.
    """
    frame = _normalise_prices(prices)
    execution_frame = (
        _normalise_prices(execution_prices) if execution_prices is not None else frame
    )
    items = _normalise_schedule(schedule)
    _validate_schedule_identity_and_execution_guards(
        items,
        valuation_prices=frame,
        separate_execution_prices_supplied=execution_prices is not None,
        require_separate_execution_prices=require_separate_execution_prices,
        require_next_session_execution=require_next_session_execution,
        require_issuer_trace=require_issuer_trace,
    )
    end_date = _date(valuation_end_date, field="valuation_end_date")
    first_execution = items[0]["execution_date"]
    last_execution = items[-1]["execution_date"]
    if end_date < last_execution:
        raise NdxDynamicWholeLotPathError(
            "valuation_end_date must not precede the final execution date"
        )
    if first_execution not in execution_frame.index or last_execution not in execution_frame.index:
        raise NdxDynamicWholeLotPathError("an execution date is absent from prices")
    if end_date not in frame.index:
        raise NdxDynamicWholeLotPathError("valuation_end_date is absent from prices")
    execution_dates = {item["execution_date"] for item in items}
    if not execution_dates.issubset(set(execution_frame.index)):
        raise NdxDynamicWholeLotPathError("an execution date is absent from prices")

    try:
        cash = float(initial_cash_usd)
        buffer = float(minimum_cash_buffer_usd)
        bps = float(transaction_cost_bps)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotPathError("execution cash/cost inputs must be numeric") from exc
    if (
        not math.isfinite(cash)
        or not math.isfinite(buffer)
        or not math.isfinite(bps)
        or cash <= 0
        or buffer < 0
        or buffer >= cash
        or bps < 0
    ):
        raise NdxDynamicWholeLotPathError("dynamic whole-lot execution contract is invalid")
    fee_rate = bps / 10_000.0

    # Slicing before any value validation or lookup is the point-in-time guard:
    # prices after the declared valuation cutoff cannot influence this result.
    path_prices = frame.loc[first_execution:end_date].copy()
    if path_prices.empty:
        raise NdxDynamicWholeLotPathError("no prices inside the valuation interval")

    holdings: dict[str, dict[str, Any]] = {}
    rebalances: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    schedule_by_date = {item["execution_date"]: item for item in items}
    total_buy = 0.0
    total_sell = 0.0
    total_fees = 0.0
    maximum_accounting_error = 0.0
    maximum_cash_error = 0.0
    minimum_cash = cash

    for date in path_prices.index:
        if date in schedule_by_date:
            item = schedule_by_date[date]
            targets = item["targets"]
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

            execution_marks: dict[str, float] = {}
            for security_id in sorted(current_ids | target_ids):
                ticker = (
                    targets[security_id]["ticker"]
                    if security_id in target_ids
                    else holdings[security_id]["ticker"]
                )
                execution_marks[security_id] = _price_at(execution_frame, date, ticker)

            cash_before = cash
            pretrade_equity = cash_before + sum(
                int(holding["shares"]) * execution_marks[security_id]
                for security_id, holding in holdings.items()
            )
            investable = pretrade_equity - buffer
            if investable <= 0:
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: no capital above cash buffer"
                )
            desired = {
                security_id: int(math.floor(
                    investable
                    * float(targets[security_id]["target_weight"])
                    / execution_marks[security_id]
                ))
                for security_id in sorted(target_ids)
            }
            if any(shares < 1 for shares in desired.values()):
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: target is not executable as positive whole lots"
                )

            def projected_cash(target_shares: Mapping[str, int]) -> tuple[float, float, float, float]:
                buy_notional = 0.0
                sell_notional = 0.0
                for security_id in sorted(current_ids | target_ids):
                    before = int(holdings.get(security_id, {}).get("shares", 0))
                    after = int(target_shares.get(security_id, 0))
                    difference = after - before
                    if difference > 0:
                        buy_notional += difference * execution_marks[security_id]
                    elif difference < 0:
                        sell_notional += -difference * execution_marks[security_id]
                fees = (buy_notional + sell_notional) * fee_rate
                after_cash = cash_before + sell_notional - buy_notional - fees
                return after_cash, buy_notional, sell_notional, fees

            after_cash, buy_notional, sell_notional, fees = projected_cash(desired)
            while after_cash < buffer - _TOLERANCE:
                reducible = [security_id for security_id, shares in desired.items() if shares > 1]
                if not reducible:
                    raise NdxDynamicWholeLotPathError(
                        f"rebalance {item['sequence']}: costs breach buffer and positive lots cannot be preserved"
                    )
                security_id = max(
                    reducible,
                    key=lambda candidate: (execution_marks[candidate], candidate),
                )
                desired[security_id] -= 1
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
                    "price_usd": execution_marks[security_id],
                    "notional_usd": 0.0,
                    "transaction_cost_usd": 0.0,
                })

            for security_id in sorted(current_ids | target_ids):
                shares_before = int(holdings.get(security_id, {}).get("shares", 0))
                shares_after = int(desired.get(security_id, 0))
                share_delta = shares_after - shares_before
                if share_delta == 0:
                    continue
                notional = abs(share_delta) * execution_marks[security_id]
                ticker = (
                    targets[security_id]["ticker"]
                    if security_id in target_ids
                    else holdings[security_id]["ticker"]
                )
                trades.append({
                    "rebalance_sequence": int(item["sequence"]),
                    "decision_date": item["decision_date"].date().isoformat(),
                    "execution_date": date.date().isoformat(),
                    "security_id": security_id,
                    "event_type": "ECONOMIC_TRADE",
                    "action": "BUY" if share_delta > 0 else "SELL",
                    "before_ticker": str(holdings.get(security_id, {}).get("ticker", "")),
                    "after_ticker": str(targets.get(security_id, {}).get("ticker", "")),
                    "trade_ticker": ticker,
                    "shares_before": shares_before,
                    "shares_after": shares_after,
                    "share_delta": share_delta,
                    "price_usd": execution_marks[security_id],
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
            cash = after_cash
            posttrade_equity = cash + sum(
                int(new_holdings[security_id]["shares"]) * execution_marks[security_id]
                for security_id in new_holdings
            )
            cash_error = abs(
                cash
                - (cash_before + sell_notional - buy_notional - fees)
            )
            accounting_error = abs(posttrade_equity - (pretrade_equity - fees))
            maximum_cash_error = max(maximum_cash_error, cash_error)
            maximum_accounting_error = max(maximum_accounting_error, accounting_error)
            cash_tolerance = _amount_tolerance(
                cash, cash_before, buy_notional, sell_notional, fees
            )
            accounting_tolerance = _amount_tolerance(
                posttrade_equity, pretrade_equity, fees
            )
            if cash_error > cash_tolerance or accounting_error > accounting_tolerance:
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: self-financing accounting invariant failed"
                )
            holdings = new_holdings
            minimum_cash = min(minimum_cash, cash)
            total_buy += buy_notional
            total_sell += sell_notional
            total_fees += fees
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

        daily_marks = {
            security_id: _price_at(path_prices, date, holding["ticker"])
            for security_id, holding in holdings.items()
        }
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
            "active_tickers": _json(sorted(
                holding["ticker"] for holding in holdings.values()
            )),
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
    path_nav = pd.concat([
        pd.Series([1.0]),
        (path_values / float(initial_cash_usd)).reset_index(drop=True),
    ], ignore_index=True)
    path_max_drawdown = float((1.0 - path_nav / path_nav.cummax()).max())
    elapsed_sessions = max(1, len(path_frame))
    path_annualized_return = float(
        (terminal_value / float(initial_cash_usd)) ** (252.0 / elapsed_sessions) - 1.0
    )
    k_path = [int(item["target_k"]) for item in rebalances]
    summary = {
        "portfolio_track": "portfolio_optimization",
        "migration_control_assumption_used": False,
        "dynamic_cardinality_enabled": True,
        "security_identity_key": "security_id",
        "issuer_identity_trace_available": all(
            bool(target.get("issuer_id"))
            for item in items for target in item["targets"].values()
        ),
        "ticker_rename_execution": "ZERO_TRADE_ZERO_FEE_IDENTITY_CONTINUATION",
        "dynamic_whole_lot_execution_mode": (
            "SECURITY_ID_CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_"
            + (
                "SEPARATE_EXECUTION_AND_VALUATION_PRICES"
                if execution_prices is not None else "REAL_CLOSES"
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
        "transaction_cost_bps": bps,
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
        "path_return_net": terminal_value / float(initial_cash_usd) - 1.0,
        "path_annualized_return_net": path_annualized_return,
        "path_max_drawdown": path_max_drawdown,
        "path_trading_session_count": len(path_frame),
        "dynamic_whole_lot_trace_sha256": trace_hash,
        "promotion_allowed": False,
    }
    return summary, rebalance_frame, trade_frame, path_frame


def simulate_dynamic_security_id_fractional_path(
    prices: pd.DataFrame,
    schedule: Iterable[Mapping[str, Any]],
    *,
    execution_prices: pd.DataFrame | None = None,
    require_separate_execution_prices: bool = False,
    require_next_session_execution: bool = False,
    require_issuer_trace: bool = False,
    initial_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float = 10.0,
    valuation_end_date: Any,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Continuous-share companion to the dynamic whole-lot path.

    This uses the same point-in-time schedule and security identity rules.  A
    bisection solves the investable amount after two-sided transaction costs so
    the declared cash buffer is preserved without an implicit cash injection.
    """
    frame = _normalise_prices(prices)
    execution_frame = (
        _normalise_prices(execution_prices) if execution_prices is not None else frame
    )
    items = _normalise_schedule(schedule)
    _validate_schedule_identity_and_execution_guards(
        items,
        valuation_prices=frame,
        separate_execution_prices_supplied=execution_prices is not None,
        require_separate_execution_prices=require_separate_execution_prices,
        require_next_session_execution=require_next_session_execution,
        require_issuer_trace=require_issuer_trace,
    )
    end_date = _date(valuation_end_date, field="valuation_end_date")
    if end_date < items[-1]["execution_date"]:
        raise NdxDynamicWholeLotPathError(
            "valuation_end_date must not precede the final execution date"
        )
    execution_dates = {item["execution_date"] for item in items}
    if end_date not in frame.index or not execution_dates.issubset(set(execution_frame.index)):
        raise NdxDynamicWholeLotPathError("an execution or valuation date is absent from prices")
    try:
        cash = float(initial_cash_usd)
        buffer = float(minimum_cash_buffer_usd)
        bps = float(transaction_cost_bps)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicWholeLotPathError("execution cash/cost inputs must be numeric") from exc
    if (
        not math.isfinite(cash) or not math.isfinite(buffer) or not math.isfinite(bps)
        or cash <= 0 or buffer < 0 or buffer >= cash or bps < 0
    ):
        raise NdxDynamicWholeLotPathError("dynamic fractional execution contract is invalid")
    fee_rate = bps / 10_000.0
    first_execution = items[0]["execution_date"]
    path_prices = frame.loc[first_execution:end_date].copy()
    holdings: dict[str, dict[str, Any]] = {}
    schedule_by_date = {item["execution_date"]: item for item in items}
    rebalances: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    total_buy = total_sell = total_fees = 0.0
    minimum_cash = cash
    maximum_accounting_error = maximum_cash_error = 0.0

    for date in path_prices.index:
        if date in schedule_by_date:
            item = schedule_by_date[date]
            targets = item["targets"]
            current_ids = set(holdings)
            target_ids = set(targets)
            renamed_ids = sorted(
                security_id
                for security_id in current_ids & target_ids
                if holdings[security_id]["ticker"] != targets[security_id]["ticker"]
            )
            marks: dict[str, float] = {}
            for security_id in sorted(current_ids | target_ids):
                ticker = (
                    targets[security_id]["ticker"]
                    if security_id in target_ids else holdings[security_id]["ticker"]
                )
                marks[security_id] = _price_at(execution_frame, date, ticker)
            cash_before = cash
            pretrade_equity = cash_before + sum(
                float(holding["shares"]) * marks[security_id]
                for security_id, holding in holdings.items()
            )
            maximum_invested = pretrade_equity - buffer
            if maximum_invested <= 0:
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: no capital above cash buffer"
                )

            def projection(invested: float) -> tuple[dict[str, float], float, float, float, float]:
                desired = {
                    security_id: (
                        invested * float(targets[security_id]["target_weight"])
                        / marks[security_id]
                    )
                    for security_id in target_ids
                }
                buy_notional = sell_notional = 0.0
                for security_id in current_ids | target_ids:
                    before = float(holdings.get(security_id, {}).get("shares", 0.0))
                    after = float(desired.get(security_id, 0.0))
                    delta = after - before
                    if delta > 0:
                        buy_notional += delta * marks[security_id]
                    elif delta < 0:
                        sell_notional += -delta * marks[security_id]
                fees = (buy_notional + sell_notional) * fee_rate
                after_cash = cash_before + sell_notional - buy_notional - fees
                return desired, after_cash, buy_notional, sell_notional, fees

            low = 0.0
            high = maximum_invested
            for _ in range(80):
                midpoint = (low + high) / 2.0
                if projection(midpoint)[1] >= buffer:
                    low = midpoint
                else:
                    high = midpoint
            desired, after_cash, buy_notional, sell_notional, fees = projection(low)
            if after_cash < buffer - _amount_tolerance(after_cash, buffer):
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: fractional cost solver breached buffer"
                )
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
                    "shares_before": float(holdings[security_id]["shares"]),
                    "shares_after": float(holdings[security_id]["shares"]),
                    "share_delta": 0.0,
                    "price_usd": marks[security_id],
                    "notional_usd": 0.0,
                    "transaction_cost_usd": 0.0,
                })
            for security_id in sorted(current_ids | target_ids):
                before = float(holdings.get(security_id, {}).get("shares", 0.0))
                after = float(desired.get(security_id, 0.0))
                delta = after - before
                if abs(delta) <= 1e-12:
                    continue
                ticker = (
                    targets[security_id]["ticker"]
                    if security_id in target_ids else holdings[security_id]["ticker"]
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
                    "shares": float(desired[security_id]),
                }
                for security_id in sorted(target_ids)
            }
            cash = after_cash
            posttrade_equity = cash + sum(
                float(new_holdings[security_id]["shares"]) * marks[security_id]
                for security_id in new_holdings
            )
            cash_error = abs(cash - (cash_before + sell_notional - buy_notional - fees))
            accounting_error = abs(posttrade_equity - (pretrade_equity - fees))
            maximum_cash_error = max(maximum_cash_error, cash_error)
            maximum_accounting_error = max(maximum_accounting_error, accounting_error)
            if (
                cash_error > _amount_tolerance(cash, cash_before, fees)
                or accounting_error > _amount_tolerance(posttrade_equity, pretrade_equity, fees)
            ):
                raise NdxDynamicWholeLotPathError(
                    f"rebalance {item['sequence']}: fractional accounting invariant failed"
                )
            holdings = new_holdings
            minimum_cash = min(minimum_cash, cash)
            total_buy += buy_notional
            total_sell += sell_notional
            total_fees += fees
            rebalances.append({
                "rebalance_sequence": int(item["sequence"]),
                "decision_date": item["decision_date"].date().isoformat(),
                "execution_date": date.date().isoformat(),
                "target_k": len(target_ids),
                "pretrade_k": len(current_ids),
                "posttrade_k": len(holdings),
                "added_security_ids": _json(sorted(target_ids - current_ids)),
                "removed_security_ids": _json(sorted(current_ids - target_ids)),
                "continued_security_ids": _json(sorted(current_ids & target_ids)),
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
        daily_marks = {
            security_id: _price_at(path_prices, date, holding["ticker"])
            for security_id, holding in holdings.items()
        }
        holdings_value = sum(
            float(holdings[security_id]["shares"]) * daily_marks[security_id]
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
    values = path_frame["total_value_usd"].astype(float)
    nav = pd.concat([
        pd.Series([1.0]),
        (values / float(initial_cash_usd)).reset_index(drop=True),
    ], ignore_index=True)
    terminal_value = float(values.iloc[-1])
    k_path = rebalance_frame["target_k"].astype(int).tolist()
    summary = {
        "portfolio_track": "portfolio_optimization",
        "migration_control_assumption_used": False,
        "dynamic_cardinality_enabled": True,
        "security_identity_key": "security_id",
        "issuer_identity_trace_available": all(
            bool(target.get("issuer_id"))
            for item in items for target in item["targets"].values()
        ),
        "fractional_shares_allowed": True,
        "ticker_rename_execution": "ZERO_TRADE_ZERO_FEE_IDENTITY_CONTINUATION",
        "dynamic_fractional_execution_mode": (
            "SECURITY_ID_CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_"
            + (
                "SEPARATE_EXECUTION_AND_VALUATION_PRICES"
                if execution_prices is not None else "REAL_CLOSES"
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
        "transaction_cost_bps": bps,
        "transaction_cost_sides": "BUY_AND_SELL",
        "rebalance_count": len(rebalance_frame),
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
        "terminal_cash_usd": cash,
        "terminal_value_usd": terminal_value,
        "path_return_net": terminal_value / float(initial_cash_usd) - 1.0,
        "path_annualized_return_net": float(
            (terminal_value / float(initial_cash_usd)) ** (252.0 / max(1, len(path_frame))) - 1.0
        ),
        "path_max_drawdown": float((1.0 - nav / nav.cummax()).max()),
        "path_trading_session_count": len(path_frame),
        "dynamic_fractional_trace_sha256": hashlib.sha256(
            _json(trace_payload).encode("utf-8")
        ).hexdigest(),
        "promotion_allowed": False,
    }
    return summary, rebalance_frame, trade_frame, path_frame


__all__ = [
    "NdxDynamicWholeLotPathError",
    "simulate_dynamic_security_id_fractional_path",
    "simulate_dynamic_security_id_whole_lot_path",
]
