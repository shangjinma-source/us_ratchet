"""Create-only local readback of the captured September 18 quote observation."""
import gzip
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
LOADED = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def build():
    sources = {}

    def bound(path, expected):
        path = Path(path)
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError(f'Source changed: {path}')
        if str(path) in sources and sources[str(path)] != actual:
            raise ValueError('Conflicting source')
        sources[str(path)] = actual
        return raw

    def load(relative, expected):
        return json.loads(bound(BASE / relative, expected))

    local = load('current_102_local_gap_20260919_v1/readback.json', '732977d6bd197554aa28a99b82eabb431f0d9d85e32463d16edef5d9076dc4b2')
    old = load('ndx_current_quote_list_capture_20260912_v1/observation.json', '950a76544cc63d11ed492b8feb37f2d7eebe4212f42b1761e9ac9a65938a5e38')
    current = load('ndx_current_quote_list_capture_20260919_v1/observation.json', '50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77')
    manifest = load('ndx_current_quote_list_capture_20260919_v1/manifest.json', '1d1443eeb4427b6b820a8e0ef6c69bc4855d91976d1023a771d60292553edad9')
    events = load('current_101_khc_exchange_20260919_v1/manifest.json', 'f976c069d84588247984aabfd503dc9df4647f2341367f77ab03239c26b3ae45')
    for artifact in (local, current, manifest, events):
        for path, sha in artifact['source_hashes'].items():
            bound(path, sha)
    request = manifest['request']
    data = json.loads(bound(request['raw_path'], request['raw_sha256']))['data']
    rows = data['data']['rows']
    if not (request['status'] == 200 and data['totalrecords'] == data['limit'] == len(rows) == 101 and data['offset'] == 0):
        raise ValueError('Incomplete current quote denominator')
    if rows != current['rows'] or data['date'] != current['provider_display_date']:
        raise ValueError('Observation does not reproduce raw')
    symbols = {row['symbol'] for row in rows}
    prior = set(old['observed_symbols'])
    if len(symbols) != 101 or prior - symbols != {'KHC'} or symbols - prior:
        raise ValueError('Unexpected observation delta')
    gaps = {row['ticker'] for row in local['rows']}
    if len(gaps) != 22 or not gaps <= symbols:
        raise ValueError('Gap denominator differs')
    texts = {}
    for capture in events['captures']:
        raw = bound(capture['raw_path'], capture['raw_sha256'])
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        if hashlib.sha256(decoded).hexdigest() != capture['decoded_sha256']:
            raise ValueError('Decoded source differs')
        if capture['http_status'] == 200:
            texts[capture['name']] = ' '.join(BeautifulSoup(decoded.decode('utf-8'), 'html.parser').stripped_strings)
    if 'under its existing ticker symbol, KHC' not in texts['nasdaq_khc_press_release'] or 'September 14, 2026' not in texts['nasdaq_khc_press_release']:
        raise ValueError('Issuer exchange announcement differs')
    if 'transferred its primary listing from the NASDAQ Stock Market to the New York Stock Exchange' not in texts['miax_khc_opening_market'] or 'effective today Monday, September 14, 2026' not in texts['miax_khc_opening_market']:
        raise ValueError('Exchange operational notice differs')
    bound(Path(__file__), LOADED)
    for path, sha in list(sources.items()):
        bound(path, sha)
    return {
        'schema': 'CURRENT_QUOTE_OBSERVATION_LOCAL_GAP_ADDENDUM_NOT_PIT_MEMBERSHIP',
        'current_observed_security_count': 101, 'previous_observed_security_count': 102,
        'removed_observed_symbols': ['KHC'], 'added_observed_symbols': [],
        'provider_display_date': data['date'], 'request_received_at_utc': request['received_at_utc'],
        'displayed_quote_is_intraday': True, 'quote_date_is_membership_effective_date': False,
        'old_107_channel_overlap': 101-len(gaps), 'missing_old_channel_count': len(gaps),
        'missing_old_channels': sorted(gaps), 'local_gap_rows': local['rows'],
        'normalized_sina_csv_count': local['existing_normalized_sina_csv_count'],
        'mutable_root_cache_count': local['existing_root_cache_count'],
        'prior_102_source_drift_preserved': [r for r in local['prior_source_status'] if not r['unchanged']],
        'khc_event': {'type': 'EXCHANGE_TRANSFER', 'issuer': 'The Kraft Heinz Company',
                      'ticker_before': 'KHC', 'ticker_after': 'KHC', 'exchange_before': 'NASDAQ',
                      'exchange_after': 'NYSE', 'announced_date': '2026-08-26',
                      'operational_notice_effective_date': '2026-09-14',
                      'split_ratio_created': False, 'new_issuer_inferred': False,
                      'ndx_removal_effective_date': None,
                      'ndx_removal_effective_date_verified': False},
        'source_capture_results': events['captures'],
        'remaining_work': ['Original HTTP price responses for the fixed 22-channel queue remain absent in the bounded local search.',
                           '13 Sina files are normalized valuation CSVs with possible Close-filled Open; not original HTTP or nominal execution evidence.',
                           'Resolve dated share-class and lifecycle identity, particularly SPCX, SNDK, NBIS, HONA, FER, ARM and WDC; do not join ticker aliases.',
                           'Establish a completed-session training cutoff independently; this intraday quote list does not set that cutoff.',
                           'Find an index-specific KHC removal announcement before claiming its membership effective time.'],
        'historical_membership_verified': False, 'point_in_time_verified': False,
        'promotion_allowed': False, 'prices_reconstructed': False, 'training_performed': False,
        'source_hashes': dict(sorted(sources.items()))}


if __name__ == '__main__':
    report = build()
    output = BASE / 'current_101_khc_exchange_20260919_v1/local_gap_addendum.json'
    payload = (json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    with output.open('xb') as handle:
        handle.write(payload)
    print(json.dumps({'path': str(output), 'sha256': hashlib.sha256(payload).hexdigest(), 'source_count': len(report['source_hashes'])}))
