"""Read-only v2 re-evaluation of explicitly selected v1 captured coordinates."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_joint_weight_runner as old
from backtest import ndx_joint_weight_evaluation_v2 as revised
from scripts.ndx_joint_weight_verify import _restore_input, _restore
from scripts.ndx_joint_weight_progress import Snapshot, RETURN_FIELDS, DRAWDOWN_FIELDS


def run(context_hashes):
    if not context_hashes or len(set(context_hashes)) != len(context_hashes):
        raise ValueError('Explicit unique v1 contexts required')
    snapshot = Snapshot()
    sources = revised.source_hashes()
    old_sources = old._source_hashes()
    if sources != revised._LOADED_SOURCES or old_sources != old._LOADED_SOURCE_HASHES:
        raise ValueError('Evaluator sources changed since import')
    rows = []
    for digest in context_hashes:
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Noncanonical context hash')
        directory = old.CHECKPOINT_ROOT / digest
        context = snapshot.read(directory / 'context.json')
        if (set(context) != {'schema', 'tasks', 'prepared_inputs', 'source_evidence', 'numerical_sources', 'runtime'}
                or context.get('schema') != 'ndx_joint_weight_checkpoint_v1'
                or not isinstance(context.get('tasks'), list) or not context['tasks']
                or len({t['job_id'] for t in context['tasks']}) != len(context['tasks'])):
            raise ValueError('Invalid context schema or duplicate/empty tasks')
        if old._sha(context) != digest or context['numerical_sources'] != old_sources:
            raise ValueError('V1 context source/identity mismatch')
        inputs = {key: _restore_input(value) for key, value in context['prepared_inputs'].items()}
        names = snapshot.directory(directory)
        expected = {'context.json'} | {t['job_id'] + '.json' for t in context['tasks']}
        if not names <= expected:
            raise ValueError('Unexpected checkpoint')
        for task in context['tasks']:
            old._validate_task(task)
            prior = None
            if task['job_id'] + '.json' in names:
                checkpoint = snapshot.read(directory / (task['job_id'] + '.json'))
                checksum = checkpoint.pop('checkpoint_sha256', None)
                if (set(checkpoint) != {'context_sha256', 'task', 'status', 'result'}
                        or old._sha(checkpoint) != checksum or checkpoint['context_sha256'] != digest
                        or old._json_bytes(checkpoint['task']) != old._json_bytes(task)
                        or checkpoint['status'] != 'EVALUATED'):
                    raise ValueError('V1 checkpoint binding mismatch')
                prior = _restore(checkpoint['result'])
                if old._json_bytes(old._normalize(prior)) != old._json_bytes(checkpoint['result']):
                    raise ValueError('V1 result encoding mismatch')
                if (prior.get('tickers') != task['tickers'] or prior.get('weight_spec') != task['weight_spec']
                        or type(prior.get('holding_count')) is not int or prior['holding_count'] != task['holding_count']):
                    raise ValueError('V1 result identity mismatch')
                for field in RETURN_FIELDS + DRAWDOWN_FIELDS:
                    if type(prior[field]) not in (int, float) or not math.isfinite(prior[field]):
                        raise ValueError('Invalid V1 metric')
                for field in ('declared_constraints_passed', 'whole_lot_executable_all_windows'):
                    if type(prior[field]) is not bool:
                        raise ValueError('Invalid V1 audit boolean')
            row = dict(context_sha256=digest, job_id=task['job_id'], tickers=task['tickers'],
                       weight_spec=task['weight_spec'], had_v1_checkpoint=prior is not None)
            try:
                result = revised.evaluate_joint_weight_task_v2(task, **inputs)
                row.update(status='V2_EVALUATED', declared_constraints_passed=result['declared_constraints_passed'],
                           constraint_failure_reasons=result['constraint_failure_reasons'])
                if prior is not None:
                    row['fractional_metric_absolute_difference'] = {
                        f: abs(result[f] - prior[f]) for f in RETURN_FIELDS + DRAWDOWN_FIELDS}
                    row['changed_audit_fields'] = [f for f in (
                        'declared_constraints_passed', 'constraint_failure_reasons', 'whole_lot_executable_all_windows')
                        if result[f] != prior[f]]
            except ValueError as error:
                row.update(status='V2_COMPUTATION_ERROR', error=str(error))
            rows.append(row)
    snapshot.verify()
    if revised.source_hashes() != sources or old._source_hashes() != old_sources:
        raise ValueError('V2 source changed during overlap')
    return dict(numerical_sources=sources, planned=len(rows),
                runtime=dict(python=old.platform.python_version(), numpy=old.np.__version__,
                             pandas=old.pd.__version__, scipy=old.scipy.__version__),
                evaluated=sum(r['status'] == 'V2_EVALUATED' for r in rows), rows=rows,
                prior_results_reused=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', action='append', required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.context), ensure_ascii=False, indent=2))
