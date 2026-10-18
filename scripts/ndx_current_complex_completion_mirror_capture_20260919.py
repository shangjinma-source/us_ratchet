"""Public filing mirrors for inaccessible issuer completion texts; provenance kept explicit."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save
OUTPUT = ROOT/'data/cache/research/current_complex_completion_mirror_capture_20260919_v1'
URLS = {
    'cmcsa_completion_filing_mirror': 'https://cdn.yahoofinance.com/prod/sec-filings/0001166691/000095010326000079/dp239108_ex9901.htm',
    'tri_completion_filing_mirror': 'https://cdn.yahoofinance.com/prod/sec-filings/0001075124/000119312526205012/d116991dex991.htm',
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
    sha = save(path, dict(schema='CURRENT_COMPLEX_COMPLETION_FILING_MIRROR_CAPTURE_V1', captures=captures,
                         source_hashes=sources, mirror_not_sec_origin_http=True,
                         complex_action_reclassified_as_simple_split=False,
                         post_action_floor_adjudicated=False, historical_identity_verified=False,
                         point_in_time_verified=False, promotion_allowed=False, no_retry_performed=True))
    print(json.dumps(dict(path=str(path), sha256=sha,
                          statuses=[(c['name'], c.get('http_status')) for c in captures])))
