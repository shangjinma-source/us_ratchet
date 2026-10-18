"""Read-only display projection of independently reviewed, sealed daily experiments."""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'tmp/monthly_latched_exit_comparison_20261016_v1/comparison.json'
REPORT_SHA = 'f4bde7366d4e2375952f34d4d1548d0a1032b738d6754836b62c035ab9dace57'
REVIEW = 'tmp/monthly_latched_sma20_exit_20261016_v1/independent_review_v1.json'
REVIEW_SHA = '3634de9fe76c09cef141f456869e202be50423a18414b571bb1f837be43624f3'
LABELS = {'B0':'月度换股、开盘执行','R2':'趋势走弱全退出、恢复即回补',
          'half':'趋势走弱半仓','premium':'月度换股、较高限价卖出',
          'latch':'趋势走弱退出、等下次月度选股'}


def _verified_bytes(root, relative, expected):
    path = (root / relative.replace('\\', '/')).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Evidence path outside repository')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError('Evidence digest mismatch')
    return content


def _number(value):
    result = float(Fraction(str(value)))
    if not math.isfinite(result):
        raise ValueError('Non-finite evidence')
    return result


def read_verified_daily_comparison(root=ROOT):
    """Fail closed; no strategy execution, writes, cache or account access."""
    try:
        report = json.loads(_verified_bytes(root, REPORT, REPORT_SHA))
        review = json.loads(_verified_bytes(root, REVIEW, REVIEW_SHA))
        if (review['status'] != 'PASS_SAVED_MONTHLY_LATCH_REVIEW'
                or report['schema'] != 'MONTHLY_LATCH_FIVE_ARM_SAVED_COMPARISON_V1'
                or report['automatic_promotion'] is not False
                or set(report['arms']) != set(LABELS)
                or report['source_hashes'].get('tmp/monthly_latched_sma20_exit_20261016_v1/outcome.json') != review['outcome_sha256']):
            raise ValueError('Review incomplete')
        for path, digest in report['source_hashes'].items():
            _verified_bytes(root, path, digest)
        columns = []
        for name,label in LABELS.items():
            column=report['arms'][name]
            years = [{**row, 'return_fraction': _number(row['return_fraction']),
                      'maximum_close_drawdown': _number(row['maximum_close_drawdown'])}
                     for row in column['years']]
            if [row['year'] for row in years] != [2024, 2025, 2026]:
                raise ValueError('Unexpected years')
            columns.append({'label': label, 'arm':name, 'years': years,
                            **{key: _number(column[key]) for key in
                               ('final_equity', 'total_return', 'cagr', 'maximum_close_drawdown')}})
        if len(columns) != 5:
            raise ValueError('Incomplete comparison')
        return {'status': 'AVAILABLE', 'schema': 'VERIFIED_DAILY_COMPARISON_V2',
                'initial_cash': 20000, 'start': '2023-12-29', 'end': '2026-10-13',
                'cagr_year_basis_days': 365, 'independent_oos': False,
                'current_candidate_performance': False, 'current_minute_execution_validated': False,
                'automatic_promotion':False,'joint_improvement_against_B0':report['joint_improvement_against_B0'],
                'columns': columns, 'report_sha256': REPORT_SHA}
    except (OSError, ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError):
        return {'status': 'UNAVAILABLE', 'reason': 'VERIFIED_EVIDENCE_UNAVAILABLE'}
