"""Append-only daily calendar extension of an immutable split timing calendar."""
from datetime import date
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import require
from data.strategy_daily_session_capture import stamp


def validate_calendar_extension(*, pinned, current):
    require(type(pinned) is dict and type(current) is dict,
            'NATIVE_CALENDAR_DOCUMENT_REQUIRED')
    require({k:v for k,v in pinned.items() if k != 'sessions'} ==
            {k:v for k,v in current.items() if k != 'sessions'} and
            current.get('schema') == 'FIXED_EXCHANGE_SESSIONS_V1' and
            current.get('exchange') == 'NASDAQ', 'NATIVE_CALENDAR_HEADER_CHANGED')
    old, rows = pinned.get('sessions'), current.get('sessions')
    require(type(old) is list and type(rows) is list and 0 < len(old) <= len(rows) <= 1000,
            'NATIVE_CALENDAR_EXTENSION_SIZE')
    require(rows[:len(old)] == old, 'NATIVE_CALENDAR_HISTORY_CHANGED')
    previous_date, previous_close = None, None
    for row in rows:
        day = date.fromisoformat(row['date']).isoformat()
        opened, closed = stamp(row['open']), stamp(row['close'])
        require(day == row['date'] and opened < closed and
                opened.astimezone(ZoneInfo('America/New_York')).date().isoformat() == day ==
                closed.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
                'NATIVE_CALENDAR_SESSION_INVALID')
        require(previous_date is None or (previous_date < day and previous_close < opened),
                'NATIVE_CALENDAR_EXTENSION_ORDER')
        previous_date, previous_close = day, closed
    return dict(pinned_session_count=len(old), added_session_count=len(rows)-len(old))
