"""Aggregate append-only advice snapshots into session-level execution evidence."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping


def _number(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _session_date(row: Mapping) -> str:
    freshness = row.get("state_freshness") or {}
    value = freshness.get("latest_closed_session_date") or row.get("as_of") or ""
    return str(value)[:10]


def _whole_lot_buy_ready(item: Mapping) -> bool:
    if item.get("side") != "BUY" or item.get("source") == "ratchet_next":
        return False
    if item.get("share_plan_eligible") is False:
        return False
    context = item.get("execution_context") or {}
    if isinstance(context, Mapping) and bool(context.get("whole_lot_ready")):
        return True
    shares = _number(item.get("shares"))
    if shares >= 1.0:
        return True
    price = _number(item.get("limit") or item.get("live_price"))
    amount = _number(item.get("amount"))
    return price > 0 and amount + 0.01 >= price


def summarize_tactical_dead_zone(rows: Iterable[Mapping]) -> dict:
    sessions = defaultdict(lambda: {
        "snapshot_count": 0,
        "first_ts": "",
        "last_ts": "",
        "market_regimes": set(),
        "max_today_actionable_count": 0,
        "max_strategy_buy_signal_count": 0,
        "whole_lot_buy_seen": False,
        "bear_zero_budget_seen": False,
    })
    invalid_session_rows = 0
    for row in rows:
        session = _session_date(row)
        if not session:
            invalid_session_rows += 1
            continue
        target = sessions[session]
        target["snapshot_count"] += 1
        ts = str(row.get("ts") or "")
        if not target["first_ts"] or ts < target["first_ts"]:
            target["first_ts"] = ts
        if not target["last_ts"] or ts > target["last_ts"]:
            target["last_ts"] = ts
        market = row.get("market") or {}
        regime = str(market.get("regime") or "UNKNOWN")
        target["market_regimes"].add(regime)
        execution = row.get("execution") or {}
        target["max_today_actionable_count"] = max(
            target["max_today_actionable_count"],
            int(_number(execution.get("actionable_count"))),
        )
        strategy_counts = execution.get("strategy_counts") or execution.get("counts") or {}
        raw_signals = int(_number(strategy_counts.get("buy_now"))) + int(
            _number(strategy_counts.get("place_limit"))
        )
        target["max_strategy_buy_signal_count"] = max(
            target["max_strategy_buy_signal_count"], raw_signals
        )
        if any(_whole_lot_buy_ready(item) for item in execution.get("items") or []):
            target["whole_lot_buy_seen"] = True
        for symbol in row.get("symbols") or []:
            tactical = symbol.get("tactical") or {}
            context = tactical.get("execution_context") or {}
            if (str(tactical.get("regime") or "") == "BEAR"
                    and isinstance(context, Mapping)
                    and str(context.get("status") or "") == "NO_TACTICAL_BUDGET"):
                target["bear_zero_budget_seen"] = True

    output_rows = []
    for session in sorted(sessions):
        row = sessions[session]
        output_rows.append({
            **{key: value for key, value in row.items() if key != "market_regimes"},
            "session_date": session,
            "market_regimes": ";".join(sorted(row["market_regimes"])),
            "zero_whole_lot_buy_session": not row["whole_lot_buy_seen"],
        })
    zero_sessions = [row for row in output_rows if row["zero_whole_lot_buy_session"]]
    return {
        "session_count": len(output_rows),
        "zero_whole_lot_buy_session_count": len(zero_sessions),
        "whole_lot_buy_session_count": len(output_rows) - len(zero_sessions),
        "first_session": output_rows[0]["session_date"] if output_rows else None,
        "last_session": output_rows[-1]["session_date"] if output_rows else None,
        "invalid_session_rows": invalid_session_rows,
        "sessions": output_rows,
    }


__all__ = ["summarize_tactical_dead_zone"]
