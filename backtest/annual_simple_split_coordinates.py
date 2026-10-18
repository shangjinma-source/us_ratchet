"""Conditional simple-split coordinates only; no strategy or trade execution."""
from fractions import Fraction
from datetime import date

COMPLEX = frozenset(('WDC', 'HON', 'CMCSA', 'AZN', 'TRI'))
FIELDS = ('open', 'high', 'low', 'close')


def canonical_day(value):
    if not isinstance(value, str):
        raise ValueError('CANONICAL_ISO_DATE_REQUIRED')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('CANONICAL_ISO_DATE_REQUIRED') from error
    if parsed.isoformat() != value:
        raise ValueError('CANONICAL_ISO_DATE_REQUIRED')
    return value


def ratio(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_NUMBER')
    result = Fraction(str(value))
    if result <= 0:
        raise ValueError('POSITIVE_NUMBER_REQUIRED')
    return result


def checked_events(events):
    dates = [canonical_day(event['date']) for event in events]
    if dates != sorted(set(dates)):
        raise ValueError('DUPLICATE_OR_UNORDERED_SPLITS')
    for event in events:
        if event.get('share_event_candidate') is not True:
            raise ValueError('UNREVIEWED_EVENT')
        ratio(event['ratio'])
    return events


def nominal_row(*, day, raw, events, capture_end):
    canonical_day(day)
    canonical_day(capture_end)
    if day > capture_end:
        raise ValueError('OUTSIDE_CAPTURE_COORDINATE')
    factor = Fraction(1)
    for event in checked_events(events):
        if day < event['date'] <= capture_end:
            factor *= ratio(event['ratio'])
    values = {field: ratio(raw[field]) * factor for field in FIELDS}
    if not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
        raise ValueError('INVALID_OHLC')
    return dict(ohlc={field: str(value) for field, value in values.items()}, factor=str(factor))


def training_close(*, day, decision_date, nominal_close, events):
    canonical_day(day)
    canonical_day(decision_date)
    if day > decision_date:
        raise ValueError('FUTURE_TRAINING_DATE')
    divisor = Fraction(1)
    for event in checked_events(events):
        if day < event['date'] <= decision_date:
            divisor *= ratio(event['ratio'])
    return str(ratio(nominal_close) / divisor)


def apply_quantity_event(*, day, quantity, event, applied_ids):
    """Pure boundary helper; fractional entitlements require a separate handler."""
    canonical_day(day)
    if type(quantity) is not int or quantity < 0:
        raise ValueError('WHOLE_NONNEGATIVE_QUANTITY_REQUIRED')
    checked_events([event])
    identifier = event['event_id']
    if identifier in applied_ids or day != event['date']:
        return dict(quantity=quantity, applied_ids=list(applied_ids))
    updated = quantity * ratio(event['ratio'])
    if updated.denominator != 1:
        raise ValueError('FRACTIONAL_ENTITLEMENT_REQUIRES_EXPLICIT_HANDLING')
    return dict(quantity=int(updated), applied_ids=list(applied_ids) + [identifier])


def build_coordinates(*, ticker, bars, events, capture_end):
    canonical_day(capture_end)
    for day in bars:
        canonical_day(day)
    for event in events:
        canonical_day(event['date'])
    if ticker in COMPLEX or any(not event.get('share_event_candidate') for event in events):
        return dict(ticker=ticker, status='BLOCKED_COMPLEX_OR_UNREVIEWED', events=events,
                    nominal_ohlc=None, execution_admitted=False)
    checked_events(events)
    output, missing = {}, []
    for day, raw in sorted(bars.items()):
        if day > capture_end:
            continue
        if any(raw.get(field) is None for field in FIELDS):
            missing.append(day)
            continue
        output[day] = nominal_row(day=day, raw=raw, events=events, capture_end=capture_end)
    return dict(ticker=ticker, status='CONDITIONAL_COORDINATES_WITH_MISSING_ROWS' if missing else 'CONDITIONAL_COORDINATES_ONLY', events=events,
                nominal_ohlc=output, missing_ohlc_dates=missing, execution_admitted=False,
                supplied_rows_complete=not missing, external_source_certified=False,
                historical_identity_admitted=False, total_return=False,
                training_rule='DIVIDE_NOMINAL_BY_TRUE_SPLITS_STRICTLY_AFTER_DAY_THROUGH_DECISION',
                price_basis='CONDITIONAL_RESTORED_NOMINAL_NOT_CERTIFIED')
