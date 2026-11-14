"""Same submission time with limit-based cash reservations and continuous holdings."""
import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from backtest.research_exact_fraction_json import loads
from scripts.research.algoseek_continuous_execution_probe import read_session
from scripts.research.algoseek_dividend_execution_probe import replay
from scripts.research.limit_reference_comparison import simulate


def execute(cash, holdings, target, sessions, fee, *, start, policy):
    if policy not in ('OPEN', 'LATEST', 'FAVORABLE'):
        raise ValueError('UNKNOWN_REFERENCE_POLICY')
    available, orders, unfilled = cash, [], []
    # Freeze quantities from available cash at submission, before any future fills.
    for symbol in sorted(set(target) | set(holdings)):
        change = target.get(symbol, 0) - holdings.get(symbol, 0)
        if not change:
            continue
        side = 'BUY' if change > 0 else 'SELL'
        data = sessions[symbol]['data']
        opening = simulate(data, side, start, 'OPEN')
        current = simulate(data, side, start, 'LATEST_COMPLETED')
        favorable = current['limit'] < opening['limit'] if side == 'BUY' else current['limit'] > opening['limit']
        choice = current if policy == 'LATEST' or policy == 'FAVORABLE' and favorable else opening
        requested = abs(change)
        quantity = min(requested, max(0, int((available - fee) / choice['limit']))) if side == 'BUY' else requested
        reservation = quantity * choice['limit'] + fee if side == 'BUY' and quantity else 0
        available -= reservation
        order = dict(symbol=symbol, side=side, requested=requested, quantity=quantity,
                     limit=choice['limit'], reference=choice['reference'], reservation=reservation)
        if quantity == 0 or choice['fill'] is None:
            unfilled.append(dict(order, reason='NO_CASH_AT_SUBMISSION' if quantity == 0 else 'LIMIT_NOT_CROSSED'))
        else:
            orders.append(dict(order, **choice['fill']))
    if available < -1e-7:
        raise ValueError('OVER_RESERVED')
    fills = []
    for order in sorted(orders, key=lambda row: (row['minute'], row['side'] != 'BUY', row['symbol'])):
        symbol, quantity, price = order['symbol'], order['quantity'], order['price']
        if order['side'] == 'BUY':
            if price > order['limit']:
                raise ValueError('BUY_LIMIT_VIOLATION')
            cash -= quantity * price + fee
            holdings[symbol] = holdings.get(symbol, 0) + quantity
        else:
            if price < order['limit'] or quantity > holdings.get(symbol, 0):
                raise ValueError('SELL_LIMIT_OR_POSITION_VIOLATION')
            cash += quantity * price - fee
            holdings[symbol] -= quantity
        if cash < -1e-7:
            raise ValueError('NEGATIVE_CASH')
        fills.append(dict(order, filled=quantity, cash_after=cash))
    return cash, fills, unfilled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--book', type=Path, required=True)
    args = parser.parse_args()
    raw = args.book.read_bytes()
    book = loads(raw.decode())
    marks = json.loads((args.directory / 'daily_close_cache.json').read_text())
    days = sorted(marks)
    original = {row['date']: row for row in book['daily_ledger'] if days[0] <= row['date'] <= days[-1]}
    if set(original) != set(days):
        raise ValueError('DAILY_COVERAGE_MISMATCH')
    validation = json.loads((args.directory / 'event_validation.json').read_text())
    if any(not row['status'].startswith('VALID') or row['event']['phase'] != 'OPEN' for row in validation['results']):
        raise ValueError('EVENT_SCOPE_MISMATCH')
    event_days = sorted({row['event']['date'] for row in validation['results']})
    targets = {day: {sid.split(':')[-1].upper(): int(quantity) for sid, quantity in original[day]['shares'].items() if quantity} for day in event_days}
    symbols = sorted(set().union(*(set(target) for target in targets.values())))
    sessions = {day: {symbol: read_session(args.directory, day, symbol) for symbol in symbols} for day in event_days}
    dividends = [row['event'] for row in book['dividend_ledger']['events'].values()]
    results = []
    for start in (60, 150):
        for policy in ('OPEN', 'LATEST', 'FAVORABLE'):
            for fee in (0, 18):
                try:
                    result = replay(days, targets, sessions, marks, original, dividends, policy, policy, fee,
                                    float(book['initial_cash']), executor=partial(execute, start=start, policy=policy))
                    result['status'] = 'COMPLETE_CONDITIONAL_RESEARCH'
                except ValueError as error:
                    if not str(error).startswith('DIVIDEND_COVERAGE_EXTENSION:'):
                        raise
                    result = dict(buy_rule=policy, sell_rule=policy, fee=fee,
                                  status='NEEDS_EXTENDED_DIVIDEND_COVERAGE', reason=str(error))
                result['submission_minute'] = start
                results.append(result)
    output = dict(book_sha256=sha256(raw).hexdigest(),
        source_hashes={day: {symbol: value['sha256'] for symbol, value in values.items()} for day, values in sessions.items()},
        assumptions=['All orders submitted together; buy reservations use limit plus fee, alphabetical priority.',
                     'Same-session future sells and price-improvement refunds do not fund new orders; no automatic retries.',
                     'Targets frozen; inherited dividend coverage checked; gross dividends at payment close.',
                     'Strict minute crossing proxy, not actual bid/ask, queue or auction executions.',
                     '2021-01-04 to 2021-12-01 only; not a full-year or bear-market strategy validation.'], runs=results)
    (args.directory / 'reserved_limit_reference_replay.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in run.items() if key != 'ledger'} for run in results if run['fee']==18], indent=2))


if __name__ == '__main__':
    main()
