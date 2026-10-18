"""Read pinned saved chart evidence; no network or corporate-action certification."""
from datetime import date, datetime
from decimal import Decimal
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
MAX_BYTES = 32 * 1024 * 1024


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('NONFINITE_JSON:' + value)
    return json.loads(raw, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def read_saved_quote(*, root, ticker, expected_security_type, entry,
                     relative_directory, decision_date, decision_session_close_at):
    """Caller authenticates close_at/calendar and entry pins, not this decoder.

    Receipt after supplied close is a necessary completion check, not proof of
    provider finality, exchange-calendar accuracy or action completeness.
    Later returned bars never substitute for the exact requested decision bar.
    """
    _require(isinstance(ticker, str) and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,14}', ticker), 'INVALID_TICKER')
    _require(expected_security_type in ('EQUITY', 'ETF'), 'INVALID_SECURITY_TYPE')
    _require(type(decision_date) is str and date.fromisoformat(decision_date).isoformat() == decision_date, 'INVALID_DECISION_DATE')
    close_at = datetime.fromisoformat(decision_session_close_at)
    _require(close_at.tzinfo is not None and close_at.date().isoformat() == decision_date
             and close_at.astimezone(NY).date().isoformat() == decision_date
             and close_at.utcoffset() == close_at.astimezone(NY).utcoffset(), 'INVALID_NEW_YORK_CLOSE_TIME')
    root = Path(root).resolve()
    relative = Path(relative_directory)
    _require(not relative.is_absolute() and '..' not in relative.parts, 'INVALID_RELATIVE_DIRECTORY')
    pins = {}
    def read(suffix, pin_key):
        name = relative / (ticker + suffix)
        path = (root / name).resolve()
        _require(path.is_relative_to(root), 'SOURCE_OUTSIDE_ROOT')
        expected = entry[pin_key]
        _require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'INVALID_SOURCE_PIN')
        _require(path.stat().st_size <= MAX_BYTES, 'SOURCE_TOO_LARGE')
        raw = path.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_HASH_MISMATCH')
        pins[name.as_posix()] = expected
        return raw
    raw = read('.response.bin', 'raw_sha256')
    receipt = _json(read('.receipt.json', 'receipt_sha256'))
    observation = _json(read('.decoded.json', 'decoded_sha256'))
    _require(receipt['http_status'] == 200 and receipt['ticker'] == ticker
             and receipt['raw_sha256'] == entry['raw_sha256'] and not receipt.get('body_truncated', False), 'RECEIPT_BINDING_MISMATCH')
    received = datetime.fromisoformat(receipt['received_at_utc'])
    _require(received.tzinfo is not None and received >= close_at, 'CAPTURE_BEFORE_DECLARED_SESSION_CLOSE')
    _require(observation['ticker'] == ticker and observation['receipt_sha256'] == entry['receipt_sha256'], 'OBSERVATION_BINDING_MISMATCH')
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            decoded = stream.read(MAX_BYTES + 1)
    else:
        decoded = raw
    _require(len(decoded) <= MAX_BYTES and hashlib.sha256(decoded).hexdigest() == observation['decoded_sha256'], 'DECODED_HASH_MISMATCH')
    chart = _json(decoded)['chart']
    _require(chart.get('error') is None and len(chart.get('result') or []) == 1, 'INVALID_CHART_RESULT')
    channel = chart['result'][0]
    meta = channel['meta']
    _require(meta['symbol'] == ticker and meta['currency'] == 'USD'
             and meta['instrumentType'] == expected_security_type
             and meta['exchangeTimezoneName'] == 'America/New_York'
             and meta.get('dataGranularity') == '1d', 'SECURITY_OR_PRICE_COORDINATE_MISMATCH')
    timestamps = channel['timestamp']
    _require(isinstance(timestamps, list) and timestamps and all(type(t) is int and t > 0 for t in timestamps)
             and timestamps == sorted(set(timestamps)), 'INVALID_TIMESTAMPS')
    dates = [datetime.fromtimestamp(t, NY).date().isoformat() for t in timestamps]
    _require(dates == sorted(set(dates)) and decision_date in dates, 'DECISION_BAR_MISSING_OR_DUPLICATE')
    rows = channel['indicators']['quote']
    _require(len(rows) == 1 and all(len(rows[0][key]) == len(dates) for key in ('open','high','low','close')), 'OHLC_ALIGNMENT_MISMATCH')
    index = dates.index(decision_date)
    def positive(value):
        _require(not isinstance(value, bool) and isinstance(value, (int, Decimal)), 'INVALID_OHLC_VALUE')
        value = Decimal(value)
        _require(value.is_finite() and value > 0, 'INVALID_OHLC_VALUE')
        return value
    bar = {key: positive(rows[0][key][index]) for key in ('open','high','low','close')}
    _require(bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high'], 'INVALID_OHLC_RANGE')
    events = channel.get('events', {})
    _require(isinstance(events, dict) and events == observation['raw_returned_events'], 'RETURNED_EVENTS_MISMATCH')
    details = []
    for kind, records in events.items():
        _require(isinstance(records, dict), 'INVALID_EVENT_COLLECTION')
        for event_id, event in records.items():
            _require(isinstance(event, dict) and type(event.get('date')) is int, 'INVALID_EVENT_DATE')
            event_day = datetime.fromtimestamp(event['date'], NY).date().isoformat()
            details.append(dict(kind=kind, event_id=event_id, session=event_day,
                after_decision=event_day > decision_date, fields=_plain(event)))
    reference = None
    market_time = meta.get('regularMarketTime')
    if type(market_time) is int and datetime.fromtimestamp(market_time, NY).date().isoformat() == decision_date:
        price = positive(meta['regularMarketPrice'])
        _require(price.quantize(Decimal('.01')) == bar['close'].quantize(Decimal('.01')), 'REFERENCE_CLOSE_CENT_MISMATCH')
        reference = dict(price=str(price), as_of=decision_date, price_kind='PROVIDER_REGULAR_MARKET_PRICE_DECIMAL')
    return dict(ticker=ticker, security_type=expected_security_type, decision_date=decision_date,
        ohlc={key:str(value) for key,value in bar.items()}, reference_quote=reference,
        source_hashes=pins, received_at=received.isoformat(), declared_session_close_at=close_at.isoformat(),
        completion_basis='CAPTURE_AFTER_CALLER_AUTHENTICATED_SESSION_CLOSE_NOT_PROVIDER_FINALITY_CERTIFICATION',
        later_provider_dates=[day for day in dates if day > decision_date],
        raw_returned_events=_plain(events), event_details=details,
        provider_current_trading_period=_plain(meta.get('currentTradingPeriod')),
        price_basis='PROVIDER_RETURNED_NOT_CERTIFIED_NOMINAL',
        exchange_calendar_verified=False, complete_corporate_actions_verified=False,
        no_unprocessed_actions_certified=False, research_only=True, execution_blocked=True)
