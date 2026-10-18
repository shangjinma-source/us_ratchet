"""Source-bound raw-first one-attempt new-cutoff capture; default is offline check."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_new_cutoff_capture_plan_20260923 as preparation
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path = Path(path)
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(raw)


def bound_json(path, expected):
    raw = Path(path).read_bytes()
    if digest(raw) != expected:
        raise ValueError('External SHA differs: ' + str(path))
    return json.loads(raw)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def default_open(request, **kwargs):
    return build_opener(NoRedirect()).open(request, **kwargs)


def utc_now():
    return datetime.now(timezone.utc)


def verify_runner(expected):
    if expected != LOADED_SHA or preparation.sha(SOURCE) != LOADED_SHA:
        raise ValueError('Loaded, current and external runner SHA must match')


def aware_utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError('Aware UTC timestamp required')
    return value


def decode_receipt(receipt, receipt_sha):
    decoded = dict(ticker=receipt['ticker'], receipt_sha256=receipt_sha, parse_status='NO_COMPLETE_BODY',
                   prices_reconstructed=False, cutoff_coverage_verified=False, promotion_allowed=False)
    try:
        start = aware_utc(datetime.fromisoformat(receipt['started_at_utc']))
        received = aware_utc(datetime.fromisoformat(receipt['received_at_utc']))
        preparation.validate_start(received)
        if received < start:
            raise ValueError('Clock moved backwards')
        if receipt.get('final_url') != receipt['request_url'] or receipt.get('http_status') != 200:
            raise ValueError('Final URL or HTTP status differs')
        if 'raw_path' in receipt:
            raw = Path(receipt['raw_path']).read_bytes()
            if digest(raw) != receipt['raw_sha256']:
                raise ValueError('Durable raw readback differs')
            body = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            parsed = json.loads(body)
            decoded.update(parse_status='JSON_CHANNEL_OBSERVATION_NOT_IDENTITY', decoded_sha256=digest(body),
                           provider_error=parsed.get('chart', {}).get('error'))
    except Exception as error:
        decoded.update(parse_status='BLOCKED_RECEIPT_OR_DECODE', error_type=type(error).__name__)
    return decoded


def validate_request(url, ticker, prior_urls):
    if not prior_urls:
        raise ValueError('Known prior request inventory required for ' + ticker)
    def epoch(value):
        return preparation.prior_url(dict(ticker=ticker, attempt_count=1, request_url=value), ticker)
    current = epoch(url)
    if '#' in url or url in prior_urls or current <= max(epoch(old) for old in prior_urls):
        raise ValueError('Request must be a distinct strictly later exact URL')
    expected = ('https://query1.finance.yahoo.com/v8/finance/chart/' + ticker +
                '?period1=1640995200&period2=' + str(current) + '&interval=1d&events=div,splits')
    if url != expected:
        raise ValueError('Noncanonical request URL')
    return current


def capture_one(row, output, plan_sha, runner_sha, prior_urls, opener=default_open, clock=utc_now):
    verify_runner(runner_sha)
    output = Path(output)
    ticker = row['ticker']
    start = clock()
    preparation.validate_start(start)
    url = row['request_url_template'].format(actual_request_start_utc_epoch=int(start.timestamp()))
    validate_request(url, ticker, prior_urls)
    # Any orphan file prohibits a new request, including a partial started write.
    if any(output.glob(ticker + '.*')):
        raise FileExistsError('Existing channel evidence; reconcile offline, never retry')
    started = dict(ticker=ticker, plan_sha256=plan_sha, runner_sha256=runner_sha,
                   request_url=url, started_at_utc=start.isoformat(), attempt_count=1,
                   request_method='GET', credentials_sent=False)
    started_sha = save(output / (ticker + '.started.json'), started)
    receipt = dict(started, started_sha256=started_sha)
    raw = None
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}
    try:
        try:
            response = opener(Request(url, headers=headers), timeout=35)
        except HTTPError as error:
            response = error
        with response:
            receipt.update(http_status=response.status, final_url=response.url,
                           response_headers={key: response.headers.get(key) for key in
                                             ('Date', 'Content-Type', 'Content-Encoding', 'Content-Length', 'ETag', 'Last-Modified')})
            raw = response.read()
    except Exception as error:
        receipt['error_type'] = type(error).__name__
    received = clock()
    if raw is not None:
        raw_path = output / (ticker + '.response.bin')
        with raw_path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        receipt.update(raw_path=str(raw_path), raw_sha256=digest(raw), raw_bytes=len(raw))
    # Preserve any returned bytes even if the clock itself is unusable; the
    # resulting orphan is an offline reconciliation case, never a retry.
    aware_utc(received)
    receipt.update(received_at_utc=received.isoformat(), request_headers=headers,
                   completed_training_excludes_dates_on_or_after=received.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
                   point_in_time_verified=False, promotion_allowed=False)
    receipt_path = output / (ticker + '.receipt.json')
    receipt_sha = save(receipt_path, receipt)
    decoded = decode_receipt(receipt, receipt_sha)
    decoded_path = output / (ticker + '.decoded.json')
    decoded_sha = save(decoded_path, decoded)
    return dict(ticker=ticker, receipt_path=str(receipt_path), receipt_sha256=receipt_sha,
                decoded_path=str(decoded_path), decoded_sha256=decoded_sha)


def check_entries(entries, plan, plan_sha, runner_sha):
    output = Path(plan['output_directory'])
    raw_expected = set()
    if [entry['ticker'] for entry in entries] != [row['ticker'] for row in plan['queue'][:len(entries)]]:
        raise ValueError('Completed prefix differs')
    if len(entries) > len(plan['queue']):
        raise ValueError('Excess completed entries')
    for entry in entries:
        ticker = entry['ticker']
        row = next(row for row in plan['queue'] if row['ticker'] == ticker)
        for kind in ('receipt', 'decoded'):
            if entry[kind + '_path'] != str(output / (ticker + '.' + kind + '.json')):
                raise ValueError('Evidence path differs')
        receipt = bound_json(entry['receipt_path'], entry['receipt_sha256'])
        started = bound_json(output / (ticker + '.started.json'), receipt['started_sha256'])
        if any(started.get(key) != value for key, value in
               dict(ticker=ticker, plan_sha256=plan_sha, runner_sha256=runner_sha, attempt_count=1).items()):
            raise ValueError('Started binding differs')
        if type(started['attempt_count']) is not int or any(receipt.get(key) != value for key, value in started.items()):
            raise ValueError('Receipt binding differs')
        start = aware_utc(datetime.fromisoformat(started['started_at_utc']))
        preparation.validate_start(start)
        if started['request_url'] != row['request_url_template'].format(actual_request_start_utc_epoch=int(start.timestamp())):
            raise ValueError('Started URL and actual clock differ')
        if row.get('prior_receipt'):
            validate_request(started['request_url'], ticker, {row['prior_receipt']['request_url']})
        received = aware_utc(datetime.fromisoformat(receipt['received_at_utc']))
        if receipt['completed_training_excludes_dates_on_or_after'] != received.astimezone(ZoneInfo('America/New_York')).date().isoformat():
            raise ValueError('Receipt exclusion day differs')
        if started['request_method'] != 'GET' or started['credentials_sent'] is not False or receipt['point_in_time_verified'] is not False or receipt['promotion_allowed'] is not False:
            raise ValueError('Receipt scope differs')
        if 'raw_path' in receipt:
            raw_expected.add(ticker)
            if receipt['raw_path'] != str(output / (ticker + '.response.bin')) or digest(Path(receipt['raw_path']).read_bytes()) != receipt['raw_sha256']:
                raise ValueError('Raw binding differs')
            if receipt['raw_bytes'] != Path(receipt['raw_path']).stat().st_size:
                raise ValueError('Raw size differs')
        decoded = bound_json(entry['decoded_path'], entry['decoded_sha256'])
        if decoded['ticker'] != ticker or decoded['receipt_sha256'] != entry['receipt_sha256']:
            raise ValueError('Decoded binding differs')
        if preparation.canonical(decoded) != preparation.canonical(decode_receipt(receipt, entry['receipt_sha256'])):
            raise ValueError('Decoded semantics differ')
    expected = {entry['ticker'] for entry in entries}
    for suffix in ('started.json', 'receipt.json', 'response.bin', 'decoded.json'):
        observed = {path.name[:-len(suffix)-1] for path in output.glob('*.' + suffix)}
        if observed != (raw_expected if suffix == 'response.bin' else expected):
            raise ValueError('Orphan or missing evidence; offline reconciliation required')


def run(plan_path, plan_sha, runner_sha, *, execute=False, index_path=None, index_sha=None):
    verify_runner(runner_sha)
    plan = bound_json(plan_path, plan_sha)
    if preparation.canonical(plan) != preparation.canonical(preparation.build()):
        raise ValueError('Preparation does not reproduce')
    if bool(index_path) != bool(index_sha):
        raise ValueError('Index and SHA required together')
    output = Path(plan['output_directory'])
    entries = []
    if index_path:
        index = bound_json(index_path, index_sha)
        if index['plan_sha256'] != plan_sha or index['runner_sha256'] != runner_sha or index['output_directory'] != str(output):
            raise ValueError('Index binding differs')
        if index.get('schema') != 'NEW_CUTOFF_RAW_CAPTURE_INDEX_V1' or index.get('prices_reconstructed') is not False or index.get('promotion_allowed') is not False:
            raise ValueError('Index scope differs')
        entries = index['entries']
    check_entries(entries, plan, plan_sha, runner_sha)
    unresolved = [row['ticker'] for row in plan['queue'] if not row['prior_url_inventory_complete']]
    if not execute:
        return dict(network_requests=0, completed_attempts=len(entries), queue_count=len(plan['queue']),
                    unresolved_prior_inventory=unresolved, executable_runner_verified=False)
    preparation.validate_start(utc_now())
    output.mkdir(parents=True, exist_ok=True)
    published = None
    for row in plan['queue'][len(entries):len(entries)+plan['maximum_requests_per_batch']]:
        if not row['prior_url_inventory_complete']:
            break  # Preserve all 104 rows; do not invent QQQ/SPY prior inventory.
        preparation.verify_sources(plan['source_hashes'])
        verify_runner(runner_sha)
        entries.append(capture_one(row, output, plan_sha, runner_sha, {row['prior_receipt']['request_url']}))
        preparation.verify_sources(plan['source_hashes'])
        verify_runner(runner_sha)
        check_entries(entries, plan, plan_sha, runner_sha)
        value = dict(schema='NEW_CUTOFF_RAW_CAPTURE_INDEX_V1', plan_sha256=plan_sha, runner_sha256=runner_sha,
                     output_directory=str(output), entries=entries, previous_index_path=index_path,
                     previous_index_sha256=index_sha, prices_reconstructed=False, promotion_allowed=False)
        path = output / ('completion_index_' + str(len(entries)).zfill(3) + '.json')
        current_sha = save(path, value)
        index_path, index_sha = str(path), current_sha
        published = dict(path=index_path, sha256=index_sha)
    preparation.verify_sources(plan['source_hashes'])
    verify_runner(runner_sha)
    return dict(last_index=published, completed_attempts=len(entries), queue_count=104,
                unresolved_prior_inventory=unresolved, all_channels_attempted=len(entries)==104)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha', required=True)
    parser.add_argument('--runner-sha', required=True)
    parser.add_argument('--index')
    parser.add_argument('--index-sha')
    parser.add_argument('--execute', action='store_true')
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.plan, arguments.plan_sha, arguments.runner_sha,
                         execute=arguments.execute, index_path=arguments.index, index_sha=arguments.index_sha)))
