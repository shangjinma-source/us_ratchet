"""Freeze whole-source SMCI quote returns and conditional nominal coordinates."""
from datetime import datetime
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def prepare(root):
    base = root / 'tmp/smci_quote_capture_20261014_v1'
    sources = {}

    def read(path):
        raw = path.read_bytes()
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw

    receipt = json.loads(read(base / 'receipt.json'))
    raw = read(base / 'SMCI.response.bin')
    if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
        raise ValueError('Raw receipt mismatch')
    decoded = gzip.decompress(raw)
    if hashlib.sha256(decoded).hexdigest() != receipt['decoded_sha256']:
        raise ValueError('Decoded receipt mismatch')
    chart = json.loads(decoded)['chart']['result'][0]
    splits = list(chart.get('events', {}).get('splits', {}).values())
    zone = ZoneInfo('America/New_York')
    if chart['meta']['symbol'] != 'SMCI' or len(splits) != 1:
        raise ValueError('Unexpected symbol or action domain')
    split = splits[0]
    split_date = datetime.fromtimestamp(split['date'], zone).date().isoformat()
    if split_date != '2024-10-01' or split['numerator'] != 10 or split['denominator'] != 1:
        raise ValueError('Registered split differs')
    if set(chart.get('events', {})) - {'splits'}:
        raise ValueError('Additional returned event needs separate treatment')
    quote = chart['indicators']['quote'][0]
    rows = {}
    for index, stamp in enumerate(chart['timestamp']):
        day = datetime.fromtimestamp(stamp, zone).date().isoformat()
        if day in rows:
            raise ValueError('Duplicate session')
        values = {key: Fraction(str(quote[key][index])) for key in ('open', 'high', 'low', 'close')}
        if not 0 < values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
            raise ValueError('Invalid OHLC')
        factor = 10 if day < split_date else 1
        rows[day] = dict(quote={key: str(value) for key, value in values.items()},
                         conditional_nominal={key: str(value * factor) for key, value in values.items()},
                         nominal_factor=factor)
    coverage = json.loads(read(root / 'tmp/fixed12_data_coverage_20261014_v3/coverage.json'))
    read(root / 'tmp/fixed12_official_actions_20261014_v1/observed_primary_facts.json')
    windows = []
    for window in coverage['windows'][:5]:
        dates = window['training_dates'] + window['outcome_dates']
        if not set(dates) <= rows.keys():
            raise ValueError('Incomplete registered window')
        windows.append(dict(decision_cutoff=window['decision_cutoff'], training_dates=window['training_dates'],
                            outcome_dates=window['outcome_dates'], rows={day: rows[day] for day in dates}))
    return dict(status='CONDITIONAL_RECONSTRUCTION_NOT_NOMINAL_AUTHENTICATION', windows=windows,
                source_hashes=sources, split_date=split_date, new_shares=10, old_shares=1,
                training_rule='Use quote endpoint ratios; never multiply split into quote returns.',
                execution_rule='Use conditional_nominal prices; multiply held shares by ten once on split date.',
                no_price_splicing=True, no_missing_fill=True, strategy_calls=0, production_adoption_allowed=False,
                limitations=['Returned events are not an independent completeness certificate.',
                             'Provider split-adjusted quote interpretation is an explicit conditional assumption.'])


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    result = prepare(root)
    path = root / 'tmp/smci_quote_capture_20261014_v1/conditional_window_inputs.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(path)
