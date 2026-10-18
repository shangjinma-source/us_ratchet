"""Versioned research evaluator with independently certified reconstruction.

The isolated probe supplies the numerical chain. Original v1/v2 module globals
and checkpoints remain untouched; numerical completion is not qualification.
"""
import hashlib
from pathlib import Path

from backtest import ndx_joint_weight_evaluation_v2 as previous_evaluation
from backtest import ndx_joint_weight_runner_v2 as previous_runner
from scripts import ndx_projection_reconstruction_probe as probe

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = tuple(sorted(set(previous_runner.NUMERICAL_SOURCES) | {
    'backtest/ndx_joint_weight_evaluation_v3.py',
    'backtest/ndx_joint_weight_runner_v3.py',
    'scripts/ndx_projection_reconstruction_probe.py',
    'backtest/ndx_projection_reconstruction_research.py',
    'backtest/ndx_projection_certificate_research.py',
    'scripts/ndx_joint_weight_verify.py',
    'scripts/ndx_joint_weight_progress.py',
    'scripts/ndx_joint_weight_batch.py',
    'backtest/ndx_joint_weight_history_inputs.py',
    'backtest/ndx_cardinality_capital_replay_summary.py',
    'data/ndx_security_identity.py', 'data/versioning.py', 'core/helpers.py',
}))


def source_hashes():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_PATHS}


_LOADED_SOURCES = source_hashes()


def _validate_loaded_sources():
    if (source_hashes() != _LOADED_SOURCES
            or previous_evaluation.source_hashes() != previous_evaluation._LOADED_SOURCES
            or previous_runner.source_hashes() != previous_runner._LOADED_SOURCE_HASHES
            or probe.LOADED_RESEARCH_SOURCES != {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in probe.RESEARCH_PATHS}):
        raise ValueError('V3 evaluator sources changed since import')


def evaluate_joint_weight_task_v3(task, **prepared_inputs):
    _validate_loaded_sources()
    try:
        evaluated = probe.evaluate_reconstructed(task, prepared_inputs)
        result = dict(evaluated['result'])
        if 'projection_reconstruction_audit' in result:
            raise ValueError('Unexpected preexisting reconstruction audit')
        attempts = evaluated['reconstruction_attempts']
        result['projection_reconstruction_audit'] = dict(
            schema='ndx_projection_reconstruction_audit_v1',
            scope='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION',
            attempt_count=len(attempts), attempts=attempts,
            prior_results_reused=False, promotion_allowed=False)
        return result
    finally:
        if source_hashes() != _LOADED_SOURCES:
            raise ValueError('V3 evaluator sources changed during evaluation')
