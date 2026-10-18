"""Isolated research evaluator using analytic projection derivatives.

Rebind only the three explicit dependency edges in private function globals.
No existing module globals, live strategy, or historical checkpoint is changed.
"""
import hashlib
from pathlib import Path
from types import FunctionType

from backtest import ndx_cardinality_discovery as discovery
from backtest import ndx_joint_weight_evaluation as original
from backtest.ndx_concentration_projection_v2 import project_concentration_envelope_weights_v2

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    'backtest/ndx_joint_weight_evaluation_v2.py',
    'backtest/ndx_concentration_projection_v2.py',
    'backtest/ndx_joint_weight_evaluation.py',
    'backtest/ndx_cardinality_discovery.py',
    'backtest/ndx_whole_lot_rebalance.py',
    'backtest/weights.py',
)


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_PATHS}


def _bind(function, **dependencies):
    namespace = dict(function.__globals__)
    if not set(dependencies).issubset(namespace):
        raise ValueError('Unknown evaluator dependency')
    namespace.update(dependencies)
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return bound


_SHRINKAGE = _bind(discovery.constrained_fixed_shrinkage_weights,
    project_concentration_envelope_weights=project_concentration_envelope_weights_v2)
_PORTFOLIO = _bind(discovery.evaluate_synthetic_portfolio,
    constrained_fixed_shrinkage_weights=_SHRINKAGE)
_EVALUATE = _bind(original.evaluate_joint_weight_task,
    evaluate_synthetic_portfolio=_PORTFOLIO)
_LOADED_SOURCES = source_hashes()


def evaluate_joint_weight_task_v2(task, **prepared_inputs):
    if source_hashes() != _LOADED_SOURCES:
        raise ValueError('V2 evaluator sources changed since import')
    result = _EVALUATE(task, **prepared_inputs)
    if source_hashes() != _LOADED_SOURCES:
        raise ValueError('V2 evaluator sources changed during evaluation')
    return result
