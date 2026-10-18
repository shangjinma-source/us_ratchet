"""Read-only reconciliation between the strategy book and a broker snapshot."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


class BrokerSnapshotError(ValueError):
    """Raised when a broker snapshot is incomplete or internally inconsistent."""


def normalize_broker_positions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        ticker = str(raw.get("ticker") or "").upper().strip()
        if not ticker or ticker in seen:
            raise BrokerSnapshotError(f"invalid or duplicate ticker: {ticker or '<blank>'}")
        try:
            shares = int(raw.get("shares"))
            average_cost = float(raw.get("average_cost"))
            observed_price = float(raw.get("observed_price"))
        except (TypeError, ValueError) as exc:
            raise BrokerSnapshotError(f"invalid numeric broker fields for {ticker}") from exc
        if shares <= 0 or float(raw.get("shares")) != shares or average_cost <= 0 or observed_price <= 0:
            raise BrokerSnapshotError(f"invalid whole-share broker position for {ticker}")
        market_value = shares * observed_price
        cost_basis = shares * average_cost
        displayed_market_value = raw.get("displayed_market_value")
        displayed_pnl = raw.get("displayed_unrealized_pnl")
        normalized.append({
            "ticker": ticker,
            "shares": shares,
            "average_cost": average_cost,
            "observed_price": observed_price,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "unrealized_pnl": market_value - cost_basis,
            "displayed_market_value": float(displayed_market_value) if displayed_market_value is not None else None,
            "displayed_unrealized_pnl": float(displayed_pnl) if displayed_pnl is not None else None,
        })
        seen.add(ticker)
    if not normalized:
        raise BrokerSnapshotError("broker snapshot is empty")
    return sorted(normalized, key=lambda row: row["ticker"])


def reconcile_strategy_book(portfolio, broker_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare account truth with the strategy book without changing either one."""
    broker = normalize_broker_positions(broker_rows)
    broker_by_ticker = {row["ticker"]: row for row in broker}
    strategy_tickers = set(portfolio.symbols)
    account_tickers = set(broker_by_ticker)
    rows: list[dict[str, Any]] = []
    for ticker in sorted(strategy_tickers | account_tickers):
        state = portfolio.symbols.get(ticker)
        actual = broker_by_ticker.get(ticker)
        state_shares = float(state.shares) if state else 0.0
        actual_shares = int(actual["shares"]) if actual else 0
        if state and actual:
            scope = "STRATEGY_AND_BROKER"
            status = "MATCH" if abs(state_shares - actual_shares) < 1e-9 and abs(float(state.cost_basis) - actual["cost_basis"]) < 0.02 else "BROKER_OVERRIDES_STALE_STATE"
        elif actual:
            scope = "BROKER_ONLY_OFF_STRATEGY"
            status = "ACCOUNT_OVERLAY_ONLY"
        else:
            scope = "STRATEGY_BOOK_ONLY_NOT_BROKER_HELD"
            status = "DO_NOT_TREAT_AS_REAL_POSITION"
        rows.append({
            "ticker": ticker,
            "scope": scope,
            "status": status,
            "strategy_book_shares": state_shares,
            "strategy_book_average_cost": (float(state.cost_basis / state.shares) if state and state.shares > 0 else None),
            "broker_whole_shares": actual_shares,
            "broker_average_cost": actual["average_cost"] if actual else None,
            "broker_market_value": actual["market_value"] if actual else 0.0,
            "portfolio_optimization_included": bool(state),
            "account_concentration_included": bool(actual),
            "automatic_state_patch_allowed": False,
        })
    total = sum(row["market_value"] for row in broker)
    concentration = []
    for row in sorted(broker, key=lambda item: (-item["market_value"], item["ticker"])):
        concentration.append({**row, "account_weight": row["market_value"] / total})
    weights = [row["account_weight"] for row in concentration]
    return {
        "reconciliation": rows,
        "broker_positions": concentration,
        "summary": {
            "broker_position_count": len(broker),
            "strategy_book_count": len(strategy_tickers),
            "strategy_and_broker_count": len(strategy_tickers & account_tickers),
            "broker_only_count": len(account_tickers - strategy_tickers),
            "strategy_book_only_count": len(strategy_tickers - account_tickers),
            "stale_state_mismatch_count": sum(row["status"] == "BROKER_OVERRIDES_STALE_STATE" for row in rows),
            "total_broker_market_value": total,
            "security_top1_weight": max(weights),
            "security_top3_weight": sum(sorted(weights, reverse=True)[:3]),
            "effective_n": 1.0 / sum(weight * weight for weight in weights),
            "strategy_and_account_separated": True,
            "portfolio_optimization_track": "VARIABLE_CARDINALITY",
            "migration_control_included": False,
            "live_state_changed": False,
        },
    }


__all__ = ["BrokerSnapshotError", "normalize_broker_positions", "reconcile_strategy_book"]
