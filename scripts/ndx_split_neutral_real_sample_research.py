"""Seal AVGO/NVDA split-day numerical counterexamples; no source-cache writes."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.ndx_split_neutral_price_return_research import build_split_neutral_price_return_research, verify

BOUND = {
    'preference_price_action_supplement_20260912_v1': 'ef8baa8d5d370b87f31543c770b09703c2b2750c2f19686e444582eea6a67e32',
    'incumbent_price_source_probe_20260912_v1': '4e30f0f7e48b157eb4a5f60cd5d6531b097d2a276f977444838778411e30d77e'}


def main():
    output = ROOT / 'data/cache/research/split_neutral_real_samples_20260912_v1'
    output.mkdir(exist_ok=False)
    sources, manifests = {}, {}
    def bind(path, expected=None):
        path = Path(path).resolve(); raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected: raise ValueError('Sealed sample source differs')
        if str(path) in sources and sources[str(path)] != digest: raise ValueError('Source conflict')
        sources[str(path)] = digest
        return raw
    bind(__file__)
    for folder, sha in BOUND.items():
        m = json.loads(bind(ROOT / 'data/cache/research' / folder / 'manifest.json', sha))
        manifests[folder] = m
        for path, digest in m['source_hashes'].items(): bind(path, digest)
    identity_path = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv'
    bind(identity_path)
    identities = pd.read_csv(identity_path, dtype=str)
    bind(ROOT / 'data/cn_source.py')
    cases = [('AVGO', '2024-07-12', '2024-07-15', list(BOUND)[0]),
             ('NVDA', '2024-06-07', '2024-06-10', list(BOUND)[1])]
    samples = []
    for ticker, before, after, folder in cases:
        matches = [p for p in manifests[folder]['probes'] if p['name'] == 'yahoo_' + ticker.lower() + '_through_received_daily_events']
        assert len(matches) == 1
        probe = matches[0]; assert probe['http_status'] == 200
        raw = bind(probe['response_path'], probe['response_sha256'])
        if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
        data = json.loads(raw)['chart']['result'][0]
        assert data['meta']['symbol'] == ticker and data['meta']['currency'] == 'USD'
        def day(stamp): return datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat()
        closes = {day(t): data['indicators']['quote'][0]['close'][i] for i, t in enumerate(data['timestamp'])}
        splits = {day(e['date']): (e['numerator'], e['denominator']) for e in data['events']['splits'].values()}
        assert splits[after] == (10, 1)
        identity = identities.loc[identities['ticker'].eq(ticker)]
        assert len(identity) == 1
        sid, issuer = identity.iloc[0]['security_id'], identity.iloc[0]['issuer_id']
        rows = []
        for session in (before, after):
            factor = math.prod(n / d for effective, (n, d) in splits.items() if effective > session)
            rows.append(dict(security_id=sid, issuer_id=issuer, ticker=ticker, session=session,
                             close=closes[session] * factor))
        cache = ROOT / 'data/cache' / (ticker + '.csv')
        bind(cache)
        local = pd.read_csv(cache).set_index('Date')['Close']
        legacy_return = float(local.loc[after] / local.loc[before] - 1)
        payload = dict(schema='ndx_split_neutral_return_input_v1', basis='NOMINAL_CLOSE',
            calendar=[before, after], securities={sid: {'issuer_id': issuer}}, rows=rows,
            dividend_adjustment_in_close=False, event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS',
            daily_share_ratios=[dict(security_id=sid, session=d, new_shares=splits.get(d, (1, 1))[0],
                                    old_shares=splits.get(d, (1, 1))[1]) for d in (before, after)],
            source_hashes=dict(sources), nominal_basis_status='CONDITIONAL_SPLIT_ONLY_PROVIDER_RECONSTRUCTION',
            stable_coordinate_status='LOCAL_IDENTITY_CLAIM_NOT_AUTHENTICATED',
            event_scope='RETURNED_PROVIDER_EVENTS_NO_OMISSION_CERTIFICATION')
        path = output / (ticker + '_input.json')
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf8')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        result = build_split_neutral_price_return_research(input_path=path, expected_sha256=sha)
        expected = closes[after] / closes[before] - 1
        assert abs(result['rows'][0]['price_return'] - expected) < 1e-12
        assert expected > 0 and legacy_return == 0
        sources.update(result['source_hashes'])
        samples.append(dict(ticker=ticker, previous_session=before, split_session=after,
            provider_split_ratio=[10, 1], adjusted_quote_return=expected, old_cache_return=legacy_return,
            new_return=result['rows'][0]['price_return'], input_path=str(path), input_sha256=sha,
            numerical_report=result))
    verify(sources)
    report = dict(schema='ndx_split_neutral_real_sample_review_v1', samples=samples, source_hashes=sources,
        old_cache_modified=False, old_training_rerun=False, old_training_reuse_authorized=False,
        scope='TWO_REAL_SPLIT_DAY_COUNTEREXAMPLES_NOT_FULL_POOL_INPUT_CERTIFICATION',
        point_in_time_verified=False, promotion_allowed=False)
    path = output / 'report.json'
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf8')
    verify(sources)
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        samples=[{k:v for k,v in sample.items() if k != 'numerical_report'} for sample in samples])))


if __name__ == '__main__': main()
