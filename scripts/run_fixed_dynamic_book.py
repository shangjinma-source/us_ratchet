"""One pre-registered dynamic book. Invoked only by the bounded batch runner."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.dynamic_historical_inputs import build_historical_inputs
from backtest.dynamic_switch_provider import build_dynamic_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.research_exact_fast_guided import enhanced_search


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--bundle-sha256', required=True)
    parser.add_argument('--book-id', choices=['L-A', 'L-B', 'E-A', 'E-B'], required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    raw = Path(args.bundle).read_bytes()
    if sha256(raw).hexdigest() != args.bundle_sha256:
        raise ValueError('REGISTERED_BUNDLE_CHANGED')
    bundle = json.loads(raw)
    if bundle['label'] != ('later' if args.book_id.startswith('L-') else 'earlier'):
        raise ValueError('BOOK_WINDOW_MISMATCH')
    for name, expected in bundle['source_sha256'].items():
        if sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('INPUT_SOURCE_CHANGED: '+name)
    result_path = Path(args.result)
    if result_path.exists():
        raise ValueError('NEW_RESULT_REQUIRED')
    selections = result_path.with_suffix('')
    selections.mkdir(exist_ok=False)
    calls = 0
    last = None

    def selector(**arguments):
        nonlocal calls, last
        calls += 1
        last = arguments['decision_date']
        if calls > len(bundle['session_dates'])-1:
            raise ValueError('REGISTERED_SEARCH_LIMIT_EXCEEDED')
        print(args.book_id, calls, last, flush=True)
        return enhanced_search(**arguments)

    def recorder(day, arguments, selection):
        path = selections/(day+'.json')
        with path.open('x', encoding='utf-8') as stream:
            json.dump(dict(arguments=arguments, selection=selection), stream)

    result = dict(status='RUNNING', book_id=args.book_id, bundle_path=str(Path(args.bundle).resolve()),
                  bundle_sha256=args.bundle_sha256, selection_directory=str(selections.resolve()))
    try:
        builder = build_historical_inputs(bundle, selector=selector, selection_recorder=recorder)
        provider, audit = build_dynamic_provider(builder,
            authorized_risk_reset_dates=bundle['reset_dates'], reviewed_risk_splits=bundle['risk_events'],
            nontradable_policy='SELECT_TRADABLE_REPORT_TOTAL',
            reentry_policy='LATER_CLOSE' if args.book_id.endswith('-B') else 'MONTHLY_ONLY',
            reviewed_post_close_distributions=bundle['distribution_events'])
        book = run_next_open_book(session_dates=bundle['session_dates'], ohlc=bundle['ohlc'],
            initial_cash=bundle['initial_cash'], initial_shares=bundle['initial_shares'],
            fee_bps=bundle['fee_bps'], slippage_bps=bundle['slippage_bps'], events=bundle['actions'],
            order_provider=provider, cash_stock_merger_events=bundle['cash_stock_merger_events'],
            fractional_settlements=bundle['fractional_settlements'],
            price_source_references=bundle['price_source_references'], distribution_events=bundle['distribution_events'],
            distribution_fractional_cash_values=bundle['distribution_fractional_cash_values'], account_model=bundle['account_model'])
        result.update(book=book, audit=audit)
        if book['status'] != 'COMPLETE' or len(audit) != len(bundle['session_dates'])-1:
            raise ValueError('INCOMPLETE_BOOK: '+str(book.get('reason')))
        result['status'] = 'COMPLETE'
    except Exception as error:
        result.update(status='FAILED_INCONCLUSIVE', error_type=type(error).__name__, detail=str(error))
        raise
    finally:
        result.update(optimizer_calls=calls, last_decision_attempt=last, production_changes=False)
        result_path.write_text(json.dumps(result)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
