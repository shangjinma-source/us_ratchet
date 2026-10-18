"""Describe frozen independent windows; never select, rerun, or annualize."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'tmp/fixed12_comparison_20261014_v1'
MODES = ('QUANTITY', 'TOP1_SAME_PROJECTION', 'QQQ')


def summarize(payload):
    books = payload['books']
    if len(books) != 36 or payload['book_calls'] != 36 or payload['search_calls'] != 0:
        raise ValueError('Complete registered comparison required')
    by_date = {}
    for book in books:
        row = by_date.setdefault(book['decision_cutoff'], {})
        if book['mode'] in row or book['mode'] not in MODES:
            raise ValueError('Duplicate or unexpected mode')
        row[book['mode']] = book
    if len(by_date) != 12 or any(set(row) != set(MODES) for row in by_date.values()):
        raise ValueError('Twelve paired windows required')
    statistics = {}
    for mode in MODES:
        complete = [row[mode] for row in by_date.values() if row[mode]['status'] == 'COMPLETE']
        returns = [Fraction(book['return_fraction']) for book in complete]
        drawdowns = [Fraction(book['maximum_drawdown']) for book in complete]
        statistics[mode] = dict(
            registered_denominator=12, complete=len(complete), blocked=12-len(complete),
            positive=sum(value > 0 for value in returns),
            mean_completed_window_return=str(sum(returns, Fraction(0))/len(returns)) if returns else None,
            worst_completed_window_return=str(min(returns)) if returns else None,
            largest_completed_window_drawdown=str(max(drawdowns)) if drawdowns else None)
    comparisons = {}
    for baseline in MODES[1:]:
        differences = []
        for row in by_date.values():
            if all(row[mode]['status'] == 'COMPLETE' for mode in ('QUANTITY', baseline)):
                differences.append(Fraction(row['QUANTITY']['return_fraction'])-Fraction(row[baseline]['return_fraction']))
        comparisons[baseline] = dict(
            registered_denominator=12, comparable=len(differences),
            wins=sum(value > 0 for value in differences), ties=sum(value == 0 for value in differences),
            losses=sum(value < 0 for value in differences),
            mean_paired_return_difference=str(sum(differences, Fraction(0))/len(differences)) if differences else None)
    return dict(status='DESCRIPTIVE_ONLY_NO_PROMOTION', statistics=statistics, comparisons=comparisons,
                windows=[dict(decision_date=date, books=row) for date, row in sorted(by_date.items())],
                limitations=['Independent fresh-cash windows may overlap; do not compound or annualize.',
                             'Retrospective conditional price returns, not independent OOS or total returns.',
                             'No limit-order swing execution or live adoption is established.'])


if __name__ == '__main__':
    source = DIRECTORY / 'result.json'
    raw = source.read_bytes()
    result = summarize(json.loads(raw))
    result['source_sha256'] = hashlib.sha256(raw).hexdigest()
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with (DIRECTORY / 'descriptive_summary.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps(dict(statistics=result['statistics'], comparisons=result['comparisons'])))
