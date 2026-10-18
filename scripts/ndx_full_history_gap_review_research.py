"""Classify actual missing dates without inventing pre-listing or alias returns."""
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/cache/research/full_history_gap_source_probe_20260912_v1'


def main():
    sources = {}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source digest differs: ' + str(path))
        if str(path) in sources and sources[str(path)] != digest:
            raise ValueError('Source changed during review')
        sources[str(path)] = digest
        return raw

    read(__file__)
    manifests = [json.loads(read(DIRECTORY / 'manifest.json',
        'fa6d97f59de455fc3fae9a81a17aa55a220e4da3c23f0066d5b8df03c4a3c83d')),
        json.loads(read(DIRECTORY / 'ceg_when_issued_manifest.json',
        'cb89b13061c81ffef66dd122e2511499fe6cbae364357b76dcdfb42fc9ab5beb'))]
    old = json.loads(read(ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json',
        'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'))
    for manifest in manifests + [old]:
        for path, digest in manifest['source_hashes'].items():
            read(path, digest)
    prices, official, probes = {}, {}, {}
    for manifest in manifests:
        for probe in manifest['probes']:
            if probe['http_status'] != 200:
                raise ValueError('Expected raw evidence unavailable')
            raw = read(probe['response_path'], probe['response_sha256'])
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            probes[probe['name']] = probe
            if not probe['name'].startswith('yahoo_'):
                official[probe['name']] = ' '.join(BeautifulSoup(raw.decode('utf8'), 'html.parser').stripped_strings)
                continue
            response, = json.loads(raw)['chart']['result']
            ticker = response['meta']['symbol']
            if probe['name'] != 'yahoo_' + ticker.lower() + '_full_history' or response['meta']['currency'] != 'USD':
                raise ValueError('Unexpected provider channel')
            dates = [datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat()
                     for stamp in response['timestamp']]
            closes = response['indicators']['quote'][0]['close']
            if len(dates) != len(closes) or dates != sorted(set(dates)):
                raise ValueError('Ambiguous raw daily quotes')
            if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in closes):
                raise ValueError('Invalid raw Close')
            prices[ticker] = dict(zip(dates, closes))
    evidence_requirements = {
        'ceg_when_issued_notice': ['CEGVV', '21037T109', 'January 19, 2022', 'February 2, 2022'],
        'ceg_regular_way_20220202': ['Feb. 2, 2022', 'regular way', 'CEG'],
        'gehc_when_issued_notice': ['GEHCV', '36266G107', 'December 15, 2022', 'January 4, 2023'],
        'gehc_regular_way_20230104': ['January 4, 2023', 'effective at the market opening today'],
        'wbd_conversion_8k': ['reclassified and converted into one share of WBD common stock', 'DISCA', 'DISCB', 'DISCK'],
    }
    for name, markers in evidence_requirements.items():
        if any(marker not in official[name] for marker in markers):
            raise ValueError('Reviewed primary-source event marker absent: ' + name)
    events = {
        'CEG': dict(kind='WHEN_ISSUED_TO_REGULAR_WAY', first_observed_market_date='2022-01-19',
            regular_way_date='2022-02-02', prior_ticker='CEGVV', regular_ticker='CEG', cusip='21037T109',
            missing_history_policy='NO_PRE_WHEN_ISSUED_PRICE_OR_ZERO_FILL',
            primary_sources=['ceg_when_issued_notice', 'ceg_regular_way_20220202']),
        'GEHC': dict(kind='WHEN_ISSUED_TO_REGULAR_WAY', first_observed_market_date='2022-12-15',
            regular_way_date='2023-01-04', prior_ticker='GEHCV', regular_ticker='GEHC', cusip='36266G107',
            missing_history_policy='NO_PRE_WHEN_ISSUED_PRICE_OR_PARENT_GE_RETURN_FILL',
            primary_sources=['gehc_when_issued_notice', 'gehc_regular_way_20230104']),
        'WBD': dict(kind='MULTIPLE_PREDECESSOR_SHARE_CLASSES_RECLASSIFIED', regular_way_date='2022-04-11',
            prior_tickers=['DISCA', 'DISCB', 'DISCK'], regular_ticker='WBD',
            missing_history_policy='PRE_APRIL11_PROVIDER_ROWS_REQUIRE_SPECIFIC_PREDECESSOR_CLASS_BINDING',
            primary_sources=['wbd_conversion_8k']),
    }
    cohorts = []
    locations = {row['coordinate']['selection_date']: row for row in old['actual_window_error_locations']}
    for cohort in old['first_last_full_training_data_coverage']:
        context_sha = locations[cohort['coordinate']['selection_date']]['context_sha256']
        context_paths = [path for path, digest in old['source_hashes'].items()
                         if digest == context_sha and Path(path).name == 'context.json']
        context_path, = context_paths
        context = json.loads(read(context_path, context_sha))
        panel = context['prepared_inputs']['returns']['payload']['mapping']
        dates = [value['timestamp'][:10] for value in panel['index']['items']]
        # Use the newly captured DASH session sequence as an observed predecessor calendar.
        # This is expressly not an independent exchange-calendar certification.
        reference = list(prices['DASH'])
        previous = {day: reference[index-1] for index, day in enumerate(reference) if index}
        if any(day not in previous for day in dates):
            raise ValueError('Reference calendar lacks a required predecessor')
        rows = []
        for ticker in ('CEG', 'GEHC', 'WBD', 'DASH', 'ROP'):
            original = [row for row in cohort['rows'] if row['ticker'] == ticker]
            if not original:
                continue
            quoted = prices[ticker]
            missing = [day for day in dates if day not in quoted or previous[day] not in quoted]
            predecessor_unresolved = [day for day in dates if ticker == 'WBD' and previous[day] < '2022-04-11']
            when_issued = [day for day in dates if ticker in ('CEG', 'GEHC')
                          and day in quoted and day < events[ticker]['regular_way_date']]
            rows.append(dict(ticker=ticker, expected_return_rows=len(dates),
                root_missing_close_dates=original[0]['missing_full_training_close_dates'],
                raw_missing_adjacent_price_return_dates=missing,
                predecessor_class_binding_unresolved_return_dates=predecessor_unresolved,
                observed_when_issued_quote_dates=when_issued,
                raw_adjacent_price_coverage_complete=not missing,
                provider_current_symbol_is_historical_ticker=False,
                historical_identity_join_authorized=False,
                complete_training_input_authorized=False))
        cohorts.append(dict(coordinate=cohort['coordinate'], context_sha256=context_sha, rows=rows))
    for path, digest in list(sources.items()):
        read(path, digest)
    report = dict(schema='ndx_full_history_gap_review_v1', source_hashes=sources, corporate_event_facts=events,
        raw_panels=[dict(ticker=ticker, row_count=len(rows), first_session=min(rows), last_session=max(rows))
                    for ticker, rows in prices.items()], first_last_cohorts=cohorts,
        primary_event_marker_checks_passed=True,
        reference_calendar='NEW_DASH_PROVIDER_OBSERVED_SESSIONS_NOT_EXCHANGE_CERTIFICATION',
        basis='RAW_QUOTE_CLOSE_PRICE_RETURN_CANDIDATE_NOT_ADJCLOSE_TOTAL_RETURN',
        numerical_gap_fill_only_is_insufficient=True, old_cache_modified=False, training_performed=False,
        stable_coordinate_authenticity_verified=False, point_in_time_verified=False, promotion_allowed=False)
    output = DIRECTORY / 'gap_review_20260912.json'
    with output.open('x', encoding='utf8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        cohorts=[dict(coordinate=cohort['coordinate'], rows=[dict(ticker=row['ticker'],
            missing_adjacent_return_dates=len(row['raw_missing_adjacent_price_return_dates']),
            unresolved_predecessor_dates=len(row['predecessor_class_binding_unresolved_return_dates']),
            when_issued_dates=len(row['observed_when_issued_quote_dates'])) for row in cohort['rows']])
            for cohort in cohorts])))


if __name__ == '__main__':
    main()
