"""Independent arithmetic review; diagnostics never become deployment evidence."""
import argparse
import json
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path

from scripts.research.rsi2_complete_window_metrics_20261106 import (
    ROOT, WINDOWS, read, summarize, compare,
)

LABEL = 'DIAGNOSTIC_NOT_DEPLOYABLE'


def review(window, book_path):
    path = Path(book_path)
    book = read(path)
    if book.get('evidence_status') != LABEL:
        raise ValueError('EXPLICIT_DIAGNOSTIC_LABEL_REQUIRED')
    if F(book['initial_cash']) != 20000:
        raise ValueError('INITIAL_CAPITAL_MISMATCH')
    folder, anchor, end, count = WINDOWS[window]
    inputs_path = ROOT / 'tmp' / folder / 'execution_inputs.json'
    expected = read(inputs_path)['assembled']['session_dates'][1:]
    if len(expected) != count or expected[-1] != end:
        raise ValueError('REFERENCE_CALENDAR_MISMATCH')
    rows = book['daily_ledger']
    if [row['date'] for row in rows] != expected[:len(rows)]:
        raise ValueError('NONCONTIGUOUS_DIAGNOSTIC_LEDGER')
    for row in rows:
        if F(row['cash']) < 0 or len(row['shares']) > 10:
            raise ValueError('CASH_OR_POSITION_CAP')
        if any(type(q) is not int or q <= 0 for q in row['shares'].values()):
            raise ValueError('INVALID_HELD_SHARES')
        components = sum((F(row[field]) for field in (
            'cash', 'stock_value', 'merger_receivable', 'dividend_receivable')), F(0))
        if components != F(row['equity']):
            raise ValueError('EQUITY_COMPONENT_MISMATCH')
    report = dict(evidence_status=LABEL, window=window, status=book['status'],
                  reason=book.get('reason'), sessions=len(rows), expected_sessions=count,
                  fills=len(book['order_log']), metrics=None, qqq_reference=None,
                  source_hashes={str(path): sha256(path.read_bytes()).hexdigest(),
                                 str(inputs_path): sha256(inputs_path.read_bytes()).hexdigest()},
                  limitations=book.get('limitations', []) + [
                      'Arithmetic review does not certify source data or corporate-action assumptions.',
                      'Approximate cash timing is not a proven return bound; no deployment approval.',
                  ])
    if book['status'] == 'COMPLETE':
        report['metrics'] = summarize(book, anchor=anchor, expected_sessions=expected)
        reference = compare(window)
        report['qqq_reference'] = reference['results']['QQQ_REINVESTED']
        report['source_hashes'].update(reference['source_hashes'])
    elif book['status'] != 'BLOCKED' or book.get('total_return') is not None:
        raise ValueError('INVALID_INCOMPLETE_RESULT')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', choices=list(WINDOWS), required=True)
    parser.add_argument('--book', required=True)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    result = review(arguments.window, arguments.book)
    Path(arguments.output).write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: result[k] for k in ('evidence_status', 'window', 'status', 'sessions', 'metrics')}))
