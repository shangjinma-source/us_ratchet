"""Bounded causal baseline with immutable selection checkpoints and exposure gates.

This is a research-only worker. Unmapped exposed actions stop the book before
that month's execution; the expensive selection survives for exact-input reuse.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from fractions import Fraction
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEADLINE = datetime(2026, 10, 26, 3, tzinfo=timezone(timedelta(hours=8)))
# Known corporate-action barriers are retained even if a price provider omits
# them. These are stop/review dates, never executable entitlement instructions.
KNOWN_ACTION_BARRIERS = (
    ('alxn','2021-07-21','CASH_STOCK_MERGER'),
    ('mxim','2021-08-26','STOCK_MERGER'),
    ('exc','2022-02-02','CEG_DISTRIBUTION'),
    ('xlnx','2022-02-14','STOCK_MERGER'),
    ('wbd','2022-04-11','PREDECESSOR_IDENTITY_TRANSITION'),
    ('atvi','2023-10-13','CASH_MERGER'),
    ('sgen','2023-12-14','CASH_MERGER'),
)


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.pending.json')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def exposed_action_blockers(arguments, selected, end_date, prices):
    start = arguments['decision_date']
    exposed = {sid for sid, quantity in arguments['account_state']['shares'].items() if quantity}
    exposed.update(sid for sid, quantity in selected['target_quantities'].items() if quantity)
    unknown = sorted(exposed & set(prices['action_stream_missing']))
    events = [event for event in prices['provider_event_inventory']
              if event['security_id'] in exposed and start < event['date'] <= end_date]
    events += [dict(security_id='research:security:'+ticker,date=day,kind=kind,
                    origin='KNOWN_ACTION_REVIEW_BARRIER_NOT_EXECUTION_INSTRUCTION')
               for ticker,day,kind in KNOWN_ACTION_BARRIERS
               if 'research:security:'+ticker in exposed and start < day <= end_date]
    return dict(decision_date=start, through=end_date, exposed=sorted(exposed),
                missing_action_streams=unknown, unmapped_events=events,
                admitted=not unknown and not events,
                evidence_scope='CONDITIONAL_PROVIDER_ABSENCE_ONLY_NOT_OFFICIAL_EXHAUSTIVE_PROOF')


def validate_selection_binding(raw, arguments):
    binding = raw['binding']
    account = arguments['account_state']
    quotes = {quote['security_id']:dict(price=str(Fraction(quote['price'])),as_of=quote['as_of'],
        price_basis=quote['price_basis'],source_references=quote['source_references'])
        for quote in arguments['valuation_quotes']}
    equity = Fraction(account['cash']) + sum((quantity*Fraction(quotes[sid]['price'])
        for sid,quantity in account['shares'].items() if quantity),Fraction(0))
    search = dict(arguments['search_arguments'])
    search.pop('quote_as_of')
    basis = search.pop('price_basis')
    search['entered_cash'] = str(equity)
    if not (binding['decision_date'] == arguments['decision_date']
            and Fraction(binding['available_cash']) == Fraction(account['cash'])
            and Fraction(binding['reserved_cash']) == Fraction(account['reserved_cash'])
            and binding['shares'] == account['shares']
            and binding['state_revision'] == account['revision']
            and binding['source_hashes'] == arguments['source_hashes']
            and binding['search_arguments'] == search
            and binding['valuation_quotes'] == quotes
            and all(quote['price_basis'] == basis for quote in quotes.values())):
        raise ValueError('RAW_SELECTION_INPUT_BINDING_MISMATCH')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembled', type=Path, required=True)
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', type=Path, help='Prior run checkpoints; exact arguments must match')
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--input-sha256', help=argparse.SUPPRESS)
    parser.add_argument('--prices-sha256', help=argparse.SUPPRESS)
    options = parser.parse_args()
    for path, expected in ((options.assembled, options.input_sha256), (options.prices, options.prices_sha256)):
        if expected and digest(path) != expected:
            raise ValueError('LAUNCH_INPUT_CHANGED:'+str(path))
    document = json.loads(options.assembled.read_text(encoding='utf-8'))
    assembled = document['assembled']
    prices = json.loads(options.prices.read_text(encoding='utf-8'))
    if document['execution_prices_sha256'] != digest(options.prices):
        raise ValueError('ASSEMBLY_PRICE_SNAPSHOT_MISMATCH')
    if len(assembled['monthly_inputs']) != 36 or assembled['session_dates'][0] != '2020-12-31' or assembled['session_dates'][-1] != '2023-12-29':
        raise ValueError('FROZEN_CONTINUOUS_BULL_BEAR_SCOPE_REQUIRED')
    from backtest.continuous_guided_account_decision import REQUIRED_PINS
    for plan in assembled['monthly_inputs']:
        if plan['source_hashes'] != assembled['source_hashes']:
            raise ValueError('MONTHLY_TOP_LEVEL_SOURCE_PIN_MISMATCH')
        if any(name not in plan['source_hashes'] for name in REQUIRED_PINS):
            raise ValueError('MISSING_METHOD_PINS')
        if plan['search_arguments']['max_objective_evaluations'] != 8192 or str(plan['search_arguments']['fee_bps']) != '0':
            raise ValueError('FIXED_SEARCH_BUDGET_REQUIRED')
    for filename, expected in assembled['source_hashes'].items():
        if digest(ROOT/filename) != expected:
            raise ValueError('SOURCE_CHANGED:'+filename)
    if any(assembled.get(key) for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events')):
        raise ValueError('THIS_INITIAL_PROBE_REQUIRES_EVENT_FREE_EXPOSURE_GATE')
    if not options.worker:
        if not options.run:
            print(json.dumps(dict(status='PREFLIGHT_ONLY', months=36, initial_cash='20000',
                fee_bps='0', slippage_bps='5', searches_per_month=1, max_original_evaluations=8192)))
            return
        remaining = (DEADLINE-datetime.now(timezone.utc)).total_seconds()-15
        if options.seconds <= 0 or remaining <= 0:
            raise ValueError('USER_DEADLINE_REACHED')
        from backtest.bounded_research_process import run_worker
        arguments = ['--worker','--assembled',str(options.assembled.resolve()),'--prices',str(options.prices.resolve()),
                     '--output',str(options.output.resolve()),'--input-sha256',digest(options.assembled),
                     '--prices-sha256',digest(options.prices)]
        if options.reuse:
            arguments += ['--reuse',str(options.reuse.resolve())]
        print(json.dumps(run_worker(script=__file__, expected_sha256=digest(__file__), arguments=arguments,
            output_directory=options.output, timeout_seconds=min(options.seconds,remaining,3600))))
        return
    if not options.output.is_dir():
        raise ValueError('BOUNDED_PARENT_REQUIRED')
    with (options.output/'attempt.lock').open('x') as attempt:
        attempt.write('One worker; no automatic retries.\n')
    import backtest.historical_dividend_frontier_research as frontier
    from backtest.capped_frontier_rerank_research import rerank
    from backtest.capped_frontier_independent_review import review_selection
    from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
    original_decide = frontier.decide_continuous_guided_for_account
    dates = [plan['decision_date'] for plan in assembled['monthly_inputs']] + [assembled['session_dates'][-1]]
    new_count, reused_count = 0, 0

    def decide(**arguments):
        nonlocal new_count, reused_count
        if datetime.now(timezone.utc) >= DEADLINE:
            raise ValueError('USER_DEADLINE_REACHED')
        day = arguments['decision_date']
        prior = options.reuse/f'{day}.selection.json' if options.reuse else None
        if prior and prior.exists():
            checkpoint = json.loads(prior.read_text(encoding='utf-8'))
            if checkpoint['arguments'] != arguments:
                raise ValueError('SAVED_SELECTION_ACCOUNT_OR_INPUT_MISMATCH:'+day)
            raw = checkpoint['raw_selection']
            reused_count += 1
        else:
            raw = original_decide(**arguments)
            new_count += 1
        save(options.output/f'{day}.selection.json', dict(arguments=arguments,raw_selection=raw))
        validate_selection_binding(raw,arguments)
        selected = rerank(deepcopy(raw))
        proof = review_selection(selected, rerank_enabled=True)
        gate = exposed_action_blockers(arguments, selected, dates[dates.index(day)+1], prices)
        gate.update(target_quantities=selected['target_quantities'], selection_review=proof)
        save(options.output/f'{day}.exposure.json',gate)
        if not gate['admitted']:
            raise ValueError('EXPOSED_ACTION_REVIEW_REQUIRED:'+day)
        return raw

    # Single bounded process only: instrument the selector without changing any
    # source module or calculation. Every call delegates to the pinned method.
    frontier.decide_continuous_guided_for_account = decide
    try:
        book = frontier.run_frontier_capped_next_open(assembled=assembled,ohlc=document['ohlc'],
            initial_cash='20000',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(assembled['actions']),
            max_new_searches=36,dividend_events=[])
    finally:
        frontier.decide_continuous_guided_for_account = original_decide
    book.update(new_searches=new_count,reused_searches=reused_count)
    save(options.output/'book.json',book)
    save(options.output/'summary.json',dict(status=book['status'],reason=book.get('reason'),
        completed_sessions=len(book.get('daily_ledger',[])),new_searches=new_count,reused_searches=reused_count,
        input_sha256=digest(options.assembled),prices_sha256=digest(options.prices),
        script_sha256=digest(__file__),performance_validated=False,full_bull_bear_validation=False))
    print(json.dumps(dict(status=book['status'],new_searches=new_count,reused_searches=reused_count)),flush=True)


if __name__ == '__main__':
    main()
