"""Declared provider-channel arithmetic; no security identity or investment admission.

The caller must bind raw bytes, quote reconstruction, calendar and every event
policy to evidence. This pure function authenticates none of those assertions.
"""
import gzip
import json
import math
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Nonfinite JSON literal')


def _number(value):
    if type(value) not in (int, float, Decimal):
        raise ValueError('Nonboolean numeric observation required')
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError('Finite positive observation required')
    return result


def _day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Exact ISO date required')
    return value


def _session(stamp):
    if type(stamp) is not int or stamp <= 0:
        raise ValueError('Positive integer provider timestamp required')
    return datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat()


def build_channel_input(*, ticker, raw_bytes, quote_rows, calendar, cutoff,
                        exclude_on_or_after, event_policy, regular_floor=None):
    """Return 126 conditional price returns and a separate liquidity disposition.

    ``event_policy`` lists every returned split, including unmodelled events at
    or before an explicit partition floor. It cannot certify event completeness.
    No provider channel is assigned a fabricated SID or a historical issuer.
    """
    if type(ticker) is not str or not ticker or ticker != ticker.strip():
        raise ValueError('Explicit ticker channel required')
    _day(cutoff); _day(exclude_on_or_after)
    if (type(calendar) is not list or len(calendar) != 127
            or [_day(d) for d in calendar] != sorted(set(calendar))
            or calendar[-1] != cutoff or cutoff >= exclude_on_or_after):
        raise ValueError('Complete 127-session calendar ending before receipt day required')
    if regular_floor is not None and _day(regular_floor) > calendar[0]:
        raise ValueError('Entire input must follow the explicit partition boundary')
    decoded = gzip.decompress(raw_bytes) if raw_bytes[:2] == b'\x1f\x8b' else raw_bytes
    body = json.loads(decoded,
                      parse_float=Decimal, object_pairs_hook=_unique, parse_constant=_invalid_constant)
    chart = body['chart']
    if chart.get('error') is not None or len(chart['result']) != 1:
        raise ValueError('One successful provider channel required')
    data = chart['result'][0]
    metadata = dict(symbol=ticker, currency='USD', instrumentType='EQUITY',
                    exchangeTimezoneName='America/New_York', dataGranularity='1d')
    if any(data['meta'].get(k) != v for k, v in metadata.items()):
        raise ValueError('Provider channel metadata differs')
    times = data['timestamp']; dates = [_session(t) for t in times]
    quotes = data['indicators']['quote']
    if dates != sorted(set(dates)) or len(quotes) != 1:
        raise ValueError('One unique ordered daily quote channel required')
    quotes = quotes[0]
    if any(len(quotes[k]) != len(dates) for k in ('open', 'close', 'volume')):
        raise ValueError('Raw dimensions differ')
    if [d for d in dates if d <= cutoff][-127:] != calendar:
        raise ValueError('Missing or compressed latest observed sessions')
    events = data.get('events', {})
    if (type(events) is not dict or set(events) - {'splits', 'dividends'}
            or type(events.get('splits', {})) is not dict
            or type(events.get('dividends', {})) is not dict):
        raise ValueError('Unknown or malformed returned event channel')
    parsed = []
    for key, item in events.get('splits', {}).items():
        session = _session(item['date'])
        ratio = Fraction(_number(item['numerator'])) / Fraction(_number(item['denominator']))
        text = item['splitRatio']
        if type(text) is not str or len(text.split(':')) != 2:
            raise ValueError('Positive numerator:denominator split text required')
        numerator, denominator = text.split(':')
        text_ratio = Fraction(_number(Decimal(numerator))) / Fraction(_number(Decimal(denominator)))
        if str(item['date']) != key or text_ratio != ratio:
            raise ValueError('Inconsistent raw split ratio or timestamp')
        parsed.append(dict(session=session, numerator=ratio.numerator, denominator=ratio.denominator))
    parsed.sort(key=lambda e: e['session'])
    if len({e['session'] for e in parsed}) != len(parsed):
        raise ValueError('Duplicate event session')
    if type(event_policy) is not list or len(event_policy) != len(parsed):
        raise ValueError('Every returned split requires an explicit policy')
    ordinary = {}
    for event, policy in zip(parsed, event_policy):
        if (type(policy) is not dict
                or set(policy) != {'session', 'numerator', 'denominator', 'kind'}
                or any(policy.get(k) != v for k, v in event.items())
                or any(type(policy[k]) is not int for k in ('numerator', 'denominator'))):
            raise ValueError('Ordered full raw event denominator differs')
        if policy['kind'] == 'ORDINARY_SPLIT':
            ordinary[event['session']] = Fraction(event['numerator'], event['denominator'])
        elif policy['kind'] == 'BEFORE_PARTITION_UNMODELLED':
            if regular_floor is None or event['session'] > regular_floor:
                raise ValueError('Unmodelled event must precede the entire partition')
        else:
            raise ValueError('Unrecognised event policy')
        if calendar[0] < event['session'] <= cutoff and event['session'] not in calendar:
            raise ValueError('In-window event lacks its actual observation session')
    if type(quote_rows) is not list or not quote_rows:
        raise ValueError('Explicit conditional nominal rows required')
    by_day = {r['session']: r for r in quote_rows}
    if len(by_day) != len(quote_rows) or list(by_day) != sorted(by_day):
        raise ValueError('Unique ordered nominal quote rows required')
    if any(d not in by_day for d in calendar):
        raise ValueError('Missing nominal price or predecessor')
    positions = {d: i for i, d in enumerate(dates)}
    maximum = Decimal(0); prices = []; return_rows = []
    with localcontext() as context:
        context.prec = 50
        for session in calendar:
            row = by_day[session]; index = positions[session]
            if (row['ticker'] != ticker or row['currency'] != 'USD'
                    or type(row['provider_timestamp']) is not int or row['provider_timestamp'] != times[index]):
                raise ValueError('Nominal daily channel differs')
            factor = Fraction(1)
            later = []
            for event_day, ratio in ordinary.items():
                if event_day > session:
                    factor *= ratio; later.append(event_day)
            if (row['split_factor_numerator'] != str(factor.numerator)
                    or row['split_factor_denominator'] != str(factor.denominator)
                    or type(row['split_factor']) not in (int, float)
                    or row['split_factor'] != float(factor)
                    or row['later_split_effective_sessions'] != later):
                raise ValueError('Complete later-event reconstruction factor differs')
            for field in ('open', 'close'):
                raw_price = _number(quotes[field][index])
                expected = raw_price * Decimal(factor.numerator) / Decimal(factor.denominator)
                actual = _number(row['nominal_' + field])
                if _number(row['quote_' + field]) != raw_price:
                    raise ValueError('Saved source quote differs')
                error = abs(actual - expected); maximum = max(maximum, error)
                if error > max(Decimal('1e-10'), abs(expected) * Decimal('1e-12')):
                    raise ValueError('Nominal reconstruction differs from original raw')
            prices.append(dict(session=session, nominal_close=float(_number(row['nominal_close']))))
        for before, after in zip(calendar, calendar[1:]):
            ratio = ordinary.get(after, Fraction(1))
            value = float(Fraction(_number(by_day[after]['nominal_close'])) * ratio
                          / Fraction(_number(by_day[before]['nominal_close'])) - 1)
            if not math.isfinite(value):
                raise ValueError('Finite computed return required')
            return_rows.append(dict(previous_session=before, session=after,
                                    declared_share_ratio=str(ratio), price_return=value))
        liquid = calendar[-63:]
        affected = [e for e in parsed if e['session'] >= liquid[0]]
        liquidity = dict(status='BLOCKED_VOLUME_UNIT_UNKNOWN', rows=None,
                         median_dollar_volume_usd=None, numerical_threshold_passed=None,
                         affecting_returned_events=affected)
        if not affected:
            rows = []
            for session in liquid:
                volume = quotes['volume'][positions[session]]
                if type(volume) is not int or volume <= 0:
                    raise ValueError('Positive integer raw volume required')
                close = _number(by_day[session]['nominal_close'])
                rows.append(dict(session=session, raw_volume=volume,
                                 dollar_volume=str(close * volume)))
            median = sorted(Decimal(r['dollar_volume']) for r in rows)[31]
            liquidity.update(status='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE', rows=rows,
                             median_dollar_volume_usd=str(median), numerical_threshold_passed=median >= 50000000)
    retained_events = json.loads(decoded, object_pairs_hook=_unique, parse_constant=_invalid_constant)['chart']['result'][0].get('events', {})
    return dict(schema='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1', ticker=ticker, cutoff=cutoff,
                coordinate_kind='PROVIDER_TICKER_CHANNEL_NOT_SECURITY_ID', calendar=list(calendar),
                regular_floor=regular_floor, returned_events=retained_events, event_policy=deepcopy(event_policy),
                price_rows=prices, price_returns=return_rows, liquidity=liquidity,
                maximum_nominal_reconstruction_error=str(maximum),
                minimum_median_dollar_volume_usd=50000000,
                event_policy_is_external_unverified_assertion=True,
                zero_unreported_events_is_explicit_research_condition=True,
                source_assertions_authenticated=False, security_identity_verified=False,
                volume_units_independently_certified=False, complete_actions_verified=False,
                exchange_calendar_verified=False, dividend_cash_flows_included=False,
                legal_training_input_admitted=False, fit_performed=False,
                point_in_time_verified=False, promotion_allowed=False)
