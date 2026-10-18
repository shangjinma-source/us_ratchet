"""Fixed current raw-close research adapter; no fitting, HTTP or publication."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import stat
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
RAW_DIRECTORY = BASE / 'current_raw_capture_20261013_v1'
TARGET = '2026-10-12'
CONTROLS = ('TSM', 'QQQ', 'SPY')
MAX_BYTES = 8_000_000
FIXED_REFERENCES = {
    'observation': (BASE / 'current_quote_list_observation_20261013_v1/observation.json',
                    '41573c3b20f683f1565e969be689d1eac52b4d1b4fb0d29d8c5b9c477e371fbf'),
    'final_index': (RAW_DIRECTORY / 'completion_index_104.json',
                    '46d30fcc30ccdb1e768e47207e93fc98a11100a4c9b02ed9f0fb450fa93f9131'),
    'independent_readback': (ROOT / 'tmp/current_raw_104_independent_readback_20261013_v1/report.json',
                    'b6f034e3cbe4ff92b9398f985b47d79bd2b1471d47c954d3af88c22652c499d5'),
    'inventory': (ROOT / 'tmp/current_input_inventory_20261013_v1/inventory.json',
                    'fddc98d61ca6aa37cdf6d9a3efb4f831daafcb8b77261397cad54bfa4230b541'),
}
FALSE_FLAGS = dict(point_in_time_verified=False, membership_certified=False,
                   security_identity_verified=False, current_risk_interval_verified=False,
                   complete_corporate_actions_verified=False, quote_basis_authenticated=False,
                   economic_total_return=False, qualified=False, promotion_allowed=False,
                   live_adoption=False, fit_performed=False, optimization_performed=False)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _loads(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('nonfinite JSON value: ' + value)
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('overflowing JSON number')
        return parsed
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject, parse_float=number)


def _read_fixed(path, expected_sha):
    for candidate in (path, *path.parents):
        attributes = candidate.lstat()
        if stat.S_ISLNK(attributes.st_mode) or getattr(attributes, 'st_file_attributes', 0) & 0x400:
            raise ValueError('reparse/symlink path forbidden')
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('regular fixed file required')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or _digest(raw) != expected_sha:
        raise ValueError('fixed source size/SHA differs')
    return raw


def parse_provider_channel(raw: bytes, ticker: str, *, control=False) -> dict:
    """Pure bounded parse: preserve raw close, never infer split adjustment."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES or type(control) is not bool:
        raise ValueError('bounded bytes and typed control required')
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
            decoded = source.read(MAX_BYTES + 1)
    else:
        decoded = raw
    if len(raw) > MAX_BYTES or len(decoded) > MAX_BYTES:
        raise ValueError('bounded raw/decoded body required')
    chart = _loads(decoded)['chart']
    if chart.get('error') is not None or len(chart.get('result') or []) != 1:
        raise ValueError('one successful raw channel required')
    source = chart['result'][0]
    metadata = source['meta']
    instrument = 'ETF' if ticker in ('QQQ', 'SPY') else 'EQUITY'
    if (metadata.get('symbol') != ticker or metadata.get('currency') != 'USD'
            or metadata.get('instrumentType') != instrument
            or metadata.get('exchangeTimezoneName') != 'America/New_York'
            or metadata.get('dataGranularity') != '1d'):
        raise ValueError('symbol/USD/instrument/timezone/granularity differs')
    if control != (ticker in CONTROLS):
        raise ValueError('controls must remain separately typed')
    timestamps = source['timestamp']
    if (not 1 <= len(timestamps) <= 20_000 or timestamps != sorted(set(timestamps))
            or any(type(value) is not int or value <= 0 for value in timestamps)):
        raise ValueError('unique ordered integer timestamps required')
    dates = [datetime.fromtimestamp(stamp, timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
             for stamp in timestamps]
    if dates != sorted(set(dates)):
        raise ValueError('unique ordered New York dates required')
    quotes = source['indicators']['quote']
    if len(quotes) != 1 or len(quotes[0]['close']) != len(dates):
        raise ValueError('close dimensions differ')
    closes = quotes[0]['close']
    if any(value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0)
           for value in closes):
        raise ValueError('finite positive raw close or explicit None required')
    events = source.get('events', {})
    if type(events) is not dict or set(events) - {'splits', 'dividends'}:
        raise ValueError('unknown returned event family')
    if any(type(events.get(kind, {})) is not dict for kind in ('splits', 'dividends')):
        raise ValueError('event maps required')
    return dict(ticker=ticker, dates=dates, closes=closes, control=control,
                raw_sha256=_digest(raw), decoded_sha256=_digest(decoded),
                events_sha256=_digest(_canonical(events)),
                splits_payload_sha256=_digest(_canonical(events.get('splits', {}))),
                dividends_payload_sha256=_digest(_canonical(events.get('dividends', {}))),
                splits_count=len(events.get('splits', {})), dividends_count=len(events.get('dividends', {})))


def bind_observed_close_panel(*, observed_symbols: list[str], channels: dict,
                              history_sessions: int | None = None, target: str = TARGET,
                              metadata_references: dict | None = None) -> dict:
    """Pure alignment; retain every observed stock and every missing calendar cell."""
    if ((history_sessions is not None and (type(history_sessions) is not int or not 2 <= history_sessions <= 20_000))
            or datetime.fromisoformat(target).date().isoformat() != target):
        raise ValueError('explicit ISO target and full calendar or 2..20000 fixture sessions required')
    if (type(observed_symbols) is not list or not observed_symbols
            or len(observed_symbols) > 101 or len(set(observed_symbols)) != len(observed_symbols)
            or any(type(ticker) is not str or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,14}', ticker)
                   or ticker in CONTROLS for ticker in observed_symbols)):
        raise ValueError('unique stock-only observed list required')
    if set(channels) != set(observed_symbols) | set(CONTROLS):
        raise ValueError('exact stocks plus separate controls required')
    for ticker, channel in channels.items():
        if (channel['ticker'] != ticker or channel['control'] != (ticker in CONTROLS)
                or type(channel['control']) is not bool
                or len(channel['dates']) != len(channel['closes'])
                or channel['dates'] != sorted(set(channel['dates']))):
            raise ValueError('channel dimensions/type/order differ')
        for day in channel['dates']:
            if datetime.fromisoformat(day).date().isoformat() != day:
                raise ValueError('exact ISO session required')
        if any(value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0)
               for value in channel['closes']):
            raise ValueError('invalid raw close')
    reference = [day for day in channels['QQQ']['dates'] if day <= target]
    if history_sessions is not None:
        reference = reference[-history_sessions:]
    if (not 2 <= len(reference) <= 20_000 or reference[-1] != target
            or (history_sessions is not None and len(reference) != history_sessions)):
        raise ValueError('QQQ lacks complete fixed observed reference history/target')
    def align(ticker):
        channel = channels[ticker]
        by_date = dict(zip(channel['dates'], channel['closes']))
        aligned = [by_date.get(day) for day in reference]
        missing_dates = [day for day in reference if day not in by_date]
        null_dates = [day for day in reference if day in by_date and by_date[day] is None]
        first_present = next((index for index, value in enumerate(aligned) if value is not None), len(reference))
        reasons = []
        if first_present:
            reasons.append('REFERENCE_PREFIX_HISTORY_SHORT')
        if missing_dates:
            reasons.append('REFERENCE_PROVIDER_DATES_MISSING')
        if null_dates:
            reasons.append('REFERENCE_RAW_CLOSE_NULL')
        own_dates = [day for day in channel['dates'] if day <= target]
        if history_sessions is not None:
            own_dates = own_dates[-history_sessions:]
        if own_dates != reference:
            reasons.append('LATEST_PROVIDER_DATES_DIFFER_FROM_QQQ_REFERENCE')
        return dict(ticker=ticker, raw_close=aligned, missing_dates=missing_dates,
                    null_close_dates=null_dates, unavailable_prefix_sessions=first_present,
                    available_close_count=sum(value is not None for value in aligned),
                    consecutive_available_suffix_sessions=next((index for index, value in enumerate(reversed(aligned)) if value is None), len(reference)),
                    excluded_future_dates=[day for day in channel['dates'] if day > target],
                    reference_calendar_exact=own_dates == reference,
                    numerical_history_complete=own_dates == reference and not any(value is None for value in aligned),
                    reasons=reasons, events_reference={key:channel[key] for key in (
                        'raw_sha256','decoded_sha256','events_sha256','splits_payload_sha256',
                        'dividends_payload_sha256','splits_count','dividends_count')},
                    old_coordinate_risk_and_gap_reference=(metadata_references or {}).get(ticker),
                    **FALSE_FLAGS)
    return dict(schema='CURRENT_CONDITIONAL_PROVIDER_CLOSE_PANEL_PREPARATION_V2',
                target=target, calendar=reference, observation_sessions=len(reference),
                calendar_scope='ALL_QQQ_OBSERVED_COMPLETED_DATES' if history_sessions is None else 'EXPLICIT_BOUNDED_PURE_FIXTURE_WINDOW',
                fixed_request_history_start_utc='2022-01-01T00:00:00+00:00',
                price_intervals=len(reference) - 1, stocks=[align(ticker) for ticker in observed_symbols],
                controls=[dict(align(ticker), role='REFERENCE_ONLY_NEVER_TRAIN') for ticker in CONTROLS],
                price_basis='CONDITIONAL_PROVIDER_RETURNED_CLOSE_NOT_AUTHENTICATED_SPLIT_ADJUSTED',
                research_condition='PRICE_ONLY_PROVIDER_CLOSE_FEATURES_NOT_ECONOMIC_TOTAL_RETURN_OR_SPLIT_EVENT_RECONSTRUCTION',
                calendar_basis='QQQ_PROVIDER_OBSERVED_DATES_NOT_CERTIFIED_EXCHANGE_CALENDAR',
                no_missing_fill=True, no_date_compression=True, no_sid_created=True,
                no_old_identity_or_risk_interval_extended=True, **FALSE_FLAGS)


def load_current_close_panel(*, execute: bool = False) -> dict:
    """Prepare by default. Explicit extraction only reads fixed files; never publishes."""
    if type(execute) is not bool:
        raise ValueError('execute must be boolean')
    references = {key:dict(path=str(path),sha256=sha) for key,(path,sha) in FIXED_REFERENCES.items()}
    if not execute:
        return dict(status='PREPARED_NOT_EXTRACTED', fixed_references=references,
                    stock_channel_count=101, controls=list(CONTROLS), target=TARGET,
                    calendar_scope='ALL_QQQ_OBSERVED_COMPLETED_DATES',
                    maximum_calendar_sessions=20_000, minimum_feature_history_sessions=253,
                    fixed_request_history_start_utc='2022-01-01T00:00:00+00:00',
                    file_reads=0, publication_performed=False, **FALSE_FLAGS)
    documents = {key:_loads(_read_fixed(path,sha)) for key,(path,sha) in FIXED_REFERENCES.items()}
    observation,index,audit,inventory = (documents[key] for key in ('observation','final_index','independent_readback','inventory'))
    symbols = observation['observed_symbols'];queue = symbols + list(CONTROLS)
    if (len(symbols) != 101 or observation.get('point_in_time_membership_verified') is not False
            or index['queue'] != queue or [entry['ticker'] for entry in index['entries']] != queue
            or index['completed_attempts'] != 104 or index['target_date'] != TARGET
            or audit['channels'] != 104 or audit['all_target_fullraw_present'] != 104
            or audit['source_unchanged'] is not True or [row['ticker'] for row in inventory['rows']] != symbols):
        raise ValueError('fixed observation/index/readback/inventory association differs')
    checked = {row['ticker']:row for row in audit['channel_checks']}
    channels = {}
    for entry in index['entries']:
        ticker = entry['ticker']
        if checked[ticker]['raw_sha256'] != entry['raw_sha256']:
            raise ValueError('saved independent raw association differs')
        raw = _read_fixed(RAW_DIRECTORY / (ticker + '.response.bin'),entry['raw_sha256'])
        channels[ticker] = parse_provider_channel(raw,ticker,control=ticker in CONTROLS)
        if channels[ticker]['dates'] != checked[ticker]['provider_dates']:
            raise ValueError('new parse differs from saved independent dates')
    metadata = {ticker:dict(references['inventory'],json_pointer='/rows/'+str(index)) for index,ticker in enumerate(symbols)}
    result = bind_observed_close_panel(observed_symbols=symbols, channels=channels,
                                       target=TARGET,metadata_references=metadata)
    for path,sha in FIXED_REFERENCES.values():
        _read_fixed(path,sha)
    result.update(status='EXTRACTED_CONDITIONAL_ONLY_NOT_PUBLISHED', fixed_references=references,
                  actual_http_requests=0, publication_performed=False,
                  source_closure_scope='FIXED_LOCAL_RAW_AND_FOUR_METADATA_FILES_ONLY_NO_TRANSITIVE_SOURCE_BANK_CLAIM')
    return result
