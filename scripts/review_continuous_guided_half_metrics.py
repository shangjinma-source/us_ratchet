"""Independently reconcile published metrics to saved daily NAV, without replay."""
import hashlib
import json
import math
import sys
from datetime import date
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'tmp/continuous_guided_half_comparison_20261016_v2'


def verify():
    previous_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(max(previous_limit, 50000) if previous_limit else 0)
        return verify_saved_metrics()
    finally:
        sys.set_int_max_str_digits(previous_limit)


def verify_saved_metrics():
    source = DIRECTORY / 'comparison.json'
    raw = source.read_bytes()
    report = json.loads(raw)
    if set(report['arms']) != {'B0', 'continuous32', 'continuous32_half'}:
        raise ValueError('ARM_COVERAGE_MISMATCH')
    for name, expected in report['source_hashes'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('SOURCE_OUTSIDE_ROOT')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_HASH_MISMATCH')
    results = {}
    expected_dates = None
    for key, folder in [('B0', 'daily_exclusion_B0_20261016_v1'),
                        ('continuous32', 'continuous_guided_monthly_book_20261016_v1'),
                        ('continuous32_half', 'continuous_guided_half_exposure_20261016_v1')]:
        name = f'tmp/{folder}/outcome.json'
        content = (ROOT / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != report['source_hashes'][name]:
            raise ValueError('OUTCOME_HASH_MISMATCH')
        rows = json.loads(content)['daily_ledger']
        dates = [row['date'] for row in rows]
        if expected_dates is not None and dates != expected_dates:
            raise ValueError('ARM_SESSION_COVERAGE_MISMATCH')
        expected_dates = dates
        previous_day = report['opening_date']
        initial = Fraction(report['initial_cash'])
        peak = initial
        drawdown = Fraction(0)
        current = initial
        year_data = {}
        for row in rows:
            day = row['date']
            if not previous_day < day <= report['through']:
                raise ValueError('DATE_ORDER')
            year = date.fromisoformat(day).year
            if year not in year_data:
                year_data[year] = {'opening': current, 'peak': current, 'drawdown': Fraction(0)}
            current = Fraction(row['equity'])
            if current <= 0:
                raise ValueError('NONPOSITIVE_NAV')
            peak = max(peak, current)
            drawdown = max(drawdown, 1-current/peak)
            annual = year_data[year]
            annual['peak'] = max(annual['peak'], current)
            annual['drawdown'] = max(annual['drawdown'], 1-current/annual['peak'])
            annual['closing'] = current
            previous_day = day
        if previous_day != report['through']:
            raise ValueError('MISSING_LAST_DAY')
        published = report['arms'][key]
        if current != Fraction(published['final_equity']) or drawdown != Fraction(published['maximum_close_drawdown']):
            raise ValueError('WHOLE_PERIOD_METRIC_MISMATCH')
        if ([y['year'] for y in published['years']] != sorted(year_data)):
            raise ValueError('YEAR_COVERAGE_MISMATCH')
        for item in published['years']:
            annual = year_data[item['year']]
            if (annual['closing']/annual['opening']-1 != Fraction(item['return_fraction'])
                    or annual['drawdown'] != Fraction(item['maximum_close_drawdown'])):
                raise ValueError('YEAR_METRIC_MISMATCH')
        elapsed = (date.fromisoformat(report['through'])-date.fromisoformat(report['opening_date'])).days
        annualized = float(current/initial)**(365/elapsed)-1
        if not math.isclose(annualized, published['cagr'], rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('CAGR_MISMATCH')
        results[key] = {'sessions': len(rows), 'years': sorted(year_data), 'final_equity': str(current),
                        'maximum_close_drawdown': str(drawdown), 'cagr': annualized}
    return {'status': 'PASS_INDEPENDENT_NAV_METRICS', 'arms': results,
            'report_sha256': hashlib.sha256(raw).hexdigest(),
            'reviewer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': 'NAV arithmetic only; does not authenticate historical market prices or establish OOS performance'}


if __name__ == '__main__':
    checked = verify()
    with (DIRECTORY / 'root_metrics_review.json').open('x', encoding='utf8') as output:
        json.dump(checked, output, indent=2)
    print(checked['status'])
