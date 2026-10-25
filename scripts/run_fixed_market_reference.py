"""Four registered price-only ETF references; no search, network or account IO.

Use --register before --run. Both modes are create-only. The existing next-open
kernel is reused unchanged; a separate one-purchase formula reviews every row.
"""
import argparse
import ast
from datetime import date, datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.current_quantity_v2_next_open_book import run_next_open_book

INITIAL_CASH = Fraction(20000)
FEE_RATE = Fraction(1, 10000)
SLIPPAGE = Fraction(10, 10000)
SYMBOLS = ('QQQ', 'SPY')
CAPTURE = 'data/cache/research/current_raw_capture_20261014_v1'
WINDOWS = {
    'earlier': dict(book='tmp/capped_earlier_reselection_20261024_v1/cap50_exit20/outcome.json',
                    registration='tmp/capped_earlier_reselection_20261024_v1/registration.json',
                    start='2023-12-29', first_open='2024-01-02', end='2025-07-30', observations=395),
    'later': dict(book='tmp/capped_actual_reselection_20261024_v2/outcome.json',
                  registration='tmp/capped_actual_reselection_20261024_v2/registration.json',
                  start='2025-07-31', first_open='2025-08-01', end='2026-07-30', observations=250),
}
RULES = dict(initial_cash='20000', fee_bps='1', slippage_bps='10', external_flows='0',
    request='floor(initial_cash / (initial_decision_close * (1 + fee_rate)))',
    execution='Only first next-open order; original kernel adverse slippage and integer cash rationing',
    later_orders=False, residual_cash_interest=False, terminal_liquidation=False,
    ordinary_dividends_included=False, adjusted_close_used=False, monthly_50_percent_cap=False,
    returned_nondividend_action='STOP; do not guess split or other action accounting',
    scope='CONDITIONAL_PRICE_RETURN_REFERENCE_NOT_TOTAL_RETURN_OR_OOS',
    maximum_books=4, maximum_search_calls=0, network_calls=0, automatic_retry=False,
    maximum_runtime_seconds=1800)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    require(not isinstance(value, bool), 'BOOLEAN_AMOUNT')
    return Fraction(str(value))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def source_closure():
    """Pin project imports of the unchanged execution kernel, not cache files."""
    pending = ['backtest/current_quantity_v2_next_open_book.py']
    found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        tree = ast.parse((ROOT / name).read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                candidate = module.replace('.', '/') + '.py'
                if (ROOT / candidate).is_file():
                    pending.append(candidate)
    return sorted(found)


def registered_source_names():
    names = set(source_closure()) | {'scripts/run_fixed_market_reference.py', 'tests/test_fixed_market_reference.py'}
    for specification in WINDOWS.values():
        names.update([specification['book'], specification['registration']])
    for symbol in SYMBOLS:
        names.update(CAPTURE + '/' + symbol + '.' + suffix
                     for suffix in ('response.bin', 'receipt.json', 'decoded.json'))
    return names


def load_market(symbol):
    require(symbol in SYMBOLS, 'UNREGISTERED_SYMBOL')
    base = ROOT / CAPTURE
    raw_path = base / (symbol + '.response.bin')
    receipt = read_json(base / (symbol + '.receipt.json'))
    raw = raw_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == receipt['raw_sha256'], 'RAW_RECEIPT_HASH_MISMATCH')
    require(receipt['ticker'] == symbol and receipt['http_status'] == 200 and not receipt['body_truncated'],
            'INVALID_CAPTURE_RECEIPT')
    payload = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
    results = payload['chart']['result']
    require(payload['chart'].get('error') is None and len(results) == 1, 'INVALID_PROVIDER_RESULT')
    result = results[0]
    require(result['meta']['symbol'] == symbol and result['meta']['instrumentType'] == 'ETF'
            and result['meta']['currency'] == 'USD', 'ETF_IDENTITY_MISMATCH')
    times = result['timestamp']
    quotes = result['indicators']['quote'][0]
    require(times == sorted(set(times)), 'TIMESTAMPS_NOT_UNIQUE_SORTED')
    require(all(len(quotes[key]) == len(times) for key in ('open', 'high', 'low', 'close')),
            'OHLC_LENGTH_MISMATCH')
    rows = {}
    for index, timestamp in enumerate(times):
        day = datetime.fromtimestamp(timestamp, ZoneInfo('America/New_York')).date().isoformat()
        require(day not in rows, 'DUPLICATE_PROVIDER_SESSION')
        bar = {key: number(quotes[key][index]) for key in ('open', 'high', 'low', 'close')}
        require(bar['low'] > 0 and bar['low'] <= min(bar['open'], bar['close'])
                <= max(bar['open'], bar['close']) <= bar['high'], 'INVALID_PROVIDER_OHLC')
        rows[day] = {key: str(value) for key, value in bar.items()}
    events = []
    for kind, values in result.get('events', {}).items():
        for event in values.values():
            day = datetime.fromtimestamp(event['date'], ZoneInfo('America/New_York')).date().isoformat()
            events.append(dict(kind=kind, date=day, amount=str(event.get('amount', ''))))
    return dict(rows=rows, events=sorted(events, key=lambda item: (item['date'], item['kind'])))


def window_market(market, calendar):
    require(calendar == sorted(set(calendar)) and len(calendar) >= 2, 'INVALID_CALENDAR')
    require(all(day in market['rows'] for day in calendar), 'MISSING_REQUIRED_SESSION')
    events = [item for item in market['events'] if calendar[0] < item['date'] <= calendar[-1]]
    require(all(item['kind'] == 'dividends' for item in events), 'UNSUPPORTED_RETURNED_ACTION')
    return {day: market['rows'][day] for day in calendar}, events


def load_window(label):
    specification = WINDOWS[label]
    book = read_json(ROOT / specification['book'])
    require(book['status'] == 'COMPLETE' and number(book['external_flows']) == 0,
            'INCOMPLETE_OR_FLOW_BASELINE')
    first = book['selection_account_states'][0]
    require(first['decision_date'] == specification['start']
            and first['account_state']['asof'] == specification['start']
            and number(first['account_state']['cash']) == INITIAL_CASH
            and not any(first['account_state']['shares'].values()), 'INITIAL_ACCOUNT_MISMATCH')
    calendar = [specification['start']] + [row['date'] for row in book['daily_ledger']]
    require(calendar == sorted(set(calendar)) and calendar[1] == specification['first_open']
            and calendar[-1] == specification['end']
            and len(calendar) == specification['observations'] + 1, 'WINDOW_CALENDAR_MISMATCH')
    require(number(book['fee_bps']) == 1 and number(book['slippage_bps']) == 10, 'COST_MISMATCH')
    require(book['terminal_state_valuation_synchronized'] is True
            and book['final_wealth_basis'] == 'REGULAR_CLOSE_CURRENT_STATE'
            and book['last_valued_date'] == calendar[-1] and book['state_date'] == calendar[-1],
            'BASELINE_TERMINAL_NOT_SYNCHRONIZED')
    return book, calendar


def metrics(calendar, equities):
    require(len(equities) == len(calendar) and equities[0] == INITIAL_CASH, 'METRIC_CALENDAR_MISMATCH')
    peak = equities[0]
    worst = Fraction(0)
    for value in equities:
        require(value >= 0, 'NEGATIVE_EQUITY')
        peak = max(peak, value)
        worst = max(worst, 1 - value / peak)
    total_return = equities[-1] / equities[0] - 1
    days = (date.fromisoformat(calendar[-1]) - date.fromisoformat(calendar[0])).days
    require(days > 0, 'EMPTY_METRIC_INTERVAL')
    return dict(start=calendar[0], first_open=calendar[1], end=calendar[-1], calendar_days=days,
        close_observations=len(calendar) - 1, final_equity=str(equities[-1]),
        total_return=str(total_return), maximum_close_drawdown=str(worst),
        return_percent=float(total_return * 100), maximum_close_drawdown_percent=float(worst * 100),
        cagr_percent=(math.pow(float(1 + total_return), 365.25 / days) - 1) * 100)


def execute_reference(symbol, calendar, prices):
    decision_close = number(prices[calendar[0]]['close'])
    requested = int(INITIAL_CASH // (decision_close * (1 + FEE_RATE)))
    sid = 'reference:' + symbol
    orders = [dict(id='fixed-market:' + symbol + ':' + calendar[0], security_id=sid,
        side='BUY', quantity=requested, decision_date=calendar[0], active_date=calendar[1],
        decision_mark=str(decision_close))] if requested else []
    book = run_next_open_book(session_dates=calendar, orders=orders, ohlc={sid: prices},
        initial_cash='20000', fee_bps='1', slippage_bps='10', account_model='FIXED_SINGLE_ETF_REFERENCE')
    require(book['status'] == 'COMPLETE' and book['terminal_state_valuation_synchronized'] is True,
            'REFERENCE_KERNEL_INCOMPLETE')
    summary = metrics(calendar, [INITIAL_CASH] + [number(row['equity']) for row in book['daily_ledger']])
    review = review_reference(symbol, calendar, prices, book, summary)
    return dict(requested_quantity=requested, outcome=book, metrics=summary, independent_formula_review=review)


def review_reference(symbol, calendar, prices, book, summary):
    """Independent one-fill formula, no call to the book or metrics functions."""
    sid = 'reference:' + symbol
    requested = int(INITIAL_CASH / (number(prices[calendar[0]]['close']) * Fraction(10001, 10000)))
    fill_price = number(prices[calendar[1]]['open']) * Fraction(1001, 1000)
    filled = min(requested, int(INITIAL_CASH / (fill_price * Fraction(10001, 10000))))
    fee = filled * fill_price / 10000
    cash = INITIAL_CASH - filled * fill_price - fee
    fills = [row for row in book['order_log'] if row.get('event') == 'ASSUMED_NEXT_OPEN_FILLED']
    require(len(fills) == (1 if filled else 0), 'FORMULA_FILL_COUNT')
    if filled:
        fill = fills[0]
        require(fill['date'] == calendar[1] and fill['side'] == 'BUY' and fill['security_id'] == sid
                and fill['quantity'] == filled and number(fill['price']) == fill_price
                and number(fill['fee']) == fee, 'FORMULA_FILL_MISMATCH')
    require([row['date'] for row in book['daily_ledger']] == calendar[1:], 'FORMULA_SESSION_MISMATCH')
    values = [INITIAL_CASH]
    for row in book['daily_ledger']:
        equity = cash + filled * number(prices[row['date']]['close'])
        require(number(row['cash']) == cash and row['shares'].get(sid, 0) == filled
                and not any(quantity for other, quantity in row['shares'].items() if other != sid)
                and number(row['stock_value']) == equity - cash and number(row['equity']) == equity
                and number(row['external_flow']) == 0 and number(row['receivable']) == 0
                and number(row['distribution_entitlement_value']) == 0
                and number(row['nontradable_entitlement_value']) == 0, 'FORMULA_DAILY_ACCOUNT_MISMATCH')
        values.append(equity)
    drawdown = max(1 - value / max(values[:index + 1]) for index, value in enumerate(values))
    require(number(summary['total_return']) == values[-1] / INITIAL_CASH - 1
            and number(summary['maximum_close_drawdown']) == drawdown
            and number(book['fees']) == fee and number(book['cash']) == cash
            and book['shares'].get(sid, 0) == filled, 'FORMULA_SUMMARY_MISMATCH')
    return dict(status='PASS_EXACT_SINGLE_PURCHASE_FORMULA', reviewed_rows=len(calendar) - 1,
        filled_quantity=filled, fill_price=str(fill_price), fee=str(fee), residual_cash=str(cash),
        independent_of_execution_kernel=True, maximum_drawdown_includes_initial_cash=True)


def build_registration():
    names = registered_source_names()
    windows = {}
    for label, specification in WINDOWS.items():
        _, calendar = load_window(label)
        windows[label] = dict(specification, calendar=calendar)
    markets = {}
    for symbol in SYMBOLS:
        market = load_market(symbol)
        markets[symbol] = {}
        for label, specification in windows.items():
            _, events = window_market(market, specification['calendar'])
            markets[symbol][label] = dict(ordinary_dividends_ignored=events,
                                          ignored_dividend_count=len(events), adjusted_close_used=False)
    pins = {name: digest(ROOT / name) for name in sorted(names)}
    baseline_pin_review = {}
    for label, specification in WINDOWS.items():
        old = read_json(ROOT / specification['registration'])
        old_pins = {name.replace('\\', '/'): value for name, value in old['source_sha256'].items()}
        for name in ['backtest/current_quantity_v2_next_open_book.py'] + [CAPTURE + '/' + symbol + '.response.bin' for symbol in SYMBOLS]:
            require(old_pins.get(name) == pins[name], 'SOURCE_DIFFERS_FROM_BASELINE_REGISTRATION:' + name)
        present_helpers = [name for name in source_closure() if name in old_pins]
        for name in present_helpers:
            require(old_pins[name] == pins[name], 'RECORDED_HELPER_SOURCE_CHANGED:' + name)
        baseline_pin_review[label] = dict(kernel_and_etf_raw_match=True,
            matching_recorded_modules=present_helpers,
            helpers_pinned_now_not_in_baseline_direct_map=[name for name in source_closure() if name not in old_pins],
            corporate_action_helpers_used=False)
    return dict(schema='FIXED_MARKET_REFERENCE_REGISTRATION_V1', created_at_utc=datetime.now(timezone.utc).isoformat(),
        rules=RULES, windows=windows, markets=markets, source_pins=pins, baseline_pin_review=baseline_pin_review, economic_books_run=0,
        independent_oos=False, point_in_time_certified=False, automatic_production_adoption=False)


def verify_pins(registration):
    require(registration['schema'] == 'FIXED_MARKET_REFERENCE_REGISTRATION_V1'
            and registration['rules'] == RULES and set(registration['windows']) == set(WINDOWS)
            and set(registration['markets']) == set(SYMBOLS), 'REGISTRATION_RULES_CHANGED')
    require(set(registration['source_pins']) == registered_source_names(), 'REGISTERED_SOURCE_SET_CHANGED')
    for name, expected in registration['source_pins'].items():
        require(digest(ROOT / name) == expected, 'REGISTERED_SOURCE_CHANGED:' + name)


def run_registered(output):
    registration_path = output / 'registration.json'
    registration = read_json(registration_path)
    registration_sha = digest(registration_path)
    verify_pins(registration)
    started = datetime.now(timezone.utc)
    save_new(output / 'started.json', dict(started_at_utc=started.isoformat(), registration_sha256=registration_sha))
    try:
        report = dict(schema='FIXED_MARKET_REFERENCE_RESULTS_V1', registration_sha256=registration_sha,
            source_pins=registration['source_pins'], rules=RULES, windows={}, independent_oos=False,
            point_in_time_certified=False, optimization_calls=0, network_calls=0, economic_books_run=0)
        markets = {symbol: load_market(symbol) for symbol in SYMBOLS}
        for label in WINDOWS:
            baseline, calendar = load_window(label)
            require(calendar == registration['windows'][label]['calendar'], 'REGISTERED_CALENDAR_CHANGED')
            baseline_metrics = metrics(calendar, [INITIAL_CASH] + [number(row['equity']) for row in baseline['daily_ledger']])
            require(number(baseline_metrics['total_return']) == number(baseline['total_return'])
                    and number(baseline_metrics['maximum_close_drawdown']) == number(baseline['drawdown']['maximum_close_drawdown']),
                    'SAVED_BASELINE_METRICS_DO_NOT_RECONCILE')
            group = dict(strategy=baseline_metrics, references={})
            for symbol in SYMBOLS:
                require((datetime.now(timezone.utc) - started).total_seconds() < RULES['maximum_runtime_seconds'], 'RUNTIME_BUDGET')
                prices, events = window_market(markets[symbol], calendar)
                require(events == registration['markets'][symbol][label]['ordinary_dividends_ignored'], 'REGISTERED_EVENTS_CHANGED')
                result = execute_reference(symbol, calendar, prices)
                filename = label + '-' + symbol + '.json'
                save_new(output / filename, result)
                group['references'][symbol] = dict(metrics=result['metrics'],
                    independent_formula_review=result['independent_formula_review'],
                    ignored_dividend_count=len(events), outcome_path=filename, outcome_sha256=digest(output / filename))
                report['economic_books_run'] += 1
            report['windows'][label] = group
        verify_pins(registration)
        require(digest(registration_path) == registration_sha, 'REGISTRATION_CHANGED_DURING_RUN')
        require(report['economic_books_run'] == RULES['maximum_books'], 'BOOK_COUNT_MISMATCH')
        save_new(output / 'report.json', report)
        save_new(output / 'terminal.json', dict(status='COMPLETE_FOUR_REFERENCES_FORMULA_REVIEWED',
            report_sha256=digest(output / 'report.json'), elapsed_seconds=(datetime.now(timezone.utc) - started).total_seconds(),
            economic_books_run=4, optimization_calls=0, network_calls=0, production_changes=False))
        return report
    except Exception as error:
        save_new(output / 'terminal.json', dict(status='FAILED_NO_AUTOMATIC_RETRY', reason=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--register', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    require(output.is_relative_to(ROOT / 'tmp'), 'OUTPUT_MUST_BE_UNDER_LOCAL_TMP')
    if arguments.register:
        registration = build_registration()
        output.mkdir(parents=True, exist_ok=False)
        save_new(output / 'registration.json', registration)
        print('REGISTERED_FOUR_BOOKS_NO_ECONOMIC_RUN')
    else:
        run_registered(output)
        print('COMPLETE_FOUR_REFERENCES_FORMULA_REVIEWED')


if __name__ == '__main__':
    main()
