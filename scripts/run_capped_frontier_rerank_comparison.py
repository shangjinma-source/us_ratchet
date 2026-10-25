"""One bounded comparison of reranking a same-call frontier after the 50% cap."""
import argparse
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_drift_cap_comparison import digest, read, save, verify, load_window, replay_baseline, WINDOWS
from scripts.run_drift_cap_later_completion import comparison
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.frontier_capped_next_open_research import run_frontier_capped_next_open
from backtest.capped_frontier_rerank_research import rerank
from backtest.capped_frontier_independent_review import review_book, review_selection

FOLDER = 'tmp/capped_frontier_rerank_20261025_v2'
PREFLIGHT = FOLDER + '/preflight.json'
EARLIER = FOLDER + '/earlier-equivalent.json'
REGISTRATION = FOLDER + '/registration.json'
CONTRACT = 'research_contracts/capped_frontier_rerank_20261025.md'
FIRST_CHANGE = '2026-01-30'
FRESH_DATES = ['2026-02-27', '2026-03-31', '2026-04-30', '2026-05-29', '2026-06-30']


def preparation_sources():
    """Bind preflight to the code and contract that actually produced it."""
    sources = {}
    for module in tuple(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if location:
            path = Path(location).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT).as_posix()
                sources[relative] = digest(relative)
    for relative in (CONTRACT, 'scripts/run_capped_frontier_rerank_comparison.py',
                     'tests/test_capped_frontier_independent_review.py',
                     'backtest/bounded_research_process.py'):
        sources[relative] = digest(relative)
    sources[str(Path(sys.executable).resolve())] = digest(Path(sys.executable).resolve())
    return sources


def prefix(book, count):
    selections = [audit['selection']['raw_selection'] for audit in book['provider_audit'] if audit.get('selection')]
    accounts = book['selection_account_states']
    if len(selections) != len(accounts) or not 0 < count <= len(accounts):
        raise ValueError('EXACT_ORIGINAL_PREFIX_REQUIRED')
    return [dict(arguments=deepcopy(account), raw_selection=deepcopy(selection))
            for account, selection in list(zip(accounts, selections))[:count]]


def equivalent_audits(candidate, baseline):
    if len(candidate) != len(baseline):
        raise ValueError('AUDIT_LENGTH_CHANGED')
    for left, right in zip(candidate, baseline):
        for key in set(left) | set(right):
            if key == 'selection':
                if bool(left.get(key)) != bool(right.get(key)):
                    raise ValueError('SELECTION_PRESENCE_CHANGED')
                if left.get(key):
                    for field in ('target_quantities', 'investable_equity', 'raw_selection'):
                        if left[key][field] != right[key][field]:
                            raise ValueError('SELECTION_ECONOMICS_CHANGED:' + field)
            elif left.get(key) != right.get(key):
                raise ValueError('PROVIDER_ECONOMICS_CHANGED:' + key)


def full_equivalence(candidate, baseline):
    for key in set(candidate) | set(baseline):
        if key in ('new_searches', 'reused_searches', 'provider_audit'):
            continue
        if candidate.get(key) != baseline.get(key):
            raise ValueError('FULL_BOOK_ECONOMICS_CHANGED:' + key)
    equivalent_audits(candidate['provider_audit'], baseline['provider_audit'])
    if candidate['new_searches'] != 0 or candidate['reused_searches'] != 19:
        raise ValueError('EARLIER_MUST_HAVE_NINETEEN_EXACT_CACHED_CALLS')


def original_sources():
    sources = {}
    for spec in WINDOWS.values():
        registered = read(spec['registration'])
        verify(registered)
        for path, expected in registered['source_sha256'].items():
            if path in sources and sources[path] != expected:
                raise ValueError('CONFLICTING_ORIGINAL_SOURCE:' + path)
            sources[path] = expected
        for path in (spec['registration'], spec['assembled'], spec['bars'], spec['baseline']):
            sources[path] = digest(path)
    return sources


def technical_preflight():
    original_sources()
    reports = {}
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
        early_inputs, early_bars, early_base = load_window('earlier')
        replay_baseline(early_inputs, early_bars, early_base)
        reports['earlier_baseline'] = review_book(early_base, early_inputs, early_bars, rerank_enabled=False)
        early = run_frontier_capped_next_open(assembled=early_inputs, ohlc=early_bars,
            initial_cash='20000', fee_bps='1', slippage_bps='10',
            risk=MonthlyExitCoreResearchAdapter(early_inputs['provider_actions']),
            verified_prefix=prefix(early_base, 19), max_new_searches=0)
        full_equivalence(early, early_base)
        reports['earlier_candidate'] = review_book(early, early_inputs, early_bars, rerank_enabled=True)
        save(ROOT / EARLIER, early)
        later_inputs, later_bars, later_base = load_window('later')
        replay_baseline(later_inputs, later_bars, later_base)
        reports['later_baseline'] = review_book(later_base, later_inputs, later_bars, rerank_enabled=False)
        truncated = deepcopy(later_inputs)
        truncated['session_dates'] = [day for day in truncated['session_dates'] if day <= FIRST_CHANGE]
        truncated['monthly_inputs'] = [plan for plan in truncated['monthly_inputs']
                                       if plan['decision_date'] in truncated['session_dates'][:-1]]
        if len(truncated['monthly_inputs']) != 6:
            raise ValueError('SIX_UNCHANGED_LATER_ANCHORS_REQUIRED')
        unchanged = run_frontier_capped_next_open(assembled=truncated, ohlc=later_bars,
            initial_cash='20000', fee_bps='1', slippage_bps='10',
            risk=MonthlyExitCoreResearchAdapter(truncated['provider_actions']),
            verified_prefix=prefix(later_base, 6), max_new_searches=0)
        if (unchanged['status'] != 'COMPLETE' or unchanged['new_searches'] != 0
                or unchanged['reused_searches'] != 6):
            raise ValueError('LATER_UNCHANGED_PREFIX_INCOMPLETE')
        expected_ledger = [row for row in later_base['daily_ledger'] if row['date'] <= FIRST_CHANGE]
        expected_orders = [row for row in later_base['order_log'] if row['date'] <= FIRST_CHANGE]
        future_freezes = [row for row in expected_orders if row['date'] == FIRST_CHANGE
                         and row['event'] == 'FROZEN_TARGET_FOR_NEXT_OPEN'
                         and row.get('active_date') == '2026-02-02']
        if len(future_freezes) != 1 or expected_orders[-1] != future_freezes[0]:
            raise ValueError('SINGLE_FINAL_FUTURE_FREEZE_REQUIRED')
        # A truncated book has no next session to freeze.  Preserve every fill,
        # cash entry and earlier order; exclude only this verified future event.
        expected_orders = expected_orders[:-1]
        if unchanged['daily_ledger'] != expected_ledger or unchanged['order_log'] != expected_orders:
            raise ValueError('LATER_UNCHANGED_LEDGER_OR_ORDERS_CHANGED')
        if unchanged['selection_account_states'] != later_base['selection_account_states'][:6]:
            raise ValueError('LATER_UNCHANGED_SEARCH_ARGUMENTS_CHANGED')
        equivalent_audits(unchanged['provider_audit'], later_base['provider_audit'][:len(expected_ledger)])
        reports['later_unchanged_prefix'] = review_book(unchanged, truncated, later_bars, rerank_enabled=True)
        seventh = prefix(later_base, 7)[-1]
        plan = next(plan for plan in later_inputs['monthly_inputs'] if plan['decision_date'] == FIRST_CHANGE)
        arguments = dict(decision_date=FIRST_CHANGE,
            account_state=dict(asof=FIRST_CHANGE, revision='synthetic-book:' + FIRST_CHANGE,
                               cash=unchanged['cash'], shares=unchanged['shares'], reserved_cash='0'),
            valuation_quotes=plan['valuation_quotes'], search_arguments=plan['search_arguments'],
            source_hashes=plan['source_hashes'])
        if arguments != seventh['arguments']:
            raise ValueError('SEVENTH_RAW_SELECTION_INPUT_NOT_IDENTICAL')
        selected = rerank(seventh['raw_selection'])
        reports['seventh_selection'] = review_selection(selected, rerank_enabled=True)
        if not selected['rerank_audit']['strict_improvement']:
            raise ValueError('EXPECTED_FIRST_STRICT_RANKING_CHANGE_MISSING')
        if [plan['decision_date'] for plan in later_inputs['monthly_inputs'][7:]] != FRESH_DATES:
            raise ValueError('FIVE_FRESH_DATES_CHANGED')
    return dict(status='TECHNICAL_PREFLIGHT_PASS_NO_NEW_SEARCH', new_searches=0,
                earlier_full_book_equivalent=True, earlier_cached_calls=19,
                later_unchanged_execution_cached_calls=6, seventh_input_exactly_bound=True,
                first_changed_execution_not_run=True, first_changed_decision=FIRST_CHANGE,
                excluded_final_future_freeze=future_freezes[0],
                earlier_equivalent_sha256=digest(EARLIER), independent_reviews=reports,
                preparation_source_sha256=preparation_sources())


def registration():
    pre = read(PREFLIGHT)
    if pre['status'] != 'TECHNICAL_PREFLIGHT_PASS_NO_NEW_SEARCH' or pre['earlier_equivalent_sha256'] != digest(EARLIER):
        raise ValueError('COMPLETE_CURRENT_PREFLIGHT_REQUIRED')
    verify(dict(source_sha256=pre['preparation_source_sha256']))
    sources = original_sources()
    for module in tuple(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if location:
            path = Path(location).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT).as_posix()
                sources[relative] = digest(relative)
    for path in (CONTRACT, PREFLIGHT, EARLIER,
                 'scripts/run_capped_frontier_rerank_comparison.py',
                 'tests/test_capped_frontier_independent_review.py',
                 'backtest/bounded_research_process.py'):
        sources[path] = digest(path)
    sources[str(Path(sys.executable).resolve())] = digest(Path(sys.executable).resolve())
    return dict(schema='CAPPED_SAME_CALL_FRONTIER_RERANK_V1', source_sha256=sources,
                output_directory=FOLDER + '/run_v1', timeout_seconds=600,
                first_changed_decision=FIRST_CHANGE, exact_cached_later_calls=7,
                new_search_limit=5, fresh_dates=FRESH_DATES,
                original_generator_budget=8192, original_continuous_steps=32,
                extra_capped_rank_scores='COUNT_EACH_DISTINCT_PROJECTED_BASKET_SEPARATELY',
                fee_bps='1', slippage_bps='10', initial_cash='20000',
                automatic_retry=False, automatic_deployment=False,
                criterion='Both windows noninferior return and drawdown, at least one strict improvement',
                limitation='Conditional historical same-call frontier ranking, not constrained optimum, PIT, OOS or actual execution')


def execute(path, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError('REGISTRATION_CHANGED')
    frozen = read(path)
    verify(frozen)
    output = ROOT / frozen['output_directory']
    output.mkdir(exist_ok=False)
    save(output / 'started.json', dict(registration_sha256=expected_sha))
    started, calls, reuses = time.monotonic(), 0, 0
    terminal = dict(status='RUNNING', production_changes=False, automatic_retry=False)
    try:
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('OFFLINE_ONLY')):
            early_inputs, early_bars, early_base = load_window('earlier')
            early = read(EARLIER)
            full_equivalence(early, early_base)
            early_review = review_book(early, early_inputs, early_bars, rerank_enabled=True)
            assembled, bars, baseline = load_window('later')
            baseline_review = review_book(baseline, assembled, bars, rerank_enabled=False)
            save(output / 'later-baseline-review.json', baseline_review)

            def progress(event):
                nonlocal calls, reuses
                if time.monotonic() - started > frozen['timeout_seconds']:
                    raise TimeoutError('FIXED_RESEARCH_BUDGET_EXHAUSTED')
                if event['stage'] == 'MONTHLY_SELECTION_REUSED':
                    reuses += 1
                    if reuses > 7 or event['decision_date'] != assembled['monthly_inputs'][reuses-1]['decision_date']:
                        raise ValueError('EXACT_SEVEN_CACHE_PREFIX_REQUIRED')
                elif event['stage'] == 'MONTHLY_SEARCH_STARTED':
                    calls += 1
                    if reuses != 7 or calls > 5 or event['decision_date'] != FRESH_DATES[calls-1]:
                        raise ValueError('FIVE_REGISTERED_FRESH_CALLS_ONLY')
                with (output / 'progress.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event) + '\n')
                print(event['stage'], event['decision_date'], flush=True)

            result = run_frontier_capped_next_open(assembled=assembled, ohlc=bars,
                initial_cash='20000', fee_bps='1', slippage_bps='10',
                risk=MonthlyExitCoreResearchAdapter(assembled['provider_actions']),
                verified_prefix=prefix(baseline, 7), max_new_searches=5, progress=progress)
            save(output / 'later-candidate.json', result)
            if (result['status'] != 'COMPLETE' or calls != 5 or result['new_searches'] != 5
                    or reuses != 7 or result['reused_searches'] != 7):
                raise ValueError('REGISTERED_COMPLETE_CALL_COUNTS_REQUIRED')
            reviewed = review_book(result, assembled, bars, rerank_enabled=True)
            reviewed['book_sha256'] = digest(output / 'later-candidate.json')
            save(output / 'later-candidate-review.json', reviewed)
            comparisons = dict(earlier=comparison(early, early_base), later=comparison(result, baseline))
            passed = all(row['noninferior'] for row in comparisons.values()) and any(
                row['strict_improvement'] for row in comparisons.values())
            verify(frozen)
            if time.monotonic() - started > frozen['timeout_seconds']:
                raise TimeoutError('FINAL_REVIEW_EXCEEDED_FIXED_BUDGET')
            ranking_counts = {label: sum(a['selection']['rerank_audit']['additional_scored_baskets']
                for a in book['provider_audit'] if a.get('selection'))
                for label, book in [('earlier', early), ('later', result)]}
            terminal.update(status='COMPLETE_TWO_WINDOWS_INDEPENDENTLY_REVIEWED',
                historical_screen='PASS' if passed else 'REJECT', comparisons=comparisons,
                additional_capped_scored_baskets=ranking_counts,
                completed_windows=dict(earlier=early_review, later=reviewed))
    except BaseException as error:
        terminal.update(status='FAILED_INCONCLUSIVE', error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        terminal.update(new_search_calls=calls, exact_cached_later_calls=reuses,
                        earlier_new_search_calls=0, elapsed_seconds=time.monotonic() - started)
        save(output / 'terminal.json', terminal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'register', 'execute'))
    parser.add_argument('--registration', default=REGISTRATION)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.mode == 'preflight':
        (ROOT / FOLDER).mkdir(exist_ok=False)
        save(ROOT / PREFLIGHT, technical_preflight())
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
