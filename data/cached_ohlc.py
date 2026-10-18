"""Read existing daily cache for selected charts, without provider or account IO."""
from __future__ import annotations

import csv
import io
import math
import re
from datetime import date
from pathlib import Path

CACHE_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "cache"
MAX_CACHE_BYTES = 8_000_000


def _plain_path(path: Path) -> bool:
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            attributes = getattr(ancestor.lstat(), "st_file_attributes", 0)
            if ancestor.is_symlink() or attributes & 0x400:
                return False
    return True


def read_cached_ohlc(ticker: str, *, allowed_tickers, interval: str = "day",
                     bars: int = 90, expected_session_date: str | None = None) -> dict:
    """Allowlist comes from server-selected publication, never request parameters."""
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", ticker):
        raise ValueError("invalid ticker")
    if ticker not in allowed_tickers:
        raise ValueError("ticker is not in the published selection")
    if interval not in {"day", "week", "month"}:
        raise ValueError("interval must be day, week or month")
    if type(bars) is not int or not 1 <= bars <= 260:
        raise ValueError("bars must be an integer from 1 to 260")
    expected = date.fromisoformat(expected_session_date) if expected_session_date else None
    result = {"ticker": ticker, "interval": interval, "source": "local_daily_cache",
              "status": "MISSING", "bars": [], "daily_as_of": None,
              "expected_session_date": expected_session_date, "stale": None,
              "adjustment_basis": "cache_unspecified", "reason": "本地日线缓存缺失"}
    path = CACHE_DIRECTORY / f"{ticker}.csv"
    if not _plain_path(path):
        return {**result, "status": "INVALID", "reason": "缓存路径异常"}
    if not path.is_file():
        return result
    try:
        with path.open("rb") as source:
            contents = source.read(MAX_CACHE_BYTES + 1)
        if len(contents) > MAX_CACHE_BYTES:
            raise ValueError("cache size limit")
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
        if not {"Date", "Open", "High", "Low", "Close"}.issubset(reader.fieldnames or []):
            raise ValueError("missing actual OHLC columns")
        daily = []
        previous = None
        for raw in reader:
            session = date.fromisoformat(raw["Date"])
            if raw["Date"] != session.isoformat() or (previous and session <= previous):
                raise ValueError("dates must be unique and increasing")
            previous = session
            values = {key.lower(): float(raw[key]) for key in ("Open", "High", "Low", "Close")}
            if not all(math.isfinite(value) and value > 0 for value in values.values()):
                raise ValueError("non-finite or non-positive OHLC")
            if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
                raise ValueError("inconsistent OHLC range")
            volume = float(raw["Volume"]) if raw.get("Volume") not in (None, "") else None
            if volume is not None and (not math.isfinite(volume) or volume < 0):
                raise ValueError("invalid volume")
            if expected is None or session <= expected:
                daily.append({"date": session.isoformat(), **values, "volume": volume})
            if reader.line_num > 20_001:
                raise ValueError("cache row limit")
        if not daily:
            return {**result, "reason": "截至指定日期无缓存日线"}
        grouped = []
        key_previous = None
        for row in daily:
            session = date.fromisoformat(row["date"])
            key = row["date"] if interval == "day" else session.isocalendar()[:2] if interval == "week" else (session.year, session.month)
            if key != key_previous:
                grouped.append({**row, "first_date": row["date"], "sessions": 1})
                key_previous = key
            else:
                candle = grouped[-1]
                candle.update(date=row["date"], high=max(candle["high"], row["high"]),
                              low=min(candle["low"], row["low"]), close=row["close"],
                              volume=candle["volume"] + row["volume"] if candle["volume"] is not None and row["volume"] is not None else None,
                              sessions=candle["sessions"] + 1)
                if candle["volume"] is not None and not math.isfinite(candle["volume"]):
                    raise ValueError("aggregate volume overflow")
        return {**result, "status": "AVAILABLE", "bars": grouped[-bars:],
                "daily_as_of": daily[-1]["date"],
                "stale": daily[-1]["date"] < expected.isoformat() if expected else None,
                "reason": "", "last_period_may_be_partial": interval != "day"}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, csv.Error):
        return {**result, "status": "INVALID", "reason": "缓存日期或 OHLC 数据无效"}
