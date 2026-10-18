"""Capture dated issuer-disclosed index-company tables; not index-provider certification."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save

OUTPUT = ROOT / 'data/cache/research/adobe_historical_peer_capture_20260919_v1'
URLS = {
    'adobe_2023_parent': 'https://www.sec.gov/Archives/edgar/data/796343/000079634323000011/adbe-20230124.htm',
    'adobe_2023_companies': 'https://www.sec.gov/Archives/edgar/data/796343/000079634323000011/adbe8-kex10212623.htm',
    'adobe_2024_companies': 'https://www.sec.gov/Archives/edgar/data/796343/000079634324000024/adbeex10212624.htm',
}

if __name__ == '__main__':
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in (Path(__file__).resolve(), Path(transport.__file__).resolve(),
                            ROOT / 'scripts/ndx_current_22_price_capture_20260919.py')}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    transport.OUTPUT = OUTPUT
    with ThreadPoolExecutor(max_workers=3) as pool:
        captures = list(pool.map(transport.capture, URLS.items()))
    for path, sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError('Capture source changed')
    path = OUTPUT / 'manifest.json'
    sha = save(path, dict(schema='DATED_ISSUER_PEER_TABLE_RAW_CAPTURE_V1', captures=captures,
                         source_hashes=sources, exact_index_baseline_verified=False,
                         full_security_class_denominator_verified=False, point_in_time_verified=False,
                         promotion_allowed=False))
    print(json.dumps(dict(path=str(path), sha256=sha,
                          statuses=[(row['name'], row.get('http_status')) for row in captures])))
