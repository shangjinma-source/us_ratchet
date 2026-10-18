"""Explicit completed-session minute evidence; never a contemporaneous quote.

The caller supplies reviewed session boundaries and security identity. Provider
metadata's current trading period is not used as a historical calendar.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import json
import re

LIMIT = 4 * 1024 * 1024


def require(ok, reason):
    if not ok: raise ValueError(reason)


def stamp(value):
    result = datetime.fromisoformat(value)
    require(result.utcoffset() is not None, 'AWARE_TIME_REQUIRED')
    return result.astimezone(timezone.utc)


def boundaries(session, session_open, session_close):
    opening, closing = stamp(session_open), stamp(session_close)
    require(opening < closing <= opening+timedelta(hours=8)
            and all(not x.second and not x.microsecond and
                    x.astimezone(ZoneInfo('America/New_York')).date().isoformat() == session
                    for x in (opening, closing)), 'INVALID_SESSION_BOUNDARY')
    return opening, closing


def request_url(ticker, opening, closing):
    require(type(ticker) is str and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}', ticker), 'INVALID_TICKER')
    return 'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker, safe='')+'?'+urlencode(
        dict(interval='1m', period1=int(opening.timestamp()), period2=int(closing.timestamp()),
             includePrePost='false', events='div,splits'))


def fetch_bytes(url):
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=10) as response:
        require(response.status == 200 and response.geturl() == url, 'UNEXPECTED_HTTP_RESPONSE')
        raw = response.read(LIMIT+1)
    require(len(raw) <= LIMIT, 'RESPONSE_TOO_LARGE')
    return raw


def decode(raw, *, security_id, ticker, session, session_open, session_close, captured_at):
    opening, closing = boundaries(session, session_open, session_close)
    captured = stamp(captured_at)
    require(captured >= closing, 'SESSION_NOT_COMPLETED')
    require(type(security_id) is str and security_id.strip(), 'SECURITY_ID_REQUIRED')
    require(type(raw) is bytes and len(raw) <= LIMIT, 'INVALID_RAW_BYTES')
    chart = json.loads(raw, parse_float=Decimal)['chart']
    require(chart.get('error') is None and len(chart['result']) == 1, 'INVALID_CHART')
    result = chart['result'][0]; meta = result['meta']
    require(meta.get('symbol') == ticker and meta.get('currency') == 'USD'
            and meta.get('instrumentType') == 'EQUITY' and meta.get('dataGranularity') == '1m'
            and meta.get('exchangeTimezoneName') == 'America/New_York', 'SOURCE_IDENTITY_MISMATCH')
    require(not any(v for k,v in result.get('events', {}).items() if k != 'dividends'), 'UNIT_ACTION_REVIEW_REQUIRED')
    timestamps = result['timestamp']; quotes = result['indicators']['quote']
    require(type(timestamps) is list and len(timestamps) <= 1440 and len(quotes) == 1, 'BOUNDED_MINUTES_REQUIRED')
    q = quotes[0]
    require(all(len(q[k]) == len(timestamps) for k in ('open','high','low','close','volume')), 'ARRAY_LENGTH_MISMATCH')
    require(all(type(t) is int for t in timestamps) and timestamps == sorted(set(timestamps)), 'ORDERED_UNIQUE_TIMESTAMPS_REQUIRED')
    minutes = []; returned = set()
    for i, t in enumerate(timestamps):
        start = datetime.fromtimestamp(t, timezone.utc); end = start+timedelta(minutes=1)
        if not opening <= start < closing: continue
        require(not start.second and end <= closing and end <= captured, 'INVALID_MINUTE_BOUNDARY')
        if any(q[k][i] is None for k in ('open','high','low','close','volume')): continue
        values = [Decimal(str(q[k][i])) for k in ('open','high','low','close','volume')]
        require(all(v.is_finite() for v in values), 'INVALID_OHLC')
        o,h,l,c,volume = values
        require(0 < l <= min(o,c) <= max(o,c) <= h and volume >= 0, 'INVALID_OHLC')
        returned.add(t)
        minutes.append(dict(security_id=security_id, ticker=ticker, session=session,
            start=start.isoformat(), end=end.isoformat(),
            **dict(zip(('open','high','low','close','volume'), map(str, values)))))
    expected = set(range(int(opening.timestamp()), int(closing.timestamp()), 60))
    missing = sorted(expected-returned)
    return dict(status='COMPLETE_SESSION_MINUTES' if not missing else 'UNKNOWN',
        reason=None if not missing else 'INCOMPLETE_SESSION_MINUTES', minutes=minutes,
        missing_minute_starts=[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in missing],
        captured_at=captured.isoformat(), observed_through=captured.isoformat(),
        security_id=security_id, ticker=ticker, session=session,
        session_open=opening.isoformat(), session_close=closing.isoformat(),
        timestamp_basis='ACTUAL_LATER_CAPTURE_NOT_HISTORICAL_RECEIVED_TIME',
        source_authenticated=False, liquidity_verified=False,
        unit_review='Only returned non-dividend events are rejected; omitted or outside-range actions are not certified. Independent continuity review remains required.')


def capture(*, directory, security_id, ticker, session, session_open, session_close,
            calendar_source_reference, fetch=fetch_bytes, clock=lambda:datetime.now(timezone.utc)):
    opening, closing = boundaries(session, session_open, session_close)
    started = stamp(clock().isoformat())
    require(started >= closing, 'SESSION_NOT_COMPLETED')
    require(type(calendar_source_reference) is str and calendar_source_reference.strip(), 'CALENDAR_REFERENCE_REQUIRED')
    url = request_url(ticker, opening, closing)
    output = Path(directory); output.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        with (output/name).open('xb') as stream:
            stream.write(value if type(value) is bytes else json.dumps(value,ensure_ascii=False,sort_keys=True).encode())
    receipt = dict(status='STARTED', security_id=security_id, ticker=ticker, session=session,
        request_url=url, started_at=started.isoformat(), session_open=opening.isoformat(),
        session_close=closing.isoformat(), calendar_source_reference=calendar_source_reference,
        calendar_reference_is_caller_declaration=True, historical_observation_claim=False)
    write('started.json', receipt)
    try:
        raw = fetch(url); captured = stamp(clock().isoformat())
        require(type(raw) is bytes and len(raw) <= LIMIT, 'INVALID_RAW_BYTES')
        write('response.bin', raw)
        receipt.update(captured_at=captured.isoformat(), raw_sha256=sha256(raw).hexdigest())
        require(captured >= started, 'CLOCK_ROLLBACK')
        result = decode(raw, security_id=security_id,ticker=ticker,session=session,
                        session_open=session_open,session_close=session_close,captured_at=captured.isoformat())
        result['source_reference'] = 'sha256:'+receipt['raw_sha256']
        write('minutes.json',result); receipt['status'] = result['status']
    except Exception:
        receipt.update(status='UNKNOWN', reason='CAPTURE_OR_DECODE_UNAVAILABLE')
        write('receipt.json',receipt)
        raise
    write('receipt.json',receipt)
    return result
