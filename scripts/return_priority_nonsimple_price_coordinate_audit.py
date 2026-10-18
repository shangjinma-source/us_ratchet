"""Independent saved-source comparison; no price splicing or trading calls."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('Open', 'High', 'Low', 'Close')


def audit():
    pins = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected and digest != expected:
            raise ValueError('Changed input: ' + str(path))
        pins[str(path)] = digest
        return raw

    def csv_rows(path, expected=None):
        records = list(csv.DictReader(io.StringIO(read(path, expected).decode('utf-8-sig'))))
        assert len({r['Date'] for r in records}) == len(records)
        return {r['Date']: [Fraction(r[k]) for k in FIELDS] for r in records}

    def comparison(left, right):
        dates = sorted(set(left) & set(right))
        errors = [(abs(left[d][i] - right[d][i]), d, FIELDS[i], left[d][i], right[d][i])
                  for d in dates for i in range(4)]
        ordered = sorted(errors, reverse=True)
        return dict(overlap_dates=len(dates), start=dates[0] if dates else None,
                    end=dates[-1] if dates else None, fields=len(errors),
                    exact_fields=sum(e[0] == 0 for e in errors),
                    within_one_cent=sum(e[0] <= Fraction(1, 100) for e in errors),
                    maximum_absolute_error=str(ordered[0][0]) if ordered else None,
                    largest_errors=[dict(error=str(e), date=d, field=f, left=str(a), right=str(b))
                                    for e, d, f, a, b in ordered[:8]])

    archive = json.loads(read('data/cache/research/root_price_byte_archive_20260919_v1/archive_manifest.json'))
    coverage = json.loads(read('tmp/fixed12_data_coverage_20261014_v3/coverage.json'))
    read('tmp/fixed12_official_actions_20261014_v1/non_simple_action_web_observations.json')
    read('tmp/historical_split_source_notes_20261014_v1/source_notes.json')
    output = []
    for ticker in ('HON', 'CMCSA', 'ILMN'):
        declaration = next(r for r in archive['rows'] if Path(r['archived_path']).name.split('.')[0] == ticker)
        old = csv_rows(declaration['archived_path'], declaration['archived_sha256'])
        path = ROOT / 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw' / (ticker + '.csv')
        manifest = json.loads(read(str(path) + '.manifest.json'))
        sina = csv_rows(path, manifest['content_sha256'])
        assert len(sina) == manifest['row_count']
        folder = ('tmp/fixed12_missing_quote_capture_20261014_v1' if ticker == 'ILMN'
                  else 'data/cache/research/current_raw_capture_20261013_v1')
        raw = read(folder + '/' + ticker + '.response.bin')
        payload = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        result = payload['chart']['result'][0]
        assert result['meta']['symbol'] == ticker
        quote = result['indicators']['quote'][0]
        day = lambda timestamp: datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        rows = {}
        for index, timestamp in enumerate(result['timestamp']):
            values = [quote[k.lower()][index] for k in FIELDS]
            if all(value is not None for value in values):
                date = day(timestamp)
                assert date not in rows
                rows[date] = [Fraction(str(v)) for v in values]
        events = sorted((day(e['date']), Fraction(str(e['numerator'])) / Fraction(str(e['denominator'])))
                        for e in result.get('events', {}).get('splits', {}).values())
        restored = {}
        for date, values in rows.items():
            factor = Fraction(1)
            for event_date, ratio in events:
                if date < event_date:
                    factor *= ratio
            restored[date] = [value * factor for value in values]
        segments = []
        boundaries = ['0000-00-00'] + [d for d, _ in events] + ['9999-99-99']
        for start, end in zip(boundaries, boundaries[1:]):
            select = lambda data: {d: v for d, v in data.items() if start <= d < end}
            segments.append(dict(start_inclusive=start, end_exclusive=end,
                archive_vs_quote=comparison(select(old), select(rows)),
                archive_vs_provider_factor_restored=comparison(select(old), select(restored)),
                sina_vs_quote=comparison(select(sina), select(rows)),
                sina_vs_provider_factor_restored=comparison(select(sina), select(restored)),
                sina_vs_archive=comparison(select(sina), select(old))))
        windows = []
        for window in coverage['windows']:
            if ticker not in window['members']:
                continue
            windows.append(dict(cutoff=window['decision_cutoff'], coverage={
                name: dict(missing_training=[d for d in window['training_dates'] if d not in data],
                           missing_outcome=[d for d in window['outcome_dates'] if d not in data])
                for name, data in [('sina', sina), ('archive', old), ('raw', rows)]}))
        output.append(dict(ticker=ticker, sina_manifest=manifest,
            source_ranges={name: dict(start=min(data), end=max(data), rows=len(data))
                           for name, data in [('sina', sina), ('archive', old), ('raw', rows)]},
            provider_price_coordinate_events=[dict(date=d, factor=str(f), share_multiplier_authorized=False)
                                              for d, f in events], segments=segments, windows=windows))
    read(__file__)
    return dict(status='INDEPENDENT_PRICE_COORDINATE_COMPARISON_ONLY', comparisons=output,
                source_hashes=pins, no_fitted_factors=True, prices_spliced=False,
                strategy_calls=0, network_calls=0, source_selection_performed=False,
                caveat='Provider factors are tested as price coordinates only, never share multipliers. '
                       'Numeric overlap cannot authenticate nominal or total return semantics beyond overlap. '
                       'A one-cent diagnostic tolerance is not an adoption criterion.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Create-only receipt exists')
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(str(args.output))
