"""Version-isolated research checkpoints for the analytic projection evaluator."""
import hashlib
from pathlib import Path

from backtest import ndx_joint_weight_runner as original
from backtest import ndx_joint_weight_evaluation_v2 as evaluation

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_ROOT = ROOT / 'data/cache/research/ndx_joint_weight_runs_v2'
NUMERICAL_SOURCES = tuple(sorted(set(original.NUMERICAL_SOURCES) | set(evaluation.SOURCE_PATHS) | {
    'backtest/ndx_joint_weight_runner_v2.py'}))


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in NUMERICAL_SOURCES}


_LOADED_SOURCE_HASHES = source_hashes()
_RUN = evaluation._bind(original.run_joint_weight_tasks,
    evaluate_joint_weight_task=evaluation.evaluate_joint_weight_task_v2,
    _source_hashes=source_hashes, _LOADED_SOURCE_HASHES=_LOADED_SOURCE_HASHES,
    CHECKPOINT_ROOT=CHECKPOINT_ROOT)


def run_joint_weight_tasks_v2(tasks, *, prepared_inputs, source_evidence, max_tasks=None):
    return _RUN(tasks, prepared_inputs=prepared_inputs,
                source_evidence=source_evidence, max_tasks=max_tasks)
