"""Independent persistence for broker account truth.

This store is deliberately separate from ``data/state.json``: broker shares and
costs drive account display and execution gaps, while the strategy book keeps
its own targets, H values, reserves, and research baseline.
"""
from __future__ import annotations

import json
import hashlib
import copy
import re
import shutil
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from core.helpers import atomic_write_text, resolve

BROKER_ACCOUNT_PATH = "data/broker_positions.json"


class BrokerAccountError(ValueError):
    pass


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise BrokerAccountError(f"invalid {field}: boolean is not a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BrokerAccountError(f"invalid {field}") from exc
    if not isfinite(number):
        raise BrokerAccountError(f"invalid {field}: must be finite")
    return number


def _iso_date(value: Any, field: str, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise BrokerAccountError(f"{field} is required")
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise BrokerAccountError(f"invalid {field}: expected ISO date YYYY-MM-DD") from exc


def _iso_datetime(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BrokerAccountError(f"invalid {field}: expected ISO datetime") from exc
    if "T" not in text or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BrokerAccountError(f"invalid {field}: timezone-aware ISO datetime required")
    return parsed.isoformat()


def validate_broker_account(payload: Mapping[str, Any]) -> dict[str, Any]:
    snapshot_as_of = _iso_date(
        payload.get("snapshot_as_of"), "snapshot_as_of", required=True
    )
    snapshot_clock = _iso_datetime(payload.get("snapshot_clock"), "snapshot_clock")
    positions = []
    seen: set[str] = set()
    for raw in payload.get("positions") or []:
        ticker = str(raw.get("ticker") or "").upper().strip()
        if not ticker or ticker in seen:
            raise BrokerAccountError(f"invalid or duplicate broker ticker: {ticker or '<blank>'}")
        shares_value = _finite_float(raw.get("shares"), f"shares for {ticker}")
        average_cost = _finite_float(raw.get("average_cost"), f"average_cost for {ticker}")
        observed_price = _finite_float(raw.get("observed_price"), f"observed_price for {ticker}")
        if (shares_value <= 0 or not shares_value.is_integer()
                or average_cost <= 0 or observed_price <= 0):
            raise BrokerAccountError(f"invalid whole-share broker position for {ticker}")
        shares = int(shares_value)
        positions.append({
            "ticker": ticker,
            "shares": shares,
            "average_cost": average_cost,
            "observed_price": observed_price,
        })
        seen.add(ticker)
    if not positions and payload.get("positions") != []:
        raise BrokerAccountError("broker positions are required")
    cash_raw = payload.get("deployable_cash_usd", 0.0)
    deployable_cash_usd = _finite_float(
        0.0 if cash_raw is None else cash_raw, "deployable_cash_usd"
    )
    if deployable_cash_usd < 0:
        raise BrokerAccountError("deployable_cash_usd must be non-negative")
    deployable_cash_session_date = _iso_date(
        payload.get("deployable_cash_session_date"),
        "deployable_cash_session_date",
        required=deployable_cash_usd > 0,
    )
    positions_confirmed_session_date = _iso_date(
        payload.get("positions_confirmed_session_date"),
        "positions_confirmed_session_date",
    )
    if deployable_cash_session_date and deployable_cash_session_date > snapshot_as_of:
        raise BrokerAccountError("deployable_cash_session_date cannot be after snapshot_as_of")
    if positions_confirmed_session_date and positions_confirmed_session_date > snapshot_as_of:
        raise BrokerAccountError("positions_confirmed_session_date cannot be after snapshot_as_of")
    deployable_cash_persistence = str(
        payload.get("deployable_cash_persistence") or "session"
    ).strip().lower()
    if deployable_cash_persistence not in {"session", "until_user_update"}:
        raise BrokerAccountError(
            "deployable_cash_persistence must be session or until_user_update"
        )
    closed_positions = []
    closed_seen: set[str] = set()
    for raw in payload.get("reported_closed_positions") or []:
        ticker = str(raw.get("ticker") or "").upper().strip()
        if not ticker or ticker in closed_seen or ticker in seen:
            raise BrokerAccountError(f"invalid reported closed ticker: {ticker or '<blank>'}")
        reported_as_of = _iso_date(
            raw.get("reported_as_of"),
            f"reported_as_of for {ticker}",
            required=True,
        )
        if reported_as_of > snapshot_as_of:
            raise BrokerAccountError(
                f"reported_as_of for {ticker} cannot be after snapshot_as_of"
            )
        closed_positions.append({
            "ticker": ticker,
            "reported_as_of": reported_as_of,
            "note": str(raw.get("note") or ""),
        })
        closed_seen.add(ticker)
    return {
        "schema_version": 1,
        "snapshot_as_of": snapshot_as_of,
        "snapshot_clock": snapshot_clock,
        "source_note": str(payload.get("source_note") or ""),
        "deployable_cash_usd": deployable_cash_usd,
        "deployable_cash_session_date": deployable_cash_session_date,
        "deployable_cash_persistence": deployable_cash_persistence,
        "positions_confirmed_session_date": positions_confirmed_session_date,
        "deployable_cash_note": str(payload.get("deployable_cash_note") or ""),
        "reported_closed_positions": sorted(closed_positions, key=lambda row: row["ticker"]),
        "positions": sorted(positions, key=lambda row: row["ticker"]),
    }


def load_broker_account(path: str | Path = BROKER_ACCOUNT_PATH) -> dict[str, Any] | None:
    target = resolve(path)
    if not target.exists():
        return None
    return validate_broker_account(json.loads(target.read_text(encoding="utf-8")))


def broker_account_fingerprint(account: Mapping[str, Any]) -> str:
    fields = (
        "snapshot_as_of", "snapshot_clock", "positions_confirmed_session_date",
        "deployable_cash_usd", "deployable_cash_session_date",
        "deployable_cash_persistence", "positions", "reported_closed_positions",
    )
    return hashlib.sha256(json.dumps(
        {field: account[field] for field in fields}, ensure_ascii=True,
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def update_broker_position(account: Mapping[str, Any], body: Mapping[str, Any],
                           *, clock: datetime | None = None) -> tuple[dict, dict]:
    """Absolute single-position correction; no inferred fills or cash movements."""
    current = validate_broker_account(account)
    ticker = str(body.get("ticker") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", ticker):
        raise BrokerAccountError("请填写有效股票代码")
    shares = _finite_float(body.get("shares"), "shares")
    if shares < 0 or not shares.is_integer():
        raise BrokerAccountError("请填写当前总股数（非负整数；0 表示清仓）")
    previous = next((row for row in current["positions"] if row["ticker"] == ticker), None)
    average_cost = None
    if shares:
        average_cost = _finite_float(
            body.get("average_cost") if body.get("average_cost") not in (None, "")
            else previous["average_cost"] if previous else None, "average_cost",
        )
        if average_cost <= 0:
            raise BrokerAccountError("新增持仓需填写正数平均成本价")
    closed = any(row["ticker"] == ticker for row in current["reported_closed_positions"])
    if previous is None and shares == 0 and not closed:
        raise BrokerAccountError("该标的尚未录入，无法确认清仓")
    difference = {
        "ticker": ticker, "old_shares": previous["shares"] if previous else 0,
        "new_shares": int(shares),
        "old_average_cost": previous["average_cost"] if previous else None,
        "new_average_cost": average_cost,
    }
    if ((previous and previous["shares"] == shares and previous["average_cost"] == average_cost)
            or (previous is None and shares == 0 and closed)):
        return current, difference
    now = clock or datetime.now().astimezone()
    snapshot = copy.deepcopy(current)
    snapshot["snapshot_as_of"] = max(current["snapshot_as_of"], now.date().isoformat())
    snapshot["snapshot_clock"] = now.isoformat(timespec="microseconds")
    snapshot["positions"] = [row for row in current["positions"] if row["ticker"] != ticker]
    snapshot["reported_closed_positions"] = [
        row for row in current["reported_closed_positions"] if row["ticker"] != ticker
    ]
    if shares:
        snapshot["positions"].append({
            "ticker": ticker, "shares": int(shares), "average_cost": average_cost,
            "observed_price": previous["observed_price"] if previous else average_cost,
        })
    else:
        snapshot["reported_closed_positions"].append({
            "ticker": ticker, "reported_as_of": now.date().isoformat(),
            "note": "用户确认当前总股数为 0；不推断卖出日期、费用或到账现金",
        })
    return validate_broker_account(snapshot), difference


def save_broker_account(payload: Mapping[str, Any], path: str | Path = BROKER_ACCOUNT_PATH) -> None:
    normalized = validate_broker_account(payload)
    atomic_write_text(resolve(path), json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")


def backup_broker_account(path: str | Path = BROKER_ACCOUNT_PATH) -> Path | None:
    target = resolve(path)
    if not target.exists():
        return None
    backup = target.with_suffix(target.suffix + ".bak")
    shutil.copy2(target, backup)
    return backup


__all__ = [
    "BROKER_ACCOUNT_PATH", "BrokerAccountError", "backup_broker_account",
    "load_broker_account", "save_broker_account", "validate_broker_account",
    "broker_account_fingerprint", "update_broker_position",
]
