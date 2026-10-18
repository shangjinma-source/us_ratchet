"""Capture public H.10 evidence once; no rate parsing or historical availability claim."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[1]
OUTPUT = ROOT / 'data/cache/research/official_fx_capture_20261003_v1'
URLS = (
    ('country_data', 'https://www.federalreserve.gov/releases/h10/Hist/', b'noon buying rates'),
    ('china_history', 'https://www.federalreserve.gov/releases/h10/Hist/dat00_ch.htm', b'Chinese yuan per U.S. dollar'),
    ('fred_series', 'https://fred.stlouisfed.org/series/DEXCHUS', b'DEXCHUS'),
)


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    save_json(OUTPUT / 'started.json', {'started_at': now(), 'source_sha256': source_sha,
                                     'requested_urls': [row[1] for row in URLS]})
    references = []
    try:
        for name, url, expected in URLS:
            started = now()
            request = Request(url, headers={'User-Agent': 'us-ratchet-research/1.0', 'Accept-Encoding': 'identity'})
            with urlopen(request, timeout=30) as response:
                body = response.read(10_000_001)
                status, final_url = response.status, response.geturl()
                content_type = response.headers.get('Content-Type')
            ended = now()
            raw_path = OUTPUT / (name + '.html')
            with raw_path.open('xb') as stream:
                stream.write(body)
            receipt = {'requested_url': url, 'final_url': final_url, 'http_status': status,
                       'read_started_at': started, 'read_completed_at': ended,
                       'content_type': content_type, 'bytes': len(body),
                       'raw_reference': {'path': raw_path.relative_to(ROOT).as_posix(),
                                         'sha256': hashlib.sha256(body).hexdigest()}}
            receipt_path = OUTPUT / (name + '.receipt.json')
            save_json(receipt_path, receipt)
            if status != 200 or final_url != url or len(body) > 10_000_000 or expected not in body:
                raise ValueError('Unexpected HTTP source response: ' + name)
            references.append({'name': name, 'raw': receipt['raw_reference'],
                               'receipt': {'path': receipt_path.relative_to(ROOT).as_posix(),
                                           'sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest()}})
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_sha:
            raise ValueError('Capture source changed')
        manifest = {'schema': 'OFFICIAL_FX_SOURCE_CAPTURE_V1', 'status': 'SAVED_SOURCE_ONLY',
                    'completed_at': now(), 'source_sha256': source_sha, 'sources': references,
                    'rates_parsed': False, 'historical_available_at_verified': False,
                    'benchmark_qualified': False, 'point_in_time_verified': False,
                    'execution_authorized': False, 'promotion_allowed': False}
        save_json(OUTPUT / 'manifest.json', manifest)
        print(json.dumps({'path': str(OUTPUT / 'manifest.json'),
                          'sha256': hashlib.sha256((OUTPUT / 'manifest.json').read_bytes()).hexdigest(),
                          'sources_saved': len(references)}))
    except Exception as error:
        save_json(OUTPUT / 'failure.json', {'failed_at': now(), 'error_type': type(error).__name__,
                                         'error': str(error), 'retry_allowed': False})
        raise


if __name__ == '__main__':
    main()
