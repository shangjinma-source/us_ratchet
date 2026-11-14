"""Frozen two-session cash replay. Hypothetical fills, not production acceptance."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.research.roa_entry_timing_event_probe import analyze, money

ARMS = ('OPEN_REFERENCE', 'BUY_1030', 'BUY_1200', 'OPEN_MINUS_1PCT')


def simulate(days, quantities, capital, arm, fee, touch=False, sell_start=1, reprice_unfilled=False):
    if sell_start not in (1, 60, 150):
        raise ValueError('UNSUPPORTED_SELL_TIME')
    if reprice_unfilled and sell_start != 1:
        raise ValueError('REPRICE_REQUIRES_OPEN_SELL')
    cash = capital
    holdings = {ticker: 0 for ticker in quantities}
    orders, fills, rejected = {}, [], []
    equity = [capital]
    minute_cash = []
    repricings = []
    submitted = False
    start = {'OPEN_REFERENCE': 1, 'OPEN_MINUS_1PCT': 1, 'BUY_1030': 60, 'BUY_1200': 150}[arm]
    for day_index, day in enumerate(days):
        orders = {}
        submitted = False
        for minute in range(390):
            submit_minute = start if day_index == 0 else sell_start
            if minute == submit_minute and not submitted:
                # Fixed ticker priority, with all outstanding orders fully reserved.
                remaining = cash
                for ticker in sorted(quantities):
                    quantity = quantities[ticker] if day_index == 0 else holdings[ticker]
                    if not quantity:
                        continue
                    bars = day[ticker]
                    reference = bars[0][0] if submit_minute == 1 else bars[(submit_minute - 1) * 60][3]
                    limit = money(reference * (.99 if day_index == 0 and arm == 'OPEN_MINUS_1PCT' else 1))
                    reserved = quantity * limit + fee
                    if day_index == 0 and reserved > remaining + 1e-8:
                        rejected.append({'ticker': ticker, 'reason': 'INSUFFICIENT_CASH'})
                        continue
                    if day_index == 0:
                        remaining -= reserved
                    orders[ticker] = (quantity, limit)
                submitted = True
            if day_index == 1 and reprice_unfilled and minute == 15:
                for ticker, (quantity, old_limit) in list(orders.items()):
                    new_limit = money(day[ticker][14 * 60][3])
                    orders[ticker] = (quantity, new_limit)
                    repricings.append(dict(ticker=ticker, minute=minute, old_limit=old_limit,
                                           new_limit=new_limit, quantity=quantity))
            if minute < 385:
                for ticker, (quantity, limit) in list(orders.items()):
                    o, high, low, close, volume = day[ticker][minute * 60]
                    crossed = ((low <= limit if touch else low < limit) if day_index == 0
                               else (high >= limit if touch else high > limit))
                    if not crossed or volume <= 0:
                        continue
                    # Crossing is an assumed execution model, not evidence of queue priority.
                    price = min(o, limit) if day_index == 0 else max(o, limit)
                    price = money(price)
                    side = 'BUY' if day_index == 0 else 'SELL'
                    cash = cash - quantity * price - fee if side == 'BUY' else cash + quantity * price - fee
                    if cash < -1e-6:
                        raise AssertionError('NEGATIVE_CASH')
                    holdings[ticker] = quantity if side == 'BUY' else 0
                    fills.append(dict(ticker=ticker, side=side, quantity=quantity, price=price,
                                      day_index=day_index, minute=minute, fee=fee))
                    del orders[ticker]
            equity.append(cash + sum(quantity * day[ticker][minute * 60][3]
                                     for ticker, quantity in holdings.items()))
            minute_cash.append(cash)
        # Unfilled day orders expire. No automatic next-session replacement.
    peak = equity[0]
    drawdown = 0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    bought = {fill['ticker'] for fill in fills if fill['side'] == 'BUY'}
    return dict(arm=arm, sell_start=sell_start, fee_per_order=fee, fill_model='TOUCH' if touch else 'STRICT_CROSS',
                initial_capital=capital, ending_equity=equity[-1], ending_cash=cash,
                net_profit=equity[-1] - capital, return_pct=100 * (equity[-1] / capital - 1),
                sampled_minute_close_drawdown_pct=100 * drawdown,
                average_cash_pct=100 * sum(minute_cash) / len(minute_cash) / capital,
                buy_count=len(bought), unbought=sorted(set(quantities) - bought),
                remaining_holdings={ticker: q for ticker, q in holdings.items() if q},
                fees=fee * len(fills), fills=fills, cash_rejected=rejected,
                reprice_unfilled=reprice_unfilled, repricings=repricings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--compare-exit-timing', action='store_true',
                        help='Compare frozen exits on the actual Nov 6/9 signal dates.')
    args = parser.parse_args()
    report_bytes = (args.directory / 'report.json').read_bytes()
    report = json.loads(report_bytes)
    cases = {(row['session'], row['ticker']): row for row in report['cases']}
    quantities, days, hashes = {}, [{}, {}], {}
    for ticker in sorted({row['ticker'] for row in report['cases']}):
        dates = ('2026-11-06', '2026-11-09')
        if any(cases[(day, ticker)]['status'] != 'OBSERVED_PRICE_PROXY' for day in dates):
            continue
        quantities[ticker] = cases[(dates[0], ticker)]['quantity']
        for index, date in enumerate(dates):
            path = args.directory / f'{ticker}_{date}.raw.json'
            raw = path.read_bytes()
            digest = sha256(raw).hexdigest()
            if digest != cases[(date, ticker)]['source_sha256']:
                raise ValueError('RAW_SOURCE_CHANGED')
            bars, missing, symbol = analyze(raw, date)
            if missing or symbol != ticker:
                raise ValueError('UNUSABLE_SESSION')
            days[index][ticker] = bars
            hashes[path.name] = digest
    # Known at the first opening, identical across arms and both fee scenarios.
    capital = money(sum(q * money(days[0][ticker][0][0]) for ticker, q in quantities.items()) + 18 * len(quantities))
    exits = ((1, False), (60, False), (150, False), (1, True)) if args.compare_exit_timing else ((1, False),)
    results = [simulate(days, quantities, capital, arm, fee, touch, sell_start, reprice)
               for fee in (0, 18) for touch in (False, True) for arm in ARMS
               for sell_start, reprice in exits]
    output = dict(status='TWO_SESSION_HYPOTHETICAL_ACCOUNT_REPLAY', input_report_sha256=sha256(report_bytes).hexdigest(),
                  sources=hashes, excluded=['ODFL: incomplete minute coverage'], results=results,
                  assumptions=['First-minute observations, not official opening-auction executions.',
                    'Opening orders submitted 09:31; delays submitted 10:30/12:00 using previous completed minute close.',
                    'All orders expire 15:55; default sell uses next-session first-minute open at 09:31; exit_policies records overrides.',
                    'Fixed target shares and fully reserved cash; no borrowing, reinvestment or next-day replacement.',
                    'Fees are sensitivity scenarios, not inferred broker charges. No spread/queue/liquidity guarantee.',
                    'Drawdown uses minute-close marks over two sessions only; not full-cycle maximum drawdown.',
                    'Separate strategy stop rules are not modeled in this execution-only event replay.'])
    output['exit_policies'] = list(exits)
    output['assumptions'].append('Optional exits use completed prior-minute prices; one reprice at 09:45 assumes immediate cancellation acknowledgement.')
    output_name = 'actual_event_exit_replay.json' if args.compare_exit_timing else 'account_replay.json'
    (args.directory / output_name).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{k: value for k, value in row.items() if k not in ('fills',)}
                      for row in results if row['fill_model'] == 'STRICT_CROSS'], ensure_ascii=False))


if __name__ == '__main__':
    main()
