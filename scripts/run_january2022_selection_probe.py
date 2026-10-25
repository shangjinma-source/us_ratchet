"""One frozen January 2022 selection, explicitly launched; no execution or tuning."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEADLINE = datetime(2026, 10, 26, 3, tzinfo=timezone(timedelta(hours=8)))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    pending.replace(path)


def arguments_from_assembled(path):
    from backtest.continuous_guided_account_decision import REQUIRED_PINS
    document = json.loads(path.read_text(encoding='utf-8'))
    assembled = document.get('assembled', document)
    plans = assembled['monthly_inputs']
    if len(plans) != 1 or plans[0]['decision_date'] != '2021-12-31':
        raise ValueError('EXACTLY_ONE_DECEMBER31_SELECTION_REQUIRED')
    plan = plans[0]
    if any(name not in plan['source_hashes'] for name in REQUIRED_PINS):
        raise ValueError('MISSING_METHOD_PINS_BEFORE_WORKER_LAUNCH')
    search = plan['search_arguments']
    if search['max_objective_evaluations'] != 8192 or str(search['fee_bps']) != '0':
        raise ValueError('FIXED_8192_ZERO_COMMISSION_REQUIRED')
    if assembled['session_dates'][0] != '2021-12-31':
        raise ValueError('INITIAL_DECISION_DATE_MISMATCH')
    for quote in plan['valuation_quotes']:
        if Fraction(str(quote['price'])) != Fraction(assembled['close_prices'][quote['security_id']]['2021-12-31']):
            raise ValueError('NOMINAL_DECISION_MARK_MISMATCH')
    for filename, expected in plan['source_hashes'].items():
        file = Path(filename) if Path(filename).is_absolute() else ROOT / filename
        if digest(file) != expected:
            raise ValueError('SOURCE_HASH_MISMATCH:' + filename)
    return dict(decision_date='2021-12-31', account_state=dict(asof='2021-12-31',
        revision='synthetic-book:2021-12-31', cash='20000', shares={}, reserved_cash='0'),
        valuation_quotes=deepcopy(plan['valuation_quotes']), search_arguments=deepcopy(search),
        source_hashes=deepcopy(plan['source_hashes']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembled', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--run', action='store_true', help='Explicitly launch the single search')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--input-sha256', help=argparse.SUPPRESS)
    options = parser.parse_args()
    path = options.assembled.resolve(strict=True)
    if options.input_sha256 and digest(path) != options.input_sha256:
        raise ValueError('ASSEMBLED_CHANGED_AFTER_LAUNCH')
    arguments = arguments_from_assembled(path)
    if not options.worker:
        if not options.run:
            print(json.dumps(dict(status='PREFLIGHT_ONLY_NO_SEARCH', input_sha256=digest(path),
                max_original_evaluations=8192, additional_continuous_steps=32,
                cap_rerank='SAME_CALL_FRONTIER_50_PERCENT', risk='20_PERCENT_BOOK_STAGE_ONLY',
                initial_cash='20000', fee_bps='0', slippage_bps='5')))
            return
        remaining = (DEADLINE - datetime.now(timezone.utc)).total_seconds() - 15
        if options.seconds <= 0 or remaining <= 0:
            raise ValueError('POSITIVE_BUDGET_BEFORE_0300_REQUIRED')
        from backtest.bounded_research_process import run_worker
        print(json.dumps(run_worker(script=__file__, expected_sha256=digest(__file__),
            arguments=['--worker', '--assembled', str(path), '--output', str(options.output.resolve()),
                       '--input-sha256', digest(path)], output_directory=options.output,
            timeout_seconds=min(options.seconds, remaining, 3600)), indent=2))
        return
    output = options.output
    if not output.is_dir():
        raise ValueError('WORKER_REQUIRES_BOUNDED_PARENT_DIRECTORY')
    with (output / 'attempt.lock').open('x') as lock:
        lock.write('One selection only; failed attempts are not retried.\n')
    try:
        from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account
        from backtest.capped_frontier_rerank_research import rerank
        from backtest.capped_frontier_independent_review import review_selection
        save(output / 'arguments.json', arguments)
        print('ONE_RAW_SEARCH_STARTED', flush=True)
        raw = decide_continuous_guided_for_account(**arguments)
        save(output / 'raw_selection.json', raw)
        save(output / 'verified_prefix_candidate.json', [dict(arguments=arguments, raw_selection=raw)])
        print('RAW_SAVED_BEFORE_RERANK', flush=True)
        selected = rerank(raw)
        save(output / 'reranked_selection.json', selected)
        review = review_selection(selected, rerank_enabled=True)
        save(output / 'review.json', review)
        save(output / 'result.json', dict(status='SELECTION_REVIEWED_NOT_EXECUTED',
            new_searches=1, target_quantities=selected['target_quantities'], initial_cash='20000',
            fee_bps='0', slippage_bps='5', risk_provider_certified=False,
            input_sha256=digest(path), raw_selection_sha256=digest(output / 'raw_selection.json')))
        print('ONE_SELECTION_COMPLETE_NO_BOOK_OR_PARAMETER_SEARCH', flush=True)
    except Exception as error:
        save(output / 'error.json', dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    main()
