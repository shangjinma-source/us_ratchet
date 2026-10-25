"""Execute a frozen, offline cash-policy comparison under an outer deadline."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.cash_balance_policy_experiment import run_case
from backtest.cash_balance_policy_independent_review import review_account, review_policy
from backtest.research_exact_fast_guided import enhanced_search


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registration', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    raw = Path(args.registration).read_bytes()
    if sha256(raw).hexdigest() != args.sha256:
        raise ValueError('REGISTRATION_CHANGED')
    registration = json.loads(raw)

    def verify():
        for name, expected in registration['source_sha256'].items():
            if sha256(Path(name).read_bytes()).hexdigest() != expected:
                raise ValueError('FROZEN_SOURCE_CHANGED: '+name)

    verify()
    output = Path(registration['output_directory'])
    output.mkdir(exist_ok=False)
    design = json.loads(Path(registration['design']).read_bytes())
    seeds = {row['id']: row for row in json.loads(Path(registration['initial_states']).read_bytes())['states']}
    started = time.monotonic()
    calls = 0
    results = {}
    terminal = dict(status='RUNNING', production_changes=False, automatic_retry=False)
    save(output/'started.json', dict(registration_sha256=args.sha256))
    try:
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
            for case in design['cases']:
                bundle = json.loads(Path(case['bundle']).read_bytes())
                seed = seeds[case['id']]
                stable_books = {}
                for stable in (True, False):
                    for mode in ('KEEP_MONTHLY', 'RESELECT_ON_FLOW'):
                        verify()
                        identifier = case['id']+('-stable-' if stable else '-flow-')+mode
                        folder = output/identifier
                        folder.mkdir()
                        selected = {}

                        def selector(**arguments):
                            nonlocal calls
                            if calls >= design['maximum_new_optimizer_calls']:
                                raise ValueError('SEARCH_BUDGET_EXHAUSTED')
                            calls += 1
                            print('SEARCH', calls, identifier, arguments['decision_date'], flush=True)
                            return enhanced_search(**arguments)

                        def recorder(day, arguments, selection):
                            record = dict(arguments=arguments, selection=selection)
                            selected[day] = record
                            save(folder/(day+'.json'), record)

                        document = run_case(case=case, bundle=bundle, seed=seed, mode=mode,
                            stable=stable, selector=selector, selection_recorder=recorder)
                        save(folder/'book.json', document)
                        if document['book']['status'] != 'COMPLETE':
                            raise ValueError(str(document['book']['reason']))
                        flows = [] if stable else case['external_flows']
                        account_bundle = dict(bundle, session_dates=case['sessions'],
                                              initial_cash=seed['cash'], initial_shares=seed['shares'])
                        metrics = review_account(account_bundle, document, flows)
                        metrics.update(review_policy(bundle, seed, document, flows, lambda day: selected[day]))
                        if stable:
                            stable_books[mode] = document['book']
                            if len(stable_books) == 2 and stable_books['KEEP_MONTHLY'] != stable_books['RESELECT_ON_FLOW']:
                                raise ValueError('STABLE_CONTROL_DIVERGED')
                        metrics['book_sha256'] = sha256((folder/'book.json').read_bytes()).hexdigest()
                        save(folder/'review.json', metrics)
                        results[identifier] = metrics
                        print('REVIEWED', identifier, flush=True)
            comparisons = {}
            for case in design['cases']:
                control = results[case['id']+'-flow-KEEP_MONTHLY']
                candidate = results[case['id']+'-flow-RESELECT_ON_FLOW']
                comparisons[case['id']] = (
                    Fraction(candidate['interval_return']) >= Fraction(control['interval_return'])
                    and Fraction(candidate['max_close_drawdown']) <= Fraction(control['max_close_drawdown']))
            verify()
            terminal.update(status='COMPLETE_INDEPENDENTLY_REVIEWED', comparisons=comparisons,
                            historical_screen='PASS' if all(comparisons.values()) else 'REJECT')
    except Exception as error:
        terminal.update(status='FAILED_INCONCLUSIVE', error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        terminal.update(new_optimizer_calls=calls, elapsed_seconds=time.monotonic()-started,
                        completed_branches=list(results), metrics=results)
        save(output/'terminal.json', terminal)


if __name__ == '__main__':
    main()
