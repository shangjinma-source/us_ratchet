"""Frozen 2021 targets, shared cash, chronological fills; price-only research."""
import argparse
import csv
from datetime import datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo

from backtest.research_exact_fraction_json import loads
from scripts.research.probe_aapl_historical_execution_events import inspect


def read_session(directory, day, symbol):
    with zipfile.ZipFile(directory / (day.replace('-', '') + '.zip')) as archive:
        names = [name for name in archive.namelist() if name.endswith('/' + symbol + '.csv')]
        if len(names) != 1:
            raise ValueError('MISSING_OR_DUPLICATE_SECURITY')
        raw = archive.read(names[0])
    data = dict(s='ok', t=[], o=[], h=[], l=[], c=[], v=[])
    for row in csv.DictReader(io.StringIO(raw.decode())):
        if not '09:30' <= row['TimeBarStart'] < '16:00':
            continue
        if row['Ticker'] != symbol or row['Date'] != day.replace('-', ''):
            raise ValueError('IDENTITY_MISMATCH')
        stamp = datetime.fromisoformat(day + 'T' + row['TimeBarStart']).replace(tzinfo=ZoneInfo('America/New_York'))
        data['t'].append(int(stamp.timestamp()))
        columns = [('o', 'FirstTradePrice'), ('h', 'HighTradePrice'), ('l', 'LowTradePrice'), ('c', 'LastTradePrice')]
        empty = all(not row[column] for _, column in columns)
        if empty and not all(row[column] == '0' for column in ('Volume', 'FinraVolume', 'TotalTrades')):
            raise ValueError('UNEXPLAINED_EMPTY_TRADE')
        for key, column in columns:
            data[key].append(None if empty else float(row[column]))
        data['v'].append(float(row['Volume']))
    payload = json.dumps(data).encode()
    checked = {side: inspect(payload, dict(date=day, side=side), allow_no_trade=True) for side in ('BUY', 'SELL')}
    return dict(close=data['c'][-1], checked=checked, sha256=sha256(raw).hexdigest())


def settle(cash, holdings, orders, fee):
    """Never spend later sales; same-minute buys precede sales conservatively."""
    records = []
    for order in sorted(orders, key=lambda item: (item['minute'], item['side'] != 'BUY', item['symbol'])):
        symbol, side, price, requested = [order[key] for key in ('symbol', 'side', 'price', 'quantity')]
        quantity = min(requested, max(0, int((cash - fee) / price))) if side == 'BUY' else requested
        if side == 'SELL' and quantity > holdings.get(symbol, 0):
            raise ValueError('SELL_EXCEEDS_HOLDINGS')
        if quantity:
            cash += quantity * price - fee if side == 'SELL' else -quantity * price - fee
            holdings[symbol] = holdings.get(symbol, 0) + (quantity if side == 'BUY' else -quantity)
        if cash < -1e-8 or any(quantity < 0 for quantity in holdings.values()):
            raise ValueError('ACCOUNT_INVARIANT')
        records.append(dict(order, filled=quantity, cash_after=cash))
    return cash, records


def replay(sessions, buy_rule, sell_rule, fee, initial_cash):
    cash, holdings, records = initial_cash, {}, []
    previous = '2021-01-01'
    for day, target, prices in sessions:
        if previous < '2021-07-20' <= day:
            holdings['NVDA'] = holdings.get('NVDA', 0) * 4
        orders, unfilled = [], []
        for symbol in sorted(set(target) | set(holdings)):
            change = target.get(symbol, 0) - holdings.get(symbol, 0)
            if not change:
                continue
            side = 'BUY' if change > 0 else 'SELL'
            rule = buy_rule if side == 'BUY' else sell_rule
            arm = next(arm for arm in prices[symbol]['checked'][side]['arms'] if arm['name'] == rule)
            order = dict(symbol=symbol, side=side, quantity=abs(change), rule=rule)
            if arm['fill']:
                orders.append(dict(order, **arm['fill']))
            else:
                unfilled.append(dict(order, reason='LIMIT_NOT_CROSSED'))
        cash, fills = settle(cash, holdings, orders, fee)
        equity = cash + sum(quantity * prices[symbol]['close'] for symbol, quantity in holdings.items() if quantity)
        records.append(dict(date=day, cash=cash, holdings=dict(holdings), equity=equity, fills=fills, unfilled=unfilled))
        previous = day
    return dict(buy_rule=buy_rule, sell_rule=sell_rule, fee=fee, terminal_equity=equity,
                price_only_return_pct=(equity / initial_cash - 1) * 100, records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--book', type=Path, required=True)
    args = parser.parse_args()
    raw = args.book.read_bytes()
    book = loads(raw.decode())
    validation = json.loads((args.directory / 'event_validation.json').read_text())
    if any(item['event']['phase'] != 'OPEN' or not item['status'].startswith('VALID') for item in validation['results']):
        raise ValueError('UNVALIDATED_OR_NON_OPEN_EVENT')
    days = sorted({item['event']['date'] for item in validation['results']})
    if len(days) != 12 or any(not day.startswith('2021') for day in days):
        raise ValueError('UNEXPECTED_EVENT_SCOPE')
    ledgers = {row['date']: row for row in book['daily_ledger']}
    targets = {day: {sid.split(':')[-1].upper(): int(quantity) for sid, quantity in ledgers[day]['shares'].items() if quantity} for day in days}
    symbols = sorted(set().union(*(set(target) for target in targets.values())))
    sessions = [(day, targets[day], {symbol: read_session(args.directory, day, symbol) for symbol in symbols}) for day in days]
    runs = [replay(sessions, buy, sell, fee, float(book['initial_cash'])) for fee in (0, 18)
            for buy, sell in [('OPEN_REFERENCE', 'OPEN_REFERENCE'), ('1030', 'OPEN_REFERENCE'),
                              ('1200', 'OPEN_REFERENCE'), ('1200', '1030'), ('1200', '1200')]]
    output = dict(scope='2021-01-04 through 2021-12-01, frozen monthly targets, price-only shared account',
        book_sha256=sha256(raw).hexdigest(), source_hashes={day: {symbol: data['sha256'] for symbol, data in prices.items()} for day, _, prices in sessions},
        limitations=['No dividends: diagnostic price-only result, not total strategy return.',
                     'No intervening-day valuation: no annual return or maximum drawdown claim.',
                     'Frozen original end-session targets, no new signals or equity-based resizing.',
                     'Same-minute buys before sells; cash shortages floor shares, no retry that day.',
                     'Raw first-trade reference is not official opening-auction price.',
                     'Strict minute crossing proxy, no queue, volume allocation, or partial-fill simulation.',
                     'No production or real-account writes; 2022 bear market not covered.'], runs=runs)
    (args.directory / 'continuous_portfolio_price_only.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in run.items() if key != 'records'} for run in runs], indent=2))


if __name__ == '__main__':
    main()
