"""Read frozen searches and declared nominal sources; never run outcomes/search."""
import argparse
import csv
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path


def prepare_window(inputs, search, calendar, nominal_by_ticker, events):
    """Pure adapter. nominal_by_ticker rows need explicit NOMINAL basis/evidence.

    An unavailable price stays missing; selected stocks are never dropped.
    events use ticker/date/kind plus frozen-outcome event-specific fields.
    """
    args = inputs['search_arguments']
    if Fraction(args.get('fee_bps', '0')) != 0:
        raise ValueError('Frozen zero-fee valuation only')
    decision = args['decision_date']
    start = calendar.index(decision)
    dates = calendar[start:start + 22]
    if len(dates) != 22 or dates != sorted(set(dates)):
        raise ValueError('Need decision plus next 21 market sessions')
    selected = search['selected']
    weights = selected['actual_weights']
    if sum(Fraction(v) for v in weights.values()) + Fraction(selected['cash_fraction']) != 1:
        raise ValueError('Frozen weight/cash conservation mismatch')
    metadata = {sid: args['metadata'][sid] for sid in weights}
    prices, gaps, coverage = {}, [], []
    mapped = {'split': [], 'merger': [], 'unmodelled': []}
    for sid, weight in weights.items():
        if Fraction(weight) <= 0:
            raise ValueError('Selected weight must be positive')
        ticker = metadata[sid]['ticker']
        source = nominal_by_ticker.get(ticker, {})
        valid_basis = source.get('basis') == 'NOMINAL' and bool(source.get('source_references'))
        rows = source.get('rows', {}) if valid_basis else {}
        prices[sid] = {}
        mergers = []
        for event in events:
            if event['ticker'] != ticker or not decision < event['date'] <= dates[-1]:
                continue
            converted = {key: value for key, value in event.items() if key not in ('ticker', 'kind')}
            converted['security_id'] = sid
            mapped[event['kind']].append(converted)
            if event['kind'] == 'merger':
                mergers.append(event['date'])
        terminal = min(mergers) if mergers else None
        for day in dates[1:]:
            row = rows.get(day, {})
            prices[sid][day] = {key: row[key] for key in ('open', 'close') if row.get(key) is not None}
            # Missing post-conversion marks are not needed; retain any entry
            # terminal event for the outcome function's explicit entry block.
            needed = ['open', 'close'] if day == dates[1] else ['close']
            if terminal and day >= terminal:
                needed = []
            for key in needed:
                if key not in prices[sid][day]:
                    gaps.append({'security_id': sid, 'ticker': ticker, 'date': day, 'field': key,
                                 'reason': 'MISSING_NOMINAL_PRICE' if valid_basis else 'NOMINAL_BASIS_UNRESOLVED'})
        coverage.append({'security_id': sid, 'ticker': ticker, 'frozen_weight': weight,
                         'source_basis': source.get('basis'), 'source_references': source.get('source_references', []),
                         'alternative_sources_not_admitted': source.get('alternatives', [])})
    return {'decision_cutoff': decision, 'status': 'PREPARED_WITH_PRICE_GAPS' if gaps else 'PREPARED_NOT_EXECUTED',
            'frozen_selected': selected, 'coverage': coverage, 'price_gaps': gaps,
            'outcome_arguments': dict(target_weights=weights, nominal_prices=prices, metadata=metadata,
                 session_dates=dates, decision_date=decision, end_date=dates[-1], entered_cash=args['entered_cash'],
                 fee_bps='0', split_events=mapped['split'], cash_merger_events=mapped['merger'],
                 unmodelled_action_events=mapped['unmodelled']),
            'selection_changed': False, 'outcome_calls': 0}


def prepare_saved(root, search_directory):
    sources = {}

    def read(path):
        path = Path(path)
        if not path.is_absolute():
            path = root / path
        raw = path.read_bytes()
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw

    panel = json.loads(read('tmp/current_ohlc_actual_projection_20261013_v1/panel.json'))
    lifecycle = read('config/ndx_security_lifecycle.yaml')
    if hashlib.sha256(lifecycle).hexdigest() != '8505e22f1c18b4a691d8b14bdb1dfc382dda8c59721201fb3276617a3a639179':
        raise ValueError('Reviewed FISV/FI dated identity rule changed')
    read(Path(__file__))
    splits = json.loads(read('tmp/historical_split_registry_diagnostic_20261014_v2/explicit_conditional_events.json'))
    terminal = json.loads(read('research_contracts/historical_terminal_event_sources_20261014.json'))
    notes_path = 'tmp/historical_split_source_notes_20261014_v1/source_notes.json'
    notes = json.loads(read(notes_path))
    events = []
    for event in splits + notes['conditional_split_supplement']:
        events.append(dict(ticker=event['ticker'], date=event['event_date'], kind='split',
                           new_shares=event['new_shares'], old_shares=event['old_shares'],
                           source_references=event.get('evidence') or [notes_path]))
    for event in terminal['events']:
        if event['ticker'] in ('SGEN', 'SPLK'):
            events.append(dict(ticker=event['ticker'], date=event['event_date'], kind='merger',
                               share_cash=event['usd_per_common_share'],
                               source_references=[event['source_url'], event['additional_source_url']]))
    events.append(dict(ticker='ILMN', date='2024-06-24', kind='unmodelled',
                       action='GRAIL_SPINOFF_ENTITLEMENT_NOT_MODELLED', source_references=[notes_path]))
    windows, pending = [], []
    registration = json.loads(read(search_directory / 'registration.json'))
    for cutoff in registration['decisions']:
        folder = search_directory / cutoff
        if not (folder / 'search.json').exists():
            pending.append(cutoff)
            continue
        inputs = json.loads(read(folder / 'inputs.json'))
        search = json.loads(read(folder / 'search.json'))
        nominal = {}
        for sid in search['selected']['actual_weights']:
            ticker = inputs['search_arguments']['metadata'][sid]['ticker']
            symbols = ['FISV', 'FI'] if ticker in ('FISV', 'FI') else [ticker]
            rows, refs = {}, []
            for symbol in symbols:
                path = root / 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw' / (symbol + '.csv')
                if not path.exists():
                    continue
                manifest = json.loads(read(str(path) + '.manifest.json'))
                raw = read(path)
                if hashlib.sha256(raw).hexdigest() != manifest['content_sha256']:
                    raise ValueError('Raw SHA mismatch')
                if not (manifest['price_basis'] == 'unadjusted_nominal_trade_price' and
                        manifest['valuation_use_only'] is True and manifest['corporate_action_adjustment'] == 'none'):
                    raise ValueError('Nominal source declaration differs')
                for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
                    day = row['Date']
                    if symbol == 'FISV' and day > '2023-06-06' or symbol == 'FI' and day < '2023-06-07':
                        continue
                    rows[day] = {'open': row['Open'], 'close': row['Close']}
                refs.append(str(path))
            nominal[ticker] = {'basis': 'NOMINAL' if refs else None, 'rows': rows, 'source_references': refs,
                              'alternatives': ['Saved Yahoo quote/archived CSV require separate unit-basis approval; not automatically nominal.']}
        windows.append(prepare_window(inputs, search, panel['calendar'], nominal, events))
    return {'windows': windows, 'pending_search_cutoffs': pending, 'source_hashes': sources,
            'outcome_calls': 0, 'search_calls': 0, 'research_only': True,
            'limitations': ['Nominal valuation only; no dividend income or taxes.',
                           'Quote and archive numerical coverage alone does not prove nominal units.',
                           'No outcome-dependent selection filtering; all frozen selections retained.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--search-directory', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = prepare_saved(root, Path(args.search_directory).resolve())
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
