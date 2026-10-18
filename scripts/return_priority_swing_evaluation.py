"""Reuse the reviewed swing provider on explicitly pinned recent frozen windows."""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.return_priority_historical_swing_experiment import provider_for
from backtest.return_priority_limit_book import run_limit_book

IMPLEMENTATIONS = {
    'scripts/return_priority_historical_swing_experiment.py': '097562e8085ffcef946b7967f66fe12b4089dd5cd2500e8cef4c38934ff61d74',
    'backtest/return_priority_limit_book.py': 'aca38fc156472a1a1e5c30fd509a58a89d8e7e674de4a95714a47a5191cb148a',
    'backtest/return_priority_swing_limit_plan.py': '4c65c25b1ecff94606a5cb0680ce8a46cfb21e2259f69ae3ce679c010761a836',
    'scripts/return_priority_historical_swing_inputs.py': 'ad08ee40b3452e7704e0c57b93f353758951d752ddd48426cb52fb880eb0cb6e',
}
PROTECTED = ['data/state.json', 'data/broker_positions.json', 'config/config.yaml',
             'api/server.py', 'web/index.html', 'web/selected_stock_charts.js']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def protected():
    return {name: sha(ROOT / name) for name in PROTECTED}


def verify(input_path, baseline_path):
    data = json.loads(input_path.read_bytes())
    baseline = json.loads(baseline_path.read_bytes())
    for name, digest in {**IMPLEMENTATIONS, **data['source_hashes']}.items():
        if sha(ROOT / name) != digest:
            raise ValueError('Source changed: ' + name)
    references = {row['decision']: row for row in baseline['windows']}
    if len(data['windows']) != 5 or len(references) != 5:
        raise ValueError('Exactly the five existing recent windows required')
    seen = set()
    for window in data['windows']:
        decision = window['decision_cutoff']
        ref = references[decision]
        if decision in seen or window['calendar'][19] != decision or window['calendar'][-1] != ref['end']:
            raise ValueError('Frozen dates differ')
        seen.add(decision)
        if window['missing_fields'] or Fraction(str(window['initial_cash'])) != 20000 or Fraction(str(window['fee_bps'])) != 0:
            raise ValueError('Missing prices or different cash/fees')
    return data, references


def prepare(input_path, baseline_path, output):
    verify(input_path, baseline_path)
    registration = dict(input_path=str(input_path), input_sha=sha(input_path),
        baseline_path=str(baseline_path), baseline_sha=sha(baseline_path), runner_sha=sha(__file__),
        implementation_pins=IMPLEMENTATIONS, modes=['trend_exit', 'band_exit'], maximum_book_calls=10,
        search_calls=0, protected_before=protected(), parameter_changes=False,
        cash_shortage_rule='Same common proportional quantity reduction as the registered historical experiment.',
        input_price_basis_assumption='Saved provider quote units treated conditionally as decision share units; not authenticated nominal prices.',
        corporate_action_completeness_verified=False,
        independent_oos=False, promotion_allowed=False)
    output.mkdir()
    save(output / 'registration.json', registration)
    print(sha(output / 'registration.json'))


def run(output, registration_sha):
    registration_path = output / 'registration.json'
    if sha(registration_path) != registration_sha or {p.name for p in output.iterdir()} != {'registration.json'}:
        raise ValueError('Registration mismatch or already started; inspect, do not rerun')
    registration = json.loads(registration_path.read_bytes())
    input_path, baseline_path = Path(registration['input_path']), Path(registration['baseline_path'])
    if sha(input_path) != registration['input_sha'] or sha(baseline_path) != registration['baseline_sha'] or sha(__file__) != registration['runner_sha']:
        raise ValueError('Registered file changed')
    data, references = verify(input_path, baseline_path)
    if protected() != registration['protected_before']:
        raise ValueError('Protected files changed')
    save(output / 'intent.json', dict(maximum_book_calls=10, registration_sha=registration_sha))
    summaries, calls = [], 0
    try:
        for window in data['windows']:
            decision = window['decision_cutoff']
            baseline = references[decision]
            for mode in registration['modes']:
                folder = output / (decision + '_' + mode)
                folder.mkdir()
                save(folder / 'intent.json', {'maximum_calls': 1})
                plans = []
                events = [dict(event, type=kind) for key, kind in (
                    ('split_events', 'split'), ('cash_merger_events', 'merger'),
                    ('unmodelled_action_events', 'unmodelled')) for event in window['events'][key]]
                calls += 1
                try:
                    book = run_limit_book(session_dates=window['calendar'][19:],
                        ohlc=window['nominal_ohlc'], initial_cash=window['initial_cash'], events=events,
                        order_provider=provider_for(window, mode, plans))
                finally:
                    save(folder / 'daily_plans.json', plans)
                save(folder / 'book.json', book)
                complete = book['status'] == 'COMPLETE'
                peak, drawdown = Fraction(window['initial_cash']), Fraction(0)
                for row in book['daily_ledger']:
                    value = Fraction(row['equity'])
                    peak = max(peak, value)
                    drawdown = max(drawdown, 1 - value / peak)
                ret = Fraction(book['daily_ledger'][-1]['equity']) / Fraction(window['initial_cash']) - 1 if complete else None
                summaries.append(dict(decision=decision, end=baseline['end'], mode=mode,
                    status=book['status'], reason=book['reason'],
                    return_fraction=str(ret) if complete else None,
                    maximum_drawdown=str(drawdown) if complete else None,
                    fills=sum(row['event'] == 'ASSUMED_FILLED' for row in book['order_log']),
                    hold_return=baseline['strategy']['net_return'], hold_drawdown=baseline['strategy']['drawdown'],
                    references={name: {'return_fraction': row['net_return'], 'maximum_drawdown': row['drawdown']}
                                for name, row in baseline['references'].items()}))
        save(output / 'result.json', dict(windows=summaries, book_calls=calls, search_calls=0,
             parameter_changes=False, independent_oos=False, cagr=None, promotion_allowed=False,
             input_price_basis_assumption=registration['input_price_basis_assumption'],
             corporate_action_completeness_verified=False,
             dividends_included=False, independent_fresh_cash_windows=True))
    except Exception as error:
        save(output / 'failure.json', dict(error=str(error), attempted_calls=calls,
             completed_books=len(summaries), automatic_retry_allowed=False))
        raise
    finally:
        after = protected()
        save(output / 'protected_after.json', dict(hashes=after, unchanged=after == registration['protected_before']))
        if after != registration['protected_before']:
            raise ValueError('Protected files changed during evaluation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.input.resolve(), args.baseline.resolve(), args.output.resolve())
    else:
        run(args.output.resolve(), args.registration_sha)
