"""Bounded raw-first current quote-channel capture. Default performs zero HTTP."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
OBSERVATION = ROOT / 'data/cache/research/current_quote_list_observation_20261013_v1/observation.json'
OBSERVATION_SHA = '41573c3b20f683f1565e969be689d1eac52b4d1b4fb0d29d8c5b9c477e371fbf'
OUTPUT = ROOT / 'data/cache/research/current_raw_capture_20261013_v1'
TARGET = '2026-10-12'
MAX_BYTES = 8_000_000
PERIOD1 = 1640995200  # 2022-01-01 UTC, explicitly unchanged history horizon.
NY = ZoneInfo('America/New_York')
FLAGS = dict(point_in_time_membership_verified=False, security_identity_verified=False,
             quote_basis_authenticated=False, exchange_calendar_verified=False,
             complete_corporate_actions_verified=False, prices_reconstructed=False,
             legal_training_input_admitted=False, promotion_allowed=False,
             live_mutation_allowed=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


LOADED_SHA = digest(SOURCE.read_bytes())


def loads(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('nonfinite JSON literal: ' + value)
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('overflowing JSON number')
        return parsed
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid, parse_float=finite_float)


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    if path.read_bytes() != raw:
        raise ValueError('durable readback differs')
    return digest(raw)


def safe_directory(path):
    for candidate in (path, *path.parents):
        if candidate.exists() and (candidate.is_symlink() or getattr(candidate.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('reparse/symlink path is forbidden')


def utc_now():
    return datetime.now(timezone.utc)


def validate_clock(clock):
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset().total_seconds() != 0:
        raise ValueError('aware UTC clock required')
    if clock.date().isoformat() != '2026-10-13' or clock.astimezone(NY).date().isoformat() != '2026-10-13':
        raise ValueError('dedicated UTC and New York 2026-10-13 window required')
    if clock.astimezone(NY).date().isoformat() <= TARGET:
        raise ValueError('target must precede actual receipt New York day')


def guard(runner_sha):
    if type(runner_sha) is not str or LOADED_SHA != runner_sha or digest(SOURCE.read_bytes()) != runner_sha:
        raise ValueError('external runner SHA differs')
    raw = OBSERVATION.read_bytes()
    if digest(raw) != OBSERVATION_SHA:
        raise ValueError('fixed current observation SHA differs')
    observation = loads(raw)
    symbols = observation['observed_symbols']
    if (observation.get('schema') != 'ndx_current_quote_list_observation_v1'
            or observation.get('observed_security_count') != 101 or len(symbols) != 101
            or len(set(symbols)) != 101 or observation.get('point_in_time_membership_verified') is not False
            or any(type(ticker) is not str or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,14}', ticker) for ticker in symbols)):
        raise ValueError('current observation denominator/scope differs')
    queue = list(dict.fromkeys(symbols + ['TSM', 'QQQ', 'SPY']))
    if len(queue) > 104:
        raise ValueError('queue exceeds 104')
    return queue


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def default_open(request, **kwargs):
    return build_opener(NoRedirect()).open(request, **kwargs)


def decode(raw, ticker, received):
    """Observation, not nominal reconstruction or exchange/session certification."""
    validate_clock(received)
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            decoded = compressed.read(MAX_BYTES + 1)
    else:
        decoded = raw
    if len(decoded) > MAX_BYTES:
        raise ValueError('decoded body exceeds bounded limit')
    body = loads(decoded)
    chart = body['chart']
    if chart.get('error') is not None or len(chart.get('result') or []) != 1:
        raise ValueError('one successful provider result required')
    channel = chart['result'][0]
    metadata = channel['meta']
    if (metadata.get('symbol') != ticker or metadata.get('currency') != 'USD'
            or metadata.get('exchangeTimezoneName') != 'America/New_York'
            or metadata.get('dataGranularity') != '1d'):
        raise ValueError('provider metadata differs')
    stamps = channel['timestamp']
    if not 1 <= len(stamps) <= 20_000 or any(type(stamp) is not int or stamp <= 0 for stamp in stamps) or stamps != sorted(set(stamps)):
        raise ValueError('invalid ordered provider timestamps')
    dates = [datetime.fromtimestamp(stamp, timezone.utc).astimezone(NY).date().isoformat() for stamp in stamps]
    if dates != sorted(set(dates)):
        raise ValueError('duplicate or unordered New York dates')
    quotes = channel['indicators']['quote']
    if len(quotes) != 1 or any(len(quotes[0][key]) != len(stamps) for key in ('open', 'high', 'low', 'close', 'volume')):
        raise ValueError('OHLCV dimensions differ')
    target_values = None
    missing_by_date = {}
    for index, day in enumerate(dates):
        values = {key: quotes[0][key][index] for key in ('open', 'high', 'low', 'close', 'volume')}
        for key, value in values.items():
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (key != 'volume' and value == 0)):
                raise ValueError('invalid raw numerical values')
        missing = [key for key, value in values.items() if value is None]
        if missing:
            missing_by_date[day] = missing
        elif not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
            raise ValueError('inconsistent raw OHLC')
        if day == TARGET:
            target_values = values
    return dict(status='RAW_TARGET_OHLCV_PRESENT_NOT_CALENDAR_CERTIFIED' if target_values and all(value is not None for value in target_values.values()) else 'RAW_TARGET_MISSING_OR_INCOMPLETE',
                decoded_sha256=digest(decoded), provider_metadata=metadata,
                raw_returned_events=channel.get('events', {}), raw_row_count=len(stamps),
                first_provider_date=dates[0], last_provider_date=dates[-1],
                target_date=TARGET, target_provider_fields=target_values,
                missing_fields_by_date=missing_by_date,
                target_provider_timestamp=None if TARGET not in dates else stamps[dates.index(TARGET)],
                actual_received_at_utc=received.isoformat(), receipt_new_york_date=received.astimezone(NY).date().isoformat(),
                excluded_dates=[day for day in dates if day > TARGET],
                target_precedes_receipt_new_york_day=True,
                close_time_certified=False, provider_dates_are_exchange_calendar=False,
                quote_price_unit='PROVIDER_RETURNED_NOT_CERTIFIED_NOMINAL', volume_unit='UNKNOWN_PROVIDER_UNIT', **FLAGS)


def capture_one(ticker, runner_sha, *, opener, clock):
    guard(runner_sha); start = clock(); validate_clock(start); safe_directory(OUTPUT)
    if any(OUTPUT.glob(ticker + '.*')):
        raise FileExistsError('existing ticker evidence; no retry')
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={PERIOD1}&period2={int(start.timestamp())}&interval=1d&events=div,splits'
    started = dict(ticker=ticker, runner_sha256=runner_sha, observation_sha256=OBSERVATION_SHA,
                   target_date=TARGET, request_url=url, started_at_utc=start.isoformat(),
                   attempt_count=1, request_method='GET', credentials_sent=False)
    started_sha = save(OUTPUT / (ticker + '.started.json'), started)
    receipt = dict(started, started_sha256=started_sha, status='TRANSPORT_FAILED')
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}
    raw = None
    try:
        try:
            response = opener(Request(url, headers=headers), timeout=35)
        except HTTPError as error:
            response = error
        with response:
            receipt.update(http_status=response.status, final_url=response.url,
                           response_headers={key: response.headers.get(key) for key in ('Date','Content-Type','Content-Encoding','Content-Length','ETag','Last-Modified')})
            raw = b''
            while len(raw) <= MAX_BYTES:
                chunk = response.read(min(65536, MAX_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw += chunk
            receipt['status'] = 'BODY_LIMIT_FAILED' if len(raw) > MAX_BYTES else 'HTTP_FAILED' if response.status != 200 or response.url != url else 'RAW_CAPTURED'
    except Exception as error:
        receipt.update(error_type=type(error).__name__, status='TRANSPORT_FAILED')
    if raw is not None:
        raw_path = OUTPUT / (ticker + '.response.bin')
        safe_directory(raw_path)
        with raw_path.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        if raw_path.read_bytes() != raw:
            raise ValueError('raw readback differs')
        receipt.update(raw_path=str(raw_path), raw_sha256=digest(raw), raw_bytes=len(raw),
                       body_truncated=len(raw) > MAX_BYTES, truncated_bytes_retained=len(raw) > MAX_BYTES,
                       transport_partial_payload_preserved=receipt['status'] == 'TRANSPORT_FAILED')
    received = clock()
    try:
        validate_clock(received)
        if received < start:
            raise ValueError('clock moved backwards')
        receipt.update(received_at_utc=received.isoformat(), receipt_new_york_date=received.astimezone(NY).date().isoformat())
    except Exception as error:
        receipt.update(status='CLOCK_FAILED', clock_error_type=type(error).__name__,
                       received_clock_observation=str(received))
    receipt.update(request_headers=headers, **FLAGS)
    safe_directory(OUTPUT)
    receipt_path = OUTPUT / (ticker + '.receipt.json'); receipt_sha = save(receipt_path, receipt)
    observation = dict(ticker=ticker, receipt_sha256=receipt_sha, status=receipt['status'], **FLAGS)
    if receipt['status'] == 'RAW_CAPTURED':
        try:
            observation.update(decode(raw, ticker, received))
        except Exception as error:
            observation.update(status='DECODE_FAILED', error_type=type(error).__name__)
    decoded_path = OUTPUT / (ticker + '.decoded.json'); decoded_sha = save(decoded_path, observation)
    return dict(ticker=ticker, receipt_sha256=receipt_sha, decoded_sha256=decoded_sha,
                status=observation['status'], raw_sha256=receipt.get('raw_sha256'))


def validate_previous(queue, runner_sha, index_sha, *, lock_held=False):
    indices = sorted(OUTPUT.glob('completion_index_*.json')) if OUTPUT.exists() else []
    entries = []
    if indices:
        if not index_sha or digest(indices[-1].read_bytes()) != index_sha:
            raise ValueError('latest fixed-directory index SHA required')
        index = loads(indices[-1].read_bytes())
        if index.get('runner_sha256') != runner_sha or index.get('observation_sha256') != OBSERVATION_SHA or index.get('queue') != queue or index.get('target_date') != TARGET:
            raise ValueError('previous index binding differs')
        entries = index['entries']
    elif index_sha:
        raise ValueError('index SHA provided without an index')
    if [entry['ticker'] for entry in entries] != queue[:len(entries)]:
        raise ValueError('completed attempt prefix differs')
    expected = {path.name for path in indices}
    if lock_held:
        expected.add('.batch.lock')
    for entry in entries:
        ticker = entry['ticker']
        for kind in ('receipt', 'decoded'):
            path = OUTPUT / f'{ticker}.{kind}.json'
            if digest(path.read_bytes()) != entry[kind + '_sha256']:
                raise ValueError('saved entry SHA differs')
            expected.add(path.name)
        receipt = loads((OUTPUT / f'{ticker}.receipt.json').read_bytes())
        started_path = OUTPUT / f'{ticker}.started.json'; expected.add(started_path.name)
        if digest(started_path.read_bytes()) != receipt['started_sha256'] or receipt['ticker'] != ticker or receipt['attempt_count'] != 1:
            raise ValueError('started/receipt binding differs')
        if entry.get('raw_sha256'):
            path = OUTPUT / f'{ticker}.response.bin'; expected.add(path.name)
            if digest(path.read_bytes()) != entry['raw_sha256'] or receipt.get('raw_sha256') != entry['raw_sha256']:
                raise ValueError('saved raw SHA differs')
    observed = {path.name for path in OUTPUT.iterdir()} if OUTPUT.exists() else set()
    if observed != expected:
        raise ValueError('orphan/unindexed evidence; offline reconciliation required, never retry')
    return entries


def run(*, runner_sha, execute=False, max_new=1, workers=1, index_sha=None,
        opener=default_open, clock=utc_now):
    if type(execute) is not bool or type(max_new) is not int or not 1 <= max_new <= 8 or type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('explicit max_new 1..8 and workers 1..4 required')
    queue = guard(runner_sha); safe_directory(OUTPUT)
    entries = validate_previous(queue, runner_sha, index_sha)
    if not execute:
        return dict(network_requests=0, queue=queue, completed_attempts=len(entries), target_date=TARGET, **FLAGS)
    if len(entries) == len(queue):
        return dict(network_requests=0, completed_attempts=len(entries), queue_count=len(queue), **FLAGS)
    validate_clock(clock()); OUTPUT.mkdir(parents=True, exist_ok=True); safe_directory(OUTPUT)
    # Fixed directory lock blocks concurrent processes before any request. Orphan
    # channel files continue to block after a crashed batch; never auto-retry.
    lock = OUTPUT / '.batch.lock'
    with lock.open('xb') as stream:
        stream.write(b'bounded batch in progress\n'); stream.flush(); os.fsync(stream.fileno())
    try:
        # Repeat all source/namespace checks after acquiring lock, allowing only it.
        entries = validate_previous(queue, runner_sha, index_sha, lock_held=True)
        tasks = queue[len(entries):len(entries) + max_new]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            completed = list(executor.map(lambda ticker: capture_one(ticker, runner_sha, opener=opener, clock=clock), tasks))
        entries = entries + completed
        guard(runner_sha)
        index = dict(schema='CURRENT_RAW_CAPTURE_20261013_V1', queue=queue, target_date=TARGET,
                     observation_sha256=OBSERVATION_SHA, runner_sha256=runner_sha, entries=entries,
                     completed_attempts=len(entries), previous_index_sha256=index_sha, **FLAGS)
        safe_directory(OUTPUT)
        path = OUTPUT / f'completion_index_{len(entries):03d}.json'; sha = save(path, index)
        return dict(network_requests=len(tasks), completed_attempts=len(entries), queue_count=len(queue),
                    last_index=str(path), last_index_sha256=sha, statuses=[entry['status'] for entry in completed], **FLAGS)
    finally:
        if lock.exists():
            lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner-sha', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--max-new', type=int, default=1)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--index-sha')
    arguments = parser.parse_args()
    print(json.dumps(run(runner_sha=arguments.runner_sha, execute=arguments.execute,
                         max_new=arguments.max_new, workers=arguments.workers,
                         index_sha=arguments.index_sha), allow_nan=False))
