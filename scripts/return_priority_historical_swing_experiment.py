"""Registered fixed 15 x 2 limit-book experiment. No search or parameter fitting."""
import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.return_priority_limit_book import run_limit_book
from backtest.return_priority_swing_limit_plan import build_swing_limit_plan
from scripts.return_priority_historical_swing_inputs import decision_unit_history

INPUT = ROOT / 'tmp/historical_swing_inputs_20261014_v1.json'
OUTPUT = ROOT / 'tmp/historical_swing_experiment_20261014_v1'
REFERENCES = ROOT / 'tmp/historical_quantity_search_20261014_v1/fund_references.json'
PINS = {
    'backtest/return_priority_limit_book.py': 'aca38fc156472a1a1e5c30fd509a58a89d8e7e674de4a95714a47a5191cb148a',
    'backtest/return_priority_swing_limit_plan.py': '4c65c25b1ecff94606a5cb0680ce8a46cfb21e2259f69ae3ce679c010761a836',
    'scripts/return_priority_historical_swing_inputs.py': 'ad08ee40b3452e7704e0c57b93f353758951d752ddd48426cb52fb880eb0cb6e',
    'tmp/historical_swing_inputs_20261014_v1.json': '9bc4cea3d5aacab86cb94fbca46d828088f61c9076b348bd0fb9d24b4a749869',
}
PROTECTED = ['data/state.json', 'data/broker_positions.json', 'config/config.yaml',
             'api/server.py', 'web/index.html', 'web/selected_stock_charts.js',
             'data/current_cash_portfolio_research.py']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    with Path(path).open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def scale_orders(orders, available_cash):
    reserved = sum(Fraction(o['limit']) * o['quantity'] for o in orders if o['side'] == 'BUY')
    factor = min(Fraction(1), Fraction(available_cash) / reserved) if reserved else Fraction(1)
    result, changes = [], []
    for original in orders:
        order = dict(original)
        if order['side'] == 'BUY':
            order['quantity'] = int(original['quantity'] * factor)
            changes.append(dict(id=order['id'], original_quantity=original['quantity'],
                                quantity=order['quantity'], common_factor=str(factor)))
        if order['quantity']:
            result.append(order)
    return result, changes


def reconstruct_entries(logs, order_atrs, decision_date, state_shares):
    entries, same_day_splits = {}, {}
    for row in logs:
        if row['date'] > decision_date:
            raise ValueError('Future execution log not allowed')
        kind = row['event']
        if kind == 'CORPORATE_ACTION':
            event, sid = row['action_details'], row['security_id']
            if row['type'] == 'split':
                ratio = Fraction(str(event['new_shares'])) / Fraction(str(event['old_shares']))
                same_day_splits[(row['date'], sid)] = ratio
                if sid in entries:
                    entries[sid]['average_cost'] /= ratio
                    entries[sid]['entry_atr14'] /= ratio
                    entries[sid]['quantity'] *= ratio
            elif row['type'] == 'merger':
                entries.pop(sid, None)
        elif kind == 'ASSUMED_FILLED':
            sid = row['security_id']
            if row['side'] == 'BUY':
                if sid in entries:
                    raise ValueError('Unexpected add-on buy')
                entries[sid] = dict(average_cost=Fraction(row['price']),
                                    entry_atr14=Fraction(order_atrs[row['id']]) / same_day_splits.get((row['date'], sid), 1),
                                    quantity=Fraction(row['quantity']))
            else:
                if sid not in entries or entries[sid]['quantity'] != row['quantity']:
                    raise ValueError('Expected full-position exit')
                del entries[sid]
    expected = {sid: Fraction(q) for sid, q in state_shares.items() if q}
    if {sid: value['quantity'] for sid, value in entries.items()} != expected:
        raise ValueError('Entry accounting differs from actual book shares')
    return {sid: dict(average_cost=str(value['average_cost']), entry_atr14=str(value['entry_atr14']),
                      basis='DECISION_NOMINAL_SHARE_UNITS', unit_asof=decision_date) for sid, value in entries.items()}


def provider_for(window, mode, plans):
    order_atrs = {}

    def provider(*, decision_date, active_date, state):
        entries = reconstruct_entries(state['order_log'], order_atrs, decision_date, state['shares'])
        observed = {sid: decision_unit_history(nominal_ohlc=window['nominal_ohlc'], calendar=window['calendar'],
                     security_id=sid, decision_date=decision_date, split_events=window['events']['split_events'])
                    for sid in window['frozen_weights'] if sid not in state['terminated_security_ids']}
        weights = {sid: weight for sid, weight in window['frozen_weights'].items()
                   if sid not in state['terminated_security_ids']}
        plan = build_swing_limit_plan(mode=mode, observed_ohlc=observed, decision_date=decision_date,
                 next_session=active_date, frozen_weights=weights, initial_cash=window['initial_cash'],
                 available_cash=state['cash'], shares=state['shares'], entry_positions=entries)
        if plan['status'] == 'CASH_ALLOCATION_REQUIRED':
            executable, changes = scale_orders(plan['proposed_orders'], state['cash'])
        else:
            executable, changes = plan['orders'], []
        for order in executable:
            if order['side'] == 'BUY':
                order_atrs[order['id']] = plan['diagnostics'][order['security_id']]['atr14']
        plans.append(dict(plan=plan, executable_orders=executable, cash_scaling=changes,
                          entry_positions=entries, state_asof=state['asof']))
        return dict(status='BLOCKED' if plan['status'] == 'BLOCKED' else 'READY', orders=executable)
    return provider


def validate():
    for name, expected in PINS.items():
        if digest(ROOT / name) != expected:
            raise ValueError('Pinned implementation/input changed: ' + name)
    data = json.loads(INPUT.read_bytes())
    for name, expected in data['source_hashes'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Source closure changed: ' + name)
    if len(data['windows']) != 15 or any(w['missing_fields'] for w in data['windows']):
        raise ValueError('Complete fifteen prepared windows required')
    return data


def prepare():
    data = validate()
    if OUTPUT.exists():
        raise ValueError('Create-only registration exists')
    baseline_pins = {str(ROOT / 'tmp/historical_quantity_outcome_20261014_v1' / (w['decision_cutoff'] + '.json')):
                     digest(ROOT / 'tmp/historical_quantity_outcome_20261014_v1' / (w['decision_cutoff'] + '.json')) for w in data['windows']}
    baseline_pins[str(REFERENCES)] = digest(REFERENCES)
    readback = ROOT / 'tmp/historical_quantity_search_20261014_v1/independent_fund_reference_readback.json'
    baseline_pins[str(readback)] = digest(readback)
    registration = dict(maximum_book_calls=30, maximum_search_calls=0, modes=['trend_exit', 'band_exit'],
                         source_pins=PINS, runner_sha256=digest(__file__), baseline_pins=baseline_pins,
                         protected_before={name: digest(ROOT / name) for name in PROTECTED},
                         cash_shortage_rule='Common available_cash / total BUY reservations factor; floor each original quantity; zero cancelled; no residual allocation or sale financing.',
                         conditional_research=True, independent_oos=False, promotion_allowed=False,
                         qqq_spy_comparison='Frozen independently reviewed same-cash zero-fee nextOpen price-return references; no dividends or extra books.')
    OUTPUT.mkdir()
    return save(OUTPUT / 'registration.json', registration)


def run(registration_sha):
    path = OUTPUT / 'registration.json'
    if digest(path) != registration_sha or {p.name for p in OUTPUT.iterdir()} != {'registration.json'}:
        raise ValueError('Registration mismatch or experiment already started; never retry blindly')
    registration = json.loads(path.read_bytes())
    if registration['runner_sha256'] != digest(__file__):
        raise ValueError('Runner changed')
    data = validate()
    for name, expected in registration['baseline_pins'].items():
        if digest(name) != expected:
            raise ValueError('Baseline changed')
    if {name: digest(ROOT / name) for name in PROTECTED} != registration['protected_before']:
        raise ValueError('Protected files changed')
    save(OUTPUT / 'intent.json', dict(maximum_book_calls=30, registration_sha256=registration_sha))
    references = {w['decision_cutoff']: w['references'] for w in json.loads(REFERENCES.read_bytes())['windows']}
    summary, calls = [], 0
    try:
        for window in data['windows']:
            baseline = json.loads((ROOT / 'tmp/historical_quantity_outcome_20261014_v1' / (window['decision_cutoff'] + '.json')).read_bytes())
            for mode in registration['modes']:
                folder = OUTPUT / (window['decision_cutoff'] + '_' + mode)
                folder.mkdir()
                save(folder / 'intent.json', dict(maximum_calls=1))
                plans = []
                events = [dict(e, type=kind) for key, kind in [('split_events','split'), ('cash_merger_events','merger'), ('unmodelled_action_events','unmodelled')] for e in window['events'][key]]
                calls += 1
                try:
                    book = run_limit_book(session_dates=window['calendar'][19:], ohlc=window['nominal_ohlc'],
                           initial_cash=window['initial_cash'], events=events, order_provider=provider_for(window, mode, plans))
                finally:
                    save(folder / 'daily_plans.json', plans)
                save(folder / 'book.json', book)
                peak, maximum_dd = Fraction(window['initial_cash']), Fraction(0)
                for row in book['daily_ledger']:
                    equity = Fraction(row['equity'])
                    peak = max(peak, equity)
                    maximum_dd = max(maximum_dd, 1 - equity / peak)
                ret = Fraction(book['daily_ledger'][-1]['equity']) / Fraction(window['initial_cash']) - 1 if book['status'] == 'COMPLETE' else None
                summary.append(dict(decision=window['decision_cutoff'], mode=mode, status=book['status'],
                           return_fraction=str(ret) if ret is not None else None,
                           maximum_drawdown=str(maximum_dd) if ret is not None else None,
                           fills=sum(r['event']=='ASSUMED_FILLED' for r in book['order_log']),
                           baseline_return=baseline['return'], baseline_difference=str(ret-Fraction(baseline['return'])) if ret is not None else None,
                           qqq_spy={ticker: dict(return_fraction=reference['return_fraction'], maximum_drawdown=reference['maximum_drawdown'],
                                               difference=str(ret-Fraction(reference['return_fraction'])) if ret is not None else None)
                                    for ticker, reference in references[window['decision_cutoff']].items()}))
        save(OUTPUT / 'result.json', dict(windows=summary, book_calls=calls, search_calls=0, promotion_allowed=False,
                                         independent_fresh_cash_windows=True, cumulative_cagr_valid=False))
    except Exception as error:
        save(OUTPUT / 'failure.json', dict(message=str(error), book_calls_attempted=calls, completed=len(summary), automatic_retry_allowed=False))
        raise
    finally:
        after = {name: digest(ROOT / name) for name in PROTECTED}
        save(OUTPUT / 'protected_after.json', dict(hashes=after, unchanged=after == registration['protected_before']))
        if after != registration['protected_before']:
            raise ValueError('Protected files changed during run')


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
