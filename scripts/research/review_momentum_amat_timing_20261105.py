"""Bound the recorded AMAT date conflict on the completed fixed late path."""
import json
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from backtest.research_exact_fraction_json import loads

ROOT = Path(__file__).resolve().parents[2]


def main():
    folder = ROOT / 'tmp/momentum_account_late_20261105_v1/D0'
    book = loads((folder / 'book.json').read_text())
    summary = loads((folder / 'summary.json').read_text())
    if summary['status'] != 'COMPLETE' or summary['completed_sessions'] != 646:
        raise ValueError('COMPLETE_LATE_PATH_REQUIRED')
    sid = 'security:0000006951:038222105'
    ledger = {r['date']: r for r in book['daily_ledger']}
    quantities = [ledger[d]['shares'].get(sid, 0) for d in ('2024-08-20', '2024-08-21', '2024-08-22')]
    if quantities != [10, 10, 10]:
        raise ValueError('RECORDED_QUANTITY_PATH_CHANGED')
    if any(r.get('date') in ('2024-08-21', '2024-08-22') and sid in str(r) for r in book['order_log']):
        raise ValueError('AMAT_ORDER_ON_DISPUTED_DAYS')
    events = [v for v in book['dividend_ledger']['events'].values()
              if v['event']['security_id'] == sid and v['event']['ex_date'] == '2024-08-22']
    if len(events) != 1 or events[0]['opening_quantity'] != 10 or F(events[0]['net']) != 4:
        raise ValueError('EXACT_FOUR_DOLLAR_ENTITLEMENT_REQUIRED')
    if events[0]['event']['payment_date'] != '2024-09-12':
        raise ValueError('PAYMENT_DATE_CHANGED')
    if any(r['decision_date'] in ('2024-08-21', '2024-08-22') for r in book['selection_account_states']):
        raise ValueError('SIZING_ON_DISPUTED_DAYS')
    def drawdown(earlier):
        peak = F(20000)
        maximum = F(0)
        for row in book['daily_ledger']:
            value = F(row['equity']) + (4 if earlier and row['date'] == '2024-08-21' else 0)
            peak = max(peak, value)
            maximum = max(maximum, 1 - value / peak)
        return maximum
    report = dict(status='RECORDED_PATH_AMAT_DATE_SENSITIVITY_CHECKED_NOT_FULL_ACCOUNT_AUDIT',
                  opening_shares_both_dates=10, total_entitlement_both_dates='4',
                  earlier_date_aug21_equity_increment='4', terminal_equity_difference='0',
                  original_max_drawdown=str(drawdown(False)), earlier_date_max_drawdown=str(drawdown(True)),
                  max_drawdown_difference=str(drawdown(True) - drawdown(False)),
                  limitation='Pathwise calculation: unchanged stock/order path, same payment date, no sizing on disputed days; unpaid dividends excluded from risk and buying power. Does not resolve issuer history conflict.',
                  source_hashes={p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
                                 for p in (folder / 'book.json', folder / 'summary.json', Path(__file__))})
    output = folder / 'amat_date_sensitivity.json'
    if output.exists():
        raise ValueError('PRESERVE_EXISTING_REVIEW')
    output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: report[k] for k in ('status', 'terminal_equity_difference', 'max_drawdown_difference')}))


if __name__ == '__main__':
    main()
