"""Historical replay clock only; supplied sessions are not calendar certification.

10:00 New York is the user's observation cadence, not an assertion that a quote
was available then or an order was accepted then. Callers must separately enforce
source available_at <= observation_at, completed-bar cutoffs, and execution delay.
This module creates no market data, orders, fills, schedules or annual returns.
"""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


OBSERVATION_TIMEZONE = 'America/New_York'
OBSERVATION_LOCAL_TIME = time(10, 0)


def _timestamp(value):
    if type(value) is not str:
        raise ValueError('AWARE_ISO_TIMESTAMP_REQUIRED')
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('AWARE_ISO_TIMESTAMP_REQUIRED')
    return parsed.astimezone(timezone.utc)


def build_observation_clock(sessions):
    """Return one UTC observation and DAY close per explicit ordered session.

    Input entries use date/timezone/open_at/close_at. Extra provenance fields
    are ignored; the caller retains and verifies them. No holidays or missing
    sessions are inferred. Early closes are preserved verbatim as UTC instants.
    The observation must be in [open, close); rejected input yields no schedule.
    """
    if type(sessions) is not list or not sessions:
        raise ValueError('EXPLICIT_NONEMPTY_SESSION_LIST_REQUIRED')
    local_zone = ZoneInfo(OBSERVATION_TIMEZONE)
    result = []
    previous_date = None
    for session in sessions:
        if not isinstance(session, dict) or not {'date', 'timezone', 'open_at', 'close_at'} <= session.keys():
            raise ValueError('EXPLICIT_SESSION_FIELDS_REQUIRED')
        if session['timezone'] != OBSERVATION_TIMEZONE:
            raise ValueError('NEW_YORK_SESSION_REQUIRED')
        if type(session['date']) is not str:
            raise ValueError('ISO_SESSION_DATE_REQUIRED')
        session_date = date.fromisoformat(session['date'])
        if session_date.isoformat() != session['date']:
            raise ValueError('ISO_SESSION_DATE_REQUIRED')
        if previous_date is not None and session_date <= previous_date:
            raise ValueError('ORDERED_UNIQUE_SESSIONS_REQUIRED')
        opened = _timestamp(session['open_at'])
        closed = _timestamp(session['close_at'])
        if (opened.astimezone(local_zone).date() != session_date
                or closed.astimezone(local_zone).date() != session_date or opened >= closed):
            raise ValueError('INVALID_SESSION_BOUNDARIES')
        observed = datetime.combine(session_date, OBSERVATION_LOCAL_TIME, local_zone).astimezone(timezone.utc)
        if not opened <= observed < closed:
            raise ValueError('OBSERVATION_OUTSIDE_SESSION')
        result.append(dict(date=session_date.isoformat(), timezone=OBSERVATION_TIMEZONE,
                           observation_at=observed.isoformat(), session_open=opened.isoformat(),
                           session_close=closed.isoformat(), order_time_in_force='DAY'))
        previous_date = session_date
    return result
