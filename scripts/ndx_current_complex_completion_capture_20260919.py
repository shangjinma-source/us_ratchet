"""Additional distinct primary sources, preserving prior failed receipts."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save
OUTPUT = ROOT/'data/cache/research/current_complex_completion_capture_20260919_v1'
URLS = {
    'cmcsa_sec_completed': 'https://www.sec.gov/Archives/edgar/data/1166691/000095010326000079/dp239108_ex9901.htm',
    'tri_2026_ratio': 'https://www.thomsonreuters.com/en/press-releases/2026/may/thomson-reuters-announces-cash-distribution-per-share-and-share-consolidation-ratio-for-return-of-capital-and-share-consolidation-transactions',
    'tri_2026_completed': 'https://ir.thomsonreuters.com/news-releases/news-release-details/thomson-reuters-reports-first-quarter-2026-results',
    'cmcsa_versant_completed': 'https://investors.versantmedia.com/news-releases/news-release-details/versant-begins-trading-nasdaq-today-independent-company',
}

if __name__ == '__main__':
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
               (Path(__file__).resolve(), Path(transport.__file__).resolve(),
                ROOT/'scripts/ndx_current_22_price_capture_20260919.py')}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    transport.OUTPUT = OUTPUT
    with ThreadPoolExecutor(max_workers=2) as pool:
        captures = list(pool.map(transport.capture, URLS.items()))
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Capture source changed')
    path = OUTPUT/'manifest.json'
    sha = save(path, dict(schema='CURRENT_COMPLEX_COMPLETION_PRIMARY_CAPTURE_V1', captures=captures,
                         source_hashes=sources, complex_action_reclassified_as_simple_split=False,
                         post_action_floor_adjudicated=False, historical_identity_verified=False,
                         point_in_time_verified=False, promotion_allowed=False, no_retry_performed=True))
    print(json.dumps(dict(path=str(path), sha256=sha,
                          statuses=[(c['name'], c.get('http_status')) for c in captures])))
