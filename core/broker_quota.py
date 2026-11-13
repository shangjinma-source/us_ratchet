"""Validate a fresh user-confirmed free BUY allowance, not broker buying power."""
from datetime import datetime, timezone
from fractions import Fraction
import re
from zoneinfo import ZoneInfo


def free_buy_budget(document, *, account_revision, now):
    fields = {'account_revision', 'month', 'observed_at', 'remaining_hkd',
              'hkd_per_usd_budget', 'turnover_reserve_hkd'}
    if type(document) is not dict or set(document) != fields:
        raise ValueError('QUOTA_FIELDS_INVALID')
    if document['account_revision'] != account_revision:
        raise ValueError('STALE_QUOTA_ACCOUNT')
    if now.tzinfo is None:
        raise ValueError('QUOTA_CLOCK_INVALID')
    try:
        observed = datetime.fromisoformat(document['observed_at'])
        age = (now-observed).total_seconds()
    except (ValueError, TypeError):
        raise ValueError('QUOTA_TIME_INVALID') from None
    if age < 0 or age > 120:
        raise ValueError('QUOTA_CONFIRMATION_EXPIRED')
    month = now.astimezone(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m')
    if document['month'] != month or observed.astimezone(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m') != month:
        raise ValueError('QUOTA_MONTH_MISMATCH')
    amounts = {}
    for field in ('remaining_hkd', 'hkd_per_usd_budget', 'turnover_reserve_hkd'):
        value = document[field]
        if type(value) is not str or not re.fullmatch(r'(?:0|[1-9]\d{0,11})(?:\.\d{1,4})?', value):
            raise ValueError('QUOTA_AMOUNT_INVALID')
        amounts[field] = Fraction(value)
    # Conservative planning conversion, never advertised as HSBC's actual FX.
    if amounts['hkd_per_usd_budget'] < 8:
        raise ValueError('QUOTA_FX_BUFFER_REQUIRED')
    if amounts['remaining_hkd'] > 250000:
        raise ValueError('QUOTA_EXCEEDS_MONTHLY_LIMIT')
    budget = max(Fraction(0), amounts['remaining_hkd']-amounts['turnover_reserve_hkd']) / amounts['hkd_per_usd_budget']
    return Fraction(int(budget*100), 100)
