"""Bound next eight channels; preserve HTTP bodies and never update price caches."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_provider_gap_first8_capture_research as transport

PLAN = ROOT / 'data/cache/research/dynamic_frozen_v2/first8_provider_coverage_addendum_20260912.json'
PLAN_SHA = '39e8264cda2a8f5055b94e45d34cc6d5ce1a03ff4f2ccf302446aaec3f50eccb'
TICKERS = ('ABNB','ADP','ADSK','AEP','ALGN','AMD','AMZN','ANSS')
OUTPUT = ROOT / 'data/cache/research/provider_gap_second8_capture_20260912_v1'


def main():
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA:
        raise ValueError('Approved fixed source plan changed')
    plan = json.loads(raw)
    if plan['next_capture_plan']['tickers'] != list(TICKERS):
        raise ValueError('Request denominator differs')
    if set(TICKERS) & set(plan['next_capture_plan']['excluded_attempted_tickers']):
        raise ValueError('Repeated request forbidden')
    sources = {str(PLAN): PLAN_SHA}
    for path in (Path(__file__).resolve(), Path(transport.__file__).resolve()):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    helper_path = str(Path(transport.__file__).resolve())
    if sources[helper_path] != plan['source_hashes'][helper_path]:
        raise ValueError('Previously reviewed transport changed')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    transport.OUTPUT = OUTPUT
    period2 = int(datetime.now(timezone.utc).timestamp())
    with ThreadPoolExecutor(max_workers=2) as executor:
        probes = list(executor.map(lambda ticker: transport.capture(ticker, period2), TICKERS))
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Source changed during capture')
    report = dict(schema='SECOND8_MISSING_PROVIDER_RAW_CAPTURE', source_hashes=sources, probes=probes,
                  explicit_request_tickers=list(TICKERS), request_count=8, maximum_attempts_per_ticker=1,
                  request_end_exclusive_utc_epoch=period2, requested_start='2022-01-01',
                  old_price_cache_modified=False, historical_ticker_aliases_stitched=False,
                  delisted_security_missing_history_filled=False, provider_to_security_identity_verified=False,
                  point_in_time_verified=False, promotion_allowed=False)
    path = OUTPUT / 'manifest.json'
    with path.open('xb') as stream:
        stream.write((json.dumps(report, indent=2, sort_keys=True)+'\n').encode())
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         actual=[dict(ticker=row['ticker'], status=row.get('http_status'),
                                      rows=row.get('observed_session_count'), parse=row.get('parse_status')) for row in probes])))


if __name__ == '__main__':
    main()
