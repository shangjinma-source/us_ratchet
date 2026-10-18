"""One new dated SEC exchange-table receipt; no retry or live registry update."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save

OUTPUT = ROOT / 'data/cache/research/current_sec_exchange_refresh_20260919_v1'
MAP = ROOT / 'data/cache/research/current101_conditional_issuer_map_20260919_v1/issuer_map.json'
MAP_SHA = '491a46b575cff58df7c53886a47d1325c2184dcd033b2b357928678d92143890'


if __name__ == '__main__':
    paths = (Path(__file__).resolve(), Path(transport.__file__).resolve(),
             ROOT/'scripts/ndx_current_22_price_capture_20260919.py', MAP)
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    if sources[str(MAP)] != MAP_SHA:
        raise ValueError('Audited current issuer map differs')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    transport.OUTPUT = OUTPUT
    capture = transport.capture(('sec_exchange_table', 'https://www.sec.gov/files/company_tickers_exchange.json'))
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Capture source changed')
    path = OUTPUT/'manifest.json'
    sha = save(path, dict(schema='CURRENT_SEC_EXCHANGE_TABLE_RECEIPT_V1', capture=capture,
                         source_hashes=sources, data_response_parsed=False,
                         historical_identity_verified=False, provider_price_identity_bound=False,
                         point_in_time_verified=False, promotion_allowed=False,
                         live_registry_modified=False, no_retry_performed=True))
    print(json.dumps(dict(path=str(path), sha256=sha, http_status=capture.get('http_status'))))
