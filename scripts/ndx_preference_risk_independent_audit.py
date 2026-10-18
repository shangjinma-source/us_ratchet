"""Remeasure five original risk constraints from saved share/price arithmetic."""
import hashlib
import json
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = ROOT / 'data/cache/research/dynamic_frozen_v2/preference_retrospective_accounting_20260912.json'
ACCOUNT_SHA = '3b0fd632ba5c53839b90199d7edf74dafdc73bdc9b3369d09bef24fdae177e59'
SCHEDULE = ROOT / 'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json'
SCHEDULE_SHA = '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559'


def measure(notionals, chains, limits):
    assert notionals and set(notionals) == set(chains)
    assert all(math.isfinite(value) and value > 0 for value in notionals.values())
    invested = sum(notionals.values())
    weights = {sid: value / invested for sid, value in notionals.items()}
    ordered = sorted(weights.values(), reverse=True)
    grouped = {}
    for sid, weight in weights.items():
        grouped[chains[sid]] = grouped.get(chains[sid], 0.0) + weight
    neff = 1 / sum(weight * weight for weight in ordered)
    measures = dict(top1_weight=max(ordered), minimum_single_weight=min(ordered),
        top3_weight=sum(ordered[:3]), effective_n=neff, risk_chain_top1_weight=max(grouped.values()))
    checks = {'MAX_SINGLE_WEIGHT': measures['top1_weight'] <= limits['max_single_weight'] + 1e-9,
        'MIN_SINGLE_WEIGHT': measures['minimum_single_weight'] >= limits['min_single_weight'] - 1e-9,
        'SECURITY_TOP3_WEIGHT': measures['top3_weight'] <= limits['top_weight_cap'] + 1e-9,
        'MINIMUM_EFFECTIVE_N': neff >= limits['minimum_effective_n_ratio'] * len(weights) - 1e-9,
        'RISK_CHAIN_TOP1_WEIGHT': measures['risk_chain_top1_weight'] <= limits['risk_chain_top1_cap'] + 1e-9}
    return dict(measures, actual_weights=weights, checks=checks, all_passed=all(checks.values()),
                invested_value_denominator=invested, cash_in_denominator=False)


def main():
    sources = {str(ACCOUNT): ACCOUNT_SHA, str(SCHEDULE): SCHEDULE_SHA,
               str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def verify():
        for path, digest in sources.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
    verify()
    report = json.loads(ACCOUNT.read_bytes())
    for path, digest in report['source_hashes'].items():
        assert path not in sources or sources[path] == digest
        sources[path] = digest
    verify()
    built = json.loads(SCHEDULE.read_bytes())['schedule_result']
    limits = built['fixed_risk_parameters']
    assert limits == {'max_single_weight': .45, 'min_single_weight': .05, 'minimum_effective_n_ratio': .7,
                      'risk_chain_top1_cap': .55, 'top_weight_cap': .8}
    engine = report['execution']
    results = []
    def audit(label, session, notionals, chains, stored=None):
        value = measure(notionals, chains, limits)
        if stored is not None:
            assert value['checks'] == stored['checks'] and value['all_passed'] == stored['all_passed']
            for key in ('top1_weight', 'minimum_single_weight', 'top3_weight', 'effective_n', 'risk_chain_top1_weight'):
                assert abs(value[key] - stored[key]) < 1e-12
            assert value['actual_weights'] == stored['actual_weights']
        results.append(dict(kind=label, session=session, **value))
    all_cash = 0
    for row in engine['daily']:
        if not row['shares']:
            assert row['risk'] == {'all_passed': False, 'checks': {'ALL_CASH': False}}
            all_cash += 1
            continue
        latest = max(day for day in built['risk_chains_by_decision'] if day <= row['session'])
        chains = built['risk_chains_by_decision'][latest]
        assert row['risk_chains'] == chains
        assert set(row['risk_chain_observation_dates'].values()) == {latest}
        audit('DAILY_CLOSE_HOLDINGS', row['session'],
            {sid: shares * row['prices'][sid] for sid, shares in row['shares'].items()}, chains, row['risk'])
    for row in engine['decisions']:
        chains = built['risk_chains_by_decision'][row['decision_date']]
        audit('DECISION_STRATEGIC_TARGET', row['decision_date'],
              {sid: target['target_weight'] for sid, target in row['targets'].items()}, chains)
        audit('DECISION_FROZEN_LOTS_AT_CLOSE', row['decision_date'],
              {sid: shares * row['prices'][sid] for sid, shares in row['desired_shares'].items()}, chains, row['decision_risk'])
    for row in engine['executions']:
        chains = built['risk_chains_by_decision'][row['decision_date']]
        audit('NEXT_OPEN_FROZEN_LOTS', row['session'],
              {sid: shares * row['prices'][sid] for sid, shares in row['desired_shares'].items()}, chains, row['risk'])
    summary = {}
    for row in results:
        tally = summary.setdefault(row['kind'], {'evaluated': 0, 'all_passed': 0, 'failed': 0})
        tally['evaluated'] += 1
        tally['all_passed' if row['all_passed'] else 'failed'] += 1
    output = {'schema': 'ndx_preference_risk_independent_audit_v1', 'status': 'PASS', 'limits': limits,
        'summary': summary, 'all_cash_sessions_excluded_from_five_risk_pass_count': all_cash,
        'risk_denominator': 'INVESTED_STOCK_NOTIONAL_EXCLUDING_CASH', 'tolerance': 1e-9,
        'engine_rerun': False, 'risk_helper_called': False, 'source_hashes': sources,
        'rows': results, 'point_in_time_verified': False, 'promotion_allowed': False,
        'eight_dimension_training_gate_evaluated': False, 'dual_benchmark_completed': False}
    verify()
    path = ACCOUNT.with_name('preference_retrospective_risk_independent_audit_20260912.json')
    with path.open('x', encoding='utf8') as handle:
        json.dump(output, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    verify()
    print(json.dumps({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'summary': summary}))


if __name__ == '__main__':
    main()
