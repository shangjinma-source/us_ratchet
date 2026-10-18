"""One bounded public quote request per missing historical ticker; no retries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/fixed12_extended_quote_capture_20261014_v1'
TICKERS = ['AZN', 'BIIB', 'CDW', 'CHTR', 'CSGP', 'CTSH', 'DLTR', 'GFS', 'ILMN',
           'KHC', 'LULU', 'MDB', 'ON', 'TEAM', 'TTD', 'VRSK', 'ZS', 'SMCI']
MAX_BYTES = 8_000_000


def save(name, value):
    with (OUTPUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def capture(ticker):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=1688169600&period2=1791936000&interval=1d&events=div,splits'
    receipt = dict(ticker=ticker, request_url=url, attempt_count=1, credentials_sent=False,
                   started_at_utc=datetime.now(timezone.utc).isoformat(), status='STARTED')
    save(ticker + '.started.json', receipt)
    try:
        try:
            response = urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}), timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(MAX_BYTES + 1)
            receipt.update(http_status=response.status, final_url=response.url)
        with (OUTPUT / (ticker + '.response.bin')).open('xb') as stream:
            stream.write(raw)
        receipt.update(raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw))
        if response.status != 200 or len(raw) > MAX_BYTES or response.url != url:
            receipt['status'] = 'HTTP_OR_SIZE_OR_REDIRECT_FAILED'
        else:
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            if len(decoded) > MAX_BYTES:
                raise ValueError('Decoded limit exceeded')
            body = json.loads(decoded)
            channel = body['chart']['result'][0]
            if channel['meta']['symbol'] != ticker:
                raise ValueError('Wrong provider symbol')
            receipt.update(status='RAW_CAPTURED_NOT_ADMITTED', decoded_sha256=hashlib.sha256(decoded).hexdigest(),
                           rows=len(channel['timestamp']), returned_events=channel.get('events', {}))
    except Exception as error:
        receipt.update(status='CAPTURE_OR_DECODE_FAILED', error_type=type(error).__name__)
    receipt.update(received_at_utc=datetime.now(timezone.utc).isoformat(), price_basis_authenticated=False,
                   identity_authenticated=False, strategy_calls=0)
    save(ticker + '.receipt.json', receipt)
    return {key: receipt.get(key) for key in ('ticker', 'status', 'http_status', 'rows', 'raw_sha256')}


def inspect_existing():
    from zoneinfo import ZoneInfo
    result = {t: [] for t in TICKERS}
    for path in (ROOT/'data/cache/research').glob('*/*.response.bin'):
        ticker = path.name.removesuffix('.response.bin')
        if ticker not in result:
            continue
        raw = path.read_bytes()
        row = {'path': str(path), 'raw_sha256': hashlib.sha256(raw).hexdigest()}
        try:
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            provider = json.loads(decoded)['chart']['result'][0]
            if provider['meta']['symbol'] != ticker:
                raise ValueError('Different symbol')
            zone = ZoneInfo(provider['meta']['exchangeTimezoneName'])
            dates = [datetime.fromtimestamp(t, zone).date().isoformat() for t in provider['timestamp']]
            row.update(first_date=min(dates), last_date=max(dates), rows=len(dates), events=provider.get('events',{}))
        except Exception as e:
            row['parse_status'] = type(e).__name__
        result[ticker].append(row)
    return result


if __name__ == '__main__':
    OUTPUT.mkdir()
    inventory = inspect_existing()
    save('existing_source_inventory.json', inventory)
    required = [t for t in TICKERS if not any(r.get('last_date','') >= '2026-10-12' and r.get('first_date','9999') <= '2023-07-03' for r in inventory[t])]
    save('intent.json', dict(tickers=TICKERS, maximum_http_calls=18, workers=2, retries=0,
                            runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            strategy_calls=0, production_mutation=False))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(capture, required))
    save('result.json', dict(results=results, attempted=len(results), strategy_calls=0))
    print(json.dumps(results))
