"""Bounded research-only source capture for the sealed preference schedule."""
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

SCHEDULE = ROOT / 'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json'
SCHEDULE_SHA = '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559'


def requests_to_probe():
    urls = {
        'amat_official_split_history': 'https://ir.appliedmaterials.com/stock-information/splits-and-offerings',
        'amat_official_split_history_faq': 'https://ir.appliedmaterials.com/shareholder-services/investor-faqs',
        'avgo_official_20240612_split_faq': 'https://investors.broadcom.com/static-files/e90fe911-25c9-47eb-afbe-8e763b71eb64',
        'avgo_official_historical_price_basis': 'https://investors.broadcom.com/financial-information/stock-information/historical-price-lookup',
        'cdns_official_investor_entry': 'https://www.cadence.com/en_US/home/company/investors.html',
        'cdns_official_historical_path_access': 'https://investor.cadence.com/Stock-Historical/default.aspx',
        'goog_official_2023_proxy': 'https://abc.xyz/assets/investor/static/pdf/2023_alphabet_proxy_statement.pdf?cache=3d0d861',
    }
    # Include post-window AVGO split to observe the provider's price units and events.
    start = int(datetime(2023, 3, 31, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2024, 7, 17, tzinfo=timezone.utc).timestamp())
    for ticker in ('AMAT', 'AVGO', 'CDNS', 'GOOG'):
        urls['yahoo_' + ticker.lower() + '_daily_and_events'] = (
            'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
            + '?period1=' + str(start) + '&period2=' + str(end) + '&interval=1d&events=div%2Csplits')
    return [dict(name=name, method='GET', url=url, direct=False) for name, url in urls.items()]


def run():
    sources = {str(SCHEDULE): SCHEDULE_SHA}
    for path in (Path(__file__).resolve(), Path(capture_module.__file__).resolve()):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    def verify():
        for path, digest in sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise ValueError('Capture dependency drift: ' + path)
    verify()
    directory = ROOT / 'data/cache/research/preference_price_action_source_probe_20260912_v1'
    directory.mkdir(parents=True, exist_ok=False)
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for metadata, raw in pool.map(capture, requests_to_probe()):
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
    report = dict(schema='ndx_preference_price_action_source_probe_v1', probes=results,
        source_hashes=sources, observed_at_utc=datetime.now(timezone.utc).isoformat(),
        schedule_sha256=SCHEDULE_SHA, schedule_start='2023-03-31', schedule_end='2024-06-03',
        price_cache_modified=False, identity_binding_adjudicated=False, point_in_time_verified=False,
        execution_performed=False, promotion_allowed=False,
        purpose='RAW_CORPORATE_ACTION_AND_PRICE_UNIT_EVIDENCE_FOR_RETROSPECTIVE_RESEARCH')
    path = directory / 'manifest.json'
    with path.open('xb') as handle:
        handle.write((json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode())
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        outcomes=[(item['name'], item['http_status'], item['response_bytes']) for item in results])))


if __name__ == '__main__':
    run()
