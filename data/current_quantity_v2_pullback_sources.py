"""Offline Yahoo raw-byte adapter for the unconnected pullback research kernel.

Hash binding establishes byte integrity, not exchange authenticity. Expected
identity/calendar and capture time are caller-owned declarations. No fetching,
file writes, orders, accepted proposals or default policy parameters.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

from data.current_quantity_v2_pullback_entry import (
    NY, build_pullback_candidate, digest, require, stamp,
)


ADAPTER_VERSION = 'V2_YAHOO_PULLBACK_RAW_ADAPTER_RESEARCH_V1'


def numeric(value):
    require(type(value) in (int, Decimal), 'RAW_NUMERIC_REQUIRED')
    value = Decimal(value)
    require(value.is_finite(), 'NONFINITE_RAW_VALUE')
    return value


def instant(value):
    value = numeric(value)
    require(value == value.to_integral_value(), 'INTEGER_TIMESTAMP_REQUIRED')
    try:
        return datetime.fromtimestamp(int(value), timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise ValueError('INVALID_RAW_TIMESTAMP') from None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('NONFINITE_JSON_CONSTANT')


def candidate_from_yahoo_bytes(*, raw, expected_sha256, security_id, ticker,
                               session, session_open, session_close,
                               captured_at, checked_at, now,
                               rebound_fraction, minimum_discount,
                               maximum_age_seconds, previous_cap):
    require(type(raw) is bytes and 0 < len(raw) <= 4 * 1024 * 1024, 'RAW_BYTES_REQUIRED')
    actual_hash = sha256(raw).hexdigest()
    require(type(expected_sha256) is str and actual_hash == expected_sha256, 'RAW_SHA256_MISMATCH')
    opening, closing, captured, checked, current = map(stamp,
        (session_open, session_close, captured_at, checked_at, now))
    require(opening < closing and opening <= captured <= checked <= current < closing,
            'CAPTURE_OR_SESSION_TIME_INVALID')
    require(all(t.astimezone(NY).date().isoformat() == session for t in
                (opening, closing, captured, checked, current)), 'EXPECTED_SESSION_MISMATCH')
    document = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    chart = document['chart']
    require(chart.get('error') is None and type(chart.get('result')) is list
            and len(chart['result']) == 1, 'RAW_CHART_RESULT_INVALID')
    result = chart['result'][0]
    meta = result['meta']
    require(meta.get('symbol') == ticker and meta.get('currency') == 'USD'
            and meta.get('instrumentType') == 'EQUITY'
            and meta.get('exchangeTimezoneName') == 'America/New_York'
            and meta.get('dataGranularity') == '1m', 'RAW_IDENTITY_OR_GRANULARITY_MISMATCH')
    regular = meta['currentTradingPeriod']['regular']
    require(instant(regular['start']) == opening and instant(regular['end']) == closing,
            'RAW_SESSION_BOUNDARIES_MISMATCH')
    require(not any(value for kind, value in result.get('events', {}).items()
                    if kind != 'dividends'), 'UNPROCESSED_RAW_UNIT_EVENT')
    times = result['timestamp']
    quotes = result['indicators']['quote']
    require(type(times) is list and 0 < len(times) <= 1440
            and type(quotes) is list and len(quotes) == 1, 'RAW_MINUTE_ARRAY_REQUIRED')
    quote = quotes[0]
    require(all(type(quote.get(key)) is list and len(quote[key]) == len(times)
                for key in ('open', 'high', 'low', 'close', 'volume')), 'RAW_ARRAY_LENGTH_MISMATCH')
    identity = dict(security_id=security_id, ticker=ticker, session=session)
    bars = []
    excluded = dict(outside_regular_session=0, incomplete_tail=0, provider_last_trade_snapshot=0)
    prior = None
    for index, value in enumerate(times):
        start = instant(value)
        require(prior is None or prior < start, 'RAW_MINUTES_NOT_ORDERED_UNIQUE')
        require(start <= captured, 'RAW_FUTURE_MINUTE')
        prior = start
        if start.second or start.microsecond:
            # Yahoo can append a last-trade snapshot after the partial minute.
            # It is not a candle and may never supply a session low.
            require(index == len(times) - 1 and start == instant(meta['regularMarketTime'])
                    and opening <= start < closing
                    and start.replace(second=0, microsecond=0)
                    == captured.replace(second=0, microsecond=0)
                    and numeric(quote['volume'][index]) == 0
                    and numeric(quote['open'][index]) > 0
                    and all(numeric(quote[key][index]) == numeric(quote['open'][index])
                            for key in ('high', 'low', 'close')),
                    'RAW_NOT_MINUTE_ALIGNED')
            excluded['provider_last_trade_snapshot'] += 1
            continue
        end = start + timedelta(minutes=1)
        if start < opening or end > closing:
            excluded['outside_regular_session'] += 1
            continue
        if end > captured:
            excluded['incomplete_tail'] += 1
            continue
        values = {key: str(numeric(quote[key][index])) for key in
                  ('open', 'high', 'low', 'close', 'volume')}
        bars.append(dict(identity, start=start.isoformat(), end=end.isoformat(),
                         synthetic=False, **values))
    reference = dict(identity, currency='USD',
        price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
        source_bytes_verified=True, source_hashes={'yahoo_raw': actual_hash},
        session_open=opening.isoformat(), session_close=closing.isoformat(),
        captured_at=captured.isoformat(), checked_at=checked.isoformat(),
        last_at=instant(meta['regularMarketTime']).isoformat(),
        last_price=str(numeric(meta['regularMarketPrice'])), bars=bars)
    candidate = build_pullback_candidate(reference=reference, now=now,
        rebound_fraction=rebound_fraction, minimum_discount=minimum_discount,
        maximum_age_seconds=maximum_age_seconds, previous_cap=previous_cap)
    receipt = dict(adapter_version=ADAPTER_VERSION, raw_sha256=actual_hash,
        raw_byte_count=len(raw), reference_digest=digest(reference),
        candidate_digest=digest(candidate), excluded_rows=excluded,
        source_integrity='RAW_SHA256_AND_DECODE_VERIFIED',
        source_authenticity='CONDITIONAL_PROVIDER_DATA_NOT_EXCHANGE_CERTIFIED',
        calendar_authenticity='CALLER_SUPPLIED_BOUNDARIES_MATCH_PROVIDER',
        research_only=True, orders_created=False)
    return dict(reference=reference, candidate=candidate, receipt=receipt)
