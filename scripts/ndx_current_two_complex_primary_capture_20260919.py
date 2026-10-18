"""Capture missing post-action primary facts, without relabeling complex actions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save
OUTPUT = ROOT/'data/cache/research/current_two_complex_primary_capture_20260919_v1'
URLS = {
    'cmcsa_completed': 'https://cmcsa.gcs-web.com/news-releases/news-release-details/comcast-announces-completion-separation-versant-media-group-inc',
    'tri_ratio_announcement': 'https://www.thomsonreuters.com/en/press-releases/2023/june/thomson-reuters-announces-share-consolidation-ratio-for-return-of-capital-transaction',
    'tri_annual_2023': 'https://investors.thomsonreuters.com/static-files/47412ad2-d720-4a02-99c7-cbd7c425c16d',
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
    sha = save(path, dict(schema='TWO_COMPLEX_ACTION_PRIMARY_CAPTURE_V1', captures=captures,
                         source_hashes=sources, complex_action_reclassified_as_simple_split=False,
                         post_action_floor_adjudicated=False, historical_identity_verified=False,
                         point_in_time_verified=False, promotion_allowed=False, no_retry_performed=True))
    print(json.dumps(dict(path=str(path), sha256=sha,
                          statuses=[(c['name'], c.get('http_status')) for c in captures])))
