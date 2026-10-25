"""Read completed reviewed books; calculate descriptive metrics, never execute a book."""
import argparse
from calendar import monthrange
from collections import Counter
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
from math import fsum
from pathlib import Path


def summarize(book, review):
    if book.get('status') != 'COMPLETE' or review.get('status') != 'INDEPENDENT_FRONTIER_ACCOUNT_RISK_REVIEW_PASS':
        raise ValueError('COMPLETE_REVIEWED_BOOK_REQUIRED')
    rows = book['daily_ledger']
    start = book['selection_account_states'][0]['decision_date']
    initial = F(20000)
    dates = [start] + [r['date'] for r in rows]
    if dates != sorted(set(dates)) or len(rows) < 1:
        raise ValueError('ORDERED_COMPLETE_LEDGER_REQUIRED')
    if any(F(r.get('external_flow', 0)) for r in rows):
        raise ValueError('EXTERNAL_FLOW_RETURN_UNSUPPORTED')
    values = [initial] + [F(r['equity']) for r in rows]
    if any(v <= 0 for v in values):
        raise ValueError('POSITIVE_EQUITY_REQUIRED')
    ratio = values[-1] / initial
    fills = [r for r in book['order_log'] if r['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
    if (F(book['total_return']) != ratio-1 or F(review['final_equity']) != values[-1]
            or F(review['interval_return']) != ratio-1 or review['fills'] != len(fills)
            or review['close_observations'] != len(rows) or F(review['fees']) != F(book['fees'])):
        raise ValueError('REVIEW_BOOK_METRICS_MISMATCH')
    peak, peak_index, worst, peak_at, trough_at = initial, 0, F(0), 0, 0
    daily = []
    months = {}
    for i in range(1, len(values)):
        daily.append(dict(date=dates[i], return_fraction=str(values[i]/values[i-1]-1)))
        month = dates[i][:7]
        months.setdefault(month, dict(base=values[i-1], first=dates[i], last=dates[i], ending=values[i]))
        months[month].update(last=dates[i], ending=values[i])
        if values[i] > peak:
            peak, peak_index = values[i], i
        decline = 1-values[i]/peak
        if decline > worst:
            worst, peak_at, trough_at = decline, peak_index, i
    if F(review['max_close_drawdown']) != worst:
        raise ValueError('REVIEW_DRAWDOWN_MISMATCH')
    recovery = next((i for i in range(trough_at+1, len(values)) if values[i] >= values[peak_at]), None) if worst else None
    elapsed = (date.fromisoformat(dates[-1])-date.fromisoformat(start)).days
    monthly = []
    for month, r in months.items():
        y, m = map(int, month.split('-'))
        partial = (month == start[:7] and int(start[-2:]) > 1) or (month == dates[-1][:7] and int(dates[-1][-2:]) < monthrange(y,m)[1])
        monthly.append(dict(month=month, return_fraction=str(r['ending']/r['base']-1),
                            first_observation=r['first'], last_observation=r['last'],
                            boundary_calendar_month_truncated=partial))
    counts = Counter(r['date'][:7] for r in fills)
    return dict(start=start, end=dates[-1], elapsed_calendar_days=elapsed,
        interval_return=str(ratio-1), annualized_return_36525=float(ratio)**(365.25/elapsed)-1,
        annualized_return_365_comparison=float(ratio)**(365/elapsed)-1,
        annualization_formula='(final_equity / 20000) ** (365.25 / elapsed_calendar_days) - 1',
        maximum_drawdown=str(worst), drawdown_peak_date=dates[peak_at] if worst else None,
        drawdown_trough_date=dates[trough_at] if worst else None,
        recovery_date=dates[recovery] if recovery is not None else None,
        unrecovered=bool(worst and recovery is None),
        peak_to_trough_calendar_days=(date.fromisoformat(dates[trough_at])-date.fromisoformat(dates[peak_at])).days,
        peak_to_recovery_or_end_calendar_days=(date.fromisoformat(dates[recovery if recovery is not None else -1])-date.fromisoformat(dates[peak_at])).days if worst else 0,
        fills=len(fills), maximum_monthly_fills=max(counts.values(), default=0), monthly_fills=dict(counts),
        mean_daily_cash_equity_ratio=fsum(float(F(r['cash'])/F(r['equity'])) for r in rows)/len(rows),
        cash_average_basis='Arithmetic mean of daily close cash/equity, excludes initial anchor',
        worst_day=min(daily,key=lambda r:F(r['return_fraction'])),
        worst_month=min(monthly,key=lambda r:F(r['return_fraction'])), monthly_returns=monthly,
        gap_loss=dict(status='NOT_CALCULATED', reason='No open-to-previous-close attribution inputs; daily loss is not gap loss'),
        source_authenticity_verified=False, production_adopted=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--baseline-review', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    if bool(args.baseline) != bool(args.baseline_review):
        parser.error('baseline and baseline-review must be supplied together')
    hashes={}
    def read(path):
        raw=path.read_bytes(); hashes[str(path.resolve())]=sha256(raw).hexdigest()
        return json.loads(raw)
    result=dict(candidate=summarize(read(args.book),read(args.review)))
    if args.baseline:
        result['baseline']=summarize(read(args.baseline),read(args.baseline_review))
        if any(result['candidate'][k] != result['baseline'][k] for k in ('start','end')):
            raise ValueError('COMPARISON_WINDOW_MISMATCH')
    result.update(source_sha256=hashes, new_searches=0, new_execution_books=0,
        review_binding='Supplied review status and summary fields checked; not a new independent ledger review')
    with args.output.open('x',encoding='utf8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)


if __name__ == '__main__':
    main()
