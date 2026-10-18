"""Independent eight-control price-unit review; preserve all old-source differences."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/cache/research/incumbent_price_source_probe_20260912_v1'
TICKERS = ['NVDA', 'TXN', 'ASML', 'CDNS', 'TSM', 'MU', 'MSFT', 'GOOG']


def run():
    sources = {}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected != digest:
            raise ValueError('Source SHA differs: ' + str(path))
        if str(path) in sources and sources[str(path)] != digest:
            raise ValueError('Conflicting source: ' + str(path))
        sources[str(path)] = digest
        return raw
    def manifest(path, digest):
        value = json.loads(read(path, digest))
        for source, expected in value['source_hashes'].items():
            read(source, expected)
        for row in value.get('probes', []):
            if row['response_path'] is not None:
                read(row['response_path'], row['response_sha256'])
        return value
    read(__file__)
    capture = manifest(DIRECTORY / 'manifest.json', '4e30f0f7e48b157eb4a5f60cd5d6531b097d2a276f977444838778411e30d77e')
    official = manifest(DIRECTORY / 'nvda_official_manifest_20260912.json', '1e1b411f19165c50ce816f7b7c2238bedae5315767c7d977152ae5dfc0fac839')
    help_manifest = manifest(ROOT / 'data/cache/research/preference_price_action_supplement_20260912_v1/manifest.json',
        'ef8baa8d5d370b87f31543c770b09703c2b2750c2f19686e444582eea6a67e32')
    schedule = json.loads(read(ROOT / 'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json',
        '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559'))
    calendar = schedule['schedule_result']['calendar']
    if len(calendar) != 295 or calendar[0] != '2023-03-31' or calendar[-1] != '2024-06-03':
        raise ValueError('Explicit original calendar differs')
    sec, = [row for row in official['probes'] if row['name'] == 'sec_nvda_20240607_effected_split']
    if sec['http_status'] != 200:
        raise ValueError('Official split document missing')
    sec_raw = read(sec['response_path'], sec['response_sha256'])
    sec_decoded = gzip.decompress(sec_raw) if sec_raw.startswith(b'\x1f\x8b') else sec_raw
    sec_text = ' '.join(BeautifulSoup(sec_decoded, 'html.parser').get_text(' ', strip=True).split())
    if not all(text in sec_text for text in ['ten-for-one forward stock split',
            'effective at 4:01 p.m. Eastern Time on June 7, 2024',
            'split-adjusted basis at market open on June 10, 2024']):
        raise ValueError('Official NVDA split terms differ')
    rows = []
    probes = {row['name']: row for row in capture['probes']}
    for ticker in TICKERS:
        probe = probes['yahoo_' + ticker.lower() + '_through_received_daily_events']
        if probe['http_status'] != 200 or probe['transport_success'] is not True:
            raise ValueError('Successful price response required')
        result, = json.loads(read(probe['response_path'], probe['response_sha256']))['chart']['result']
        if result['meta']['symbol'] != ticker or result['meta']['currency'] != 'USD':
            raise ValueError('Price coordinate differs')
        dates = [datetime.fromtimestamp(t, ZoneInfo('America/New_York')).date().isoformat() for t in result['timestamp']]
        if dates != sorted(set(dates)) or not set(calendar) <= set(dates):
            raise ValueError('Actual unique daily coverage differs')
        end = int(parse_qs(urlparse(probe['request']['url']).query)['period2'][0])
        end_utc = datetime.fromtimestamp(end, timezone.utc)
        received = datetime.fromisoformat(probe['received_at_utc'])
        if end_utc > received or end_utc.astimezone(ZoneInfo('America/New_York')).date() != received.astimezone(ZoneInfo('America/New_York')).date():
            raise ValueError('Returned split request lacks reception-date horizon')
        expected_events = {'1718026200': {'date': 1718026200, 'numerator': 10.0, 'denominator': 1.0, 'splitRatio': '10:1'}} if ticker == 'NVDA' else {}
        events = result.get('events', {}).get('splits', {})
        if events != expected_events:
            raise ValueError('Split-event review changed')
        factor = 10 if ticker == 'NVDA' else 1
        quote, = result['indicators']['quote']
        observed = pd.DataFrame({'Open': quote['open'], 'Close': quote['close']}, index=dates).loc[calendar] * factor
        if not observed.notna().all().all() or not (observed > 0).all().all():
            raise ValueError('Complete positive quotes required')
        folder = 'ndx_cardinality_execution_prices_all_ready_v1' if ticker in ('CDNS', 'GOOG', 'TXN') else 'ndx_cardinality_execution_prices_walkforward_v2'
        archived_path = ROOT / 'data/cache/research' / folder / 'raw' / (ticker + '.csv')
        sidecar = json.loads(read(archived_path.with_suffix('.csv.manifest.json')))
        if sidecar['price_basis'] != 'unadjusted_nominal_trade_price' or sidecar['corporate_action_adjustment'] != 'none':
            raise ValueError('Archived source does not declare nominal price basis')
        read(archived_path, sidecar['content_sha256'])
        archived = pd.read_csv(archived_path, index_col='Date')
        if not archived.index.is_unique:
            raise ValueError('Archived duplicate dates')
        common = [day for day in calendar if day in archived.index]
        if len(common) != 294 or sorted(set(calendar) - set(common)) != ['2024-06-03']:
            raise ValueError('Archived overlap denominator differs')
        differences = observed.loc[common] - archived.loc[common, ['Open', 'Close']]
        mismatches = [dict(session=day, field=field, new_reconstructed_price=float(observed.loc[day, field]),
            archived_price=float(archived.loc[day, field]), absolute_difference=float(abs(differences.loc[day, field])))
            for day in common for field in ('Open', 'Close') if abs(differences.loc[day, field]) > .01]
        rows.append(dict(ticker=ticker, price_response_path=probe['response_path'], price_response_sha256=probe['response_sha256'],
            received_at_utc=probe['received_at_utc'], requested_event_horizon_end_utc=end_utc.isoformat(),
            target_session_count=295, provider_session_count=len(dates), target_nominal_reconstruction_factor=factor,
            observed_full_requested_split_events=events, archived_source_path=str(archived_path), archived_source=sidecar['source'],
            archived_overlap_sessions=len(common), absent_archived_sessions=['2024-06-03'],
            max_absolute_open_difference=float(differences['Open'].abs().max()),
            max_absolute_close_difference=float(differences['Close'].abs().max()),
            diagnostic_threshold_usd=.01, differences_over_one_cent=mismatches,
            historical_provider_security_identity_decision='NOT_ADJUDICATED_HERE',
            retrospective_price_unit_decision='SUPPORTED_FOR_SAME_PROVIDER_RESEARCH_WITH_DISCLOSED_SOURCE_DIFFERENCES',
            old_economic_results_equivalent=False))
    output = dict(schema='ndx_incumbent_price_basis_review_v1',
        quote_field_basis='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS', basis_status='CONDITIONAL_RESEARCH_ONLY',
        control_role='ORIGINAL_INCUMBENT_BENCHMARK_NOT_TARGET_CARDINALITY', tickers=TICKERS,
        calendar=calendar, calendar_count=295, rows=rows, source_hashes=sources,
        nvda_official_split_terms_verified=True, nvda_official_document=sec['response_path'],
        nvda_legal_effective_date='2024-06-07', nvda_first_split_adjusted_session='2024-06-10',
        nvda_event_inside_target_window=False, quote_basis_review_independently_scoped_to_eight_controls=True,
        comparison_policy='Use same provider and same numerical reconstruction for preference and control; archived observations are corroboration, not a requirement to force equality.',
        raw_provider_documentation_limit='Yahoo help raw explains adjusted-close splits and dividends; split-only quote interpretation is conditionally supported by full returned events, official NVDA split terms and separate archived nominal price comparisons.',
        unresolved_difference='MSFT 2024-03-04 Close: Yahoo 414.9200134277344 versus archived Sina 414.77; preserve both, no overwrite. Different prices can affect integer trading thresholds.',
        dividends_must_remain_separate=True, adjclose_used=False, official_no_action_interval_certified=False,
        strategy_information_pit_verified=False, current_to_historical_security_binding_verified=False,
        execution_performed=False, promotion_allowed=False)
    for path, digest in list(sources.items()):
        read(path, digest)
    path = DIRECTORY / 'incumbent_price_basis_review_20260912.json'
    encoded = (json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()
    with path.open('xb') as handle:
        handle.write(encoded)
    if path.read_bytes() != encoded:
        raise ValueError('Readback differs')
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(encoded).hexdigest(),
        overlap_sessions_per_ticker=294, mismatch_cells=sum(len(row['differences_over_one_cent']) for row in rows))))


if __name__ == '__main__':
    run()
