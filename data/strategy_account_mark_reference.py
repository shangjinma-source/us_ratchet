"""Current regular-session valuation marks, not buy or sell limit suggestions.

Valuing a candidate uses its fresh last trade. A buy's complete-minute and
pullback requirements belong to the separate execution adapter after selection.
Original capture time is retained even when the caller waits for a subsecond
provider timestamp; this decoder never waits or changes any timestamp.
"""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import json

from core.strategy_account_ledger import require

NY = ZoneInfo('America/New_York')


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'DUPLICATE_QUOTE_FIELD')
        result[key] = value
    return result


def _number(value):
    require(value is not None and not isinstance(value, bool), 'INVALID_NUMERIC_QUOTE')
    number = Decimal(str(value))
    require(number.is_finite(), 'NONFINITE_QUOTE')
    return number


def _stamp(value):
    number = _number(value)
    require(number == number.to_integral_value(), 'NONINTEGER_TIMESTAMP')
    return int(number)


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def decode_current_mark(raw, *, ticker, now, captured_at, maximum_age_seconds=120):
    require(type(maximum_age_seconds) is int and maximum_age_seconds in (120,900), 'UNSUPPORTED_MARK_AGE_POLICY')
    require(type(raw) is bytes and 0 < len(raw) <= 4*1024*1024, 'RAW_QUOTE_BYTES_REQUIRED')
    require(isinstance(now, datetime) and now.utcoffset() is not None
            and isinstance(captured_at, datetime) and captured_at.utcoffset() is not None
            and captured_at <= now, 'CAPTURE_TIME_INVALID')
    document = json.loads(raw, parse_float=Decimal, object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_QUOTE')))
    chart = document['chart']
    require(chart.get('error') is None and type(chart.get('result')) is list
            and len(chart['result']) == 1, 'INVALID_CHART_RESULT')
    meta = chart['result'][0]['meta']
    require(meta.get('symbol') == ticker and meta.get('currency') == 'USD'
            and meta.get('instrumentType') == 'EQUITY'
            and meta.get('exchangeTimezoneName') == 'America/New_York', 'QUOTE_IDENTITY_CURRENCY_MISMATCH')
    require(meta.get('dataGranularity') == '1m', 'NOT_ONE_MINUTE_DATA')
    regular = meta['currentTradingPeriod']['regular']
    opening, closing = _stamp(regular['start']), _stamp(regular['end'])
    current, captured = Decimal(str(now.timestamp())), Decimal(str(captured_at.timestamp()))
    require(opening <= captured <= current < closing and opening < closing, 'OUTSIDE_REGULAR_SESSION')
    session = now.astimezone(NY).date().isoformat()
    require(all(datetime.fromtimestamp(t, NY).date().isoformat() == session
                for t in (opening, closing)), 'SESSION_DATE_MISMATCH')
    price, observed = _number(meta['regularMarketPrice']), _stamp(meta['regularMarketTime'])
    require(price > 0 and opening <= observed < closing, 'INVALID_LAST_QUOTE')
    require(observed <= current, 'LAST_QUOTE_FUTURE')
    require(observed <= captured + 1, 'QUOTE_CLOCK_SKEW_EXCEEDED')
    require(current - observed < maximum_age_seconds and current - captured < maximum_age_seconds, 'LAST_QUOTE_STALE')
    return dict(session=session, last_price=str(price), last_at=_iso(observed),
        refresh_by=_iso(min(observed+maximum_age_seconds, closing)), session_open=_iso(opening),
        session_close=_iso(closing), source='YAHOO_REGULAR_LAST_VALUATION_ONLY',
        executable_limit=False)
