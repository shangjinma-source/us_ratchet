"""Capture six missing original-incumbent controls; reuse bound CDNS/GOOG raw."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_identity_source_probe import capture
import scripts.ndx_identity_source_probe as capture_module


def run():
    existing = ROOT / 'data/cache/research/preference_price_action_supplement_20260912_v1/manifest.json'
    sources = {str(existing): 'ef8baa8d5d370b87f31543c770b09703c2b2750c2f19686e444582eea6a67e32'}
    for path in (Path(__file__).resolve(), Path(capture_module.__file__).resolve()):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    def bind(path, digest):
        if path in sources and sources[path] != digest:
            raise ValueError('Conflicting source')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Source drift: ' + path)
        sources[path] = digest
    bind(str(existing), sources[str(existing)])
    previous = json.loads(existing.read_bytes())
    for path, digest in previous['source_hashes'].items():
        bind(path, digest)
    results = []
    for ticker in ('CDNS', 'GOOG'):
        item = next(x for x in previous['probes'] if x['name'] == 'yahoo_' + ticker.lower() + '_through_received_daily_events')
        bind(item['response_path'], item['response_sha256'])
        results.append(dict(item, reused_existing_capture=True))
    now = datetime.now(timezone.utc)
    start = int(datetime(2023, 3, 31, tzinfo=timezone.utc).timestamp())
    requests = [dict(name='yahoo_' + ticker.lower() + '_through_received_daily_events',
        method='GET', direct=False,
        url='https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
            + '?period1=' + str(start) + '&period2=' + str(int(now.timestamp()))
            + '&interval=1d&events=div%2Csplits') for ticker in ('NVDA', 'TXN', 'ASML', 'TSM', 'MU', 'MSFT')]
    directory = ROOT / 'data/cache/research/incumbent_price_source_probe_20260912_v1'
    directory.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for metadata, raw in pool.map(capture, requests):
            if raw is not None:
                path = directory / (metadata['name'] + '.response.bin')
                with path.open('xb') as handle:
                    handle.write(raw)
                digest = hashlib.sha256(raw).hexdigest()
                bind(str(path), digest)
                metadata.update(response_path=str(path), response_sha256=digest, response_bytes=len(raw))
            else:
                metadata.update(response_path=None, response_sha256=None, response_bytes=0)
            results.append(dict(metadata, reused_existing_capture=False))
    for path, digest in sources.items():
        bind(path, digest)
    report = dict(schema='ndx_incumbent_price_source_probe_v1', probes=results, source_hashes=sources,
        requested_control_tickers=['NVDA', 'TXN', 'ASML', 'CDNS', 'TSM', 'MU', 'MSFT', 'GOOG'],
        control_role='ORIGINAL_INCUMBENT_BENCHMARK_NOT_TARGET_CARDINALITY',
        target_window_start='2023-03-31', target_window_end='2024-06-03',
        new_requests_end_exclusive_utc=now.isoformat(), observed_at_utc=datetime.now(timezone.utc).isoformat(),
        price_cache_modified=False, identity_binding_adjudicated=False, point_in_time_verified=False,
        execution_performed=False, promotion_allowed=False)
    path = directory / 'manifest.json'
    with path.open('xb') as handle:
        handle.write((json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode())
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        outcomes=[(item['name'], item['http_status'], item['response_bytes']) for item in results])))


if __name__ == '__main__':
    run()
