"""Complete only the untouched later window after a saved-book review correction.

Preserves the failed original batch; no earlier optimization or automatic retry.
"""
import argparse
from fractions import Fraction
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_drift_cap_comparison import (
    digest, read, save, verify, load_window, replay_baseline,
    run_drift_capped_next_open, MonthlyExitCoreResearchAdapter)
from backtest.drift_cap_independent_review_v2 import review_book

ORIGINAL = 'tmp/drift_cap_research_20261025/registration.json'
ORIGINAL_SHA256 = '9f70d7dda0f3387b1a079418ad0d9b84978f8da818ee0fc8b1042b5e18efdb1a'
ORIGINAL_TERMINAL = 'tmp/drift_cap_research_20261025/run_v1/terminal.json'
EARLIER = 'tmp/drift_cap_research_20261025/run_v1/earlier-candidate.json'
EARLIER_REVIEW = 'tmp/drift_cap_research_20261025/earlier_candidate_independent_review_v2.json'
PREFLIGHT = 'tmp/drift_cap_research_20261025/later_completion_preflight_v2.json'
REGISTRATION = 'tmp/drift_cap_research_20261025/later_completion_registration_v2.json'
CONTRACT = 'research_contracts/drift_cap_later_completion_20261025.md'
OUTPUT = 'tmp/drift_cap_research_20261025/later_completion_v2'
TIMEOUT_SECONDS = 900


def validate_prior():
    if digest(ORIGINAL) != ORIGINAL_SHA256:
        raise ValueError('ORIGINAL_REGISTRATION_CHANGED')
    original = read(ORIGINAL)
    verify(original)
    terminal = read(ORIGINAL_TERMINAL)
    if terminal['status'] != 'FAILED_INCONCLUSIVE' or terminal['new_search_calls'] != 19:
        raise ValueError('EXACT_ORIGINAL_FAILED_EARLIER_ONLY_BATCH_REQUIRED')
    if terminal['completed_windows'] or terminal['comparisons']:
        raise ValueError('ORIGINAL_COMPLETION_STATE_CHANGED')
    receipt = read(EARLIER_REVIEW)
    if (receipt['status'] != 'COMPLETE_SAVED_EARLIER_BOOK_REVIEWED_V2'
            or receipt['new_searches'] != 0 or receipt['new_execution_books'] != 0
            or receipt['review']['status'] != 'INDEPENDENT_ACCOUNT_RISK_DRIFT_REVIEW_PASS'
            or receipt['review']['review_version'] != 2):
        raise ValueError('EARLIER_ZERO_SEARCH_REVIEW_PASS_REQUIRED')
    verify(receipt)
    if receipt['source_sha256'][EARLIER] != digest(EARLIER):
        raise ValueError('SAVED_EARLIER_BOOK_CHANGED')
    book = read(EARLIER)
    if book['new_searches'] != 19 or book['reused_searches'] != 0:
        raise ValueError('EXACT_PRIOR_EARLIER_SEARCH_COUNT_REQUIRED')
    if terminal['elapsed_seconds'] + TIMEOUT_SECONDS >= 1800:
        raise ValueError('ORIGINAL_COMBINED_TIME_BUDGET_EXCEEDED')
    return original, terminal, receipt, book


def preflight():
    validate_prior()
    reports = {}
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
        for label in ('earlier', 'later'):
            assembled, bars, baseline = load_window(label)
            replay_baseline(assembled, bars, baseline)
            reports[label + '_baseline'] = review_book(baseline, assembled, bars, drift_enabled=False)
            if label == 'earlier':
                reports['earlier_candidate'] = review_book(read(EARLIER), assembled, bars, drift_enabled=True)
    return dict(status='ZERO_NEW_SEARCH_PREFLIGHT_PASS', new_searches=0,
                exact_baseline_replays=2, independent_reviews=reports,
                earlier_book_sha256=digest(EARLIER), earlier_review_sha256=digest(EARLIER_REVIEW))


def registration():
    original, prior_terminal, _, _ = validate_prior()
    pre = read(PREFLIGHT)
    if (pre['status'] != 'ZERO_NEW_SEARCH_PREFLIGHT_PASS' or pre['new_searches'] != 0
            or pre['earlier_book_sha256'] != digest(EARLIER)
            or pre['earlier_review_sha256'] != digest(EARLIER_REVIEW)):
        raise ValueError('CURRENT_PREFLIGHT_REQUIRED')
    sources = dict(original['source_sha256'])
    for module in tuple(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if location:
            path = Path(location).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT).as_posix()
                sources[relative] = digest(relative)
    for path in (ORIGINAL, ORIGINAL_TERMINAL, EARLIER, EARLIER_REVIEW, PREFLIGHT, CONTRACT,
                 'tests/test_drift_cap_independent_review_v2.py',
                 'scripts/run_drift_cap_later_completion.py'):
        sources[path] = digest(path)
    return dict(schema='DRIFT_CAP_LATER_COMPLETION_V2', source_sha256=sources,
                output_directory=OUTPUT, original_registration_sha256=ORIGINAL_SHA256,
                preserved_original_status='FAILED_INCONCLUSIVE', earlier_book=EARLIER,
                earlier_review=EARLIER_REVIEW, earlier_new_search_calls=19,
                allowed_window='later', new_search_limit=12, combined_search_limit=31,
                timeout_seconds=TIMEOUT_SECONDS, prior_elapsed_seconds=prior_terminal['elapsed_seconds'],
                combined_execution_budget_seconds=1800, fee_bps='1', slippage_bps='10',
                initial_cash='20000', automatic_retry=False, automatic_deployment=False,
                criterion='Each window return >= baseline and drawdown <= baseline; at least one strict improvement across the two windows',
                limitation='Same conditional historical inputs, original economic kernel and A rule; '
                           'only independent WAIT validation corrected; not PIT, OOS or actual execution')


def comparison(candidate, baseline):
    candidate_return, baseline_return = Fraction(candidate['total_return']), Fraction(baseline['total_return'])
    candidate_dd = Fraction(candidate['drawdown']['maximum_close_drawdown'])
    baseline_dd = Fraction(baseline['drawdown']['maximum_close_drawdown'])
    return dict(noninferior=candidate_return >= baseline_return and candidate_dd <= baseline_dd,
                strict_improvement=candidate_return > baseline_return or candidate_dd < baseline_dd,
                candidate_return=str(candidate_return), baseline_return=str(baseline_return),
                candidate_drawdown=str(candidate_dd), baseline_drawdown=str(baseline_dd))


def execute(path, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError('REGISTRATION_CHANGED')
    frozen = read(path)
    verify(frozen)
    _, _, receipt, earlier = validate_prior()
    output = ROOT / frozen['output_directory']
    output.mkdir(exist_ok=False)
    save(output / 'started.json', dict(registration_sha256=expected_sha))
    started, calls = time.monotonic(), 0
    terminal = dict(status='RUNNING', production_changes=False, automatic_retry=False,
                    prior_batch_preserved='FAILED_INCONCLUSIVE', prior_new_search_calls=19)
    try:
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
            assembled, bars, baseline = load_window('later')
            replay_baseline(assembled, bars, baseline)
            baseline_review = review_book(baseline, assembled, bars, drift_enabled=False)
            save(output / 'later-baseline-review.json', baseline_review)
            earlier_baseline = read('tmp/capped_earlier_reselection_20261024_v1/cap50_exit20/outcome.json')
            comparisons = dict(earlier=comparison(earlier, earlier_baseline))
            if not comparisons['earlier']['noninferior']:
                raise ValueError('EARLIER_NECESSARY_SCREEN_FAILED')

            def progress(event):
                nonlocal calls
                if time.monotonic() - started > frozen['timeout_seconds']:
                    raise TimeoutError('REMAINING_FIXED_BUDGET_EXHAUSTED')
                if event['stage'] == 'MONTHLY_SEARCH_STARTED':
                    calls += 1
                    if calls > 12:
                        raise ValueError('LATER_TWELVE_SEARCH_LIMIT_EXCEEDED')
                with (output / 'progress.jsonl').open('a', encoding='utf-8') as stream:
                    import json
                    stream.write(json.dumps(dict(window='later', **event)) + '\n')
                print('later', event['stage'], event['decision_date'], flush=True)

            result = run_drift_capped_next_open(
                assembled=assembled, ohlc=bars, initial_cash='20000', fee_bps='1', slippage_bps='10',
                risk=MonthlyExitCoreResearchAdapter(assembled['provider_actions']),
                drift_enabled=True, progress=progress)
            book_path = output / 'later-candidate.json'
            save(book_path, result)
            if calls != 12 or result['new_searches'] != 12 or result['reused_searches'] != 0:
                raise ValueError('LATER_COMPLETE_SEARCH_COUNT_MISMATCH')
            reviewed = review_book(result, assembled, bars, drift_enabled=True)
            reviewed['book_sha256'] = digest(book_path)
            save(output / 'later-candidate-review.json', reviewed)
            comparisons['later'] = comparison(result, baseline)
            passed = all(row['noninferior'] for row in comparisons.values())
            passed = passed and any(row['strict_improvement'] for row in comparisons.values())
            verify(frozen)
            if time.monotonic() - started > frozen['timeout_seconds']:
                raise TimeoutError('REMAINING_FIXED_BUDGET_EXHAUSTED_DURING_FINAL_REVIEW')
            terminal.update(status='COMPLETE_TWO_WINDOWS_INDEPENDENTLY_REVIEWED_V2',
                            historical_screen='PASS' if passed else 'REJECT', comparisons=comparisons,
                            completed_windows=dict(earlier=receipt['review'], later=reviewed))
    except BaseException as error:
        terminal.update(status='FAILED_INCONCLUSIVE', error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        terminal.update(new_search_calls=calls, total_new_search_calls=19 + calls,
                        elapsed_seconds=time.monotonic() - started)
        save(output / 'terminal.json', terminal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'register', 'execute'))
    parser.add_argument('--registration', default=REGISTRATION)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.mode == 'preflight':
        save(ROOT / PREFLIGHT, preflight())
        print(digest(PREFLIGHT))
    elif args.mode == 'register':
        save(ROOT / args.registration, registration())
        print(digest(args.registration))
    else:
        if not args.sha256:
            parser.error('--sha256 required')
        execute(args.registration, args.sha256)


if __name__ == '__main__':
    main()
