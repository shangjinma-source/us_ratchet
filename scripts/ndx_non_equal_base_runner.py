"""Create-only checkpoints for independent non-equal base research tasks."""
import argparse
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import scipy
from scripts import ndx_non_equal_base_inputs as preparation
from backtest import ndx_non_equal_fractional_research as evaluator
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore

_SOURCE = Path(__file__).resolve()
_LOADED = {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
           for path in (__file__, preparation.__file__, evaluator.__file__)}


def _bytes(value):
    return encoding._json_bytes(value)


def _sha(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _verify_sources(sources):
    for path, digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Research source drift: ' + path)


def _read(path):
    raw = path.read_bytes()
    value = json.loads(raw)
    if _bytes(value) != raw:
        raise ValueError('Noncanonical research checkpoint')
    return value


def _publish(path, value):
    """Hard-link a flushed temporary file without replacing an existing path."""
    raw = _bytes(value)
    descriptor, temporary = tempfile.mkstemp(prefix='.publishing-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError('Create-only artifact already differs: ' + str(path))
    finally:
        Path(temporary).unlink(missing_ok=True)


def _output_root(value):
    path = Path(value)
    path = (ROOT/path).resolve() if not path.is_absolute() else path.resolve()
    research = (ROOT/'data/cache/research').resolve()
    if path == research or not path.is_relative_to(research):
        raise ValueError('Output must be a named directory beneath data/cache/research')
    # Never append an independent runner to the frozen task namespaces.
    if any(part.startswith('ndx_joint_weight_runs') or part.startswith('ndx_joint_weight_batches')
           for part in path.relative_to(research).parts):
        raise ValueError('Frozen delta namespaces cannot be used as output')
    return path


def _validate_result(result, task, numerical_sources):
    if (type(result) is not dict or result.get('schema') != 'ndx_non_equal_fractional_research_v1'
            or result.get('whole_lot_status') != 'NOT_EVALUATED'
            or result.get('continuous_whole_lot_executed') is not False
            or result.get('aggregate_declared_gate_available') is not False
            or result.get('promotion_allowed') is not False
            or result.get('source_hashes') != numerical_sources):
        raise ValueError('Invalid fractional result scope/source')
    for key in ('source_authenticity_verified','point_in_time_verified','full_legacy_result_compatible',
                'saved_weights_are_current_targets','historical_minimum_weight_verified'):
        if result.get(key) is not False:
            raise ValueError('Unexpected fractional scope claim: '+key)
    if result.get('independent_floor_diagnostics_discarded') is not True:
        raise ValueError('Independent floor diagnostics must be discarded')
    metrics = result['result']
    if type(metrics) is not dict or any(metrics.get(k) != task[k] for k in ('tickers', 'holding_count', 'weight_spec')):
        raise ValueError('Fractional result/task identity differs')
    if type(metrics.get('holding_count')) is not int:
        raise ValueError('Result cardinality must be integer')
    for key in ('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90',
                'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
                'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent',
                'return_p50_vs_012922','return_p10_vs_012922',
                'max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922','target_012922_distance'):
        if type(metrics.get(key)) not in (int,float) or not math.isfinite(metrics[key]):
            raise ValueError('Missing/nonfinite fractional metric: '+key)
    for key in ('declared_max_single_passed','declared_security_top3_weight_passed',
                'declared_risk_chain_top1_weight_passed','declared_effective_n_passed',
                'liquidity_constraint_passed','fit_strictly_before_evaluation',
                'risk_chain_projection_relaxed_any_window','structural_single_cap_relaxation'):
        if type(metrics.get(key)) is not bool:
            raise ValueError('Missing/nonboolean fractional observation: '+key)
    if any(k.startswith('whole_lot_') or k in ('declared_constraints_passed', 'constraint_failure_reasons') for k in metrics):
        raise ValueError('Unexpected whole-lot result claim')
    if (type(metrics.get('rolling_fit_window_count')) is not int
            or metrics['rolling_fit_window_count'] < 1
            or type(result.get('historical_window_weights')) is not list
            or len(result['historical_window_weights']) != metrics['rolling_fit_window_count']):
        raise ValueError('Fractional result window coverage differs')
    names = task['tickers'].split(';')
    previous_end = None
    cutoff = date.fromisoformat(task['decision_data_end'])
    for window in result['historical_window_weights']:
        if type(window) is not dict or window.get('tickers') != names:
            raise ValueError('Historical window ticker coverage differs')
        parsed = []
        for key in ('fit_start','fit_end'):
            value = window.get(key)
            if type(value) is not str or date.fromisoformat(value).isoformat() != value:
                raise ValueError('Canonical historical fit dates required')
            parsed.append(date.fromisoformat(value))
        start, end = parsed
        if start > end or end >= cutoff or (previous_end is not None and end <= previous_end):
            raise ValueError('Historical fit dates outside ordered cutoff interval')
        previous_end = end
        if type(window.get('fit_row_count')) is not int or window['fit_row_count'] < 1:
            raise ValueError('Historical fit row count required')
        for key in ('weights','anchor_weights'):
            weights = window.get(key)
            if key == 'anchor_weights' and weights is None:
                continue
            if (type(weights) is not dict or set(weights) != set(names)
                    or any(type(value) not in (int,float) or not math.isfinite(value) or value < 0
                           for value in weights.values())
                    or not math.isclose(sum(weights.values()),1.,rel_tol=0,abs_tol=1e-9)):
                raise ValueError('Historical window weights invalid')
        strength = window.get('turnover_anchor_strength')
        if (type(strength) not in (int,float) or not math.isfinite(strength) or not 0 <= strength <= 1
                or type(window.get('risk_chain_projection_relaxed')) is not bool):
            raise ValueError('Historical fit policy observation invalid')
    audit = result['projection_reconstruction_audit']
    if (type(audit.get('attempt_count')) is not int or audit['attempt_count'] < 0
            or type(audit.get('attempts')) is not list or audit['attempt_count'] != len(audit['attempts'])):
        raise ValueError('Fractional reconstruction audit differs')
    encoding._normalize(result)  # Reject unsupported values and nonfinite floats.


def _read_checkpoint(path, context_sha, task, numerical):
    checkpoint = _read(path)
    digest = checkpoint.pop('checkpoint_sha256', None)
    if (set(checkpoint) != {'schema','context_sha256','task','status','result'}
            or checkpoint['schema'] != 'ndx_non_equal_base_checkpoint_v1'
            or _sha(checkpoint) != digest or checkpoint['context_sha256'] != context_sha
            or checkpoint['task'] != task or checkpoint['status'] != 'EVALUATED'):
        raise ValueError('Resume checkpoint binding differs')
    result = _restore(checkpoint['result'])
    if encoding._normalize(result) != checkpoint['result']:
        raise ValueError('Result typed encoding differs')
    _validate_result(result, task, numerical)
    return result


def run(*, source_batch, universe_track, selection_date, output_root,
        execute=False, resume=False, max_new_tasks=None):
    if type(execute) is not bool or type(resume) is not bool:
        raise ValueError('Explicit boolean execution options required')
    if max_new_tasks is not None and (type(max_new_tasks) is not int or max_new_tasks < 1):
        raise ValueError('Positive max-new-tasks required')
    destination_root = _output_root(output_root)
    _verify_sources(_LOADED)
    prepared = preparation.prepare_non_equal_base_date(source_batch=source_batch,
        universe_track=universe_track, selection_date=selection_date)
    numerical = evaluator._sources()
    sources = dict(_LOADED)
    for mapping in (prepared['source_hashes'], numerical):
        for path, digest in mapping.items():
            if path in sources and sources[path] != digest:
                raise ValueError('Conflicting runner source identity')
            sources[path] = digest
    tasks = prepared['tasks']
    if len({t['job_id'] for t in tasks}) != len(tasks):
        raise ValueError('Duplicate base task identity')
    for task in tasks:
        if task['schema_version'] != preparation.SCHEMA or preparation._sha({k:v for k,v in task.items() if k!='job_id'}) != task['job_id']:
            raise ValueError('Invalid independent base task identity')
    context = dict(schema='ndx_non_equal_base_context_v1', source_batch=source_batch,
        universe_track=universe_track, selection_date=selection_date, tasks=tasks,
        training_semantics=prepared['training_semantics'], source_hashes=sources,
        numerical_sources=numerical, planned=len(tasks),
        runtime=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__))
    context_sha = _sha(context)
    destination = destination_root/context_sha
    _verify_sources(sources)
    if not execute:
        return dict(status='PLAN_ONLY', planned=len(tasks), context_sha256=context_sha,
                    output_dir=str(destination), promotion_allowed=False)
    destination.mkdir(parents=True, exist_ok=True)
    attempted = resumed = completed = 0
    try:
        with encoding._lock(destination/'.lock'):
            _publish(destination/'context.json', context)
            for task in tasks:
                path = destination/(task['job_id']+'.json')
                if path.exists():
                    if not resume:
                        raise ValueError('Existing checkpoint requires explicit --resume')
                    _read_checkpoint(path, context_sha, task, numerical)
                    resumed += 1; completed += 1
                    if resumed % 50 == 0:
                        print(f'non-equal base resumed={resumed} completed={completed}/{len(tasks)}', flush=True)
                    continue
                if max_new_tasks is not None and attempted >= max_new_tasks:
                    continue
                attempted += 1
                print(f'non-equal base evaluating={task["job_id"]} completed={completed}/{len(tasks)}', flush=True)
                result = evaluator.evaluate_non_equal_fractional(task=task, inputs=prepared['inputs'])
                _validate_result(result, task, numerical)
                checkpoint = dict(schema='ndx_non_equal_base_checkpoint_v1', context_sha256=context_sha,
                    task=task, status='EVALUATED', result=encoding._normalize(result))
                checkpoint['checkpoint_sha256'] = _sha(checkpoint)
                _publish(path, checkpoint)
                saved = _read_checkpoint(path, context_sha, task, numerical)
                if _bytes(encoding._normalize(saved)) != _bytes(encoding._normalize(result)):
                    raise ValueError('Published result readback differs from evaluated result')
                completed += 1
                print(f'non-equal base completed={completed}/{len(tasks)} attempted={attempted}', flush=True)
    finally:
        _verify_sources(sources)
    return dict(status='COMPLETE' if completed==len(tasks) else 'PARTIAL', planned=len(tasks),
        attempted=attempted, resumed=resumed, completed=completed, context_sha256=context_sha,
        output_dir=str(destination), promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-batch', required=True)
    parser.add_argument('--universe-track', required=True)
    parser.add_argument('--selection-date', required=True)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--fail-fast', action='store_true', help='Always enabled; exceptions never become completed jobs')
    parser.add_argument('--max-new-tasks', type=int)
    args = vars(parser.parse_args()); args.pop('fail_fast')
    print(json.dumps(run(**args), indent=2), flush=True)
