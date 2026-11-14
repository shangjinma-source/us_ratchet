"""Inventory saved historical executions before requesting intraday data. Read-only."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from backtest.research_exact_fraction_json import loads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.book.read_bytes()
    book = loads(raw.decode('utf-8'))
    if book['status'] != 'COMPLETE':
        raise ValueError('INCOMPLETE_BOOK')
    daily = {row['date']: row for row in book['daily_ledger']}
    if len(daily) != len(book['daily_ledger']):
        raise ValueError('DUPLICATE_SESSION')
    records = []
    for index, order in enumerate(book['order_log']):
        day = daily[order['date']]
        records.append(dict(order_index=index, date=order['date'],
            security_id=order['security_id'], side=order['side'], phase=order['phase'],
            quantity=str(order['quantity']), reason=order['reason'],
            ledger_risk_on=day['risk_on'], signal_date=day['signal_date']))
    years = {}
    for year in sorted({row['date'][:4] for row in records}):
        subset = [r for r in records if r['date'].startswith(year)]
        years[year] = dict(orders=len(subset),
            security_days=len({(r['date'], r['security_id']) for r in subset}),
            sessions=len({r['date'] for r in subset}),
            sides=dict(Counter(r['side'] for r in subset)),
            phases=dict(Counter(r['phase'] for r in subset)))
    result = dict(status='HISTORICAL_EXECUTION_INVENTORY_NOT_INTRADAY_BACKTEST',
        book_sha256=sha256(raw).hexdigest(), years=years, records=records,
        limitations=[
            'Executed orders alone exclude signals that did not fill and do not reconstruct target sizing.',
            'ledger_risk_on is saved daily state, not necessarily the pre-order signal.',
            'Security IDs require historical ticker and corporate-action mapping before source requests.',
            'No intraday coverage is claimed. Full account replay also needs intervening valuation and exit paths.',
            'CLOSE phase exits must remain distinct from OPEN market-switch orders.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(years, ensure_ascii=False))


if __name__ == '__main__':
    main()
