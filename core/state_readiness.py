"""Read-only safety checks before advancing the persisted portfolio clock."""
from __future__ import annotations

from datetime import date


def state_clock_readiness(portfolio, latest_completed_session: str) -> dict:
    """Describe chronology blockers without changing the portfolio."""
    latest = date.fromisoformat(str(latest_completed_session))
    state_date = date.fromisoformat(portfolio.last_run_date) if portfolio.last_run_date else None
    blockers: list[dict] = []
    warnings: list[dict] = []
    for ticker, state in sorted(portfolio.symbols.items()):
        entry = date.fromisoformat(state.entry_date) if state.entry_date else None
        if entry and entry > latest:
            blockers.append({
                "code": "ENTRY_DATE_AFTER_LATEST_COMPLETED_SESSION",
                "ticker": ticker, "entry_date": state.entry_date,
                "latest_completed_session": latest.isoformat(),
            })
        elif entry and state_date and entry > state_date:
            blockers.append({
                "code": "POSITION_EVENT_AFTER_STATE_CLOCK",
                "ticker": ticker, "entry_date": state.entry_date,
                "state_last_run_date": portfolio.last_run_date,
            })
        if float(state.shares or 0.0) > 0 and not state.entry_date:
            warnings.append({
                "code": "POSITION_CHRONOLOGY_UNCONFIRMED",
                "ticker": ticker, "shares": float(state.shares),
            })
    if state_date and state_date > latest:
        blockers.append({
            "code": "STATE_CLOCK_AFTER_LATEST_COMPLETED_SESSION",
            "state_last_run_date": portfolio.last_run_date,
            "latest_completed_session": latest.isoformat(),
        })
    return {
        "status": "BLOCKED_USER_RECONCILIATION_REQUIRED" if blockers else "READY",
        "safe_to_apply_daily_update": not blockers,
        "state_last_run_date": portfolio.last_run_date,
        "latest_completed_session": latest.isoformat(),
        "blockers": blockers, "warnings": warnings,
    }


__all__ = ["state_clock_readiness"]
