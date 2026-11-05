"""Bounded offline volume coverage check; no trading or price-basis admission."""
import gzip
import csv
import argparse
import io
import json
from collections import Counter
from datetime import datetime
from hashlib import sha256
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo


def trace_derived_volume(name, bars, pins):
    """Follow only the derivative's explicit source provenance; no ticker join."""
    path = Path(name)
    ticker = path.name.split('_')[0]
    if path.parent.name == 'candlestick_gap_probe_20261025':
        audit_path = path.parent / 'ALXN_price_candidate_audit.json'
        aliases = {'CANDLESTICK_ARCHIVE': str(path.parent / 'ALXN.csv'),
                   'QUIVER_TABLE': 'tmp/modern_missing_probe_20261025/ALXN_quiver.csv'}
    elif path.parent.name == 'modern_archive_inventory_20261025':
        audit_path = path.parent / 'ATVI_price_candidate_audit.json'
        aliases = {'PAULMOONEY_ARCHIVE': str(path.parent / 'ATVI.csv'),
                   'QUIVER_VISIBLE_DAILY_TABLE': 'tmp/modern_missing_probe_20261025/ATVI_quiver.csv'}
    elif path.parent.name == 'chartexchange_gap_20261025':
        audit_path = path.parent / (ticker+'_audit.json')
        aliases = {'ARCHIVE': f'tmp/candlestick_gap_probe_20261025/{ticker}.csv',
                   'CHARTEXCHANGE': str(path.parent / (ticker+'_chart.csv')),
                   'QUIVER': f'tmp/modern_missing_probe_20261025/{ticker}_quiver.csv'}
    elif path.parent.name == 'recent_price_bridges_20261026':
        audit_path, aliases = path.parent / (ticker+'_audit.json'), {}
    elif path.parent.name == 'anss_terminal_bridge_20261026':
        audit_path, aliases = path.parent / 'review.json', {}
    else:
        raise ValueError('NO_EXPLICIT_DERIVATION_ROUTE')
    norm = lambda value: str(value).replace('\\', '/')
    audit_raw = audit_path.read_bytes()
    audit = json.loads(audit_raw)
    expected = {norm(p): h for p, h in audit.get('source_hashes', {}).items()}
    expected.update({norm(r['path']): r['sha256'] for r in audit.get('sources', [])})
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    if pins.get(name) != digest:
        raise ValueError('DERIVED_PARENT_PIN_MISMATCH')
    if norm(name) in expected and expected[norm(name)] != digest:
        raise ValueError('AUDIT_DERIVED_HASH_MISMATCH')
    if 'output_sha256' in audit and audit['output_sha256'] != digest:
        raise ValueError('AUDIT_OUTPUT_HASH_MISMATCH')
    source_rows, hashes, series, failures = {}, {norm(audit_path): sha256(audit_raw).hexdigest()}, {}, []
    comparisons = []
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
        day = row['date']
        if day not in bars:
            continue
        source = norm(aliases.get(row['source'], row['source']))
        try:
            if source not in source_rows:
                value = Path(source).read_bytes()
                actual = sha256(value).hexdigest()
                if expected.get(source) != actual:
                    raise ValueError('ORIGINAL_AUDIT_PIN_MISSING_OR_CHANGED')
                if source in pins and pins[source] != actual:
                    raise ValueError('PARENT_SOURCE_PIN_CONFLICT')
                hashes[source] = actual
                rows = {}
                for item in csv.DictReader(io.StringIO(value.decode('utf-8-sig'))):
                    item = {key.lower(): value for key, value in item.items()}
                    date = item['date'][:10]
                    if source in ('tmp/modern_archive_inventory_20261025/ATVI.csv',
                                  'tmp/modern_archive_inventory_20261025/SGEN.csv',
                                  'tmp/modern_archive_inventory_20261025/SPLK.csv'):
                        date = datetime.strptime(date, '%d-%m-%Y').date().isoformat()
                    else:
                        datetime.fromisoformat(date)
                    if date in rows:
                        raise ValueError('ORIGINAL_DUPLICATE_DATE')
                    rows[date] = item
                source_rows[source] = rows
            original = source_rows[source][day]
            if row.get('source_sha256') and row['source_sha256'] != hashes[source]:
                raise ValueError('ROW_SOURCE_PIN_MISMATCH')
            if any(Fraction(original[key].replace(',', '')) != Fraction(row[key])
                   for key in ('open', 'high', 'low', 'close')):
                raise ValueError('DERIVED_ORIGINAL_OHLC_MISMATCH')
            volume = Fraction(original['volume'].replace(',', ''))
            if volume < 0 or volume.denominator != 1:
                raise ValueError('ORIGINAL_INVALID_VOLUME')
            series.setdefault(source, {})[day] = int(volume)
            comparisons.append(dict(date=day, original_source=source, ohlc_exact_match=True))
        except (ValueError, KeyError, OSError) as error:
            failures.append(dict(date=day, path=source, error=str(error)))
    return dict(series=series, hashes=hashes, comparisons=comparisons, failures=failures,
                provenance='Parent-pinned derivative + existing audit expected original hash + exact per-row OHLC; audit newly snapshotted, not claimed part of old frozen closure')


def inspect(window):
    source = Path(f'tmp/momentum_account_{window}_20261105_v1/D0/execution_inputs.json')
    raw = source.read_bytes()
    document = json.loads(raw)['payload']['document']
    assembled = document['assembled']
    pins = document['source_hashes']
    output, cache, trace_hashes = {}, {}, {}
    for security, bars in document['ohlc'].items():
        paths = assembled['price_source_references'].get(security, [])
        series, failures = {}, []
        for name in paths:
            if name not in cache:
                try:
                    value = Path(name).read_bytes()
                    if name not in pins or sha256(value).hexdigest() != pins[name]:
                        raise ValueError('SOURCE_NOT_PINNED_OR_CHANGED')
                    if len(value) > 8*1024*1024:
                        raise ValueError('TRANSPORT_SIZE_LIMIT')
                    body = value
                    if value[:2] == b'\x1f\x8b':
                        with gzip.GzipFile(fileobj=io.BytesIO(value)) as stream:
                            body = stream.read(8*1024*1024+1)
                    if len(body) > 8*1024*1024:
                        raise ValueError('DECODED_SIZE_LIMIT')
                    if name.endswith('.csv'):
                        records = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
                        if not records or 'Volume' not in records[0] or 'Date' not in records[0]:
                            raise ValueError('CSV_WITHOUT_VOLUME')
                        rows = {}
                        for record in records:
                            day = record['Date'][:10]
                            datetime.fromisoformat(day)
                            volume = Fraction(record['Volume'].replace(',', ''))
                            if volume < 0 or volume.denominator != 1 or day in rows:
                                raise ValueError('INVALID_CSV_VOLUME_OR_DUPLICATE')
                            rows[day] = int(volume)
                        cache[name] = dict(rows=rows, source_sha256=pins[name], ticker=None)
                        series[name] = {day: volume for day, volume in rows.items() if day in bars}
                        continue
                    chart = json.loads(body)['chart']['result'][0]
                    times = chart['timestamp']
                    volumes = chart['indicators']['quote'][0]['volume']
                    if len(times) != len(volumes):
                        raise ValueError('VOLUME_LENGTH_MISMATCH')
                    rows = {}
                    for epoch, volume in zip(times, volumes):
                        day = datetime.fromtimestamp(epoch, ZoneInfo('America/New_York')).date().isoformat()
                        if type(volume) is int and volume >= 0:
                            if day in rows:
                                raise ValueError('DUPLICATE_DAY')
                            rows[day] = volume
                    cache[name] = dict(rows=rows, source_sha256=pins[name], ticker=chart['meta'].get('symbol'))
                except (ValueError, KeyError, TypeError, OSError) as error:
                    cache[name] = dict(error=type(error).__name__+':'+str(error)[:100])
            value = cache[name]
            if 'error' in value:
                failures.append(dict(path=name, error=value['error']))
            else:
                series[name] = {day: volume for day, volume in value['rows'].items() if day in bars}
        trace_reviews = []
        for failure in list(failures):
            if failure['error'] != 'ValueError:CSV_WITHOUT_VOLUME':
                continue
            try:
                traced = trace_derived_volume(failure['path'], bars, pins)
                for original, rows in traced.pop('series').items():
                    series[original] = rows
                for original, digest in traced.pop('hashes').items():
                    if original in trace_hashes and trace_hashes[original] != digest:
                        raise ValueError('TRACE_HASH_CONFLICT')
                    trace_hashes[original] = digest
                trace_reviews.append(dict(derived_path=failure['path'], **traced))
            except (ValueError, KeyError, OSError) as error:
                trace_reviews.append(dict(derived_path=failure['path'], error=str(error)))
        covered = set().union(*(set(rows) for rows in series.values())) if series else set()
        # Keep source-separated values: identity segments and split-volume units
        # must be reviewed before merging or forming dollar-volume filters.
        output[security] = dict(required_days=len(bars), available_days=len(covered),
            missing_days=sorted(set(bars)-covered), volume_by_source=series, failures=failures,
            derived_source_trace=trace_reviews)
    return dict(input_sha256=sha256(raw).hexdigest(), securities=output,
        source_hashes={**trace_hashes, **{name:value['source_sha256'] for name,value in cache.items() if 'source_sha256' in value}},
        failure_counts=dict(Counter(item['error'] for row in output.values() for item in row['failures'])),
        source_identity_and_volume_units_admitted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='tmp/pullback_volume_inventory_20261105')
    folder = Path(parser.parse_args().output)
    folder.mkdir(parents=True, exist_ok=False)
    for window in ('early', 'late'):
        result = inspect(window)
        (folder/(window+'.json')).write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')
        rows = result['securities']
        print(window, 'securities',len(rows),'complete',sum(not row['missing_days'] for row in rows.values()),
              'missing_days',sum(len(row['missing_days']) for row in rows.values()),'failures',result['failure_counts'])
