"""Read-only complete-coordinate overlap using the isolated reconstruction probe."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_projection_reconstruction_probe import run as probe
from scripts.ndx_joint_weight_progress import Snapshot, RETURN_FIELDS, DRAWDOWN_FIELDS
from scripts.ndx_joint_weight_verify import _restore
from backtest import ndx_joint_weight_runner as encoding
from backtest import ndx_joint_weight_runner_v2 as runner


def run(context_sha256):
    if not isinstance(context_sha256, str) or len(context_sha256) != 64 or any(
            c not in '0123456789abcdef' for c in context_sha256):
        raise ValueError('Canonical v2 context required')
    source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    snapshot = Snapshot()
    directory = runner.CHECKPOINT_ROOT/context_sha256
    context = snapshot.read(directory/'context.json')
    if (encoding._sha(context) != context_sha256
            or set(context) != {'schema','tasks','prepared_inputs','source_evidence','numerical_sources','runtime'}
            or context.get('schema') != 'ndx_joint_weight_checkpoint_v1'):
        raise ValueError('Context identity differs')
    if (not isinstance(context['tasks'], list) or not context['tasks']
            or len({t['job_id'] for t in context['tasks']}) != len(context['tasks'])):
        raise ValueError('Invalid task denominator')
    names = snapshot.directory(directory)
    expected = {'context.json'} | {t['job_id']+'.json' for t in context['tasks']}
    if not names <= expected:
        raise ValueError('Unexpected context files')
    rows = []
    experiment_sources = None
    for task in context['tasks']:
        previous = None
        filename = task['job_id']+'.json'
        if filename in names:
            checkpoint = snapshot.read(directory/filename)
            checksum = checkpoint.pop('checkpoint_sha256', None)
            if (set(checkpoint) != {'context_sha256','task','status','result'}
                    or encoding._sha(checkpoint) != checksum or checkpoint.get('context_sha256') != context_sha256
                    or checkpoint.get('status') != 'EVALUATED'
                    or encoding._json_bytes(checkpoint.get('task')) != encoding._json_bytes(task)):
                raise ValueError('Prior checkpoint identity differs')
            previous = _restore(checkpoint['result'])
            if encoding._json_bytes(encoding._normalize(previous)) != encoding._json_bytes(checkpoint['result']):
                raise ValueError('Prior result encoding differs')
            if (previous.get('tickers') != task['tickers'] or previous.get('weight_spec') != task['weight_spec']
                    or type(previous.get('holding_count')) is not int or previous['holding_count'] != task['holding_count']):
                raise ValueError('Prior result identity differs')
            for key in RETURN_FIELDS+DRAWDOWN_FIELDS:
                if type(previous[key]) not in (int,float) or not math.isfinite(previous[key]):
                    raise ValueError('Invalid prior metric')
            for key in ('declared_constraints_passed','whole_lot_executable_all_windows'):
                if type(previous[key]) is not bool:
                    raise ValueError('Invalid prior boolean')
        observed = probe(context_sha256, task['job_id'])
        bindings = dict(source_hashes=observed['source_hashes'],
                        numerical_sources=observed['original_numerical_sources'], runtime=observed['current_runtime'])
        if experiment_sources is not None and bindings != experiment_sources:
            raise ValueError('Mixed evaluation sources in coordinate')
        experiment_sources = bindings
        result = observed['result']
        rows.append(dict(job_id=task['job_id'], tickers=task['tickers'], weight_spec=task['weight_spec'],
            had_previous_result=previous is not None,
            previous_result_exactly_unchanged=None if previous is None else
                encoding._json_bytes(encoding._normalize(previous)) == encoding._json_bytes(encoding._normalize(result)),
            result_sha256=encoding._sha(encoding._normalize(result)),
            metrics={key: result[key] for key in RETURN_FIELDS+DRAWDOWN_FIELDS},
            declared_constraints_passed=result['declared_constraints_passed'],
            constraint_failure_reasons=result['constraint_failure_reasons'],
            reconstruction_attempts=observed['reconstruction_attempts']))
    snapshot.verify()
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != source:
        raise ValueError('Overlap source changed')
    return dict(schema='ndx_projection_reconstruction_overlap_v1', context_sha256=context_sha256,
        planned=len(context['tasks']), evaluated=len(rows), rows=rows, experiment_sources=experiment_sources,
        overlap_source_sha256=source, old_results_reused=False, checkpoint_created=False,
        scope='ONE_COMPLETE_COORDINATE_NOT_GLOBAL_BATCH', promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.context), ensure_ascii=False, indent=2))
