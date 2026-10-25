"""Read saved research books; recompute returns and reconcile drawdown losses.

No optimization, market fetch, execution simulation or production account IO.
The source book's execution and historical-data limitations remain applicable.
"""
import argparse
import hashlib
import json
from datetime import date
from fractions import Fraction
from pathlib import Path


def number(value):
    return Fraction(str(value))


def analyze_book(path):
    raw = Path(path).read_bytes()
    book = json.loads(raw)
    if book['status'] != 'COMPLETE' or number(book['external_flows']) != 0:
        raise ValueError('Only complete books without external flows are supported')
    initial = book['selection_account_states'][0]
    start = initial['decision_date']
    start_date = date.fromisoformat(start)
    if initial['account_state']['asof'] != start:
        raise ValueError('Initial account date does not match the decision date')
    if any(initial['account_state']['shares'].values()):
        raise ValueError('Initial account must be all cash')
    initial_equity = number(initial['account_state']['cash'])
    if initial_equity <= 0:
        raise ValueError('Initial equity must be positive')
    rows = book['daily_ledger']
    if not rows or any(a['date'] >= b['date'] for a, b in zip(rows, rows[1:])):
        raise ValueError('Daily ledger must be nonempty and strictly ordered')
    if any(date.fromisoformat(row['date']) <= start_date for row in rows):
        raise ValueError('Daily ledger must follow the initial decision close')
    terminal = rows[-1]
    if (book.get('state_date') != terminal['date']
            or book.get('last_valued_date') != terminal['date']
            or book.get('terminal_state_valuation_synchronized') is not True
            or book.get('final_wealth_basis') != 'REGULAR_CLOSE_CURRENT_STATE'):
        raise ValueError('Terminal state and valued close must be synchronized')
    if (number(book['cash']) != number(terminal['cash'])
            or book['shares'] != terminal['shares']
            or number(book.get('receivable', 0)) != number(terminal.get('receivable', 0))
            or book.get('distribution_rights', []) != terminal.get('distribution_rights', [])
            or book.get('merger_entitlements', []) != terminal.get('merger_entitlements', [])):
        raise ValueError('Terminal account does not match the final daily ledger')
    peak, peak_date, maximum = initial_equity, start, Fraction(0)
    episode = None
    for row in rows:
        equity = number(row['equity'])
        if equity < 0:
            raise ValueError('Negative equity is not supported')
        if number(row.get('external_flow', 0)) != 0:
            raise ValueError('External flow requires a unitized performance model')
        if equity > peak:
            peak, peak_date = equity, row['date']
        drawdown = 1 - equity / peak
        if drawdown > maximum:
            maximum = drawdown
            episode = dict(peak_date=peak_date, trough_date=row['date'],
                           peak_equity=peak, trough_equity=equity)
    total_return = number(rows[-1]['equity']) / initial_equity - 1
    if total_return != number(book['total_return']):
        raise ValueError('Saved total return does not reconcile')
    if maximum != number(book['drawdown']['maximum_close_drawdown']):
        raise ValueError('Saved maximum drawdown does not reconcile')
    days = (date.fromisoformat(terminal['date']) - start_date).days
    result = dict(source=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                  start=start, end=rows[-1]['date'], calendar_days=days,
                  initial_equity=float(initial_equity), close_observations=len(rows),
                  return_percent=float(total_return * 100),
                  cagr_percent=((1 + float(total_return)) ** (365.25 / days) - 1) * 100,
                  maximum_close_drawdown_percent=float(maximum * 100),
                  fee_bps=book['fee_bps'], slippage_bps=book['slippage_bps'],
                  execution_assumption=book['execution_assumption'],
                  independent_oos=book['independent_oos'],
                  point_in_time_certified=book['point_in_time_certified'])
    if episode:
        result['worst_episode'] = {key: float(value) if isinstance(value, Fraction) else value
                                   for key, value in episode.items()}
        result['worst_episode']['recovered_date'] = next(
            (row['date'] for row in rows if row['date'] > episode['trough_date']
             and number(row['equity']) >= episode['peak_equity']), None)
    if episode and any(a.get('risk_overlay') for a in book['provider_audit']):
        result['worst_episode'].update(attribute_episode(book, episode))
    else:
        result['attribution_status'] = 'NO_RISK_MARKS_NOT_ATTRIBUTED'
    return result


def attribute_episode(book, episode):
    """Endpoint marks + exact signed fills: accounting attribution, not causality."""
    dates = episode['peak_date'], episode['trough_date']
    initial = book['selection_account_states'][0]
    initial_day = initial['decision_date']
    endpoints = []
    for day in dates:
        if day == initial_day:
            account = initial['account_state']
            if any(account['shares'].values()):
                raise ValueError('Initial attribution endpoint must be all cash')
            endpoints.append(dict(date=day, cash=account['cash'], shares={}, stock_value='0'))
        else:
            matched = [row for row in book['daily_ledger'] if row['date'] == day]
            if len(matched) != 1:
                raise ValueError('Unique endpoint ledger snapshot required')
            endpoints.append(matched[0])
    marks, values = [], []
    for day, row in zip(dates, endpoints):
        closes = {}
        if any(row['shares'].values()):
            states = [a['risk_overlay']['state'] for a in book['provider_audit']
                      if (a.get('risk_overlay') or {}).get('state', {}).get('session_date') == day]
            if len(states) != 1:
                raise ValueError('Unique endpoint risk-price snapshot required')
            closes = states[0]['last_closes']
        marked = {sid: quantity * number(closes[sid])
                  for sid, quantity in row['shares'].items() if quantity}
        if sum(marked.values()) != number(row['stock_value']):
            raise ValueError('Endpoint stock valuation does not reconcile')
        if any(number(row.get(key, 0)) for key in
               ('receivable', 'distribution_entitlement_value', 'nontradable_entitlement_value')):
            raise ValueError('Noncash rights need their own attribution model')
        marks.append(closes)
        values.append(marked)
    fills = [row for row in book['order_log'] if dates[0] < row['date'] <= dates[1]
             and row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
    trade_cash, fees = {}, {}
    for row in fills:
        sid = row['security_id']
        if row['side'] not in ('BUY', 'SELL'):
            raise ValueError('Unsupported fill side')
        signed = (1 if row['side'] == 'SELL' else -1) * number(row['quantity']) * number(row['price'])
        trade_cash[sid] = trade_cash.get(sid, Fraction(0)) + signed
        fees[sid] = fees.get(sid, Fraction(0)) + number(row['fee'])
    cash_difference = number(endpoints[1]['cash']) - number(endpoints[0]['cash'])
    if sum(trade_cash.values()) - sum(fees.values()) != cash_difference:
        raise ValueError('Other cash events prevent exact fill-only attribution')
    names = {quote['security_id']: quote['ticker'] for state in book['selection_account_states']
             for quote in state['valuation_quotes']}
    securities = set(values[0]) | set(values[1]) | set(trade_cash)
    contributions = []
    total = Fraction(0)
    for sid in sorted(securities):
        pnl = (values[1].get(sid, 0) - values[0].get(sid, 0)
               + trade_cash.get(sid, 0) - fees.get(sid, 0))
        total += pnl
        contributions.append(dict(security_id=sid, ticker=names.get(sid, sid),
                                  net_profit_loss=float(pnl),
                                  peak_equity_contribution_pp=float(pnl / episode['peak_equity'] * 100),
                                  peak_value=float(values[0].get(sid, 0)),
                                  peak_weight_percent=float(values[0].get(sid, 0) / episode['peak_equity'] * 100),
                                  trough_value=float(values[1].get(sid, 0)),
                                  fees=float(fees.get(sid, 0))))
    if total != episode['trough_equity'] - episode['peak_equity']:
        raise ValueError('Contributions do not reconcile to portfolio equity loss')
    return dict(attribution_status='EXACT_ENDPOINT_AND_FILL_RECONCILIATION',
                attribution_scope='Saved marks and fills; accounting decomposition, not a causal counterfactual',
                contributions=sorted(contributions, key=lambda row: row['net_profit_loss']),
                fills=[dict(row, ticker=names.get(row['security_id'], row['security_id'])) for row in fills],
                residual='0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('books', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = dict(schema='SAVED_STRATEGY_DRAWDOWN_AUDIT_V1',
                  cagr_basis='(terminal_equity / initial_equity) ** (365.25 / elapsed_calendar_days) - 1',
                  optimization_calls=0, production_changes=False,
                  books=[analyze_book(path) for path in args.books])
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    else:
        print(encoded)


if __name__ == '__main__':
    main()
