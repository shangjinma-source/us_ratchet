"""Compare completed D0/D1/D5 paths; not an independent finance audit."""
import json
from pathlib import Path
from hashlib import sha256
from backtest.research_exact_fraction_json import loads

ROOT = Path(__file__).resolve().parents[2]


def main():
    root = ROOT / 'tmp/momentum_account_early_20261105_v1'
    books, pins = {}, {}
    for delay in (0, 1, 5):
        directory = root / ('D' + str(delay))
        summary = loads((directory / 'summary.json').read_text())
        if (summary['status'], summary['completed_sessions'], summary['target_sizing_calls'],
                summary['settlement_delay']) != ('COMPLETE', 753, 36, delay):
            raise ValueError('COMPLETE_FIXED_SCENARIO_REQUIRED')
        books[delay] = loads((directory / 'book.json').read_text())
        for name in ('book.json', 'summary.json', 'contract.json'):
            path = directory / name
            pins[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    def fills(book):
        return [r for r in book['order_log'] if r.get('event') == 'ASSUMED_NEXT_OPEN_FILLED']
    def curve(book):
        return [(r['date'], r['equity']) for r in book['daily_ledger']]
    records = []
    for delay, book in books.items():
        differences = [r['date'] for r, base in zip(book['daily_ledger'], books[0]['daily_ledger'])
                       if r['cash'] != base['cash'] or r['receivable'] != base['receivable']]
        records.append(dict(delay=delay, releases=book['cash_merger_settlement']['releases'],
                            fill_count=len(fills(book)), same_fills_as_D0=fills(book) == fills(books[0]),
                            same_equity_curve_as_D0=curve(book) == curve(books[0]),
                            cash_or_receivable_difference_dates=differences))
    path = Path(__file__)
    pins[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    report = dict(status='THREE_COMPLETED_PATHS_COMPARED_NOT_FULL_FINANCE_AUDIT', records=records,
                  source_hashes=pins,
                  limitation='Only these fixed scenarios on this realized path. Does not prove actual broker credit dates or insensitivity under other holdings.')
    output = root / 'settlement_sensitivity.json'
    if output.exists():
        raise ValueError('EXISTING_COMPARISON_MUST_BE_PRESERVED')
    output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(status=report['status'], records=records)))


if __name__ == '__main__':
    main()
