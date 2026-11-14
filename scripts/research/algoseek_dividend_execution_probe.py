"""Continuous execution with inherited research dividends; no production writes."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from backtest.research_exact_fraction_json import loads
from scripts.research.algoseek_continuous_execution_probe import read_session, settle


def accrue(events, day, holdings, pending):
    for event in events:
        if event['ex_date'] != day:
            continue
        symbol = event['security_id'].split(':')[-1].upper()
        amount = holdings.get(symbol, 0) * float(Fraction(event['amount_per_share'])) * (1 - float(Fraction(event['withholding_rate'])))
        pending.append(dict(event_id=event['event_id'], amount=amount, payment_date=event['payment_date']))


def pay(day, pending):
    paid = sum(item['amount'] for item in pending if item['payment_date'] and item['payment_date'] <= day)
    pending[:] = [item for item in pending if not item['payment_date'] or item['payment_date'] > day]
    return paid


def replay(days, targets, sessions, marks, original, dividends, buy_rule, sell_rule, fee, initial_cash):
    cash, holdings, pending, ledger = initial_cash, {}, [], []
    peak, drawdown, paid_total = initial_cash, 0.0, 0.0
    prior_original = {}
    for day in days:
        # Inherit source coverage only when every opening exposure existed in the old book.
        for symbol, quantity in holdings.items():
            if quantity and not prior_original.get('research:security:' + symbol.lower(), 0):
                raise ValueError('DIVIDEND_COVERAGE_EXTENSION:' + day + ':' + symbol)
        accrue(dividends, day, holdings, pending)
        if day == '2021-07-20':
            holdings['NVDA'] = holdings.get('NVDA', 0) * 4
        fills, unfilled = [], []
        if day in targets:
            orders = []
            for symbol in sorted(set(targets[day]) | set(holdings)):
                change = targets[day].get(symbol, 0) - holdings.get(symbol, 0)
                if not change:
                    continue
                side = 'BUY' if change > 0 else 'SELL'
                rule = buy_rule if side == 'BUY' else sell_rule
                arm = next(item for item in sessions[day][symbol]['checked'][side]['arms'] if item['name'] == rule)
                order = dict(symbol=symbol, side=side, quantity=abs(change), rule=rule)
                if arm['fill']:
                    orders.append(dict(order, **arm['fill']))
                else:
                    unfilled.append(order)
            cash, fills = settle(cash, holdings, orders, fee)
        payment = pay(day, pending)
        cash += payment
        paid_total += payment
        receivable = sum(item['amount'] for item in pending)
        equity = cash + receivable + sum(quantity * marks[day][symbol]['price'] for symbol, quantity in holdings.items() if quantity)
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
        ledger.append(dict(date=day, cash=cash, holdings=dict(holdings), dividend_paid=payment,
                           dividend_receivable=receivable, equity=equity, fills=fills, unfilled=unfilled))
        prior_original = original[day]['shares']
    return dict(buy_rule=buy_rule, sell_rule=sell_rule, fee=fee, return_pct=(equity / initial_cash - 1) * 100,
                maximum_drawdown_pct=drawdown * 100, dividends_paid=paid_total,
                ending_dividend_receivable=receivable, ledger=ledger)


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
        raise ValueError('DAILY_SESSION_COVERAGE_MISMATCH')
    validation = json.loads((args.directory / 'event_validation.json').read_text())
    if any(item['event']['phase'] != 'OPEN' or not item['status'].startswith('VALID') for item in validation['results']):
        raise ValueError('INVALID_EVENT_SCOPE')
    event_days = sorted({item['event']['date'] for item in validation['results']})
    targets = {day: {sid.split(':')[-1].upper(): int(quantity) for sid, quantity in original[day]['shares'].items() if quantity} for day in event_days}
    symbols = sorted(set().union(*(set(target) for target in targets.values())))
    sessions = {day: {symbol: read_session(args.directory, day, symbol) for symbol in symbols} for day in event_days}
    dividends = [record['event'] for record in book['dividend_ledger']['events'].values()]
    runs = [replay(days, targets, sessions, marks, original, dividends, buy, sell, fee, float(book['initial_cash']))
            for fee in (0, 18) for buy, sell in [('OPEN_REFERENCE', 'OPEN_REFERENCE'), ('1030', 'OPEN_REFERENCE'),
                                               ('1200', 'OPEN_REFERENCE'), ('1200', '1030'), ('1200', '1200')]]
    result = dict(scope='2021-01-04 to 2021-12-01 frozen target, inherited gross research dividend catalog',
                  book_sha256=sha256(raw).hexdigest(), marks_sha256=sha256((args.directory / 'daily_close_cache.json').read_bytes()).hexdigest(),
                  limitations=['Original dividend source coverage inherited, not independently recertified.',
                               'Gross dividends paid at supplied payment session close, not actual broker net credits.',
                               'Frozen targets, strict crossing fill proxy, no queue or volume allocation.',
                               'First-trade/final-minute marks, not official opening/closing auction fills.',
                               'Partial 2021 sample, no 2022 bear market or annualized performance claim.'], runs=runs)
    (args.directory / 'continuous_dividend_replay.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in run.items() if key != 'ledger'} for run in runs], indent=2))


if __name__ == '__main__':
    main()
