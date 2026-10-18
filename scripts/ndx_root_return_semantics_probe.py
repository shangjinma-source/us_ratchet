"""Five-provider-sample raw capture covering both original full training windows."""
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
    directory = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1'
    directory.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    start = int(datetime(2022, 1, 11, tzinfo=timezone.utc).timestamp())
    requests = [dict(name='yahoo_' + ticker.lower() + '_full_training_and_later_events', method='GET', direct=False,
        url='https://query1.finance.yahoo.com/v8/finance/chart/' + ticker + '?period1=' + str(start)
            + '&period2=' + str(int(now.timestamp())) + '&interval=1d&events=div%2Csplits')
        for ticker in ('AMAT', 'AVGO', 'CDNS', 'GOOG', 'NVDA')]
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
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
                    raise ValueError('Response readback differs')
                metadata.update(response_path=str(path), response_sha256=digest, response_bytes=len(raw))
            else:
                metadata.update(response_path=None, response_sha256=None, response_bytes=0)
            results.append(metadata)
    for path, digest in source_hashes.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Capture source drift')
    output = dict(schema='ndx_root_return_semantics_probe_v1', probes=results, source_hashes=source_hashes,
        requested_end_exclusive_utc=now.isoformat(), observed_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='PRICE_RETURN_VS_TOTAL_RETURN_AND_LEGACY_SPLIT_ADJUSTMENT_EVIDENCE',
        data_cache_modified=False, training_performed=False, point_in_time_verified=False, promotion_allowed=False)
    path = directory / 'manifest.json'
    raw = (json.dumps(output, indent=2, ensure_ascii=False) + '\n').encode()
    with path.open('xb') as handle:
        handle.write(raw)
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
        outcomes=[(row['name'],row['http_status'],row['response_bytes']) for row in results])))


if __name__ == '__main__':
    run()
