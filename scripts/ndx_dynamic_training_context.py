"""Restore every task in an explicit v3 context without selecting a winner."""
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_joint_weight_runner as encoding
from backtest import ndx_joint_weight_runner_v3 as runner
from scripts.ndx_joint_weight_verify import _restore, _restore_input
from scripts.ndx_joint_weight_progress import RETURN_FIELDS, DRAWDOWN_FIELDS

_SOURCE = Path(__file__).resolve()
_LOADED = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def load_context(context_sha256):
    if type(context_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', context_sha256):
        raise ValueError('Explicit context SHA required')
    numerical = runner.source_hashes()
    if numerical != runner._LOADED_SOURCE_HASHES:
        raise ValueError('Numerical source drift')
    sources = {str(ROOT/path): digest for path, digest in numerical.items()}
    sources[str(_SOURCE)] = _LOADED
    directory = runner.CHECKPOINT_ROOT/context_sha256

    def read(path):
        raw = path.read_bytes()
        value = json.loads(raw)
        if encoding._json_bytes(value) != raw:
            raise ValueError('Noncanonical checkpoint JSON')
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return value

    context = read(directory/'context.json')
    if (encoding._sha(context) != context_sha256
            or context['schema'] != 'ndx_joint_weight_checkpoint_v1'
            or context['numerical_sources'] != numerical):
        raise ValueError('Context source binding differs')
    tasks = context['tasks']
    if not tasks or len({task['job_id'] for task in tasks}) != len(tasks):
        raise ValueError('Invalid task denominator')
    inputs = {key: _restore_input(value) for key, value in context['prepared_inputs'].items()}
    returns = inputs['returns']
    if (not isinstance(returns, pd.DataFrame) or returns.empty
            or not isinstance(returns.index, pd.DatetimeIndex)
            or returns.index.hasnans or returns.index.tz is not None
            or not returns.index.is_unique or not returns.index.is_monotonic_increasing
            or not returns.index.equals(returns.index.normalize())
            or not returns.columns.is_unique):
        raise ValueError('Canonical ordered training return panel required')
    records = []
    for task in tasks:
        encoding._validate_task(task)
        if str(returns.index[-1].date()) != task['decision_data_end']:
            raise ValueError('Return panel cutoff differs from decision')
        path = directory/(task['job_id']+'.json')
        if not path.exists():
            records.append(dict(task=task, status='MISSING_CHECKPOINT', result=None))
            continue
        checkpoint = read(path)
        digest = checkpoint.pop('checkpoint_sha256', None)
        if (set(checkpoint) != {'context_sha256','task','status','result'}
                or encoding._sha(checkpoint) != digest
                or checkpoint['context_sha256'] != context_sha256
                or encoding._json_bytes(checkpoint['task']) != encoding._json_bytes(task)
                or checkpoint['status'] != 'EVALUATED'):
            raise ValueError('Task checkpoint binding differs')
        result = _restore(checkpoint['result'])
        if encoding._json_bytes(encoding._normalize(result)) != encoding._json_bytes(checkpoint['result']):
            raise ValueError('Result encoding differs')
        if any(result.get(key) != task[key] for key in ('tickers','weight_spec','holding_count')):
            raise ValueError('Result portfolio identity differs')
        for field in RETURN_FIELDS+DRAWDOWN_FIELDS:
            if type(result[field]) not in (int,float) or not math.isfinite(result[field]):
                raise ValueError('Invalid training metric')
        for field in ('declared_constraints_passed','whole_lot_executable_all_windows'):
            if type(result[field]) is not bool:
                raise ValueError('Invalid training gate flag')
        records.append(dict(task=task, status='EVALUATED', result=result,
                            saved_weights_role='LAST_HISTORICAL_FIT_NOT_CURRENT_TARGET'))
    for path, digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Training source changed during restore')
    return dict(context_sha256=context_sha256, inputs=inputs, records=records,
        source_hashes=sources, summary=dict(planned=len(tasks),
            evaluated=sum(row['status']=='EVALUATED' for row in records),
            missing=sum(row['status']=='MISSING_CHECKPOINT' for row in records),
            declared_failure_rows_retained=sum(row['result'] is not None and
                not row['result']['declared_constraints_passed'] for row in records),
            source_batches=sorted({task['source_batch'] for task in tasks}),
            selection_dates=sorted({task['selection_date'] for task in tasks}),
            cardinalities=sorted({task['holding_count'] for task in tasks}),
            training_cutoff=str(returns.index[-1].date()),
            scope='ONE_EXPLICIT_CONTEXT_NOT_FULL_206_COORDINATE_DENOMINATOR',
            current_targets_refitted=False, portfolio_selected=False, promotion_allowed=False))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context-sha256', required=True)
    print(json.dumps(load_context(parser.parse_args().context_sha256)['summary'], indent=2))
