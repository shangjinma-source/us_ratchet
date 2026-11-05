"""Independent completed-ledger metrics; never annualize a blocked run."""
import argparse
import json
from datetime import date
from fractions import Fraction as F
from pathlib import Path
from backtest.research_exact_fraction_json import loads


def audit(book, document):
    if book['status'] != 'COMPLETE':
        raise ValueError('COMPLETE_ACCOUNT_REQUIRED')
    days = document['assembled']['session_dates']
    rows = book['daily_ledger']
    if [row['date'] for row in rows] != days[1:]:
        raise ValueError('FULL_WINDOW_REQUIRED')
    initial = F(book['initial_cash'])
    peak = initial
    maximum_drawdown = F(0)
    underwater = longest_underwater = 0
    annual = {}
    year_start = initial
    previous_year = days[0][:4]
    previous_equity = initial
    maximum_weight = F(0)
    maximum_positions = 0
    for row in rows:
        equity = F(row['equity'])
        stock = sum((quantity * F(document['ohlc'][sid][row['date']]['close'])
                     for sid, quantity in row['shares'].items()), F(0))
        rebuilt = F(row['cash']) + stock + F(row['merger_receivable']) + F(row['dividend_receivable'])
        if rebuilt != equity or stock != F(row['stock_value']):
            raise ValueError('EQUITY_RECONCILIATION:' + row['date'])
        if equity < peak:
            underwater += 1
        else:
            underwater = 0
        longest_underwater = max(longest_underwater, underwater)
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, 1 - equity / peak)
        year = row['date'][:4]
        if year != previous_year:
            annual[previous_year] = float(previous_equity / year_start - 1)
            year_start = previous_equity
            previous_year = year
        previous_equity = equity
        maximum_positions = max(maximum_positions, len(row['shares']))
        for sid, quantity in row['shares'].items():
            maximum_weight = max(maximum_weight, quantity * F(document['ohlc'][sid][row['date']]['close']) / equity)
    annual[previous_year] = float(previous_equity / year_start - 1)
    if maximum_drawdown != F(book['maximum_drawdown']):
        raise ValueError('DRAWDOWN_MISMATCH')
    elapsed = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days
    return dict(start=days[0], end=days[-1], initial_cash=float(initial),
                ending_equity=float(previous_equity),
                cagr=float(previous_equity / initial) ** (365.25 / elapsed) - 1,
                maximum_close_drawdown=float(maximum_drawdown),
                annual_returns=annual, longest_underwater_sessions=longest_underwater,
                ending_underwater_sessions=underwater,
                maximum_close_single_position_weight=float(maximum_weight),
                maximum_close_positions=maximum_positions,
                buy_fills=sum(fill['side'] == 'BUY' for fill in book['order_log']),
                sell_fills=sum(fill['side'] == 'SELL' for fill in book['order_log']),
                scope='Full-window close equity; partial years retained; no claim of intraday drawdown or out-of-sample evidence.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('book', type=Path)
    parser.add_argument('inputs', type=Path)
    arguments = parser.parse_args()
    book = loads(arguments.book.read_text(encoding='utf-8'))
    document = loads(arguments.inputs.read_text(encoding='utf-8'))['document']
    print(json.dumps(audit(book, document), indent=2))
