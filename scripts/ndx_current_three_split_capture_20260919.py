"""Capture three primary split announcements once; no admission or price writes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save

OUTPUT = ROOT / 'data/cache/research/current_three_split_official_20260919_v1'
URLS = {
    'mstr_split': 'https://www.strategy.com/press/microstrategy-announces-10-for-1-stock-split_07-11-2024',
    'shop_split': 'https://www.shopify.com/news/shopify-announces-results-of-its-2022-annual-general-and-special-meeting-of-shareholders-and-further-details-regarding-previously-announced-share-split',
    'wmt_split': 'https://corporate.walmart.com/news/2024/01/30/walmart-announces-3-for-1-stock-split',
}


if __name__ == '__main__':
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in (Path(__file__).resolve(), Path(transport.__file__).resolve(),
                            ROOT / 'scripts/ndx_current_22_price_capture_20260919.py')}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    transport.OUTPUT = OUTPUT
    with ThreadPoolExecutor(max_workers=3) as executor:
        captures = list(executor.map(transport.capture, URLS.items()))
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Capture source changed')
    document = dict(schema='CURRENT_THREE_SPLIT_PRIMARY_RAW_CAPTURE_V1',
                    captures=captures, source_hashes=sources,
                    historical_membership_verified=False, price_identity_verified=False,
                    point_in_time_verified=False, promotion_allowed=False,
                    scope='ANNOUNCEMENTS_ONLY_NOT_PROVIDER_QUOTE_BASIS_AUTHENTICATION')
    path = OUTPUT / 'manifest.json'
    digest = save(path, document)
    print(json.dumps(dict(path=str(path), sha256=digest,
                          statuses=[(row['name'], row.get('http_status')) for row in captures])))
