"""Read saved books and nominal bars to describe concentration and trading work.

No optimizer, strategy execution, network, or production account imports.
Attribution labels describe saved orders, not causal performance contributions.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import fmean


def number(value):
    return Fraction(str(value))


def analyze(book_path, bars_path):
    raw = Path(book_path).read_bytes()
    bar_raw = Path(bars_path).read_bytes()
    book, bars = json.loads(raw), json.loads(bar_raw)['ohlc']
    if book['status'] != 'COMPLETE' or number(book['external_flows']) != 0:
        raise ValueError('COMPLETE_ZERO_EXTERNAL_FLOW_BOOK_REQUIRED')
    audits = {audit['risk_overlay']['state']['session_date']: audit
              for audit in book['provider_audit'] if audit.get('risk_overlay', {}).get('state')}
    order_audits = {}
    for decision, audit in audits.items():
        for order in audit['orders']:
            if order['id'] in order_audits:
                raise ValueError('DUPLICATE_ORDER_ID')
            order_audits[order['id']] = decision, audit, order
    names = {quote['security_id']: quote['ticker']
             for account in book['selection_account_states'] for quote in account['valuation_quotes']}
    cash_percentages, weights, holding_counts = [], [], Counter()
    maximum = None
    for row in book['daily_ledger']:
        holdings = {sid: quantity for sid, quantity in row['shares'].items() if quantity}
        values = {sid: quantity * number(bars[sid][row['date']]['close'])
                  for sid, quantity in holdings.items()}
        equity, cash = number(row['equity']), number(row['cash'])
        stock = sum(values.values(), Fraction(0))
        if stock != number(row['stock_value']) or cash + stock != equity:
            raise ValueError('NOMINAL_MARK_OR_ENTITLEMENT_RECONCILIATION_FAILED:' + row['date'])
        if equity <= 0:
            raise ValueError('POSITIVE_EQUITY_REQUIRED')
        cash_percentages.append(float(cash / equity * 100))
        holding_counts[len(holdings)] += 1
        sid, value = max(values.items(), key=lambda pair: pair[1]) if values else ('cash', Fraction(0))
        weight = value / equity
        weights.append(weight)
        if maximum is None or weight > number(maximum['weight']):
            maximum = dict(date=row['date'], security_id=sid, ticker=names.get(sid, sid),
                           weight=str(weight), weight_percent=float(weight * 100))
    fills = [row for row in book['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
    categories, trim_quantities, monthly, trim_monthly = Counter(), Counter(), Counter(), Counter()
    turnover, fees, slippage = Fraction(0), Fraction(0), Fraction(0)
    trim_rows = []
    for fill in fills:
        sid, quantity = fill['security_id'], fill['quantity']
        decision, audit, order = order_audits[fill['id']]
        if order['active_date'] != fill['date'] or order['security_id'] != sid or order['side'] != fill['side']:
            raise ValueError('FILL_ORDER_IDENTITY_MISMATCH')
        reductions = {row['security_id']: row for row in audit.get('drift_overlay', {}).get('reductions', [])}
        risk_targets = audit['risk_overlay']['effective_target_quantities']
        if fill['side'] == 'SELL' and risk_targets.get(sid) == 0 and audit['monthly_ceiling'].get(sid, 0) > 0:
            category = 'risk_exit'
        elif fill['side'] == 'SELL' and sid in reductions:
            category = 'drift_reduction'
            trim_quantities[quantity] += 1
            trim_monthly[fill['date'][:7]] += 1
            trim_rows.append(dict(date=fill['date'], decision_date=decision,
                                  ticker=names.get(sid, sid), security_id=sid, quantity=quantity,
                                  notional=str(quantity * number(fill['price'])),
                                  fee=fill['fee'], trigger=reductions[sid]))
        else:
            category = 'other_target_difference'
        categories[category] += 1
        monthly[fill['date'][:7]] += 1
        turnover += quantity * number(fill['price'])
        fees += number(fill['fee'])
        slippage += quantity * number(bars[sid][fill['date']]['open']) * number(book['slippage_bps']) / 10000
    if fees != number(book['fees']):
        raise ValueError('FEE_RECONCILIATION_FAILED')
    trim_dates = {row['date'] for row in trim_rows}
    streak, longest_streak = 0, 0
    for row in book['daily_ledger']:
        streak = streak + 1 if row['date'] in trim_dates else 0
        longest_streak = max(longest_streak, streak)
    return dict(source=str(book_path), sha256=hashlib.sha256(raw).hexdigest(),
                bars_source=str(bars_path), bars_sha256=hashlib.sha256(bar_raw).hexdigest(),
                close_observations=len(weights), mean_daily_cash_percent=fmean(cash_percentages),
                all_cash_days=holding_counts[0], positive_holdings_count_distribution=dict(holding_counts),
                days_largest_exceeds_50=sum(value > Fraction(1, 2) for value in weights),
                days_largest_exceeds_55=sum(value > Fraction(55, 100) for value in weights),
                max_concentration=maximum, fills=len(fills), fills_by_month=dict(sorted(monthly.items())),
                max_monthly_fills=max(monthly.values(), default=0), fill_categories=dict(categories),
                drift_trim_quantity_frequency=dict(sorted(trim_quantities.items())),
                drift_trims_by_month=dict(sorted(trim_monthly.items())),
                longest_consecutive_close_sessions_with_trim_fills=longest_streak,
                drift_trim_fills=trim_rows, gross_buy_sell_notional=str(turnover),
                modeled_fees=str(fees), modeled_adverse_slippage=str(slippage),
                scope='Exact saved book marks and fills; mean cash is an arithmetic mean of daily percentages; '
                      'trade labels are not a causal return decomposition or a broker fee estimate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', type=Path, required=True)
    parser.add_argument('--bars', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.book, args.bars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(dict(schema='SAVED_DRIFT_CAP_TRADE_BURDEN_V1', new_searches=0,
                       new_executions=0, result=result), stream, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
