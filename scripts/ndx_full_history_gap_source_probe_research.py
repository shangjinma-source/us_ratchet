"""Capture five bounded history gaps and dated corporate events; no cache repair."""
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


def main():
    directory = ROOT / 'data/cache/research/full_history_gap_source_probe_20260912_v1'
    directory.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    start = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
    requests = [dict(name='yahoo_' + ticker.lower() + '_full_history', method='GET', direct=False,
        url='https://query1.finance.yahoo.com/v8/finance/chart/' + ticker + '?period1=' + str(start)
        + '&period2=' + str(int(now.timestamp())) + '&interval=1d&events=div%2Csplits')
        for ticker in ('CEG', 'WBD', 'GEHC', 'DASH', 'ROP')]
    official = {
        'ceg_regular_way_20220202': 'https://www.constellationenergy.com/news/2022/constellation-launches-as-largest-u-s--clean-energy-company-afte.html',
        'gehc_regular_way_20230104': 'https://www.gehealthcare.com/en-us/about/newsroom/press-releases/ge-healthcare-completes-spin-off-and-begins-trading-on-nasdaq',
        'gehc_when_issued_notice': 'https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-405',
        'wbd_conversion_8k': 'https://www.sec.gov/Archives/edgar/data/1437107/000119312522103051/d328161d8k.htm',
    }
    requests.extend(dict(name=name, method='GET', direct=False, url=url) for name, url in official.items())
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).resolve(), Path(capture_module.__file__).resolve())}
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for metadata, raw in pool.map(capture, requests):
            if raw is not None:
                path = directory / (metadata['name'] + '.response.bin')
                with path.open('xb') as handle:
                    handle.write(raw)
                digest = hashlib.sha256(raw).hexdigest()
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('Raw readback differs')
                metadata.update(response_path=str(path), response_sha256=digest, response_bytes=len(raw))
                sources[str(path)] = digest
            else:
                metadata.update(response_path=None, response_sha256=None, response_bytes=0)
            results.append(metadata)
    for path, digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during capture')
    result = dict(schema='ndx_full_history_gap_probe_v1', probes=results, source_hashes=sources,
        requested_end_exclusive_utc=now.isoformat(), observed_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='BOUNDED_MISSING_HISTORY_AND_CORPORATE_EVENT_EVIDENCE_NOT_AUTOMATIC_ALIAS_JOIN',
        old_cache_modified=False, training_performed=False, point_in_time_verified=False, promotion_allowed=False)
    path = directory / 'manifest.json'
    with path.open('x', encoding='utf8') as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        outcomes=[(row['name'], row['http_status'], row['response_bytes']) for row in results])))


if __name__ == '__main__':
    main()
