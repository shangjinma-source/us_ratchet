"""Bounded conditional old-window baseline (not independent out-of-sample) with immutable selection checkpoints and exposure gates.

This is a research-only worker. Unmapped exposed actions stop the book before
that month's execution; the expensive selection survives for exact-input reuse.
"""
import argparse
from copy import deepcopy
from datetime import date
import time
from hashlib import sha256
from fractions import Fraction
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAX_SEARCHES = 31
MAX_SECONDS = 3600


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.pending.json')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def canonical_day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('CANONICAL_ISO_DATE_REQUIRED')
    return value


def gross_dividend_events(action_review, prices, sessions):
    """Map reviewed historical nominal amounts; never rescale provider amounts."""
    if not action_review:
        raise ValueError('GROSS_DIVIDENDS_REQUIRE_PINNED_ACTION_REVIEW')
    events, seen = [], set()
    for row in action_review['rows']:
        if row['status'] != 'REVIEWED_ORDINARY_CASH_DIVIDEND':
            continue
        ex = canonical_day(row['ex_date'])
        pay = row['payment_date']
        if pay is not None:
            canonical_day(pay)
            if pay < ex:raise ValueError('PAYMENT_BEFORE_EX_DATE')
        if row.get('record_date') is not None:canonical_day(row['record_date'])
        key = (row['security_id'],ex)
        if key in seen:raise ValueError('DUPLICATE_REVIEWED_DIVIDEND')
        seen.add(key)
        if ex not in sessions[1:]:raise ValueError('DIVIDEND_OUTSIDE_EXECUTION_SESSIONS')
        if isinstance(row['amount_per_share'],bool) or Fraction(row['amount_per_share'])<=0 or row['currency']!='USD':
            raise ValueError('ORDINARY_NOMINAL_AMOUNT_REQUIRED')
        matches=[e for e in prices['provider_event_inventory'] if e['security_id']==key[0] and e['date']==ex and e.get('kind')=='dividends']
        if len(matches)!=1:raise ValueError('EXACT_PROVIDER_DIVIDEND_REQUIRED')
        provider=matches[0]
        if action_review['source_hashes'].get(provider['source'])!=provider['source_sha256']:
            raise ValueError('DIVIDEND_PROVIDER_SOURCE_NOT_BOUND')
        events.append(dict(event_id='ordinary-gross:'+key[0]+':'+ex,security_id=key[0],ex_date=ex,
            payment_date=pay,amount_per_share=str(Fraction(row['amount_per_share'])),withholding_rate='0',
            assumption='EXPLICIT_GROSS_RESEARCH_NO_WITHHOLDING_MODELED_NOT_USER_TAX_RATE; PAYMENT_AT_SESSION_CLOSE',currency='USD'))
    return events


def build_candidate(document):
    from scripts.assemble_old_continuous_inputs_v1 import assemble
    from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
    schema = ROOT / 'tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json'
    expected = assemble(schema)
    if document != expected:
        raise ValueError('ENVELOPE_MUST_MATCH_FROZEN_SCHEMA_AND_GATE')
    prepared = deepcopy(document['prepared_input_candidate'])
    for key in ('split_events_reference_only', 'identity_migrations', 'cash_stock_merger_events',
                'distribution_events', 'supported_conversions', 'unsupported_conversions'):
        prepared[key] = []
    for key in ('fractional_settlements', 'distribution_fractional_cash_values'):
        prepared[key] = {}
    candidate = assemble_monthly_execution_inputs_v4(prepared)
    candidate['admission_scope'] = 'UNTRUSTED_UNTIL_EACH_INTERVAL_EXPOSURE_GATE'
    # The assembler sorts quotes by SID; the frozen schema used ticker order.
    # Compare every full quote, including provenance, while preserving schema order.
    for actual, expected_plan in zip(candidate['monthly_inputs'], document['monthly_inputs']):
        actual_quotes = actual['valuation_quotes']
        expected_quotes = expected_plan['valuation_quotes']
        if (len({q['security_id'] for q in actual_quotes}) != len(actual_quotes)
                or len({q['security_id'] for q in expected_quotes}) != len(expected_quotes)
                or sorted(actual_quotes, key=lambda q: q['security_id']) != sorted(expected_quotes, key=lambda q: q['security_id'])):
            raise ValueError('CANDIDATE_VALUATION_QUOTES_CHANGED')
        actual['valuation_quotes'] = deepcopy(expected_quotes)
    if candidate['monthly_inputs'] != document['monthly_inputs']:
        raise ValueError('CANDIDATE_MONTHLY_INPUT_CHANGED')
    return candidate



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


def validate_scope(assembled):
    if len(assembled['monthly_inputs']) != 31 or assembled['session_dates'][0] != '2023-12-29' or assembled['monthly_inputs'][0]['decision_date'] != '2023-12-29' or assembled['monthly_inputs'][-1]['decision_date'] != '2026-06-30' or assembled['session_dates'][-1] != '2026-07-30':
        raise ValueError('FROZEN_CONTINUOUS_BULL_BEAR_SCOPE_REQUIRED')
    dates = [plan['decision_date'] for plan in assembled['monthly_inputs']]
    if len(set(dates)) != 31 or dates != sorted(dates):
        raise ValueError('UNIQUE_ORDERED_MONTHLY_DECISIONS_REQUIRED')
    expected = [(2023, 12)] + [(year, month) for year in (2024, 2025) for month in range(1, 13)] + [(2026, month) for month in range(1, 7)]
    if [(date.fromisoformat(day).year, date.fromisoformat(day).month) for day in dates] != expected:
        raise ValueError('EXACT_31_MONTH_COVERAGE_REQUIRED')
    if any(day not in assembled['session_dates'] for day in dates):
        raise ValueError('DECISION_SESSION_REQUIRED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembled', type=Path, required=True)
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', type=Path, help='Prior run checkpoints; exact arguments must match')
    parser.add_argument('--action-review', type=Path, help='Pinned no-action evidence for an exact missing-stream period')
    parser.add_argument('--gross-dividends', action='store_true', help='Explicit tax-before-withholding research; not user tax treatment')
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--input-sha256', help=argparse.SUPPRESS)
    parser.add_argument('--prices-sha256', help=argparse.SUPPRESS)
    parser.add_argument('--action-review-sha256', help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.action_review or options.gross_dividends:
        raise ValueError('ACTION_ADAPTER_NOT_ADMITTED_IN_V1')
    if not 0 < options.seconds <= MAX_SECONDS:
        raise ValueError('EXPLICIT_SECONDS_1_TO_3600_REQUIRED')
    if options.worker and not (options.input_sha256 and options.prices_sha256):
        raise ValueError('BOUNDED_PARENT_INPUT_PINS_REQUIRED')
    started = time.monotonic()
    for path, expected in ((options.assembled, options.input_sha256), (options.prices, options.prices_sha256)):
        if expected and digest(path) != expected:
            raise ValueError('LAUNCH_INPUT_CHANGED:'+str(path))
    document = json.loads(options.assembled.read_text(encoding='utf-8'))
    assembled = build_candidate(document)
    prices = json.loads(options.prices.read_text(encoding='utf-8'))
    action_review = None
    if options.action_review:
        if options.action_review_sha256 and digest(options.action_review)!=options.action_review_sha256:
            raise ValueError('ACTION_REVIEW_CHANGED_AFTER_LAUNCH')
        action_review = json.loads(options.action_review.read_text(encoding='utf-8'))
        pins = action_review['source_hashes']
        if not pins or not action_review['rows']:
            raise ValueError('EMPTY_PERIOD_ACTION_REVIEW')
        for filename,expected in pins.items():
            if filename in assembled['source_hashes'] and assembled['source_hashes'][filename]!=expected:
                raise ValueError('CONFLICTING_ACTION_SOURCE_PIN:'+filename)
            if digest(ROOT/filename)!=expected:
                raise ValueError('ACTION_REVIEW_SOURCE_CHANGED:'+filename)
        for row in action_review['rows']:
            if (row['status'] not in ('REVIEWED_NO_ACTION_FOR_PERIOD','REVIEWED_ORDINARY_CASH_DIVIDEND') or not row['source_references']
                    or any(reference not in pins for reference in row['source_references'])):
                raise ValueError('UNPINNED_PERIOD_ACTION_REVIEW')
            if row['status']=='REVIEWED_ORDINARY_CASH_DIVIDEND':
                canonical_day(row['ex_date'])
                for field in ('record_date','payment_date'):
                    if row.get(field) is not None:canonical_day(row[field])
                if not row['ex_date'] or row['currency']!='USD' or Fraction(row['amount_per_share'])<=0:
                    raise ValueError('ORDINARY_CASH_DIVIDEND_REVIEW_REQUIRED')
            else:
                canonical_day(row['start_exclusive']);canonical_day(row['end_inclusive'])
                if row['end_inclusive']<=row['start_exclusive']:raise ValueError('INVALID_REVIEW_PERIOD')
            sources = [source for source in prices['source_reviews'] if source['security_id']==row['security_id']]
            if not sources or any(pins.get(source['source'])!=source['sha256'] for source in sources):
                raise ValueError('ACTION_REVIEW_PRICE_SOURCE_NOT_BOUND')
    if digest(options.prices) != '3a0c0d3cc2b917a34c6f4328876dda50ee4cd8509af5c08e10fd86218729dfbf':
        raise ValueError('FROZEN_EXECUTION_PRICE_SNAPSHOT_REQUIRED')
    if options.action_review or options.gross_dividends:
        raise ValueError('ACTION_ADAPTER_NOT_ADMITTED_IN_V1')
    validate_scope(assembled)
    from backtest.continuous_guided_account_decision import REQUIRED_PINS
    for plan in assembled['monthly_inputs']:
        if plan['source_hashes'] != assembled['source_hashes']:
            raise ValueError('MONTHLY_TOP_LEVEL_SOURCE_PIN_MISMATCH')
        if any(name not in plan['source_hashes'] for name in REQUIRED_PINS):
            raise ValueError('MISSING_METHOD_PINS')
        if plan['search_arguments']['max_objective_evaluations'] != 8192 or str(plan['search_arguments']['fee_bps']) != '0' or str(plan['search_arguments']['minimum_cash_buffer']) != '0' or plan['search_arguments']['fixed_seed'] != 'fresh-quantity-20261014-v1':
            raise ValueError('FIXED_SEARCH_BUDGET_REQUIRED')
    for filename, expected in assembled['source_hashes'].items():
        if digest(ROOT/filename) != expected:
            raise ValueError('SOURCE_CHANGED:'+filename)
    if any(assembled.get(key) for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events')):
        raise ValueError('THIS_INITIAL_PROBE_REQUIRES_EVENT_FREE_EXPOSURE_GATE')
    dividend_events = gross_dividend_events(action_review,prices,assembled['session_dates']) if options.gross_dividends else []
    if not options.worker:
        if not options.run:
            print(json.dumps(dict(status='PREFLIGHT_ONLY', months=31, initial_cash='20000',
                fee_bps='0', slippage_bps='5', searches_per_month=1, max_original_evaluations=8192,
                gross_dividends_research=options.gross_dividends, mapped_dividend_events=len(dividend_events))))
            return
        from backtest.bounded_research_process import run_worker
        arguments = ['--worker','--seconds',str(options.seconds),'--assembled',str(options.assembled.resolve()),'--prices',str(options.prices.resolve()),
                     '--output',str(options.output.resolve()),'--input-sha256',digest(options.assembled),
                     '--prices-sha256',digest(options.prices)]
        if options.reuse:
            arguments += ['--reuse',str(options.reuse.resolve())]
        if options.action_review:
            arguments += ['--action-review',str(options.action_review.resolve()),
                          '--action-review-sha256',digest(options.action_review)]
        if options.gross_dividends:arguments.append('--gross-dividends')
        print(json.dumps(run_worker(script=__file__, expected_sha256=digest(__file__), arguments=arguments,
            output_directory=options.output, timeout_seconds=options.seconds)))
        return
    if not options.output.is_dir():
        raise ValueError('BOUNDED_PARENT_REQUIRED')
    with (options.output/'attempt.lock').open('x') as attempt:
        attempt.write('One worker; no automatic retries.\n')
    execution_inputs=deepcopy(document)
    execution_inputs['assembled'] = deepcopy(assembled)
    execution_inputs.update(dividend_events=dividend_events,gross_dividends_research=options.gross_dividends,
        action_source_hashes=deepcopy((action_review or {}).get('source_hashes',{})),
        action_review_sha256=digest(options.action_review) if options.action_review else None,
        original_assembled_sha256=digest(options.assembled),execution_assumption=(
            'GROSS_RESEARCH_NOT_ACTUAL_ACCOUNT_NET_RETURN' if options.gross_dividends else 'NO_NONZERO_DIVIDEND_ADMISSION'))
    save(options.output/'execution_inputs.json',execution_inputs)
    import backtest.historical_dividend_frontier_research as frontier
    from backtest.capped_frontier_rerank_research import rerank
    from backtest.capped_frontier_independent_review import review_selection
    from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
    original_decide = frontier.decide_continuous_guided_for_account
    dates = [plan['decision_date'] for plan in assembled['monthly_inputs']] + [assembled['session_dates'][-1]]
    new_count, reused_count = 0, 0
    liquidation_obligations = []
    zero_dividend_obligations = []

    def decide(**arguments):
        nonlocal new_count, reused_count
        if time.monotonic()-started >= options.seconds:
            raise ValueError('SINGLE_ATTEMPT_TIME_BUDGET_REACHED')
        day = arguments['decision_date']
        prior = options.reuse/f'{day}.selection.json' if options.reuse else None
        if prior and prior.exists():
            checkpoint = json.loads(prior.read_text(encoding='utf-8'))
            if checkpoint['arguments'] != arguments:
                raise ValueError('SAVED_SELECTION_ACCOUNT_OR_INPUT_MISMATCH:'+day)
            raw = checkpoint['raw_selection']
            reused_count += 1
        else:
            if new_count >= MAX_SEARCHES:
                raise ValueError('MAX_31_NEW_SEARCHES_REACHED')
            raw = original_decide(**arguments)
            new_count += 1
        save(options.output/f'{day}.selection.json', dict(arguments=arguments,raw_selection=raw))
        validate_selection_binding(raw,arguments)
        selected = rerank(deepcopy(raw))
        proof = review_selection(selected, rerank_enabled=True)
        sessions = assembled['session_dates']
        active_date = sessions[sessions.index(day)+1]
        from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
        gate = exposure_gate(document, arguments, selected, dates[dates.index(day)+1], active_date)
        gate.update(target_quantities=selected['target_quantities'], selection_review=proof)
        save(options.output/f'{day}.exposure.json',gate)
        if not gate['admitted']:
            raise ValueError('EXPOSED_ACTION_REVIEW_REQUIRED:'+day)
        liquidation_obligations.extend(dict(date=active_date,security_id=sid,quantity=quantity)
            for sid,quantity in arguments['account_state']['shares'].items()
            if quantity and not selected['target_quantities'].get(sid,0))
        zero_dividend_obligations.extend(gate.get('ignored_zero_entitlement', []))
        return raw

    # Single bounded process only: instrument the selector without changing any
    # source module or calculation. Every call delegates to the pinned method.
    frontier.decide_continuous_guided_for_account = decide
    try:
        book = frontier.run_frontier_capped_next_open(assembled=assembled,ohlc=document['ohlc'],
            initial_cash='20000',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(assembled['actions']),
            max_new_searches=31,dividend_events=dividend_events)
    finally:
        frontier.decide_continuous_guided_for_account = original_decide
    book.update(new_searches=new_count,reused_searches=reused_count)
    save(options.output/'candidate_book.json',book)
    by_date = {row['date']:row for row in book['daily_ledger']}
    for obligation in liquidation_obligations:
        if obligation['date'] not in by_date:
            continue  # A blocked execution grants no completed-period proof.
        filled = sum(log['quantity'] for log in book['order_log']
            if log.get('event')=='ASSUMED_NEXT_OPEN_FILLED' and log.get('side')=='SELL'
            and log['date']==obligation['date'] and log['security_id']==obligation['security_id'])
        if by_date[obligation['date']]['shares'].get(obligation['security_id'],0) or filled!=obligation['quantity']:
            raise ValueError('SHORT_EXPOSURE_LIQUIDATION_NOT_PROVEN')
    save(options.output/'liquidation_review.json',dict(obligations=liquidation_obligations,
        verified_executed=[row for row in liquidation_obligations if row['date'] in by_date]))
    checked_zero = []
    for obligation in zero_dividend_obligations:
        event = obligation['provider_event']
        day,sid = event['date'],event['security_id']
        if day not in by_date:
            continue
        prior_day = assembled['session_dates'][assembled['session_dates'].index(day)-1]
        prior_shares = by_date[prior_day]['shares'] if prior_day in by_date else {}
        records = book.get('dividend_ledger',{}).get('events',{}).values()
        if prior_shares.get(sid,0) or any(record['event']['security_id']==sid
                and record['event']['ex_date']==day and Fraction(record['net'])!=0 for record in records):
            raise ValueError('ZERO_DIVIDEND_ENTITLEMENT_NOT_PROVEN')
        checked_zero.append(obligation)
    save(options.output/'zero_dividend_review.json',dict(obligations=zero_dividend_obligations,
        verified_executed=checked_zero))
    save(options.output/'book.json',book)
    save(options.output/'summary.json',dict(status=book['status'],reason=book.get('reason'),
        completed_sessions=len(book.get('daily_ledger',[])),new_searches=new_count,reused_searches=reused_count,
        input_sha256=digest(options.assembled),prices_sha256=digest(options.prices),
        action_review_sha256=digest(options.action_review) if options.action_review else None,
        gross_dividends_research=options.gross_dividends,execution_inputs_sha256=digest(options.output/'execution_inputs.json'),
        script_sha256=digest(__file__),performance_validated=False,full_bull_bear_validation=False))
    print(json.dumps(dict(status=book['status'],new_searches=new_count,reused_searches=reused_count)),flush=True)


if __name__ == '__main__':
    main()
