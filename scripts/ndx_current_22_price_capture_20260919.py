"""Explicit planned, at-most-once raw capture. Default command does no network IO."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'current_22_price_capture_20260919_v1'
LOADED = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
ANCHORS = {
    'ndx_current_quote_list_capture_20260919_v1/observation.json': '50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77',
    'current_101_khc_exchange_20260919_v1/local_gap_addendum.json': 'eb4911f6cc7feb0434b1c85964587928b03553b6b420ff8d544f9285f6d6828a',
    'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json': '5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bound(path, expected):
    raw = Path(path).read_bytes()
    if digest(raw) != expected:
        raise ValueError('Source SHA differs: ' + str(path))
    return json.loads(raw)


def save(path, document):
    raw = (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with Path(path).open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest(raw)


def build_plan():
    documents = [read_bound(BASE / path, sha) for path, sha in ANCHORS.items()]
    observation, gap, old = documents
    symbols = observation['observed_symbols']
    channels = old['provider_channels']
    tickers = sorted(set(symbols) - set(channels))
    if len(symbols) != len(set(symbols)) or len(symbols) != 101 or len(channels) != 107:
        raise ValueError('Original denominators differ')
    if len(tickers) != 22 or tickers != gap['missing_old_channels']:
        raise ValueError('Hard difference differs')
    sources = {str(BASE / path): sha for path, sha in ANCHORS.items()}
    for path, sha in observation['source_hashes'].items():
        if path in sources and sources[path] != sha:
            raise ValueError('Observation source conflict')
        sources[path] = sha
    sources[str(Path(__file__).resolve())] = LOADED
    for path, sha in sources.items():
        if digest(Path(path).read_bytes()) != sha:
            raise ValueError('Source changed during preparation')
    return dict(schema='CURRENT_22_RAW_CHANNEL_CAPTURE_PLAN_V1', tickers=tickers,
                observed_security_count=101, old_channel_count=107, overlap=79,
                observation_display_date=observation['provider_display_date'],
                period1_utc_epoch=1640995200, period2_policy='ACTUAL_REQUEST_START_UTC_EPOCH',
                maximum_requests_per_batch=8, request_attempt_limit_per_ticker=1,
                output_directory=str(OUTPUT), source_hashes=sources,
                historical_ticker_identity_verified=False, historical_membership_verified=False,
                same_ticker_alias_join_allowed=False, promotion_allowed=False,
                partial_bar_policy='RECEIPT_NEW_YORK_DATE_AND_LATER_EXCLUDED_FROM_COMPLETED_TRAINING',
                purpose='RAW_CHANNEL_OBSERVATION_ONLY_NO_RETURN_GENERATION')


def load_plan(path, sha):
    saved = read_bound(path, sha)
    if saved != build_plan():
        raise ValueError('Saved plan does not reproduce hard anchors')
    return saved


def checked_entries(index, output, plan_sha):
    if index['plan_sha256'] != plan_sha or index['output_directory'] != str(output):
        raise ValueError('Completion index belongs to another plan/root')
    entries = index['entries']
    for entry in entries:
        ticker = entry['ticker']
        if entry['receipt_path'] != str(output / (ticker + '.receipt.json')):
            raise ValueError('Receipt path differs')
        receipt = read_bound(entry['receipt_path'], entry['receipt_sha256'])
        if receipt['ticker'] != ticker or receipt['plan_sha256'] != plan_sha:
            raise ValueError('Receipt binding differs')
        started = read_bound(output / (ticker + '.started.json'), receipt['started_sha256'])
        if started['ticker'] != ticker or started['plan_sha256'] != plan_sha:
            raise ValueError('Attempt binding differs')
        if receipt.get('raw_path'):
            if receipt['raw_path'] != str(output / (ticker + '.response.bin')):
                raise ValueError('Raw path differs')
            if digest(Path(receipt['raw_path']).read_bytes()) != receipt['raw_sha256']:
                raise ValueError('Raw changed')
        if entry['decoded_path'] != str(output / (ticker + '.decoded.json')):
            raise ValueError('Decoded record path differs')
        decoded_record = read_bound(entry['decoded_path'], entry['decoded_sha256'])
        if decoded_record['receipt_sha256'] != entry['receipt_sha256'] or decoded_record['ticker'] != ticker:
            raise ValueError('Decoded receipt binding differs')
        if decoded_record.get('decoded_sha256'):
            raw = Path(receipt['raw_path']).read_bytes()
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            if digest(decoded) != decoded_record['decoded_sha256']:
                raise ValueError('Decoded body changed')
    return entries


def capture_one(ticker, output, plan_sha, opener=urlopen):
    now = datetime.now(timezone.utc)
    url = ('https://query1.finance.yahoo.com/v8/finance/chart/' + ticker +
           '?period1=1640995200&period2=' + str(int(now.timestamp())) + '&interval=1d&events=div,splits')
    started = dict(ticker=ticker, plan_sha256=plan_sha, request_url=url,
                   started_at_utc=now.isoformat(), period2_utc_epoch=int(now.timestamp()),
                   request_method='GET', attempt_count=1, credentials_sent=False)
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
        receipt.update(error_type=type(error).__name__)
    received = datetime.now(timezone.utc)
    receipt.update(received_at_utc=received.isoformat(), request_headers=headers,
                   completed_training_excludes_dates_on_or_after=received.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
                   historical_identity_verified=False, promotion_allowed=False)
    if raw is not None:
        path = output / (ticker + '.response.bin')
        with path.open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        receipt.update(raw_path=str(path), raw_bytes=len(raw), raw_sha256=digest(raw))
    # Persist receipt before decoding or parsing: failures remain durable evidence.
    receipt_path = output / (ticker + '.receipt.json')
    receipt_sha = save(receipt_path, receipt)
    parsed = dict(ticker=ticker, receipt_sha256=receipt_sha, parse_status='NO_COMPLETE_BODY')
    if raw is not None:
        try:
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            parsed['decoded_sha256'] = digest(decoded)
            body = json.loads(decoded)
            parsed.update(parse_status='JSON_CHANNEL_OBSERVATION_NOT_IDENTITY', provider_error=body.get('chart', {}).get('error'))
        except Exception as error:
            parsed.update(parse_status='DECODE_OR_PARSE_FAILED', error_type=type(error).__name__)
    parsed_sha = save(output / (ticker + '.decoded.json'), parsed)
    return dict(ticker=ticker, receipt_path=str(receipt_path), receipt_sha256=receipt_sha,
                decoded_path=str(output / (ticker + '.decoded.json')), decoded_sha256=parsed_sha)


def run_batch(plan, plan_sha, output, index_path=None, index_sha=None, opener=urlopen):
    output = Path(output)
    if str(output) != plan['output_directory']:
        raise ValueError('Fixed output directory required')
    if bool(index_path) != bool(index_sha):
        raise ValueError('External completion index and SHA required together')
    entries = []
    if index_path:
        index = read_bound(index_path, index_sha)
        entries = checked_entries(index, output, plan_sha)
    done = [entry['ticker'] for entry in entries]
    if done != plan['tickers'][:len(done)]:
        raise ValueError('Completed prefix differs from fixed queue')
    output.mkdir(parents=True, exist_ok=True)
    on_disk = {path.name.split('.')[0] for path in output.glob('*.started.json')}
    if on_disk != set(done):
        raise ValueError('Unindexed attempt exists: reconcile durably; never retry HTTP')
    batch = plan['tickers'][len(done):len(done)+8]
    if not batch:
        raise ValueError('Queue already complete')
    for ticker in batch:
        entries.append(capture_one(ticker, output, plan_sha, opener))
    index = dict(schema='CURRENT22_COMPLETION_INDEX_V1', plan_sha256=plan_sha,
                 output_directory=str(output), entries=entries,
                 previous_index_path=str(index_path) if index_path else None,
                 previous_index_sha256=index_sha)
    path = output / ('completion_index_' + str(len(entries)).zfill(2) + '.json')
    sha = save(path, index)
    return dict(path=str(path), sha256=sha, attempted_count=len(entries))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--plan-sha')
    parser.add_argument('--index')
    parser.add_argument('--index-sha')
    args = parser.parse_args()
    path = OUTPUT / 'plan.json'
    if not args.execute:
        plan = build_plan()
        OUTPUT.mkdir(parents=True, exist_ok=True)
        print(json.dumps(dict(path=str(path), sha256=save(path, plan), network_requests=0)))
        return
    if not args.plan_sha:
        parser.error('--execute requires externally reviewed --plan-sha')
    plan = load_plan(path, args.plan_sha)
    print(json.dumps(run_batch(plan, args.plan_sha, OUTPUT, args.index, args.index_sha)))


if __name__ == '__main__':
    main()
