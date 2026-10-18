"""Capture through-reception split events and provider price-basis documentation."""
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
    original = ROOT / 'data/cache/research/preference_price_action_source_probe_20260912_v1/manifest.json'
    sources = {str(original): 'fac4d6e47a266d69891a9415919d0a3cfbad639c0e3d7bc111a2a15ab30e32f7'}
    for path in (Path(__file__).resolve(), Path(capture_module.__file__).resolve()):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    def verify():
        for path, digest in sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise ValueError('Capture dependency drift: ' + path)
    verify()
    now = datetime.now(timezone.utc)
    start = int(datetime(2023, 3, 31, tzinfo=timezone.utc).timestamp())
    # Entire completed daily history through actual reception cutoff, not window end.
    urls = {
        'yahoo_official_adjusted_close_help': 'https://help.yahoo.com/kb/SLN28256.html',
        'yahoo_official_avgo_history_basis': 'https://ca.finance.yahoo.com/quote/AVGO/history/',
    }
    for ticker in ('AMAT', 'AVGO', 'CDNS', 'GOOG'):
        urls['yahoo_' + ticker.lower() + '_through_received_daily_events'] = (
            'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
            + '?period1=' + str(start) + '&period2=' + str(int(now.timestamp()))
            + '&interval=1d&events=div%2Csplits')
    directory = ROOT / 'data/cache/research/preference_price_action_supplement_20260912_v1'
    directory.mkdir(parents=True, exist_ok=False)
    requests = [dict(name=name, method='GET', url=url, direct=False) for name, url in urls.items()]
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for metadata, raw in pool.map(capture, requests):
            if raw is not None:
                path = directory / (metadata['name'] + '.response.bin')
                with path.open('xb') as handle:
                    handle.write(raw)
                digest = hashlib.sha256(raw).hexdigest()
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('Raw response readback differs')
                metadata.update(response_path=str(path), response_sha256=digest, response_bytes=len(raw))
            else:
                metadata.update(response_path=None, response_sha256=None, response_bytes=0)
            results.append(metadata)
    verify()
    report = dict(schema='ndx_preference_price_action_supplement_v1', probes=results,
        source_hashes=sources, request_end_exclusive_utc=now.isoformat(),
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
        purpose='FULL_POST_WINDOW_PROVIDER_SPLIT_EVENTS_AND_PRICE_BASIS_PRIMARY_DOCUMENTATION',
        price_cache_modified=False, identity_binding_adjudicated=False, point_in_time_verified=False,
        execution_performed=False, promotion_allowed=False)
    path = directory / 'manifest.json'
    with path.open('xb') as handle:
        handle.write((json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode())
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        outcomes=[(item['name'], item['http_status'], item['response_bytes']) for item in results])))


if __name__ == '__main__':
    run()
