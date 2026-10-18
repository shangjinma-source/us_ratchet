"""Replay a source-bound prior execution comparison using next-session fills."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_joint_weight_runner as encoding
from backtest import ndx_joint_weight_runner_v2 as runner
from backtest.ndx_integer_allocation_research import RISK_FIELDS
from backtest.ndx_next_session_execution_research import simulate_next_session_execution_research
from scripts.ndx_joint_weight_verify import _restore_input


def run(comparison_path, expected_comparison_sha256):
    path = Path(comparison_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_comparison_sha256:
        raise ValueError('Comparison artifact identity differs')
    comparison = json.loads(raw)
    if comparison.get('schema') != 'ndx_integer_execution_comparison_v1':
        raise ValueError('Explicit original comparison required')
    required_sources = {str(ROOT/p) for p in (
        'scripts/ndx_integer_execution_comparison.py','scripts/ndx_whole_lot_failure_probe.py',
        'scripts/ndx_joint_weight_verify.py','scripts/ndx_joint_weight_progress.py',
        'backtest/ndx_periodic_execution_clock.py','backtest/ndx_integer_allocation_research.py',
        'backtest/ndx_integer_rebalance_research.py','config/config.yaml',
        'data/state.json','data/broker_positions.json')}
    if set(comparison['source_hashes']) != required_sources:
        raise ValueError('Incomplete comparison source binding')
    source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def check_sources():
        if (runner.source_hashes() != comparison['numerical_sources']
                or runner.source_hashes() != runner._LOADED_SOURCE_HASHES
                or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h
                       for p,h in comparison['source_hashes'].items())
                or path.read_bytes() != raw
                or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != source):
            raise ValueError('Comparison source drift')
    check_sources()
    context_path = runner.CHECKPOINT_ROOT/comparison['context_sha256']/'context.json'
    context_raw = context_path.read_bytes()
    context = json.loads(context_raw)
    if (encoding._sha(context) != comparison['context_sha256']
            or context['numerical_sources'] != comparison['numerical_sources']):
        raise ValueError('Input context identity differs')
    tasks = context['tasks']
    if not isinstance(tasks,list) or not tasks or len({t['job_id'] for t in tasks}) != len(tasks):
        raise ValueError('Invalid task denominator')
    selected = [t for t in tasks if t['job_id'] == comparison['job_id']]
    if len(selected) != 1:
        raise ValueError('Explicit task not found')
    task = selected[0]
    encoding._validate_task(task)
    inputs = {k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
    names = sorted(task['tickers'].split(';'))
    prices = inputs['nominal_prices'].loc[comparison['date_start']:comparison['date_end'],names]
    if (len(prices) != comparison['day_count'] or str(prices.index[0].date()) != comparison['date_start']
            or str(prices.index[-1].date()) != comparison['date_end']):
        raise ValueError('Execution interval differs')
    contract = inputs['contract']
    schedule = [(r['execution_date'],r['weights']) for r in comparison['periodic_clock']['schedule']]
    if not schedule or schedule[0][0] != comparison['date_start']:
        raise ValueError('Schedule must begin on comparison start')
    results = []
    for policy in ('TRACKING_FIRST','FEES_FIRST'):
        results.append(simulate_next_session_execution_research(
            prices=prices, execution_calendar=prices.index, schedule=schedule,
            initial_cash=contract['portfolio_cash_usd'], initial_shares={t:0 for t in names},
            minimum_cash_buffer_usd=contract['minimum_cash_buffer_usd'],
            transaction_cost_bps=contract['transaction_cost_bps'],
            risk_chain_by_ticker=inputs['universe'].set_index('ticker').loc[names,'risk_chain'].to_dict(),
            constraints={k:contract[k] for k in RISK_FIELDS}, domain_radius=2,
            max_evaluations_per_rebalance=1000000, selection_policy=policy))
    check_sources()
    if context_path.read_bytes() != context_raw:
        raise ValueError('Input context changed')
    return dict(schema='ndx_next_session_execution_probe_v1', comparison_sha256=hashlib.sha256(raw).hexdigest(),
        comparison_path=str(path.resolve()), probe_source_sha256=source,
        context_sha256=comparison['context_sha256'], job_id=comparison['job_id'],
        date_start=comparison['date_start'], date_end=comparison['date_end'],
        domain_radius=2, max_evaluations_per_rebalance=1000000,
        paths=results, scope='SAME_HISTORICAL_FIXED_COMPOSITION_EXECUTION_TIMING_RESEARCH',
        promotion_allowed=False, order_generation_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison',required=True)
    parser.add_argument('--expected-comparison-sha256',required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.comparison,arguments.expected_comparison_sha256),ensure_ascii=False,indent=2))
