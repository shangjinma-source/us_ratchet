"""Compare fixed historical execution policies on exactly the same date range."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_whole_lot_failure_probe import run as observe
from scripts.ndx_joint_weight_verify import _restore_input
from backtest import ndx_joint_weight_runner as encoding
from backtest import ndx_joint_weight_runner_v2 as runner
from backtest.ndx_periodic_execution_clock import build_periodic_execution_schedule, PARAMETERS
from backtest.ndx_integer_allocation_research import RISK_FIELDS
from backtest.ndx_integer_rebalance_research import simulate_integer_rebalance_research


def run(context_sha256, job_id, *, domain_radius, max_evaluations_per_rebalance):
    watched = [Path(__file__)] + [ROOT / p for p in (
        'scripts/ndx_whole_lot_failure_probe.py', 'scripts/ndx_joint_weight_verify.py',
        'scripts/ndx_joint_weight_progress.py',
        'backtest/ndx_periodic_execution_clock.py', 'backtest/ndx_integer_allocation_research.py',
        'backtest/ndx_integer_rebalance_research.py', 'config/config.yaml',
        'data/state.json', 'data/broker_positions.json')]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    numerical_sources = runner.source_hashes()
    baseline = observe(context_sha256, job_id)
    context_path = runner.CHECKPOINT_ROOT / context_sha256 / 'context.json'
    context_raw = context_path.read_bytes()
    context = json.loads(context_raw)
    if encoding._sha(context) != context_sha256:
        raise ValueError('Context changed after baseline observation')
    task = next(t for t in context['tasks'] if t['job_id'] == job_id)
    inputs = {k: _restore_input(v) for k, v in context['prepared_inputs'].items()}
    days = baseline['observation']['attribution']['daily']
    start, end = days[0]['date'], days[-1]['date']
    names = sorted(task['tickers'].split(';'))
    labels = inputs['universe'].set_index('ticker').loc[names, 'risk_chain'].to_dict()
    contract = inputs['contract']
    clock = build_periodic_execution_schedule(returns=inputs['returns'], tickers=names,
        fit_days=contract['fit_days'], step_days=contract['step_days'], execution_end=end,
        weight_spec=task['weight_spec'], risk_chain_by_ticker=labels,
        projection_parameters={k: contract[k] for k in PARAMETERS})
    schedules = {
        'LEGACY_STATISTICAL_WINDOW_STARTS': [(d['date'], d['rebalance_target_weights'])
            for d in days if d['phase'] == 'REBALANCE_DAY'],
        'PERIODIC_EXECUTION_CLOCK': [(r['execution_date'], r['weights']) for r in clock['schedule']],
    }
    prices = inputs['nominal_prices'].loc[start:end, names]
    execution_dates = [str(date.date()) for date in prices.index]
    if execution_dates != [d['date'] for d in days]:
        raise ValueError('Comparison execution calendar differs from baseline')
    if any(not schedule or schedule[0][0] != start for schedule in schedules.values()):
        raise ValueError('Comparison schedules must begin on baseline start')
    rows = []
    for clock_name, schedule in schedules.items():
        for policy in ('TRACKING_FIRST', 'FEES_FIRST'):
            result = simulate_integer_rebalance_research(
                prices=prices, schedule=schedule,
                initial_cash=contract['portfolio_cash_usd'], initial_shares={t: 0 for t in names},
                minimum_cash_buffer_usd=contract['minimum_cash_buffer_usd'],
                transaction_cost_bps=contract['transaction_cost_bps'], risk_chain_by_ticker=labels,
                constraints={k: contract[k] for k in RISK_FIELDS}, domain_radius=domain_radius,
                max_evaluations_per_rebalance=max_evaluations_per_rebalance, selection_policy=policy)
            rows.append(dict(clock=clock_name, **{k: v for k, v in result.items() if k != 'daily'},
                risk_failure_days=sum(not r['all_constraints_passed'] for r in result['daily']),
                risk_failures=[r for r in result['daily'] if not r['all_constraints_passed']],
                first_risk_failure=next((r for r in result['daily'] if not r['all_constraints_passed']), None)))
    if runner.source_hashes() != numerical_sources or context_path.read_bytes() != context_raw or before != {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}:
        raise ValueError('Comparison sources changed')
    return dict(schema='ndx_integer_execution_comparison_v1', context_sha256=context_sha256,
        job_id=job_id, date_start=start, date_end=end, day_count=len(days),
        baseline_floor_risk_failure_days=sum(bool(d['failures']) for d in days),
        baseline_whole_lot_fields={k: v for k, v in baseline['result'].items() if k.startswith('whole_lot_')},
        periodic_clock=clock, paths=rows, source_hashes=before, numerical_sources=numerical_sources,
        scope='ONE_HISTORICAL_FIXED_COMPOSITION_EXECUTION_COMPARISON',
        future_performance_proven=False, promotion_allowed=False, order_generation_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--domain-radius', required=True, type=int)
    parser.add_argument('--max-evaluations-per-rebalance', required=True, type=int)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.context, arguments.job_id, domain_radius=arguments.domain_radius,
        max_evaluations_per_rebalance=arguments.max_evaluations_per_rebalance), ensure_ascii=False, indent=2))
