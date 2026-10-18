"""Create-only two-book horizon falsification; never rerun sealed baselines."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import return_priority_fixed12_monthly_limit_run as baseline

OUTPUT = ROOT / 'tmp/holding_horizon_execution_20261014_v1'
CONTRACT = 'research_contracts/holding_horizon_exit_20261014_v1.json'
PROVIDER = 'backtest/return_priority_holding_horizon_provider.py'
MODES = ['QUANTITY_FROZEN_WEIGHT_REPLAY', 'TOP1_SAME_PROJECTION_FROZEN_WEIGHT_REPLAY']


def prepare(provider_sha, review_path, review_sha):
    if OUTPUT.exists():
        raise ValueError('Output already exists; inspect it, never restart')
    if baseline.digest(ROOT / baseline.INPUT) != baseline.INPUT_SHA:
        raise ValueError('Input differs')
    if baseline.digest(ROOT / PROVIDER) != provider_sha or baseline.digest(ROOT / review_path) != review_sha:
        raise ValueError('Reviewed provider/evidence differs')
    payload = json.loads((ROOT / baseline.INPUT).read_bytes())
    baseline.validate(payload)
    contract = json.loads((ROOT / CONTRACT).read_bytes())
    if contract['holding_sessions'] != 21:
        raise ValueError('Frozen horizon differs')
    pins = dict(payload['source_hashes'])
    pins.update(baseline.PINS)
    pins[baseline.INPUT] = baseline.INPUT_SHA
    for name in [CONTRACT, PROVIDER, review_path, 'scripts/return_priority_fixed12_monthly_limit_run.py',
                 'tmp/fixed12_monthly_limit_execution_20261014_v1/result.json']:
        pins[name] = baseline.digest(ROOT / name)
    for name, expected in pins.items():
        if baseline.digest(ROOT / name) != expected:
            raise ValueError('Source changed: ' + name)
    OUTPUT.mkdir()
    registration = dict(source_hashes=pins, runner_sha256=baseline.digest(__file__),
        protected_before=baseline.guards(), input_path=baseline.INPUT, modes=MODES,
        maximum_book_calls=2, maximum_search_calls=0, automatic_retry_allowed=False,
        historical_role='ALREADY_SEEN_RETROSPECTIVE_FALSIFICATION', independent_oos=False,
        adoption_allowed=False, provider_review_path=review_path, provider_review_sha256=review_sha)
    print(baseline.save(OUTPUT / 'registration.json', registration))


def run(registration_sha):
    if baseline.digest(OUTPUT / 'registration.json') != registration_sha:
        raise ValueError('Reviewed registration differs')
    if {p.name for p in OUTPUT.iterdir()} != {'registration.json'}:
        raise ValueError('Execution already started; never repeat')
    registration = json.loads((OUTPUT / 'registration.json').read_bytes())
    if baseline.digest(__file__) != registration['runner_sha256']:
        raise ValueError('Runner changed')
    for name, expected in registration['source_hashes'].items():
        if baseline.digest(ROOT / name) != expected:
            raise ValueError('Source changed: ' + name)
    if baseline.guards() != registration['protected_before']:
        raise ValueError('Protected state changed')
    payload = json.loads((ROOT / baseline.INPUT).read_bytes())
    baseline.validate(payload)
    from backtest.return_priority_holding_horizon_provider import build_holding_horizon_provider
    from backtest.return_priority_limit_book import run_limit_book
    baseline.save(OUTPUT / 'started.json', dict(registration_sha256=registration_sha, maximum_book_calls=2))
    results = []
    try:
        for mode in payload['modes']:
            if mode['mode'] not in MODES:
                continue
            folder = OUTPUT / mode['mode']
            folder.mkdir()
            baseline.save(folder / 'intent.json', dict(mode=mode['mode'], maximum_calls=1, search_calls=0))
            audit = []
            def recorded_provider(*, decision_date, active_date, state):
                response = provider(decision_date=decision_date, active_date=active_date, state=state)
                audit.append(dict(decision_date=decision_date, active_date=active_date,
                    prior_cash=state['cash'], prior_shares=deepcopy(state['shares']), response=deepcopy(response)))
                return response
            try:
                provider = build_holding_horizon_provider(session_dates=payload['session_dates'],
                    monthly_decisions=mode['monthly_decisions'], actions=mode['actions'],
                    close_prices={sid: {day: row['close'] for day, row in rows.items()} for sid, rows in mode['ohlc'].items()})
                outcome = run_limit_book(session_dates=payload['session_dates'], ohlc=mode['ohlc'],
                    initial_cash=mode['initial_cash'], initial_shares=mode['initial_shares'],
                    events=mode['actions'], fee_bps=mode['fee_bps'], order_provider=recorded_provider)
            except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
                outcome = dict(status='BLOCKED_EXCEPTION', reason=str(error), daily_ledger=[], order_log=[],
                    shares={}, cash=None, receivable=None, state_not_reconstructed_after_exception=True)
            baseline.save(folder / 'provider_audit.json', audit)
            baseline.save(folder / 'outcome.json', outcome)
            metrics = baseline.summarize(outcome, audit, mode['initial_cash'], payload['session_dates'])
            metrics['flat_close_days'] = sum(not any(row['shares'].values()) for row in outcome.get('daily_ledger', []))
            exit_orders = {order['id'] for row in audit for order in row['response'].get('orders', [])
                if order['side'] == 'SELL' and row['response'].get('pending_exit_flags', {}).get(order['security_id'])}
            metrics['expired_horizon_exit_orders'] = sum(row.get('event') == 'EXPIRED_UNFILLED' and row.get('id') in exit_orders
                for row in outcome.get('order_log', []))
            metrics['horizon_exit_order_count'] = len(exit_orders)
            metrics['pending_exit_close_days'] = sum(any(row['response'].get('pending_exit_flags', {}).values()) for row in audit)
            baseline.save(folder / 'metrics.json', metrics)
            results.append(dict(mode=mode['mode'], **metrics))
        baseline.save(OUTPUT / 'result.json', dict(modes=results, book_calls=len(results), search_calls=0,
            denominator=2, independent_oos=False, adoption_allowed=False))
    finally:
        after = baseline.guards()
        baseline.save(OUTPUT / 'protected_after.json', dict(hashes=after, unchanged=after == registration['protected_before']))
        if after != registration['protected_before']:
            raise ValueError('Protected state changed during execution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    parser.add_argument('--provider-sha')
    parser.add_argument('--review-path')
    parser.add_argument('--review-sha')
    parser.add_argument('--registration-sha')
    arguments = parser.parse_args()
    if arguments.prepare:
        prepare(arguments.provider_sha, arguments.review_path, arguments.review_sha)
    else:
        run(arguments.registration_sha)
