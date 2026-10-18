"""Deterministic, read-only state reconciliation and session catch-up helpers."""
from __future__ import annotations

import copy
from datetime import date
from math import isfinite
from typing import Any, Mapping

from core import live


class StateCatchupError(ValueError):
    """Raised when an account reconciliation contract is incomplete."""


def _index_date(value: Any) -> str:
    """Normalize a pandas-like index value to an ISO session date."""
    try:
        candidate = value.date() if hasattr(value, "date") else date.fromisoformat(str(value)[:10])
    except (AttributeError, TypeError, ValueError) as exc:
        raise StateCatchupError(f"invalid daily-bar index value: {value!r}") from exc
    return candidate.isoformat()


def build_exact_session_close_panel(
    cfg,
    daily_frames: Mapping[str, Any],
    *,
    snapshot_as_of: str,
    latest_session: str,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """Build an exact all-symbol close panel for every intervening US session.

    The union of observed risk-leg dates is the expected calendar.  This is
    deliberately fail-closed: a date present for one configured symbol but
    absent for another is reported as an internal data gap rather than being
    silently removed by an intersection.
    """
    try:
        start = date.fromisoformat(str(snapshot_as_of or ""))
        end = date.fromisoformat(str(latest_session or ""))
    except ValueError as exc:
        raise StateCatchupError("snapshot_as_of and latest_session must be ISO dates") from exc
    if end < start:
        raise StateCatchupError(
            f"latest session {end.isoformat()} is before state clock {start.isoformat()}"
        )

    tickers = [str(symbol.ticker).upper() for symbol in cfg.symbols]
    if not tickers:
        raise StateCatchupError("configured risk sleeve is empty")
    close_by_ticker: dict[str, dict[str, float]] = {}
    observed_sessions: set[str] = set()
    for ticker in tickers:
        frame = daily_frames.get(ticker)
        if frame is None or getattr(frame, "empty", True):
            raise StateCatchupError(f"missing daily bars for {ticker}")
        if "Close" not in frame:
            raise StateCatchupError(f"daily bars for {ticker} have no Close column")
        values: dict[str, float] = {}
        for index_value, raw_close in frame["Close"].items():
            session = _index_date(index_value)
            if not (start.isoformat() < session <= end.isoformat()):
                continue
            try:
                close = float(raw_close)
            except (TypeError, ValueError) as exc:
                raise StateCatchupError(f"invalid close for {ticker} on {session}") from exc
            if not isfinite(close) or close <= 0:
                raise StateCatchupError(f"invalid close for {ticker} on {session}")
            values[session] = close
            observed_sessions.add(session)
        close_by_ticker[ticker] = values

    sessions = sorted(observed_sessions)
    if end > start and (not sessions or sessions[-1] != end.isoformat()):
        raise StateCatchupError(
            f"daily bars do not reach declared latest session {end.isoformat()}"
        )
    missing = {
        session: [ticker for ticker in tickers if session not in close_by_ticker[ticker]]
        for session in sessions
    }
    missing = {session: names for session, names in missing.items() if names}
    if missing:
        detail = "; ".join(
            f"{session}: {','.join(names)}" for session, names in sorted(missing.items())
        )
        raise StateCatchupError(f"incomplete cross-ticker session panel: {detail}")

    panel = {
        session: {ticker: close_by_ticker[ticker][session] for ticker in tickers}
        for session in sessions
    }
    audit = {
        "status": "EXACT_SESSION_PANEL_READY",
        "snapshot_as_of": start.isoformat(),
        "latest_session": end.isoformat(),
        "session_count": len(sessions),
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "ticker_count": len(tickers),
        "tickers": tickers,
        "calendar_rule": "UNION_OF_CONFIGURED_RISK_LEG_DATES_REQUIRE_COMPLETE_CROSS_SECTION",
    }
    return panel, audit


def build_reconciliation_template(portfolio) -> dict[str, Any]:
    known_dates = [portfolio.last_run_date] if portfolio.last_run_date else []
    known_dates.extend(state.entry_date for state in portfolio.symbols.values() if state.entry_date)
    suggested = max(known_dates) if known_dates else ""
    return {
        "schema_version": 1,
        "status": "USER_INPUT_REQUIRED",
        "snapshot_as_of": suggested,
        "snapshot_as_of_user_confirmed": None,
        "account_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
        "holdings": [
            {
                "ticker": ticker,
                "state_shares": float(state.shares),
                "state_entry_date": state.entry_date or None,
                "state_average_cost": (
                    float(state.cost_basis / state.shares) if state.shares > 0 else None
                ),
                "actual_position_held": None,
                "actual_whole_shares": None,
                "actual_entry_date": None,
                "actual_average_cost": None,
                "state_snapshot_matches_account": None,
            }
            for ticker, state in sorted(portfolio.symbols.items())
        ],
        "instructions": [
            "snapshot_as_of must be the date after all listed transactions were reflected in this state snapshot",
            "fill every actual_* field from HSBC records; use actual_whole_shares=0 when not held",
            "state_snapshot_matches_account=true only when shares, date, and average cost agree",
            "a mismatch creates a separate state patch; it is never silently folded into catch-up",
        ],
    }


def validate_reconciliation_contract(contract: Mapping[str, Any], expected_tickers: set[str]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    try:
        snapshot = date.fromisoformat(str(contract.get("snapshot_as_of") or ""))
    except ValueError:
        snapshot = None
        errors.append({"code": "INVALID_SNAPSHOT_AS_OF"})
    if contract.get("snapshot_as_of_user_confirmed") is not True:
        errors.append({"code": "SNAPSHOT_AS_OF_NOT_CONFIRMED"})
    rows = contract.get("holdings") or []
    tickers = [str(row.get("ticker") or "").upper() for row in rows]
    if set(tickers) != set(expected_tickers) or len(tickers) != len(set(tickers)):
        errors.append({"code": "HOLDING_TICKER_SET_MISMATCH", "observed": sorted(tickers)})
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        held = row.get("actual_position_held")
        shares = row.get("actual_whole_shares")
        if held not in {True, False}:
            errors.append({"code": "ACTUAL_POSITION_STATUS_REQUIRED", "ticker": ticker})
            continue
        try:
            shares_value = int(shares)
        except (TypeError, ValueError):
            errors.append({"code": "ACTUAL_WHOLE_SHARES_REQUIRED", "ticker": ticker})
            continue
        if shares_value < 0 or float(shares) != shares_value or (held and shares_value <= 0) or (not held and shares_value != 0):
            errors.append({"code": "ACTUAL_WHOLE_SHARES_INCONSISTENT", "ticker": ticker})
        if held:
            try:
                date.fromisoformat(str(row.get("actual_entry_date") or ""))
                average_cost = float(row.get("actual_average_cost"))
                if average_cost <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append({"code": "ACTUAL_ENTRY_DATE_AND_COST_REQUIRED", "ticker": ticker})
        if row.get("state_snapshot_matches_account") is not True:
            errors.append({"code": "STATE_ACCOUNT_MISMATCH_REQUIRES_PATCH", "ticker": ticker})
    return {
        "status": "READY" if not errors else "USER_INPUT_OR_STATE_PATCH_REQUIRED",
        "ready": not errors, "snapshot_as_of": snapshot.isoformat() if snapshot else None,
        "errors": errors,
    }


def replay_session_catchup(portfolio, cfg, *, snapshot_as_of: str, session_closes: Mapping[str, Mapping[str, float]]):
    """Rebase a confirmed snapshot clock and replay every later supplied session."""
    start = date.fromisoformat(snapshot_as_of)
    proposed = copy.deepcopy(portfolio)
    proposed.last_run_date = start.isoformat()
    ledger: list[dict[str, Any]] = []
    for date_text in sorted(session_closes):
        session = date.fromisoformat(date_text)
        if session <= start:
            continue
        closes = {str(ticker).upper(): float(value) for ticker, value in session_closes[date_text].items()}
        missing = [symbol.ticker for symbol in cfg.symbols if symbol.ticker not in closes]
        if missing:
            raise StateCatchupError(f"missing closes for {date_text}: {missing}")
        before_index = proposed.day_index
        live.advance_trading_day(proposed, date_text)
        signals = live.generate_signals(proposed, closes, cfg)
        ledger.append({
            "session_date": date_text, "day_index_before": before_index,
            "day_index_after": proposed.day_index,
            "immediate_buys": {
                signal.ticker: [
                    {"amount": float(amount), "price": float(price), "reason": str(reason)}
                    for amount, price, reason in signal.immediate_buys
                ]
                for signal in signals if signal.immediate_buys
            },
        })
    return proposed, ledger


__all__ = [
    "StateCatchupError", "build_exact_session_close_panel",
    "build_reconciliation_template", "replay_session_catchup",
    "validate_reconciliation_contract",
]
