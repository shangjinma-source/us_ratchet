"""Audit saved next-open books for cash recycling and exit-price gaps.

Read-only accounting, not a delayed-settlement or limit-order counterfactual.
No optimizer, market connection, account mutation or return extrapolation.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path


def audit_execution(book):
    if book['status'] != 'COMPLETE' or F(book['external_flows']) != 0:
        raise ValueError('Complete zero-external-flow book required')
    initial = book['selection_account_states'][0]['account_state']
    if any(initial['shares'].values()):
        raise ValueError('All-cash initial account required')
    cash = F(initial['cash'])
    if cash <= 0:
        raise ValueError('Positive initial cash required')
    rows, audits = book['daily_ledger'], book['provider_audit']
    if not rows or len(rows) != len(audits):
        raise ValueError('Daily audit coverage required')
    dates = [row['date'] for row in rows]
    if dates != sorted(set(dates)) or dates[0] <= initial['asof']:
        raise ValueError('Strictly ordered daily ledger required')
    fills_by_day = defaultdict(list)
    unique = set()
    for fill in book['order_log']:
        if fill['event'] != 'ASSUMED_NEXT_OPEN_FILLED':
            continue
        key = fill['date'], fill['id']
        if fill['date'] not in dates or key in unique:
            raise ValueError('Fill date or duplicate fill invalid')
        unique.add(key)
        fills_by_day[fill['date']].append(fill)
    names = {quote['security_id']: quote['ticker'] for state in book['selection_account_states']
             for quote in state['valuation_quotes']}
    funding, exits = [], []
    rebased_action_exits, buy_days, fill_count = 0, 0, 0
    total_buys, total_sale_dependency, total_fees = F(0), F(0), F(0)
    slippage = F(book['slippage_bps']) / 10000
    if not 0 <= slippage < 1:
        raise ValueError('Invalid slippage')
    for audit, row in zip(audits, rows):
        day = row['date']
        if any(F(row.get(key, 0)) != 0 for key in ('external_flow', 'receivable')):
            raise ValueError('Cash flows or nontradeable claims require separate accounting')
        if row.get('distribution_rights') or row.get('merger_entitlements'):
            raise ValueError('Nontradeable claims require separate accounting')
        before, purchases, proceeds = cash, F(0), F(0)
        orders = {order['id']: order for order in audit['orders']}
        if len(orders) != len(audit['orders']):
            raise ValueError('Duplicate order id')
        buy_seen = False
        for fill in fills_by_day[day]:
            order = orders.get(fill['id'])
            if (order is None or order['active_date'] != day
                    or not order['decision_date'] < day
                    or order['security_id'] != fill['security_id']
                    or order['side'] != fill['side']):
                raise ValueError('Fill must bind to its prior decision')
            quantity, price, fee = fill['quantity'], F(fill['price']), F(fill['fee'])
            if type(quantity) is not int or quantity <= 0 or price <= 0 or fee < 0:
                raise ValueError('Invalid fill amount')
            amount = quantity * price
            if fill['side'] == 'BUY':
                buy_seen = True
                cash -= amount + fee
                purchases += amount + fee
            elif fill['side'] == 'SELL':
                if buy_seen:
                    raise ValueError('Saved model must execute sells before buys')
                cash += amount - fee
                proceeds += amount - fee
            else:
                raise ValueError('Unsupported fill side')
            if cash < 0 or cash != F(fill['cash_after']):
                raise ValueError('Per-fill cash does not reconcile')
            total_fees += fee
            fill_count += 1
            state = audit.get('risk_overlay', {}).get('state', {})
            sid = fill['security_id']
            if fill['side'] == 'SELL' and sid in state.get('exited', []):
                if state.get('session_date') != order['decision_date']:
                    raise ValueError('Exit state date differs from signal')
                peak, close = F(state['peaks'][sid]), F(state['last_closes'][sid])
                if peak <= 0 or close <= 0 or close * 5 > peak * 4:
                    raise ValueError('Exit lacks its completed-close trigger')
                # Explicit action evidence, never a guessed quantity ratio, rebases
                # the signal and peak into the fill's share units.
                ratio = F(1)
                actions = [item for item in book['order_log'] if item['date'] == day
                           and item['event'] == 'CORPORATE_ACTION' and item.get('security_id') == sid]
                for action in actions:
                    details = action['action_details']
                    if action['type'] != 'split' or not details['source_references']:
                        raise ValueError('Exit price units require a sourced same-identity split')
                    if details['date'] != day or details['security_id'] != sid:
                        raise ValueError('Exit split evidence binding mismatch')
                    step = F(details['new_shares']) / F(details['old_shares'])
                    if step <= 0:
                        raise ValueError('Invalid split units')
                    ratio *= step
                if F(order['quantity']) * ratio != quantity:
                    raise ValueError('Exit quantity change lacks matching split evidence')
                peak, close = peak / ratio, close / ratio
                rebased_action_exits += int(ratio != 1)
                raw_open = price / (1 - slippage)
                exits.append(dict(security_id=sid, ticker=names.get(sid, sid),
                    decision_date=order['decision_date'], fill_date=day, quantity=quantity,
                    peak=str(peak), signal_close=str(close), assumed_open=str(raw_open),
                    fill_price=str(price), signal_drop=str(1 - close / peak),
                    fill_drop=str(1 - price / peak), open_gap=str(raw_open / close - 1),
                    fill_gap=str(price / close - 1), split_ratio=str(ratio), fee=str(fee)))
        if cash != F(row['cash']):
            raise ValueError('Daily cash has unexplained non-fill changes')
        if purchases:
            buy_days += 1
        shortfall = max(F(0), purchases - before)
        if shortfall > proceeds:
            raise ValueError('Sale funding exceeds available proceeds')
        if shortfall:
            funding.append(dict(date=day, cash_before=str(before), buy_outflow=str(purchases),
                                net_sale_proceeds=str(proceeds), sale_dependent_cash=str(shortfall)))
        total_buys += purchases
        total_sale_dependency += shortfall
    if F(book['cash']) != cash or F(book['fees']) != total_fees:
        raise ValueError('Terminal cash or total fees do not reconcile')
    return dict(status='EXACT_SAVED_CASH_RECONCILED', fills=fill_count, buy_days=buy_days,
        sale_funded_buy_days=len(funding), buy_outflow=str(total_buys),
        sale_dependent_cash_sum=str(total_sale_dependency), funding_days=funding,
        risk_exit_fills=exits, action_unit_exits_rebased=rebased_action_exits,
        limitation='Accounting dependence only; no alternative fills, returns, broker settlement or limit execution inferred')


def analyze_path(path):
    source = Path(path)
    raw = source.read_bytes()
    result = audit_execution(json.loads(raw))
    result.update(source=str(source), sha256=hashlib.sha256(raw).hexdigest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('books', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = [analyze_path(path) for path in args.books]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps([dict(source=row['source'], status=row['status'],
                          sale_funded_buy_days=row['sale_funded_buy_days'],
                          buy_days=row['buy_days']) for row in result]))


if __name__ == '__main__':
    main()
