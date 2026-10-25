"""Frozen, offline, single-attempt monthly relative-variance comparison."""
import argparse
from copy import deepcopy
from pathlib import Path
import json
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_drift_cap_comparison import read, save, digest, verify, load_window
from scripts.run_capped_frontier_rerank_comparison import original_sources, prefix
from scripts.run_drift_cap_later_completion import comparison
from backtest import frontier_capped_next_open_research as engine
from backtest.capped_frontier_rerank_research import rerank
from backtest.capped_frontier_independent_review import review_book as review_baseline
from backtest.relative_volatility_monthly_research import scale_selection
from backtest.relative_variance_independent_review import review_book as review_candidate
from backtest.relative_variance_independent_review import review_selection as review_scaled_selection
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.bounded_research_process import run_worker

FOLDER = ROOT / 'tmp/relative_variance_comparison_20261025_v1'
CONTRACT = 'docs/relative_variance_fixed_run_list_20261025.md'
SPECS = {
    'earlier': dict(months=19,
        baseline='tmp/capped_frontier_rerank_20261025_v2/earlier-equivalent.json',
        training='tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'),
    'later': dict(months=12,
        baseline='tmp/capped_frontier_rerank_20261025_v2/run_v1/later-candidate.json',
        training='tmp/next12_training_prepare_20261014_v1/prepared.json'),
}


def windows_for(label):
    data = read(SPECS[label]['training'])
    windows = {row.get('decision_date', row.get('decision_cutoff')): row for row in data['windows']}
    if len(windows) != len(data['windows']):
        raise ValueError('DUPLICATE_TRAINING_WINDOW')
    return windows


def sources():
    result = original_sources()
    for spec in SPECS.values():
        for key in ('baseline', 'training'):
            result[spec[key]] = digest(spec[key])
    for module in tuple(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if location:
            path = Path(location).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                result[path.relative_to(ROOT).as_posix()] = digest(path)
    for path in (CONTRACT, 'scripts/run_relative_variance_comparison.py',
                 'tests/test_relative_volatility_monthly_research.py',
                 'tests/test_relative_variance_independent_review.py'):
        result[path] = digest(path)
    result[str(Path(sys.executable).resolve())] = digest(Path(sys.executable).resolve())
    return result


def preflight():
    FOLDER.mkdir(exist_ok=False)
    frozen = sources()
    reports = {}
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
        for label, spec in SPECS.items():
            assembled, bars, _ = load_window(label)
            baseline = read(spec['baseline'])
            replay = engine.run_frontier_capped_next_open(assembled=assembled, ohlc=bars,
                initial_cash='20000', fee_bps='1', slippage_bps='10',
                risk=MonthlyExitCoreResearchAdapter(assembled['provider_actions']),
                verified_prefix=prefix(baseline, spec['months']), max_new_searches=0)
            differences = [key for key in set(replay) | set(baseline)
                           if key not in ('new_searches', 'reused_searches')
                           and replay.get(key) != baseline.get(key)]
            if differences or replay['new_searches']:
                raise ValueError('V27_REPLAY_CHANGED:' + ','.join(differences))
            reports[label] = review_baseline(replay, assembled, bars, rerank_enabled=True)
            # No candidate execution here: only check all required window bindings.
            windows = windows_for(label)
            for audit in replay['provider_audit']:
                if audit.get('selection'):
                    selected = audit['selection']
                    day = selected['raw_selection']['binding']['search_arguments']['decision_date']
                    scaled = scale_selection(selected, windows[day])
                    review_scaled_selection(scaled, windows[day])
    verify(dict(source_sha256=frozen))
    save(FOLDER / 'preflight.json', dict(status='PASS_ZERO_NEW_SEARCH',
        source_sha256=frozen, baseline_reviews=reports, new_searches=0))


def register():
    pre = read(FOLDER / 'preflight.json')
    if pre['status'] != 'PASS_ZERO_NEW_SEARCH':
        raise ValueError('PREFLIGHT_REQUIRED')
    verify(pre)
    frozen = sources()
    frozen[str(FOLDER / 'preflight.json')] = digest(FOLDER / 'preflight.json')
    save(FOLDER / 'registration.json', dict(schema='RELATIVE_VARIANCE_FIXED_V1',
        source_sha256=frozen, specs=SPECS, new_search_limit=31, timeout_seconds=1800,
        output_directory=str(FOLDER / 'run_v1'), automatic_retry=False,
        production_changes=False, initial_cash='20000', fee_bps='1', slippage_bps='10'))


def execute(registration, expected):
    if digest(registration) != expected:
        raise ValueError('REGISTRATION_CHANGED')
    frozen = read(registration)
    verify(frozen)
    if frozen['specs'] != SPECS or frozen['new_search_limit'] != 31:
        raise ValueError('FIXED_SCOPE_CHANGED')
    output = Path(frozen['output_directory'])
    output.mkdir(exist_ok=False)
    started = time.monotonic()
    calls, completed = 0, {}
    terminal = dict(status='RUNNING', production_changes=False, automatic_retry=False)
    try:
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
            for label, spec in SPECS.items():
                assembled, bars, _ = load_window(label)
                baseline = read(spec['baseline'])
                windows = windows_for(label)
                dates = [row['decision_date'] for row in assembled['monthly_inputs']]
                seen = []

                def progress(event):
                    nonlocal calls
                    if time.monotonic() - started > 1800:
                        raise TimeoutError('FIXED_BUDGET_EXHAUSTED')
                    if event['stage'] == 'MONTHLY_SEARCH_STARTED':
                        calls += 1
                        seen.append(event['decision_date'])
                        if calls > 31 or seen != dates[:len(seen)] or len(seen) > spec['months']:
                            raise ValueError('REGISTERED_SEARCH_SCOPE_EXCEEDED')
                    with (output / 'progress.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(dict(window=label, **event)) + '\n')
                    print(label, event['stage'], event['decision_date'], flush=True)

                def scaled(raw):
                    selected = rerank(raw)
                    return scale_selection(selected, windows[raw['decision_date']])

                with patch.object(engine, 'rerank', scaled):
                    candidate = engine.run_frontier_capped_next_open(
                        assembled=assembled, ohlc=bars, initial_cash='20000',
                        fee_bps='1', slippage_bps='10',
                        risk=MonthlyExitCoreResearchAdapter(assembled['provider_actions']),
                        max_new_searches=spec['months'], progress=progress)
                save(output / (label + '-candidate.json'), candidate)
                if candidate['status'] != 'COMPLETE' or seen != dates:
                    raise ValueError('INCOMPLETE_CANDIDATE:' + label)
                reviewed = review_candidate(candidate, assembled, bars, windows=windows)
                save(output / (label + '-review.json'), reviewed)
                completed[label] = comparison(candidate, baseline)
                terminal['comparisons'] = deepcopy(completed)
            verify(frozen)
            if calls != 31 or time.monotonic() - started > 1800:
                raise ValueError('FINAL_SCOPE_OR_BUDGET_MISMATCH')
            terminal.update(status='COMPLETE_TWO_WINDOWS_REVIEWED',
                preferred_screen=all(row['noninferior'] for row in completed.values()) and
                                 any(row['strict_improvement'] for row in completed.values()))
    except BaseException as error:
        terminal.update(status='FAILED_INCONCLUSIVE', reason=str(error), error_type=type(error).__name__)
        raise
    finally:
        terminal.update(new_search_calls=calls, elapsed_seconds=time.monotonic()-started)
        save(output / 'terminal.json', terminal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'register', 'launch', 'execute'])
    parser.add_argument('--sha256')
    args = parser.parse_args()
    registration = FOLDER / 'registration.json'
    if args.mode == 'preflight':
        preflight()
    elif args.mode == 'register':
        register()
    elif args.mode == 'launch':
        frozen = read(registration)
        verify(frozen)
        print(json.dumps(run_worker(script=__file__, expected_sha256=digest(__file__),
            arguments=['execute', '--sha256', digest(registration)],
            output_directory=FOLDER / 'supervisor_v1', timeout_seconds=1800)))
    else:
        if not args.sha256:
            parser.error('--sha256 required')
        execute(registration, args.sha256)


if __name__ == '__main__':
    main()
