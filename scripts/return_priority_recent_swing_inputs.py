"""Prepare five previously frozen recent windows; no strategy/book/search calls."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'tmp/quantity_temporal_conditional_20261014_v1'


def prepare():
    hashes = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source changed: ' + str(path))
        hashes[str(path)] = digest
        return raw

    read(Path(__file__))
    panel_path = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
    panel = json.loads(read(panel_path, '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822'))
    original = json.loads(read(BASE / 'result.json'))
    registration = json.loads(read(BASE / 'registration.json'))
    read(BASE / 'independent_readback.json')
    for path, expected in registration['source_pins'].items():
        read(path, expected)
    calendar = panel['calendar']
    stocks = {stock['ticker']: stock for stock in panel['stocks']}
    raw_cache, windows = {}, []
    for baseline in original['windows']:
        decision, end = baseline['decision'], baseline['end']
        folder = BASE / decision
        frozen = json.loads(read(folder / 'frozen_execution_target.json'))
        inputs = json.loads(read(folder / 'inputs.json'))
        read(folder / 'search.json')
        read(folder / 'strategy_book.json')
        read(folder / 'strategy_outcome.json')
        for symbol in ('QQQ', 'SPY'):
            read(folder / (symbol + '_outcome.json'))
        start = calendar.index(decision)
        stop = calendar.index(end)
        dates = calendar[start - 19:stop + 1]
        if len(dates[:20]) != 20 or dates[19] != decision:
            raise ValueError('Warmup calendar missing')
        values, provenance, gaps, audits, blocked = {}, {}, [], {}, []
        metadata = {sid: inputs['search_arguments']['metadata'][sid] for sid in frozen['target_weights']}
        for sid, meta in metadata.items():
            ticker = meta['ticker']
            if ticker not in raw_cache:
                base = 'data/cache/research/current_raw_capture_20261013_v1/' + ticker
                receipt = json.loads(read(base + '.receipt.json'))
                raw = read(base + '.response.bin', receipt['raw_sha256'])
                decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
                chart = json.loads(decoded)['chart']['result'][0]
                if chart['meta']['symbol'] != ticker:
                    raise ValueError('Raw ticker mismatch')
                zone = ZoneInfo(chart['meta']['exchangeTimezoneName'])
                quote = chart['indicators']['quote'][0]
                raw_dates = [datetime.fromtimestamp(t, zone).date().isoformat() for t in chart['timestamp']]
                if len(raw_dates) != len(set(raw_dates)):
                    raise ValueError('Duplicate provider sessions')
                rows = {day: {key: quote[key][i] for key in ('open', 'high', 'low', 'close')} for i, day in enumerate(raw_dates)}
                events = []
                for kind, group in chart.get('events', {}).items():
                    if kind == 'dividends':
                        continue
                    for event in group.values():
                        events.append(dict(provider_type=kind, date=datetime.fromtimestamp(event['date'], zone).date().isoformat(), payload=event))
                raw_cache[ticker] = (rows, events, receipt, base)
            rows, provider_events, receipt, base = raw_cache[ticker]
            relevant_events = [event for event in provider_events if dates[0] <= event['date'] <= receipt['receipt_new_york_date']]
            if relevant_events:
                blocked.append(dict(security_id=sid, reason='PROVIDER_CORPORATE_ACTION_REQUIRES_UNIT_REVIEW', events=relevant_events))
            audits[sid] = dict(ticker=ticker, capture_date=receipt['receipt_new_york_date'],
                               whole_window_start=dates[0], whole_window_end=end,
                               events_from_warmup_through_capture=relevant_events,
                               earlier_provider_events=[event for event in provider_events if event['date'] < dates[0]],
                               provider_event_completeness_authenticated=False,
                               spinoff_absence_authenticated=False,
                               interpretation='No returned event in relevant interval is conditional evidence only, not proof of no corporate actions. WDC 2025 provider ratio is not admitted as a simple share split; it predates all these windows.',
                               price_basis='CONDITIONAL_PROVIDER_QUOTE_UNITS_NO_RECONSTRUCTION')
            values[sid], provenance[sid] = {}, {}
            for day in dates:
                panel_row = stocks[ticker]['values'][calendar.index(day)]
                values[sid][day], provenance[sid][day] = {}, {}
                for offset, key in enumerate(('open', 'high', 'low', 'close')):
                    raw_value = rows.get(day, {}).get(key)
                    if raw_value != panel_row[offset]:
                        raise ValueError('Panel/raw field mismatch: ' + ticker + ' ' + day + ' ' + key)
                    if raw_value is None or Fraction(str(raw_value)) <= 0:
                        gaps.append(dict(security_id=sid, date=day, field=key, reason='MISSING_OR_INVALID_PROVIDER_FIELD'))
                        continue
                    values[sid][day][key] = str(Fraction(str(raw_value)))
                    provenance[sid][day][key] = dict(path=base + '.response.bin', receipt=base + '.receipt.json',
                                                    panel_path=panel_path, panel_row=calendar.index(day), multiplier='1',
                                                    basis='CONDITIONAL_PROVIDER_QUOTE_UNITS_NOT_AUTHENTICATED_NOMINAL')
                row = values[sid][day]
                if len(row) == 4 and not Fraction(row['low']) <= min(Fraction(row['open']), Fraction(row['close'])) <= max(Fraction(row['open']), Fraction(row['close'])) <= Fraction(row['high']):
                    blocked.append(dict(security_id=sid, date=day, reason='INCONSISTENT_PROVIDER_OHLC'))
        windows.append(dict(decision_cutoff=decision, calendar=dates, nominal_ohlc=values,
                            metadata=metadata, frozen_weights=frozen['target_weights'], initial_cash='20000', fee_bps='0',
                            price_field_sources=provenance, events=dict(split_events=[], cash_merger_events=[], unmodelled_action_events=[]),
                            missing_fields=gaps, blocking_issues=blocked, provider_event_audit=audits,
                            status='BLOCKED' if blocked or gaps else 'PREPARED_CONDITIONAL_PROVIDER_OHLC',
                            baseline=baseline, original_end_date=end,
                            baseline_limitations=['nominal_ohlc is schema-compatible name only; values remain conditional provider quote units, not certified nominal.',
                              'No complete corporate-action or spinoff-absence certification. Provider div/splits request cannot establish all actions.',
                              'Frozen selection and original holding endpoint retained; no outcome-dependent selection filtering.',
                              'Price return only; dividend cash, taxes and other charges excluded.']))
    return dict(windows=windows, source_hashes=hashes, book_calls=0, search_calls=0,
                research_only=True, point_in_time_authenticated=False, complete_corporate_actions_verified=False,
                conditional_price_basis_requires_root_review=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        raise ValueError('Create-only output exists')
    result = prepare()
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
