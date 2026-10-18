"""Prepare frozen historical OHLC only; no strategy, search or book invocation."""
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


def decision_unit_history(*, nominal_ohlc, calendar, security_id, decision_date, split_events):
    """Return last20 bars in decision-day share units; no future price/event payload reads."""
    end = calendar.index(decision_date)
    days = calendar[max(0, end - 19):end + 1]
    if len(days) != 20:
        raise ValueError('Twenty completed sessions required')
    splits = {}
    for event in split_events:
        if event['date'] > decision_date or event['date'] <= days[0]:
            continue
        if event['security_id'] != security_id:
            continue
        if event['date'] in splits or not event.get('source_references'):
            raise ValueError('Duplicate or unsupported split')
        ratio = Fraction(str(event['new_shares'])) / Fraction(str(event['old_shares']))
        if ratio <= 0:
            raise ValueError('Positive split ratio required')
        splits[event['date']] = ratio
    bars = []
    for day in days:
        factor = Fraction(1)
        for effective, ratio in splits.items():
            if day < effective <= decision_date:
                factor *= ratio
        raw = nominal_ohlc[security_id][day]
        values = {key: Fraction(str(raw[key])) / factor for key in ('open', 'high', 'low', 'close')}
        if min(values.values()) <= 0 or not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
            raise ValueError('Invalid OHLC')
        bars.append(dict(date=day, **{key: str(value) for key, value in values.items()}))
    return dict(basis='DECISION_NOMINAL_SHARE_UNITS', unit_asof=decision_date,
                complete_session_history=True, bars=bars)


def prepare(input_path):
    sources = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source changed: ' + str(path))
        sources[str(path)] = digest
        return raw

    def rows(raw):
        records = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        if len({r['Date'] for r in records}) != len(records):
            raise ValueError('Duplicate CSV date')
        return {r['Date']: {k.lower(): r[k] for k in ('Open', 'High', 'Low', 'Close')} for r in records}

    data = json.loads(read(input_path, '9e19a08d16719b72603ba049ceab4ad2157f33755370e47bd8ba0a98319d316f'))
    for path, expected in data['source_hashes'].items():
        read(path, expected)
    read(Path(__file__))
    panel = json.loads(read('tmp/current_ohlc_actual_projection_20261013_v1/panel.json'))
    calendar = panel['calendar']
    registry = json.loads(read('tmp/historical_split_registry_diagnostic_20261014_v2/explicit_conditional_events.json'))
    notes_path = 'tmp/historical_split_source_notes_20261014_v1/source_notes.json'
    registry += json.loads(read(notes_path))['conditional_split_supplement']
    cache, output = {}, []

    def nominal(ticker):
        path = 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw/' + ticker + '.csv'
        if path not in cache:
            manifest = json.loads(read(path + '.manifest.json'))
            if manifest['price_basis'] != 'unadjusted_nominal_trade_price' or manifest['corporate_action_adjustment'] != 'none':
                raise ValueError('Nominal anchor basis differs')
            cache[path] = rows(read(path, manifest['content_sha256']))
        return cache[path], path

    for window in data['windows']:
        args = window['outcome_arguments']
        decision = window['decision_cutoff']
        index = calendar.index(decision)
        days = calendar[index - 19:index + 22]
        if len(days) != 41 or days[19:] != args['session_dates']:
            raise ValueError('Frozen 41-session calendar differs')
        values, provenance, gaps, splits = {}, {}, [], []
        for sid, metadata in args['metadata'].items():
            ticker = metadata['ticker']
            values[sid], provenance[sid] = {}, {}
            for event in registry:
                if event['ticker'] == ticker and days[0] < event['event_date'] <= days[-1]:
                    splits.append(dict(security_id=sid, date=event['event_date'],
                                       new_shares=event['new_shares'], old_shares=event['old_shares'],
                                       source_references=event.get('evidence') or [notes_path]))
            for day in days:
                multiplier = Fraction(1)
                basis = 'SINA_DECLARED_NOMINAL_VALUATION_ONLY'
                if decision == '2024-05-31' and day > decision:
                    source = window['price_field_sources'][sid][day]['open']
                    path = source['path']
                    multiplier = Fraction(str(source['multiplier']))
                    basis = window['supplement_source_audits'][ticker]['basis']
                    if path not in cache:
                        raw = read(path)
                        if ticker == 'NVDA':
                            chart = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)['chart']['result'][0]
                            zone = ZoneInfo(chart['meta']['exchangeTimezoneName'])
                            quote = chart['indicators']['quote'][0]
                            cache[path] = {datetime.fromtimestamp(stamp, zone).date().isoformat():
                                           {key: quote[key][i] for key in ('open', 'high', 'low', 'close')}
                                           for i, stamp in enumerate(chart['timestamp'])}
                        else:
                            cache[path] = rows(raw)
                    raw_rows = cache[path]
                else:
                    symbol = ('FISV' if day <= '2023-06-06' else 'FI') if ticker in ('FISV', 'FI') else ticker
                    raw_rows, path = nominal(symbol)
                values[sid][day], provenance[sid][day] = {}, {}
                for key in ('open', 'high', 'low', 'close'):
                    raw_value = raw_rows.get(day, {}).get(key)
                    if raw_value is None:
                        gaps.append(dict(security_id=sid, ticker=ticker, date=day, field=key, reason='MISSING_SOURCE_FIELD'))
                        continue
                    value = Fraction(str(raw_value)) * multiplier
                    if value <= 0:
                        gaps.append(dict(security_id=sid, ticker=ticker, date=day, field=key, reason='NONPOSITIVE_SOURCE_FIELD'))
                        continue
                    values[sid][day][key] = str(value)
                    provenance[sid][day][key] = dict(path=path, multiplier=str(multiplier), basis=basis)
                    if day > decision and key in ('open', 'close') and key in args['nominal_prices'][sid].get(day, {}):
                        if value != Fraction(args['nominal_prices'][sid][day][key]):
                            raise ValueError('Baseline price differs')
        output.append(dict(decision_cutoff=decision, calendar=days, nominal_ohlc=values,
                           metadata=args['metadata'], frozen_weights=args['target_weights'],
                           initial_cash=args['entered_cash'], fee_bps='0', price_field_sources=provenance,
                           events=dict(split_events=splits, cash_merger_events=args['cash_merger_events'],
                                       unmodelled_action_events=args['unmodelled_action_events']),
                           missing_fields=gaps, status='PREPARED_WITH_GAPS' if gaps else 'PREPARED_COMPLETE_OHLC',
                           baseline_limitations=data['limitations']))
    return dict(windows=output, source_hashes=sources, book_calls=0, search_calls=0,
                point_in_time_authenticated=False, research_only=True,
                rule='No outcome-dependent selection changes; nominal OHLC plus explicit dated corporate actions.')


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
        json.dump(result, stream, ensure_ascii=False, indent=2)
