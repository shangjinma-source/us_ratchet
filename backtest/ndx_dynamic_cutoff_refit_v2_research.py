"""Latest-cutoff refit with the exact v3 certified projection recovery closure.

Reuse v1 date/identity/anchor validation unchanged. Only its numerical fitter
dependency is privately rebound; no historical evaluation weights are inputs.
"""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from backtest import ndx_dynamic_cutoff_refit_research as previous
from backtest import ndx_joint_weight_evaluation_v2 as binding
from backtest import ndx_joint_weight_evaluation_v3 as v3

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _sources():
    v3._validate_loaded_sources()
    sources = previous._sources()
    if hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _LOADED_SHA:
        raise ValueError('V2 cutoff refit source drift')
    return sources | {str(v3.ROOT / name): digest for name, digest in v3._LOADED_SOURCES.items()} | {
        str(_SOURCE): _LOADED_SHA}


def refit_dynamic_cutoff_weights(**parameters):
    """Same explicit inputs/defaults as v1, using v3 projection semantics.

    The probe builds its certified fitter in a private closure. We replace only
    its final evaluation entrypoint with v1 cutoff validation and one latest fit.
    This is not a six-input historical task evaluation, and does not claim one.
    """
    sources = _sources()
    fitters, calls = [], []

    def private_bind(function, **dependencies):
        if function is binding._PORTFOLIO:
            fitters.append(dependencies['constrained_fixed_shrinkage_weights'])
        elif function is binding._EVALUATE:
            if len(fitters) != 1:
                raise ValueError('Unexpected v3 fitter construction coverage')
            proxy = SimpleNamespace(**dict(vars(binding), _SHRINKAGE=fitters[0]))
            cutoff_refit = binding._bind(previous.refit_dynamic_cutoff_weights, evaluation=proxy)

            def evaluate_cutoff(unused_task, **unused_inputs):
                if unused_task is not None or unused_inputs:
                    raise ValueError('Historical task inputs forbidden in cutoff refit')
                calls.append(True)
                return cutoff_refit(**parameters)

            return evaluate_cutoff
        return binding._bind(function, **dependencies)

    proxy = SimpleNamespace(**dict(vars(binding), _bind=private_bind))
    reconstructed = binding._bind(v3.probe.evaluate_reconstructed, evaluator=proxy)
    try:
        evaluated = reconstructed(None, {})
        if len(calls) != 1 or len(fitters) != 1:
            raise ValueError('Unexpected cutoff refit invocation coverage')
        result = dict(evaluated['result'])
        result.update(schema='ndx_dynamic_cutoff_refit_research_v2', source_hashes=sources,
            numerical_projection='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE',
            projection_reconstruction_audit=dict(schema='ndx_projection_reconstruction_audit_v1',
                scope='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION',
                attempt_count=len(evaluated['reconstruction_attempts']),
                attempts=evaluated['reconstruction_attempts'], prior_results_reused=False,
                promotion_allowed=False),
            historical_task_evaluation_performed=False, order_generation_allowed=False)
        return result
    finally:
        if _sources() != sources:
            raise ValueError('V2 cutoff refit sources changed during evaluation')
