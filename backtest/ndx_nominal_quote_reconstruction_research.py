"""Conditional split-only quote reconstruction; no price-identity adjudication."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASIS = 'SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS'
NEW_YORK = ZoneInfo('America/New_York')


def verify(sources):
    if type(sources) is not dict or not sources:
        raise ValueError('Explicit nonempty source bindings required')
    for path, expected in sources.items():
        if (type(path) is not str or not Path(path).is_absolute() or type(expected) is not str
                or re.fullmatch('[0-9a-f]{64}', expected) is None
                or hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected):
            raise ValueError('Nominal reconstruction source drift: ' + str(path))


def _unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('Duplicate raw JSON key: ' + key)
        output[key] = value
    return output


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('Finite positive nonboolean price or split value required')
    return value


def _timestamp(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Positive integer epoch timestamp required')
    return datetime.fromtimestamp(value, timezone.utc)


def _day(value):
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is None:
        raise ValueError('Canonical session date required')
    if datetime.strptime(value, '%Y-%m-%d').date().isoformat() != value:
        raise ValueError('Invalid session date')
    return value


def reconstruct_nominal_quote_ticker(*, raw, ticker, calendar, request, received_at_utc, quote_field_basis):
    """Use an explicit independently supplied basis, without authenticating it."""
    if quote_field_basis != BASIS:
        raise ValueError('Unknown/unsupported quote field basis; adjclose cannot be reconstructed here')
    if type(raw) is not bytes or type(ticker) is not str or re.fullmatch('[A-Z][A-Z0-9.-]*', ticker) is None:
        raise ValueError('Explicit raw bytes and ticker required')
    if type(calendar) is not list or not calendar or calendar != sorted(set(map(_day, calendar))):
        raise ValueError('Unique strictly ascending explicit calendar required')
    received = datetime.fromisoformat(received_at_utc)
    if received.tzinfo is None or received.utcoffset().total_seconds() != 0:
        raise ValueError('Explicit UTC reception timestamp required')
    if request.get('method') != 'GET' or request.get('credentials_sent') is not False:
        raise ValueError('Explicit public GET request required')
    url = urlparse(request['url'])
    query = parse_qs(url.query, keep_blank_values=True)
    if (url.scheme != 'https' or url.netloc != 'query1.finance.yahoo.com'
            or url.path != '/v8/finance/chart/' + ticker or url.fragment
            or set(query) != {'period1', 'period2', 'interval', 'events'}
            or query.get('interval') != ['1d'] or query.get('events') != ['div,splits']
            or any(len(query.get(key, [])) != 1 or re.fullmatch('[0-9]+', query[key][0]) is None
                   for key in ('period1', 'period2'))):
        raise ValueError('Request ticker/daily/split-event coverage differs')
    start, end = (int(query[key][0]) for key in ('period1', 'period2'))
    if (_timestamp(start) >= _timestamp(end) or _timestamp(end) > received
            or _timestamp(end).astimezone(NEW_YORK).date() != received.astimezone(NEW_YORK).date()
            or _timestamp(start).astimezone(NEW_YORK).date().isoformat() > calendar[0]
            or _timestamp(end).astimezone(NEW_YORK).date().isoformat() < calendar[-1]):
        raise ValueError('Request interval must cover calendar through reception market date without future data')
    chart = json.loads(raw, object_pairs_hook=_unique_pairs)['chart']
    if chart.get('error') is not None or type(chart.get('result')) is not list or len(chart['result']) != 1:
        raise ValueError('Unique successful chart response required')
    data = chart['result'][0]
    meta = data['meta']
    if (meta.get('symbol') != ticker or meta.get('currency') != 'USD'
            or meta.get('exchangeTimezoneName') != 'America/New_York'
            or meta.get('instrumentType') != 'EQUITY' or meta.get('dataGranularity') != '1d'):
        raise ValueError('Response ticker/currency/market/basis coordinates differ')
    timestamps = data['timestamp']
    quotes = data['indicators']['quote']
    if type(timestamps) is not list or not timestamps or type(quotes) is not list or len(quotes) != 1:
        raise ValueError('Explicit timestamp and unique quote arrays required')
    quote = quotes[0]
    if any(type(quote.get(key)) is not list or len(quote[key]) != len(timestamps) for key in ('open', 'close')):
        raise ValueError('Complete Open/Close timestamp denominator required')
    daily = {}
    previous = None
    for index, timestamp in enumerate(timestamps):
        instant = _timestamp(timestamp)
        day = instant.astimezone(NEW_YORK).date().isoformat()
        if (timestamp < start or timestamp >= end or day in daily
                or (previous is not None and timestamp <= previous)):
            raise ValueError('Duplicate/unordered/out-of-request daily quote date')
        previous = timestamp
        daily[day] = dict(timestamp=timestamp, open=_number(quote['open'][index]), close=_number(quote['close'][index]))
    if not set(calendar) <= set(daily):
        raise ValueError('Supplied schedule calendar has missing quote sessions')
    events = data.get('events', {})
    if type(events) is not dict or type(events.get('splits', {})) is not dict:
        raise ValueError('Explicit split event mapping required')
    splits, seen_days = [], set()
    for key, event in events.get('splits', {}).items():
        date = event['date']
        instant = _timestamp(date)
        day = instant.astimezone(NEW_YORK).date().isoformat()
        if (key != str(date) or day in seen_days or date < start or date >= end
                or instant > received or day not in daily):
            raise ValueError('Split key/date conflict, duplicate effective day, or uncovered split session')
        seen_days.add(day)
        numerator, denominator = _number(event['numerator']), _number(event['denominator'])
        ratio = Fraction(str(numerator)) / Fraction(str(denominator))
        text = event['splitRatio']
        if type(text) is not str or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?:[0-9]+(?:\.[0-9]+)?', text) is None:
            raise ValueError('Explicit split ratio text required')
        first, second = text.split(':')
        if Fraction(second) <= 0 or Fraction(first) <= 0 or Fraction(first) / Fraction(second) != ratio:
            raise ValueError('Split numerator/denominator and ratio text conflict')
        splits.append(dict(effective_session=day, provider_timestamp=date,
                           numerator=str(ratio.numerator), denominator=str(ratio.denominator)))
    splits.sort(key=lambda row: row['effective_session'])
    rows = []
    for day in calendar:
        # Effective-day quotes already use new shares: never undo their own split.
        later = [event for event in splits if event['effective_session'] > day]
        factor = Fraction(1)
        for event in later:
            factor *= Fraction(int(event['numerator']), int(event['denominator']))
        factor_float = float(factor)
        open_price = _number(float(daily[day]['open']) * factor_float)
        close_price = _number(float(daily[day]['close']) * factor_float)
        rows.append(dict(session=day, ticker=ticker, currency='USD',
            provider_timestamp=daily[day]['timestamp'], quote_open=float(daily[day]['open']),
            quote_close=float(daily[day]['close']), nominal_open=open_price, nominal_close=close_price,
            split_factor_numerator=str(factor.numerator), split_factor_denominator=str(factor.denominator),
            split_factor=factor_float, later_split_effective_sessions=[row['effective_session'] for row in later]))
    return dict(ticker=ticker, rows=rows, row_count=len(rows), provider_quote_session_count=len(daily),
        provider_split_events=splits, raw_sha256=hashlib.sha256(raw).hexdigest(),
        requested_event_horizon_end_utc=_timestamp(end).isoformat(), received_at_utc=received_at_utc,
        quote_field_basis=quote_field_basis, basis_was_supplied_not_authenticated=True,
        dividend_event_count=len(events.get('dividends', {})), dividends_applied_to_quote=False,
        adjclose_used=False, split_event_coverage_scope='RETURNED_PROVIDER_EVENTS_WITHIN_REQUEST_ONLY',
        official_split_event_completeness_verified=False, provider_price_identity_verified=False,
        point_in_time_verified=False, promotion_allowed=False)


def build_nominal_quote_research(*, calendar, probes, quote_field_basis, source_hashes):
    """Read bound raw responses; output ticker coordinates and factor evidence."""
    verify(source_hashes)
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != LOADED_SHA:
        raise ValueError('Loaded nominal reconstruction source changed')
    if type(probes) is not dict or not probes:
        raise ValueError('Explicit nonempty ticker probe denominator required')
    output = {}
    for ticker, probe in sorted(probes.items()):
        path = Path(probe['response_path']).resolve()
        if (source_hashes.get(str(path)) != probe['response_sha256'] or probe['http_status'] != 200
                or probe['transport_success'] is not True):
            raise ValueError('Successful raw source binding required')
        raw = path.read_bytes()
        if (len(raw) != probe['response_bytes']
                or hashlib.sha256(raw).hexdigest() != probe['response_sha256']):
            raise ValueError('Raw response byte count differs')
        output[ticker] = reconstruct_nominal_quote_ticker(raw=raw, ticker=ticker, calendar=calendar,
            request=probe['request'], received_at_utc=probe['received_at_utc'], quote_field_basis=quote_field_basis)
    verify(source_hashes)
    sources = dict(source_hashes)
    if str(SOURCE) in sources and sources[str(SOURCE)] != LOADED_SHA:
        raise ValueError('Conflicting reconstruction source')
    sources[str(SOURCE)] = LOADED_SHA
    verify(sources)
    return dict(schema='ndx_nominal_quote_reconstruction_research_v1',
        scope='CONDITIONAL_SPLIT_ONLY_NUMERICAL_RECONSTRUCTION_NOT_IDENTITY_ADJUDICATION',
        calendar=list(calendar), calendar_count=len(calendar), tickers=sorted(output),
        security_count=len(output), total_rows=sum(row['row_count'] for row in output.values()),
        by_ticker=output, source_hashes=sources,
        stable_security_coordinates_assigned=False, quote_basis_authentication_performed=False,
        price_identity_binding_verified=False, official_split_event_completeness_verified=False,
        historical_information_available_at_verified=False, point_in_time_verified=False,
        cache_modified=False, execution_performed=False, promotion_allowed=False)
