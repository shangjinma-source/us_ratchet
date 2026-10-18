"""Two preregistered top1 controls, no quantity search or winner promotion."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.return_priority_frozen_nominal_outcome import frozen_nominal_outcome

OUTPUT = ROOT / 'tmp/top1_baselines_20261014_v1'
ENGINE = 'backtest/return_priority_frozen_nominal_outcome.py'
ENGINE_SHA = '0494a78bdd36b00a6009c9f02e73098104f75c6db57f1e0e6bd805099e68bf70'
PROTECTED = ['data/state.json', 'data/broker_positions.json', 'config/config.yaml',
             'api/server.py', 'web/index.html', 'web/selected_stock_charts.js',
             'data/current_cash_portfolio_research.py', 'data/current_quantity_portfolio_research.py']
MODES = ['TOP1_SAME_PROJECTION', 'TOP1_FULL_CASH']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, payload):
    raw = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode()
    with Path(path).open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def select_top1(arguments):
    """Exact mean-log equivalent ranking of full supplied mature price scenarios."""
    prices, scenarios, dates = arguments['prices'], arguments['training_scenarios'], arguments['scenario_dates']
    if len(scenarios) != 12 or len(dates) != 12 or dates != sorted(set(dates)) or max(dates) > arguments['decision_date']:
        raise ValueError('Twelve distinct mature scenario endpoints required')
    if not prices or set(prices) != set(arguments['metadata']) or any(set(s) != set(prices) for s in scenarios):
        raise ValueError('Full common candidate domain required')
    products = {}
    for sid in sorted(prices):
        product = Fraction(1)
        for scenario in scenarios:
            gross = Fraction(str(scenario[sid]))
            if gross <= 0:
                raise ValueError('Positive scenario gross required')
            product *= gross
        products[sid] = product
    winner = min(products, key=lambda sid: (-products[sid], sid))
    cash, price = Fraction(arguments['entered_cash']), Fraction(prices[winner])
    if cash != 20000 or price <= 0 or Fraction(arguments['fee_bps']) or Fraction(arguments['minimum_cash_buffer']):
        raise ValueError('Registered fresh 20k zero-fee zero-buffer required')
    quantity = int(cash // price)
    return dict(security_id=winner, metadata=arguments['metadata'][winner], decision_close=str(price),
                decision_quantity=quantity, training_gross_product=str(products[winner]),
                eligible_candidate_count=len(products), ranking_rule='EXACT_PRODUCT_DESC_THEN_SID_ASC',
                modes={'TOP1_SAME_PROJECTION': str(quantity * price / cash), 'TOP1_FULL_CASH': '1'},
                forecast_return=None)


def prepare():
    if OUTPUT.exists():
        raise ValueError('Create-only output exists')
    hashes = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if expected and sha != expected:
            raise ValueError('Changed source: ' + str(path))
        hashes[str(path)] = sha
        return raw

    def json_read(path, expected=None):
        return json.loads(read(path, expected))

    read(ENGINE, ENGINE_SHA)
    read(__file__)
    panel = json_read('tmp/current_ohlc_actual_projection_20261013_v1/panel.json', '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822')
    historical = ROOT / 'tmp/historical_quantity_search_20261014_v1'
    recent = ROOT / 'tmp/quantity_temporal_conditional_20261014_v1'
    historical_registration = json_read(historical / 'registration.json')
    original_inputs = json_read(historical_registration['input_path'], historical_registration['input_sha256'])
    for path, sha in original_inputs['source_hashes'].items():
        read(path, sha)
    recent_registration = json_read(recent / 'registration.json')
    for path, sha in recent_registration['source_pins'].items():
        read(path, sha)
    old_outcomes = json_read(historical / 'outcome_inputs_v2.json', '9e19a08d16719b72603ba049ceab4ad2157f33755370e47bd8ba0a98319d316f')
    for path, sha in old_outcomes['source_hashes'].items():
        read(path, sha)
    refs = json_read(historical / 'fund_references.json')
    for path, sha in refs['source_hashes'].items():
        read(path, sha)
    refs_by_date = {w['decision_cutoff']: w['references'] for w in refs['windows']}
    recent_result = json_read(recent / 'result.json')
    registry = json_read('tmp/historical_split_registry_diagnostic_20261014_v2/explicit_conditional_events.json')
    notes_path = 'tmp/historical_split_source_notes_20261014_v1/source_notes.json'
    registry += json_read(notes_path)['conditional_split_supplement']
    terminal = json_read('research_contracts/historical_terminal_event_sources_20261014.json')
    read('config/ndx_security_lifecycle.yaml', '8505e22f1c18b4a691d8b14bdb1dfc382dda8c59721201fb3276617a3a639179')
    tasks = [('historical', w['decision_cutoff'], w['outcome_arguments']['end_date'], historical, w)
             for w in old_outcomes['windows']]
    tasks += [('recent', w['decision'], w['end'], recent, w) for w in recent_result['windows']]
    windows = []
    for cohort, decision, end, folder, old in tasks:
        inputs = json_read(folder / decision / 'inputs.json')
        arguments = inputs['search_arguments']
        selected = select_top1(arguments)
        sid, ticker = selected['security_id'], selected['metadata']['ticker']
        calendar = panel['calendar']
        days = calendar[calendar.index(decision):calendar.index(end) + 1]
        prices, provenance, issues, events = {}, {}, [], dict(split_events=[], cash_merger_events=[], unmodelled_action_events=[])
        basis = 'SINA_DECLARED_NOMINAL'
        if cohort == 'historical':
            # Reuse approved entire last-window source ONLY if this SID was
            # covered by that existing approval. Never substitute a runner-up.
            if decision == '2024-05-31' and sid in old['outcome_arguments']['nominal_prices']:
                prices = old['outcome_arguments']['nominal_prices'][sid]
                provenance = old['price_field_sources'][sid]
                basis = 'PREVIOUSLY_APPROVED_CONDITIONAL_LAST_WINDOW_SOURCE'
            else:
                symbols = ['FISV', 'FI'] if ticker in ('FISV', 'FI') else [ticker]
                for symbol in symbols:
                    path = ROOT / 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw' / (symbol + '.csv')
                    if not path.exists():
                        issues.append(dict(reason='MISSING_NOMINAL_SOURCE', path=str(path)))
                        continue
                    declaration = json_read(str(path) + '.manifest.json')
                    if declaration['price_basis'] != 'unadjusted_nominal_trade_price' or declaration['corporate_action_adjustment'] != 'none':
                        issues.append(dict(reason='UNAPPROVED_PRICE_BASIS', path=str(path)))
                        continue
                    raw = read(path, declaration['content_sha256'])
                    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
                        day = row['Date']
                        if day not in days[1:] or symbol == 'FISV' and day > '2023-06-06' or symbol == 'FI' and day < '2023-06-07':
                            continue
                        prices[day] = {'open': row['Open'], 'close': row['Close']}
                        provenance[day] = dict(path=str(path), basis=basis)
            for event in registry:
                if event['ticker'] == ticker and decision < event['event_date'] <= end:
                    events['split_events'].append(dict(security_id=sid, date=event['event_date'], new_shares=event['new_shares'], old_shares=event['old_shares'], source_references=event.get('evidence') or [notes_path]))
            for event in terminal['events']:
                if event['ticker'] == ticker and decision < event['event_date'] <= end and ticker in ('SGEN', 'SPLK'):
                    events['cash_merger_events'].append(dict(security_id=sid, date=event['event_date'], share_cash=event['usd_per_common_share'], source_references=[event['source_url'], event['additional_source_url']]))
            if ticker == 'ILMN' and decision < '2024-06-24' <= end:
                events['unmodelled_action_events'].append(dict(security_id=sid, date='2024-06-24', source_references=[notes_path]))
            baseline = json_read(ROOT / 'tmp/historical_quantity_outcome_20261014_v1' / (decision + '.json'))
            comparisons = dict(quantity_return=baseline['return'], quantity_drawdown=baseline['maximum_drawdown'], funds=refs_by_date[decision])
        else:
            basis = 'CONDITIONAL_PROVIDER_QUOTE_NOT_AUTHENTICATED_NOMINAL'
            base = ROOT / 'data/cache/research/current_raw_capture_20261013_v1' / ticker
            receipt = json_read(str(base) + '.receipt.json')
            raw = read(str(base) + '.response.bin', receipt['raw_sha256'])
            chart = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)['chart']['result'][0]
            if chart['meta']['symbol'] != ticker:
                raise ValueError('Provider identity mismatch')
            zone = ZoneInfo(chart['meta']['exchangeTimezoneName'])
            quote = chart['indicators']['quote'][0]
            raw_rows = {datetime.fromtimestamp(stamp, zone).date().isoformat(): {key: quote[key][i] for key in ('open', 'close')} for i, stamp in enumerate(chart['timestamp'])}
            channel = next(stock for stock in panel['stocks'] if stock['ticker'] == ticker)
            for day in days[1:]:
                original_row = channel['values'][calendar.index(day)]
                row = raw_rows.get(day, {})
                if row.get('open') != original_row[0] or row.get('close') != original_row[3]:
                    raise ValueError('Raw/panel mismatch')
                prices[day] = {key: str(value) for key, value in row.items() if value is not None}
                provenance[day] = dict(path=str(base) + '.response.bin', basis=basis)
            for kind, group in chart.get('events', {}).items():
                if kind == 'dividends':
                    continue
                for event in group.values():
                    when = datetime.fromtimestamp(event['date'], zone).date().isoformat()
                    if decision <= when <= receipt['receipt_new_york_date']:
                        issues.append(dict(reason='PROVIDER_EVENT_REQUIRES_UNIT_REVIEW', kind=kind, date=when, event=event))
            comparisons = dict(quantity_return=old['strategy']['net_return'], quantity_drawdown=old['strategy']['drawdown'], funds=old['references'])
        termination = min((e['date'] for e in events['cash_merger_events']), default=None)
        for day in days[1:]:
            if termination and day >= termination:
                continue
            for key in (('open', 'close') if day == days[1] else ('close',)):
                try:
                    valid = Fraction(prices[day][key]) > 0
                except (KeyError, ValueError, ZeroDivisionError):
                    valid = False
                if not valid:
                    issues.append(dict(reason='MISSING_OR_INVALID_PRICE', date=day, field=key))
        windows.append(dict(cohort=cohort, decision_cutoff=decision, end_date=end, selected=selected,
                            calendar=days, nominal_prices={sid: prices}, price_provenance=provenance, price_basis=basis,
                            events=events, preparation_issues=issues, comparisons=comparisons,
                            outcome_status='BLOCKED_SOURCE' if issues else 'PREPARED_NOT_EXECUTED'))
    if len(windows) != 20:
        raise ValueError('All twenty windows required')
    OUTPUT.mkdir()
    prepared_sha = save(OUTPUT / 'prepared.json', dict(windows=windows, source_hashes=hashes, valuation_calls=0, quantity_search_calls=0))
    registration = dict(prepared_sha256=prepared_sha, runner_sha256=digest(__file__), engine_sha256=ENGINE_SHA,
                         modes=MODES, maximum_valuation_calls=40, maximum_quantity_search_calls=0,
                         protected_before={path: digest(ROOT / path) for path in PROTECTED},
                         main_comparison='TOP1_SAME_PROJECTION', auxiliary='TOP1_FULL_CASH changes deployment too',
                         independent_oos=False, promotion_allowed=False,
                         limitations=['Retrospective conditional training price scenarios, not forecasts.', 'No substitution when selected top1 lacks outcome sources.',
                                      'Independent fresh-cash windows; no cumulative CAGR.', 'Price-only gross events; dividends/taxes/other charges excluded.'])
    return save(OUTPUT / 'registration.json', registration)


def run(registration_sha):
    if {p.name for p in OUTPUT.iterdir()} != {'prepared.json', 'registration.json'} or digest(OUTPUT / 'registration.json') != registration_sha:
        raise ValueError('Already started or registration mismatch; do not rerun')
    registration = json.loads((OUTPUT / 'registration.json').read_bytes())
    if digest(__file__) != registration['runner_sha256'] or digest(ROOT / ENGINE) != registration['engine_sha256'] or digest(OUTPUT / 'prepared.json') != registration['prepared_sha256']:
        raise ValueError('Pinned runner/engine/inputs changed')
    prepared = json.loads((OUTPUT / 'prepared.json').read_bytes())
    for path, sha in prepared['source_hashes'].items():
        if digest(path) != sha:
            raise ValueError('Source changed')
    if {path: digest(ROOT / path) for path in PROTECTED} != registration['protected_before']:
        raise ValueError('Protected files changed')
    save(OUTPUT / 'intent.json', dict(maximum_valuation_calls=40, quantity_search_calls=0))
    calls, results = 0, []
    try:
        for window in prepared['windows']:
            for mode in MODES:
                sid = window['selected']['security_id']
                weight = window['selected']['modes'][mode]
                if window['preparation_issues']:
                    outcome = dict(status='BLOCKED_SOURCE', return_fraction=None, issues=window['preparation_issues'])
                else:
                    calls += 1
                    save(OUTPUT / (window['decision_cutoff'] + '_' + mode + '_intent.json'), dict(maximum_calls=1))
                    book = frozen_nominal_outcome(target_weights={sid: weight} if Fraction(weight) else {},
                            nominal_prices=window['nominal_prices'], metadata={sid: window['selected']['metadata']},
                            session_dates=window['calendar'], decision_date=window['decision_cutoff'], end_date=window['end_date'],
                            entered_cash='20000', fee_bps='0', **window['events'])
                    outcome = dict(status=book['status'], return_fraction=book['return'], book=book)
                outcome.update(decision_cutoff=window['decision_cutoff'], cohort=window['cohort'], mode=mode,
                               selected_ticker=window['selected']['metadata']['ticker'], comparisons=window['comparisons'])
                if outcome['return_fraction'] is not None:
                    outcome['difference_vs_quantity'] = str(Fraction(outcome['return_fraction']) - Fraction(window['comparisons']['quantity_return']))
                save(OUTPUT / (window['decision_cutoff'] + '_' + mode + '.json'), outcome)
                results.append({key: value for key, value in outcome.items() if key not in ('book', 'comparisons')})
        save(OUTPUT / 'result.json', dict(windows=results, valuation_calls=calls, quantity_search_calls=0, promotion_allowed=False))
    except Exception as error:
        save(OUTPUT / 'failure.json', dict(error=str(error), calls_attempted=calls, completed=len(results), automatic_retry_allowed=False))
        raise
    finally:
        after = {path: digest(ROOT / path) for path in PROTECTED}
        save(OUTPUT / 'protected_after.json', dict(hashes=after, unchanged=after == registration['protected_before']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare:
        print(prepare())
    else:
        run(args.registration_sha)
