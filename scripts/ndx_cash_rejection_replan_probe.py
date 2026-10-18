"""One-replan A/B against explicit immutable historical execution baselines."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_v3_same_execution_recheck as baseline

BASELINE_DIGESTS = (
    'b713a80cdf706534a1a23f29a9fed36d8923eebef0dc10a198090cbafa52c281',
    '51a3e53e0f9496f98a6d61432e6a476c2299ff1fbd647cec7d988f3f77012268',
    '7a9095e4186aaee4fa760c955d1946f4c189b5c3f9a57c4f7f4968cf5510e942',
    'f81b857188e80c5e63419219e0bf484154de085671184171288f94abde96e06b',
)
_SOURCE = Path(__file__).resolve()
_LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
           for path in (_SOURCE, Path(baseline.__file__).resolve())}
METRICS = ('path_return_net', 'path_max_drawdown', 'annualized_return_252_session',
           'total_fees_usd', 'risk_failure_days', 'trade_execution_count',
           'rejected_execution_count')


def read_baseline(case_index):
    if type(case_index) is not int or not 0 <= case_index < len(BASELINE_DIGESTS):
        raise ValueError('Explicit case index required')
    path = ROOT/'data/cache/research/ndx_joint_weight_experiment_v2'/f'v3_same_execution_case{case_index}_20260911.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASELINE_DIGESTS[case_index]:
        raise ValueError('Baseline report identity differs')
    report = json.loads(raw)
    if baseline.encoding._json_bytes(report) != raw or report['case_index'] != case_index:
        raise ValueError('Baseline encoding/case differs')
    baseline._check_sources(report['source_hashes'])
    return report, path


def path_summary(path):
    result = {key: path[key] for key in METRICS}
    supplemental_dates = {row['decision_date'] for row in path.get('decision_lineage', [])
                          if row['decision_kind'] == 'ONE_REPLAN_AFTER_CASH_REJECTION'}
    recovered = [row for row in path['executions'] if row['decision_date'] in supplemental_dates]
    targets = {row['decision_date']: row['target_weights'] for row in path['decisions']}
    target, tracking = None, []
    for row in path['daily']:
        target = targets.get(row['date'], target)
        if target is None:
            continue
        equity, cash = row['equity_usd'], row['cash_usd']
        buffer = path['minimum_cash_buffer_usd']
        tracking.append(sum((row['security_weights'][ticker]*(equity-cash)/equity
                             - weight*(equity-buffer)/equity)**2
                            for ticker, weight in target.items()) + ((cash-buffer)/equity)**2)
    result.update(
        first_filled_session=next((row['execution_date'] for row in path['executions']
                                  if row['status'] == 'FILLED'), None),
        all_cash_days=sum(sum(row['shares'].values()) == 0 for row in path['daily']),
        invested_risk_failure_days=sum(not row['all_constraints_passed'] and
                                      sum(row['shares'].values()) > 0 for row in path['daily']),
        decision_count=len(path['decisions']),
        supplemental_decision_count=len(supplemental_dates),
        supplemental_filled_count=sum(row['status'] == 'FILLED' for row in recovered),
        supplemental_no_trade_count=sum(row['status'] == 'NO_TRADE_REQUIRED' for row in recovered),
        supplemental_rejected_count=sum(row['status'].startswith('REJECTED') for row in recovered),
        mean_cash_inclusive_tracking_error=sum(tracking)/len(tracking) if tracking else None,
        tracking_observation_count=len(tracking),
        any_partial_search=path['any_partial_search'],
        any_unresolved_decision=path['any_unresolved_decision'])
    return result


def compare_reports(before, after):
    # These inputs must not change alongside the sole recovery-policy change.
    for key in ('case_index', 'preparation', 'periodic_clock', 'calendar',
                'inherited_context_capital_usd', 'nav_benchmark', 'corporate_actions',
                'nominal_bundle', 'risk_overlay'):
        if baseline.encoding._json_bytes(before[key]) != baseline.encoding._json_bytes(after[key]):
            raise ValueError('A/B input differs: ' + key)
    result = {}
    for role in ('candidate', 'incumbent'):
        a, b = before[role], after[role]
        lineage = b.get('decision_lineage')
        if lineage is not None:
            if len(lineage) != len(b['decisions']):
                raise ValueError('A/B decision lineage length differs')
            original = []
            for decision, origin in zip(b['decisions'], lineage):
                if origin['decision_date'] != decision['decision_date']:
                    raise ValueError('A/B decision lineage date differs')
                if origin['decision_kind'] == 'ORIGINAL_SCHEDULE':
                    original.append((decision['decision_date'], decision['target_weights']))
            if original != [(row['decision_date'], row['target_weights']) for row in a['decisions']]:
                raise ValueError('A/B original decision targets differ')
        for key in ('initial_equity_usd', 'minimum_cash_buffer_usd', 'transaction_cost_bps',
                    'constraints', 'risk_chain_by_ticker', 'domain_radius',
                    'max_evaluations_per_rebalance', 'selection_policy'):
            if a[key] != b[key]:
                raise ValueError('A/B execution contract differs: ' + key)
        result[role] = dict(baseline=path_summary(a), one_replan=path_summary(b),
                           delta={key: b[key]-a[key] for key in METRICS})
    return result


def run(case_index=0):
    baseline._check_sources(_LOADED)
    before, before_path = read_baseline(case_index)
    from backtest.ndx_cash_rejection_replan_research import simulate_cash_rejection_replan
    from backtest.ndx_incumbent_cash_rejection_replan_research import simulate_fixed_weight_incumbent_replan
    original_globals = dict(baseline.__dict__)
    bindings = dict(baseline.run.__globals__)
    bindings.update(simulate_next_session_execution_research_v2=simulate_cash_rejection_replan,
                    simulate_fixed_weight_incumbent_control_v2=simulate_fixed_weight_incumbent_replan)
    private_run = FunctionType(baseline.run.__code__, bindings)
    report = private_run(case_index)
    if any(baseline.__dict__.get(key) is not value for key, value in original_globals.items()):
        raise ValueError('Baseline module globals mutated')
    for role in ('candidate', 'incumbent'):
        if report[role].get('recovery_policy') != 'ONE_REPLAN_AFTER_CASH_REJECTION':
            raise ValueError('Both roles require identical replan policy')
    comparison = compare_reports(before, report)
    for path, digest in {**_LOADED, str(before_path): BASELINE_DIGESTS[case_index],
                         **before['source_hashes']}.items():
        if path in report['source_hashes'] and report['source_hashes'][path] != digest:
            raise ValueError('Conflicting A/B source binding')
        report['source_hashes'][path] = digest
    report.update(schema='ndx_cash_rejection_replan_probe_v1',
        recovery_policy='ONE_REPLAN_AFTER_CASH_REJECTION',
        sole_experimental_change='ONE_EXTRA_QUANTITY_DECISION_AFTER_CASH_REJECTION',
        baseline_reference=dict(path=str(before_path), sha256=BASELINE_DIGESTS[case_index]),
        baseline_recomputed=False, comparison=comparison,
        promotion_allowed=False, order_generation_allowed=False)
    baseline._check_sources(report['source_hashes'])
    return report


def compact(report):
    result = baseline.compact(report)
    result.update(schema='ndx_cash_rejection_replan_compact_v1',
                  recovery_policy=report['recovery_policy'],
                  baseline_reference=report['baseline_reference'],
                  baseline_recomputed=False, comparison=report['comparison'])
    return result


def run_and_export(case_index=0, output_path=None):
    bindings = dict(baseline.run_and_export.__globals__)
    bindings.update(run=run, compact=compact)
    return FunctionType(baseline.run_and_export.__code__, bindings)(case_index, output_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-index', type=int, default=0)
    parser.add_argument('--output-path')
    arguments = parser.parse_args()
    print(json.dumps(run_and_export(arguments.case_index, arguments.output_path), indent=2))
