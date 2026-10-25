"""Register or execute one bounded two-window drift-cap comparison, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.continuous_guided_account_decision import REQUIRED_PINS
from backtest.continuous_guided_cost_stress import prepare_arm
from backtest.drift_capped_next_open_research import run_drift_capped_next_open
from backtest.drift_cap_independent_review import review_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter

WINDOWS = {
    'earlier': dict(assembled='tmp/daily_verified_domain_experiment_20261016_v2/assembled.json',
                    bars='tmp/daily_verified_domain_experiment_20261016_v2/prepared.json',
                    baseline='tmp/capped_earlier_reselection_20261024_v1/cap50_exit20/outcome.json',
                    registration='tmp/capped_earlier_reselection_20261024_v1/registration.json', months=19),
    'later': dict(assembled='tmp/cap_exit_reclaim_two_windows_20261024_v1/later_assembled.json',
                  bars='tmp/next12_execution_prepare_20261014_v3/prepared.json',
                  baseline='tmp/capped_actual_reselection_20261024_v2/outcome.json',
                  registration='tmp/capped_actual_reselection_20261024_v2/registration.json', months=12),
}
FOLDER = ROOT / 'tmp/drift_cap_research_20261025'


def read(path):
    return json.loads((ROOT / path).read_bytes())


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def load_window(label):
    spec = WINDOWS[label]
    original = read(spec['registration'])['source_sha256']
    for path in REQUIRED_PINS:
        if digest(path) != original[path]:
            raise ValueError('ORIGINAL_SEARCH_SOURCE_CHANGED: ' + path)
    assembled = read(spec['assembled'])
    if label == 'earlier':
        assembled['session_dates'] = [d for d in assembled['session_dates'] if d <= '2025-07-30']
        assembled['monthly_inputs'] = [p for p in assembled['monthly_inputs']
                                       if p['decision_date'] in assembled['session_dates'][:-1]]
    assembled = prepare_arm(assembled, 'fee1_slippage10', {p: original[p] for p in REQUIRED_PINS})
    if len(assembled['monthly_inputs']) != spec['months']:
        raise ValueError('MONTH_COUNT_CHANGED')
    return assembled, read(spec['bars'])['ohlc'], read(spec['baseline'])


def replay_baseline(assembled, bars, baseline):
    selections = [a['selection'] for a in baseline['provider_audit'] if a.get('selection')]
    prefix = [dict(arguments=a, selection=s) for a, s in zip(baseline['selection_account_states'], selections)]
    if len(prefix) != len(assembled['monthly_inputs']):
        raise ValueError('BASELINE_SELECTION_COUNT')
    result = run_drift_capped_next_open(
        assembled=assembled, ohlc=bars, initial_cash='20000', fee_bps='1', slippage_bps='10',
        risk=MonthlyExitCoreResearchAdapter(assembled['provider_actions']), verified_prefix=prefix)
    mismatches = [key for key in set(result) | set(baseline)
                  if key not in ('reused_searches', 'new_searches') and result.get(key) != baseline.get(key)]
    if mismatches or result['new_searches'] != 0:
        raise ValueError('BASELINE_REPLAY_CHANGED: ' + ','.join(mismatches))
    return review_book(result, assembled, bars, drift_enabled=False)


def registration():
    sources = {}
    for spec in WINDOWS.values():
        original = read(spec['registration'])['source_sha256']
        for path, expected in original.items():
            if digest(path) != expected:
                raise ValueError('ORIGINAL_SOURCE_CHANGED: ' + path)
            if path in sources and sources[path] != expected:
                raise ValueError('CONFLICTING_ORIGINAL_PIN: ' + path)
            sources[path] = expected
        for path in (spec['assembled'], spec['bars'], spec['baseline'], spec['registration']):
            sources[path] = digest(path)
    # Freeze all loaded local Python dependencies, not only the top-level runner.
    for module in tuple(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if location:
            path = Path(location).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT).as_posix()
                sources[relative] = digest(relative)
    for path in ('research_contracts/drift_cap_comparison_20261025.md',
                 'tests/test_monthly_drift_cap_research.py',
                 'tests/test_drift_cap_independent_review.py',
                 'backtest/bounded_research_process.py',
                 'backtest/monthly_drift_cap_research.py'):
        sources[path] = digest(path)
    sources[str(Path(sys.executable).resolve())] = digest(Path(sys.executable).resolve())
    return dict(schema='DRIFT_CAP_COMPARISON_V1', windows=WINDOWS,
                output_directory='tmp/drift_cap_research_20261025/run_v1', source_sha256=sources,
                new_search_limit=31, absolute_technical_search_cap=62, timeout_seconds=1800,
                fee_bps='1', slippage_bps='10', initial_cash='20000',
                automatic_retry=False, automatic_deployment=False,
                criterion='Both windows: return >= same-window baseline and drawdown <= baseline; otherwise retain current strategy',
                limitation='Conditional historical next-open sell-first immediate-sale-cash research, not actual user fees or live limits')


def verify(frozen):
    for path, expected in frozen['source_sha256'].items():
        if digest(path) != expected:
            raise ValueError('FROZEN_SOURCE_CHANGED: ' + path)


def execute(path, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError('REGISTRATION_CHANGED')
    frozen = read(path)
    verify(frozen)
    output = ROOT / frozen['output_directory']
    output.mkdir(exist_ok=False)
    save(output / 'started.json', dict(registration_sha256=expected_sha))
    started, calls, completed, comparisons = time.monotonic(), 0, {}, {}
    terminal = dict(status='RUNNING', production_changes=False, automatic_retry=False)
    try:
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
            for label in WINDOWS:
                verify(frozen)
                assembled, bars, baseline = load_window(label)
                baseline_review = replay_baseline(assembled, bars, baseline)
                save(output / (label + '-baseline-review.json'), baseline_review)
                local_calls = 0

                def progress(event):
                    nonlocal calls, local_calls
                    if time.monotonic() - started > frozen['timeout_seconds']:
                        raise TimeoutError('BOUNDED_RESEARCH_TIME_EXHAUSTED')
                    if event['stage'] == 'MONTHLY_SEARCH_STARTED':
                        calls += 1
                        local_calls += 1
                        if calls > frozen['new_search_limit'] or local_calls > WINDOWS[label]['months']:
                            raise ValueError('FIXED_SEARCH_LIMIT_EXCEEDED')
                    with (output / 'progress.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(dict(window=label, **event)) + '\n')
                    print(label, event['stage'], event['decision_date'], flush=True)

                result = run_drift_capped_next_open(
                    assembled=assembled, ohlc=bars, initial_cash='20000', fee_bps='1', slippage_bps='10',
                    risk=MonthlyExitCoreResearchAdapter(assembled['provider_actions']),
                    drift_enabled=True, progress=progress)
                book_path = output / (label + '-candidate.json')
                save(book_path, result)
                reviewed = review_book(result, assembled, bars, drift_enabled=True)
                reviewed['book_sha256'] = digest(book_path)
                save(output / (label + '-candidate-review.json'), reviewed)
                completed[label] = reviewed
                from fractions import Fraction
                comparisons[label] = (Fraction(result['total_return']) >= Fraction(baseline['total_return'])
                                      and Fraction(result['drawdown']['maximum_close_drawdown'])
                                      <= Fraction(baseline['drawdown']['maximum_close_drawdown']))
            verify(frozen)
            terminal.update(status='COMPLETE_INDEPENDENTLY_REVIEWED',
                            historical_screen='PASS' if all(comparisons.values()) else 'REJECT')
    except BaseException as error:
        terminal.update(status='FAILED_INCONCLUSIVE', error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        terminal.update(new_search_calls=calls, completed_windows=completed, comparisons=comparisons,
                        elapsed_seconds=time.monotonic() - started)
        save(output / 'terminal.json', terminal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'register', 'execute'))
    parser.add_argument('--registration', default='tmp/drift_cap_research_20261025/registration.json')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.mode == 'preflight':
        reports = {}
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
            for label in WINDOWS:
                assembled, bars, baseline = load_window(label)
                reports[label] = replay_baseline(assembled, bars, baseline)
        print(json.dumps(reports, ensure_ascii=False))
    elif args.mode == 'register':
        FOLDER.mkdir(exist_ok=True)
        save(ROOT / args.registration, registration())
        print(digest(args.registration))
    else:
        if not args.sha256:
            parser.error('--sha256 is required for execute')
        execute(args.registration, args.sha256)


if __name__ == '__main__':
    main()
