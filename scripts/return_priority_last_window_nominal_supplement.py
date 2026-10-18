"""One create-only conditional unit-basis supplement; zero search/outcome calls."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    'BKR': '110f448aed291c25bf0898d4a5747e694208b49b845c62a0b6245e7cbc63f6b7',
    'CEG': '77722c4c61388ca4f1073ad77f2f921a20713c93275b3f3c2918c1943e39806e',
}


def prepare(input_path):
    hashes = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source hash mismatch: ' + str(path))
        hashes[str(path)] = digest
        return raw

    def csv_rows(raw):
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        if len({row['Date'] for row in rows}) != len(rows):
            raise ValueError('Duplicate price dates')
        return {row['Date']: row for row in rows}

    payload = json.loads(read(input_path))
    for path, digest in payload['source_hashes'].items():
        read(path, digest)
    read(Path(__file__))
    windows_before = json.dumps(payload['windows'][:-1], sort_keys=True)
    window = payload['windows'][-1]
    if len(payload['windows']) != 15 or window['decision_cutoff'] != '2024-05-31':
        raise ValueError('Expected fifteen frozen windows')
    args = window['outcome_arguments']
    symbols = {row['ticker']: sid for sid, row in args['metadata'].items()}
    if set(symbols) != {'NVDA', 'BKR', 'CEG'}:
        raise ValueError('Frozen last-window selection differs')
    days = args['session_dates'][1:]
    original = json.loads(json.dumps(args['nominal_prices']))
    audits, field_sources = {}, {}
    for ticker, sid in symbols.items():
        nominal_path = 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw/' + ticker + '.csv'
        manifest = json.loads(read(nominal_path + '.manifest.json'))
        if manifest['price_basis'] != 'unadjusted_nominal_trade_price' or manifest['corporate_action_adjustment'] != 'none':
            raise ValueError('Nominal anchor basis changed')
        anchors = csv_rows(read(nominal_path, manifest['content_sha256']))
        if ticker in ARCHIVES:
            source = 'data/cache/research/root_price_byte_archive_20260919_v1/' + ticker + '.' + ARCHIVES[ticker] + '.csv'
            rows = csv_rows(read(source, ARCHIVES[ticker]))
            overlap = sorted(set(rows) & set(anchors))
            differences = [{'date': day, 'field': key, 'nominal': anchors[day][key], 'archive': rows[day][key]}
                           for day in overlap for key in ('Open', 'High', 'Low', 'Close')
                           if Fraction(anchors[day][key]) != Fraction(rows[day][key])]
            if not overlap or differences:
                raise ValueError('Archive does not match all nominal overlap')
            audits[ticker] = {'overlap_days': len(overlap), 'overlap_fields': 4 * len(overlap),
                              'differences': differences, 'basis': 'CONDITIONAL_ARCHIVE_WITH_EXACT_NOMINAL_OVERLAP'}
            factors = {day: 1 for day in days}
        else:
            source = 'data/cache/research/current_raw_capture_20261013_v1/NVDA.response.bin'
            receipt = json.loads(read(source.replace('.response.bin', '.receipt.json')))
            raw = read(source, receipt['raw_sha256'])
            chart = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)['chart']['result'][0]
            if chart['meta']['symbol'] != 'NVDA':
                raise ValueError('Provider symbol mismatch')
            zone = ZoneInfo(chart['meta']['exchangeTimezoneName'])
            quote = chart['indicators']['quote'][0]
            rows = {datetime.fromtimestamp(stamp, zone).date().isoformat():
                    {key.title(): str(quote[key][i]) for key in ('open', 'high', 'low', 'close')}
                    for i, stamp in enumerate(chart['timestamp'])}
            registry = json.loads(read('tmp/historical_split_registry_diagnostic_20261014_v2/explicit_conditional_events.json'))
            event = next(e for e in registry if e['ticker'] == 'NVDA' and e['event_date'] == '2024-06-10')
            if Fraction(event['factor']) != 10:
                raise ValueError('Official split ratio changed')
            for evidence in event['evidence']:
                read(evidence['path'], evidence['sha256'])
            provider_events = chart.get('events', {}).get('splits', {})
            if len(provider_events) != 1:
                raise ValueError('Unexpected provider split set')
            provider_event = next(iter(provider_events.values()))
            if datetime.fromtimestamp(provider_event['date'], zone).date().isoformat() != '2024-06-10' or Fraction(str(provider_event['numerator'])) / Fraction(str(provider_event['denominator'])) != 10:
                raise ValueError('Provider split differs from official event')
            overlap = sorted(set(rows) & set(anchors))
            comparisons = [{'date': day, 'field': key, 'nominal': anchors[day][key],
                            'quote_times_ten': str(Fraction(rows[day][key]) * 10),
                            'absolute_difference': str(abs(Fraction(rows[day][key]) * 10 - Fraction(anchors[day][key])))}
                           for day in overlap for key in ('Open', 'High', 'Low', 'Close')]
            price_differences = [row for row in comparisons if Fraction(row['absolute_difference']) > Fraction('0.001')]
            recent = [row for row in comparisons if row['date'] >= '2024-01-01']
            recent_differences = [row for row in price_differences if row['date'] >= '2024-01-01']
            if len(recent) != 424 or len(recent_differences) != 1 or recent_differences[0]['date'] != '2024-05-10' or Fraction(recent_differences[0]['absolute_difference']) > Fraction('0.011'):
                raise ValueError('Root-reviewed conditional crosscheck differs')
            audits[ticker] = {'basis': 'CONDITIONAL_QUOTE_RECONSTRUCTED_NOMINAL', 'all_overlap_field_count': len(comparisons),
                              'all_overlap_comparisons': comparisons, 'price_level_differences_not_float_noise': price_differences,
                              'recent_2024_field_count': len(recent), 'recent_price_level_differences': recent_differences,
                              'root_accepted_scope': '2024 unit consistency; one circa USD0.01 supplier Open difference accepted. Earlier circa USD0.15 differences retained. Not permanent cross-provider price equality or live order price approval.'}
            factors = {day: 10 if day < '2024-06-10' else 1 for day in days}
        args['nominal_prices'][sid] = {}
        field_sources[sid] = {}
        for day in days:
            args['nominal_prices'][sid][day] = {}
            field_sources[sid][day] = {}
            for key in ('open', 'close'):
                value = Fraction(rows[day][key.title()]) * factors[day]
                if value <= 0:
                    raise ValueError('Nonpositive or missing replacement price')
                args['nominal_prices'][sid][day][key] = str(value)
                field_sources[sid][day][key] = {'path': source, 'multiplier': factors[day], 'conditional': True}
    window['original_sina_nominal_prices_preserved'] = original
    window['supplement_source_audits'] = audits
    window['price_field_sources'] = field_sources
    window['original_price_gaps_preserved'] = window['price_gaps']
    window['price_gaps'] = []
    window['status'] = 'PREPARED_CONDITIONAL_COMPLETE_LAST_WINDOW_NOT_EXECUTED'
    for row in window['coverage']:
        row['original_source_basis_preserved'] = row['source_basis']
        row['source_basis'] = audits[row['ticker']]['basis']
    payload['source_hashes'].update(hashes)
    payload['limitations'].append('Last window uses complete 21-day source sequences per stock. NVDA raw quote reconstructed via June10 10:1; BKR/CEG archives accepted conditionally on exact nominal overlap. No PIT certification. Supplier price differences explicitly retained; no live price tolerance change.')
    if json.dumps(payload['windows'][:-1], sort_keys=True) != windows_before:
        raise ValueError('Earlier windows changed')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        raise ValueError('Create-only output exists')
    result = prepare(args.input)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
