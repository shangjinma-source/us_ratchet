"""Read three sealed paths on one calendar; no winner selection or re-execution."""
import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND = {
    'USER_PREFERENCE': ('data/cache/research/dynamic_frozen_v2/preference_retrospective_accounting_20260912.json',
        '3b0fd632ba5c53839b90199d7edf74dafdc73bdc9b3369d09bef24fdae177e59'),
    'INCUMBENT': ('data/cache/research/incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json',
        '53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'),
    '012922': ('data/cache/research/dynamic_frozen_v2/preference_retrospective_nav_20260912.json',
        'e1bb2b71d777b39cea5526ce4cc39a7b90d281609d3d2b9d8d0a0dbaa8a28b33')}


def verify(sources):
    for path, digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Comparison source differs: ' + path)


def build_report():
    sources, loaded = {str(SOURCE): LOADED_SHA}, {}
    for role, (name, digest) in BOUND.items():
        path = ROOT / name
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Comparison artifact differs: ' + role)
        report = json.loads(raw)
        if report['promotion_allowed'] is not False:
            raise ValueError('Conditional research-only report required')
        for source, sha in report['source_hashes'].items():
            if source in sources and sources[source] != sha:
                raise ValueError('Conflicting comparison source')
            sources[source] = sha
        sources[str(path)] = digest
        loaded[role] = report
    verify(sources)
    reference = loaded['USER_PREFERENCE']['execution']
    calendar = [row['session'] for row in reference['daily']]
    clock = [(row['decision_date'], row['execution_date']) for row in reference['decisions']]
    if len(calendar) != 295 or len(clock) != 15:
        raise ValueError('Complete 295-session 15-decision path required')
    rows, equity_indices = [], {}
    for role in ('USER_PREFERENCE', 'INCUMBENT'):
        execution = loaded[role]['execution']
        if ([row['session'] for row in execution['daily']] != calendar
                or [(row['decision_date'], row['execution_date']) for row in execution['decisions']] != clock
                or execution['execution_policy'] != reference['execution_policy']
                or execution['daily'][0]['total_value_usd'] != 25000
                or execution['daily'][0]['cash_usd'] != 25000
                or execution['daily'][0]['shares'] != {} or execution['dividend_modelled'] is not False):
            raise ValueError('Stock clock, cash origin, or accounting policy differs')
        values = [row['total_value_usd'] / 25000 for row in execution['daily']]
        peak, drawdown = 1., 0.
        for value in values:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        result = values[-1] - 1
        if abs(result - execution['summary']['path_return_net']) > 1e-12 or abs(drawdown - execution['summary']['path_max_drawdown']) > 1e-12:
            raise ValueError('Reported path statistics differ from saved daily equity')
        rows.append(dict(role=role, path_return=result, annualized_return_252_session=values[-1] ** (252 / 294) - 1,
            max_drawdown=drawdown, terminal_value_usd=execution['daily'][-1]['total_value_usd'],
            trade_count=len(execution['trades']), fees_usd=sum(row['transaction_cost_usd'] for row in execution['trades']),
            invested_risk_failure_days=sum(any(row['shares'].values()) and not row['risk']['all_passed'] for row in execution['daily']),
            target_cardinalities=sorted(set(execution['summary']['k_path'])),
            risk_used_as_order_gate=role == 'USER_PREFERENCE', currency='USD', dividends_modelled=False))
        equity_indices[role] = values
    nav = loaded['012922']['nav']
    if [row['session'] for row in nav['rows']] != calendar or nav['fx_modelled'] is not False:
        raise ValueError('Native NAV calendar or currency convention differs')
    nav_values = [row['equity_index'] for row in nav['rows']]
    if nav_values[0] != 1 or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in nav_values):
        raise ValueError('Finite positive NAV index with initial unit value required')
    ages = [(date.fromisoformat(row['session']) - date.fromisoformat(row['nav_date'])).days for row in nav['rows']]
    if min(ages) < 0:
        raise ValueError('Future NAV date in backward alignment')
    peak, drawdown = 1., 0.
    for value in nav_values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    recomputed = dict(path_return=nav_values[-1] - 1, path_max_drawdown=drawdown,
                      annualized_return_252_session=nav_values[-1] ** (252 / 294) - 1)
    if any(abs(nav[key] - value) > 1e-12 for key, value in recomputed.items()):
        raise ValueError('NAV statistics differ from saved daily index')
    rows.append(dict(role='012922_NATIVE_CURRENCY', path_return=nav['path_return'],
        annualized_return_252_session=nav['annualized_return_252_session'], max_drawdown=nav['path_max_drawdown'],
        currency='FUND_NATIVE_CURRENCY_NOT_CONVERTED_TO_USD', subscription_redemption_fees_modelled=False,
        alignment=nav['alignment'], maximum_nav_age_calendar_days=max(ages), publication_time_verified=False))
    equity_indices['012922_NATIVE_CURRENCY'] = nav_values
    comparisons = [dict(reference_role=row['role'],
        observed_annualized_return_difference=rows[0]['annualized_return_252_session'] - row['annualized_return_252_session'],
        observed_drawdown_difference=rows[0]['max_drawdown'] - row['max_drawdown'],
        observed_two_metric_noninferior=(rows[0]['annualized_return_252_session'] >= row['annualized_return_252_session']
                                        and rows[0]['max_drawdown'] <= row['max_drawdown'])) for row in rows[1:]]
    verify(sources)
    return dict(schema='ndx_retrospective_same_calendar_comparison_research_v1',
        scope='CONDITIONAL_FIXED_REFERENCE_PATH_OBSERVATION_NOT_PORTFOLIO_SELECTION',
        source_hashes=sources, calendar=calendar, decision_clock=clock, rows=rows,
        normalized_equity_by_role=equity_indices, observed_comparisons=comparisons,
        original_incumbent_weights_unchanged=True, current_user_account_data_used=False,
        original_incumbent_risk_is_order_gate=False, stock_dividend_cash_flows_modelled=False,
        nav_currency_and_publication_equivalence_verified=False, fee_cash_flow_equivalence_verified=False,
        conditional_three_path_arithmetic_compared=True, formal_dual_benchmark_admission_completed=False,
        rolling_eight_metric_training_gate_replaced=False, whole_ndx_search_completed=False,
        selected_winner=False, independent_oos=False, point_in_time_verified=False,
        execution_rerun=False, refit_rerun=False, training_rerun=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to((ROOT / 'data/cache/research').resolve()) or output.exists():
        raise ValueError('New research output path required')
    report = build_report()
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    verify(report['source_hashes'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(encoded)
    verify(report['source_hashes'])
    print(json.dumps({'sha256': hashlib.sha256(encoded).hexdigest(), 'rows': report['rows']}))
