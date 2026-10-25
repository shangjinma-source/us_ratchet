"""Read-only readiness adapter for saved Yahoo daily bytes; no signal approval.

Reports concrete gaps before normalizing. A current-mark interval unit review is
not accepted as a historical constant-share-unit normalization review.
"""
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_difference import require, timestamp


def inspect_saved_daily_source(*, raw_bytes, raw_sha256, captured_at, ticker,
                               signal_date, calendar_sessions, unit_review,
                               permitted_for_strategy):
    require(type(raw_bytes) is bytes and sha256(raw_bytes).hexdigest() == raw_sha256,
            'SAVED_DAILY_HASH_MISMATCH')
    captured = timestamp(captured_at)
    results = json.loads(raw_bytes)['chart']['result']
    require(type(results) is list and len(results) == 1, 'SAVED_DAILY_RESULT_REQUIRED')
    source = results[0]
    require(source['meta']['symbol'] == ticker and source['meta']['currency'] == 'USD',
            'SAVED_DAILY_IDENTITY_MISMATCH')
    stamps = source.get('timestamp', [])
    quotes = source['indicators']['quote']
    require(len(quotes) == 1 and len(quotes[0]['close']) == len(stamps),
            'SAVED_DAILY_LENGTH_MISMATCH')
    observed_rows = {}
    for stamp, close in zip(stamps, quotes[0]['close']):
        day = datetime.fromtimestamp(stamp, timezone.utc).astimezone(
            ZoneInfo('America/New_York')).date().isoformat()
        require(day not in observed_rows, 'DUPLICATE_DAILY_DATE')
        if close is not None:
            require(type(close) is not bool and Fraction(str(close)) > 0,
                    'INVALID_SAVED_DAILY_CLOSE')
        observed_rows[day] = close
    dates = [s['date'] for s in calendar_sessions]
    require(dates == sorted(set(dates)), 'INVALID_FIXED_CALENDAR')
    by_date = {s['date']: s for s in calendar_sessions}
    reasons = []
    if sum(close is not None for day, close in observed_rows.items() if day <= signal_date) < 20:
        reasons.append('WAIT_TWENTY_DAILY_ROWS')
    if permitted_for_strategy is not True:
        reasons.append('WAIT_STRATEGY_SOURCE_REVIEW')
    if signal_date not in by_date or dates.index(signal_date) < 19:
        reasons.append('WAIT_TWENTY_SESSION_CALENDAR')
        expected = []
    else:
        index = dates.index(signal_date)
        expected = dates[index-19:index+1]
    missing = [day for day in expected if observed_rows.get(day) is None]
    if observed_rows.get(signal_date) is None or missing:
        reasons.append('WAIT_COMPLETED_DAILY_PRICES')
    if signal_date in by_date and captured < timestamp(by_date[signal_date]['close']):
        reasons.append('WAIT_AFTER_SESSION_CLOSE_CAPTURE')
    if (type(unit_review) is not dict
            or unit_review.get('schema') != 'REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1'
            or unit_review.get('unit_asof') != signal_date
            or unit_review.get('currency') != 'USD'
            or not unit_review.get('basis_id')
            or not unit_review.get('review_reference')):
        reasons.append('WAIT_HISTORICAL_UNIT_NORMALIZATION')
    return dict(status='WAIT_SAVED_DAILY_EVIDENCE' if reasons else 'READY_FOR_SERVER_NORMALIZATION_REVIEW',
                reasons=reasons, requested_signal_date=signal_date,
                raw_sha256=raw_sha256, captured_at=captured_at,
                saved_last_date=max(observed_rows) if observed_rows else None,
                saved_row_count=len(observed_rows),
                missing_expected_dates=missing, available_calendar_sessions=len(dates),
                normalized_inputs=None, approval_receipt=None, production_enabled=False)
