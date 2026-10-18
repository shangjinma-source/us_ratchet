"""Independent, network-free audit of the two sealed official quote-list receipts."""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
SOURCE_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CAPTURE = ROOT / 'scripts/ndx_current_quote_list_capture_v2_research.py'
CAPTURE_SHA = '590de084a6f58a0741e3628f90a7ed8143539465f64d15080ae3d59c8b7c854f'
URL = 'https://api.nasdaq.com/api/quote/list-type/nasdaq100'
NEW = ('current_quote_list_observation_20260923_v1', '3c7b97a1080595dee1b14e34f10ad3b46f8792ff0bed1e7a3d3d7425fbbc3b8b', 'a6d8899fb2bc22f755ecd721271ed173f24a0b959b6ff8da9c96985f940fa990')
OLD = ('ndx_current_quote_list_capture_20260919_v1', '1d1443eeb4427b6b820a8e0ef6c69bc4855d91976d1023a771d60292553edad9', '50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77')


def pack(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('Nonfinite JSON constant')
    def floating(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('Nonfinite JSON number')
        return parsed
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)


def utc(value):
    if not isinstance(value, str):
        raise ValueError('UTC string required')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('Explicit UTC required')
    return parsed


def inspect(raw, manifest, manifest_path):
    request = manifest['request']
    flags = ('historical_backfill_allowed', 'issuer_security_binding_verified',
             'membership_effective_timestamp_verified', 'promotion_allowed', 'selection_performed')
    if (manifest['schema'] != 'ndx_current_quote_list_capture_v1'
        or any(manifest.get(key) is not False for key in flags)
        or manifest['source_hashes'] != {str(CAPTURE): CAPTURE_SHA}
        or request['request_url'] != URL or request['final_url'] != URL
        or request['request_method'] != 'GET' or request['credentials_sent'] is not False
        or type(request['status']) is not int or request['status'] != 200
        or type(request['raw_bytes']) is not int or request['raw_bytes'] != len(raw)
        or request['raw_sha256'] != sha(raw)
        or Path(request['raw_path']) != manifest_path.parent / 'nasdaq100_quote_list.response.bin'):
        raise ValueError('Receipt identity, source, or scope differs')
    started, received = utc(request['started_at_utc']), utc(request['received_at_utc'])
    if started > received:
        raise ValueError('Receipt clock reversed')
    headers = {key.lower(): value for key, value in request['headers'].items()}
    if len(headers) != len(request['headers']) or not headers.get('content-type', '').lower().startswith('application/json'):
        raise ValueError('Response header ambiguity or content type')
    if 'content-length' in headers and (not re.fullmatch(r'[0-9]+', headers['content-length']) or int(headers['content-length']) != len(raw)):
        raise ValueError('Content length differs')
    server_time = parsedate_to_datetime(headers['date'])
    if server_time.tzinfo is None:
        raise ValueError('HTTP date needs timezone')
    decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
    payload = strict_json(decoded)
    data = payload['data']
    rows = data['data']['rows']
    if type(rows) is not list or not rows or any(type(row) is not dict for row in rows):
        raise ValueError('Rows required')
    if any(type(data[key]) is not int for key in ('totalrecords', 'offset', 'limit')) or data['totalrecords'] != len(rows) or data['offset'] != 0 or data['limit'] < len(rows):
        raise ValueError('Incomplete page denominator')
    symbols = [row['symbol'] for row in rows]
    if any(type(symbol) is not str or not re.fullmatch(r'[A-Z][A-Z0-9.\-]*', symbol) for symbol in symbols) or len(set(symbols)) != len(symbols):
        raise ValueError('Invalid or duplicate symbol')
    display = data.get('date')
    if not isinstance(display, str):
        raise ValueError('Display date required')
    display_precision = 'DATE_ONLY'
    try:
        datetime.strptime(display, '%b %d, %Y')
    except ValueError:
        datetime.strptime(display, '%b %d, %Y %I:%M %p')
        display_precision = 'MINUTE_WITHOUT_TIMEZONE'
    asof = data['data'].get('asOf')
    if asof is not None and not isinstance(asof, str):
        raise ValueError('Ambiguous asOf type')
    expected = dict(schema='ndx_current_quote_list_observation_v1', source_hashes=manifest['source_hashes'] | {
        str(manifest_path): sha(manifest_path.read_bytes()), request['raw_path']: sha(raw)},
        observed_security_count=len(rows), provider_display_date=display, provider_asof=asof,
        rows=rows, observed_symbols=symbols,
        observation_scope='CURRENT_OFFICIAL_QUOTE_LIST_ENDPOINT_NOT_HISTORICAL_MEMBERSHIP_CERTIFICATE',
        quote_display_time_is_not_membership_effective_time=True,
        security_class_to_issuer_adjudicated=False, historical_backfill_allowed=False,
        source_payload_says_100_issuers=False, point_in_time_membership_verified=False,
        current_tradable_pool_admitted=False, prices_used_for_training=False, promotion_allowed=False)
    times = dict(started_at_utc=request['started_at_utc'], received_at_utc=request['received_at_utc'],
                 http_date=headers['date'], server_minus_receipt_seconds=(server_time-received).total_seconds(),
                 provider_display_date=display, provider_asof=asof, provider_display_precision=display_precision,
                 provider_display_timezone_verified=False, membership_effective_time_verified=False)
    return expected, dict(decoded_sha256=sha(decoded), raw_sha256=sha(raw), time_information=times)


def verify_sources(sources):
    for path, expected in sources.items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Source drift: ' + path)


def build():
    sources = {str(SOURCE): SOURCE_SHA, str(CAPTURE): CAPTURE_SHA}
    verify_sources(sources)
    observations, details = [], []
    for folder, manifest_sha, observation_sha in (OLD, NEW):
        manifest_path = BASE / folder / 'manifest.json'
        observation_path = BASE / folder / 'observation.json'
        sources.update({str(manifest_path): manifest_sha, str(observation_path): observation_sha})
        verify_sources(sources)
        manifest = strict_json(manifest_path.read_bytes())
        raw_path = Path(manifest['request']['raw_path'])
        raw = raw_path.read_bytes()
        expected, detail = inspect(raw, manifest, manifest_path)
        if pack(strict_json(observation_path.read_bytes())) != pack(expected):
            raise ValueError('Saved observation differs from independently decoded raw')
        sources[str(raw_path)] = sha(raw)
        observations.append(expected)
        details.append(dict(observation_reference=dict(path=str(observation_path), sha256=observation_sha),
                            security_count=len(expected['rows']), **detail))
    old, new = [set(value['observed_symbols']) for value in observations]
    verify_sources(sources)
    return dict(schema='CURRENT_OFFICIAL_QUOTE_OBSERVATION_INDEPENDENT_AUDIT_V1', details=details,
                added_symbols=sorted(new-old), removed_symbols=sorted(old-new), retained_count=len(old & new),
                ordered_symbols_unchanged=observations[0]['observed_symbols'] == observations[1]['observed_symbols'],
                raw_observation_reconstruction_exact=True, source_hashes=sources,
                http_performed=False, fit_performed=False, membership_effective_time_verified=False,
                issuer_count_authenticated=False, point_in_time_membership_verified=False,
                prices_used_for_training=False, promotion_allowed=False)


def publish_verified(path, value):
    if pack(value) != pack(build()):
        raise ValueError('Report differs from independent reconstruction')
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.observation-audit-')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf8') as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
            stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    verify_sources(value['source_hashes'])
    return sha(path.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(publish_verified(args.output, build()))
