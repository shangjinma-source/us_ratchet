"""Read-only isolated evaluation of one v2 task with certified reconstruction.

This experiment never writes a checkpoint or replaces a frozen evaluator.
Only a failed optimizer proposal may seed reconstruction; it is never accepted
as-is. Economic qualification remains separate from numerical completion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from backtest import ndx_concentration_projection_v2 as projection
from backtest import ndx_joint_weight_evaluation_v2 as evaluator
from backtest import ndx_joint_weight_runner as encoding
from backtest import ndx_joint_weight_runner_v2 as runner
from backtest.ndx_projection_reconstruction_research import reconstruct_projection_candidate
from backtest.ndx_projection_certificate_research import certify_projection_candidate
from scripts.ndx_joint_weight_progress import Snapshot
from scripts.ndx_joint_weight_verify import _restore_input

RESEARCH_PATHS = (Path(__file__), ROOT/'backtest/ndx_projection_reconstruction_research.py',
                  ROOT/'backtest/ndx_projection_certificate_research.py')
LOADED_RESEARCH_SOURCES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in RESEARCH_PATHS}


def evaluate_reconstructed(task, inputs):
    attempts = []

    def projected(raw, **parameters):
        proposals = []

        def capture(*args, **kwargs):
            result = projection.minimize(*args, **kwargs)
            proposals.append(result)
            return result

        private_solver = evaluator._bind(
            projection.project_concentration_envelope_weights_v2, minimize=capture)
        try:
            return private_solver(raw, **parameters)
        except projection.ProjectionError:
            # Invalid inputs, successful-but-invalid points, and unrelated
            # exceptions must not be reclassified as recoverable line searches.
            if len(proposals) != 1 or proposals[0].success:
                raise
            proposal = np.asarray(proposals[0].x, dtype=float).copy()
            if proposal.shape != (2*len(raw)+1,) or not np.isfinite(proposal).all():
                raise ValueError('Invalid failed optimizer proposal')
            contract = dict(parameters)
            tolerance = contract.pop('tolerance', 1e-9)
            if tolerance != 1e-9:
                raise ValueError('Probe requires original default projection tolerance')
            reconstruction = reconstruct_projection_candidate(
                raw, pd.Series(proposal[:len(raw)], index=raw.index), **contract)
            attempts.append(dict(optimizer_message=str(proposals[0].message),
                                 reconstruction=reconstruction))
            if reconstruction.get('certified') is not True:
                raise ValueError('Failed proposal reconstruction was not certified')
            weights = pd.Series(reconstruction['weights'], index=raw.index, dtype=float)
            independent = certify_projection_candidate(raw, weights, **contract)
            attempts[-1]['independent_certificate'] = independent
            attempts[-1]['failed_optimizer_vector'] = proposal.tolist()
            if independent['certified'] is not True:
                raise ValueError('Reconstruction failed independent original-contract certificate')
            return weights

    shrinkage = evaluator._bind(evaluator._SHRINKAGE,
        project_concentration_envelope_weights=projected)
    portfolio = evaluator._bind(evaluator._PORTFOLIO, constrained_fixed_shrinkage_weights=shrinkage)
    evaluate = evaluator._bind(evaluator._EVALUATE, evaluate_synthetic_portfolio=portfolio)
    result = evaluate(task, **inputs)
    return dict(result=result, reconstruction_attempts=attempts)


def run(context_sha256, job_id):
    for name, value in (('context', context_sha256), ('job', job_id)):
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Explicit canonical '+name+' SHA required')
    sources = runner.source_hashes()
    if (sources != runner._LOADED_SOURCE_HASHES
            or evaluator.source_hashes() != evaluator._LOADED_SOURCES
            or LOADED_RESEARCH_SOURCES != {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in RESEARCH_PATHS}):
        raise ValueError('Probe sources changed since import')
    watched = [Path(__file__)] + [ROOT / p for p in (
        'backtest/ndx_projection_reconstruction_research.py',
        'backtest/ndx_projection_certificate_research.py',
        'scripts/ndx_joint_weight_verify.py', 'scripts/ndx_joint_weight_progress.py',
        'config/config.yaml', 'data/state.json', 'data/broker_positions.json')]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    snapshot = Snapshot()
    context = snapshot.read(runner.CHECKPOINT_ROOT / context_sha256 / 'context.json')
    if (encoding._sha(context) != context_sha256
            or context.get('schema') != 'ndx_joint_weight_checkpoint_v1'
            or context.get('numerical_sources') != sources):
        raise ValueError('V2 context identity/source mismatch')
    tasks = context['tasks']
    if not isinstance(tasks, list) or not tasks or len({t['job_id'] for t in tasks}) != len(tasks):
        raise ValueError('Invalid task denominator')
    selected = [t for t in tasks if t['job_id'] == job_id]
    if len(selected) != 1:
        raise ValueError('Explicit task not found')
    encoding._validate_task(selected[0])
    inputs = {k: _restore_input(v) for k, v in context['prepared_inputs'].items()}
    try:
        result = evaluate_reconstructed(selected[0], inputs)
    finally:
        snapshot.verify()
        if sources != runner.source_hashes() or before != {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}:
            raise ValueError('Reconstruction probe sources changed')
    return dict(schema='ndx_projection_reconstruction_probe_v1', **result,
        context_sha256=context_sha256, job_id=job_id, source_hashes=before,
        original_numerical_sources=sources, original_runtime=context['runtime'],
        current_runtime=dict(python=encoding.platform.python_version(), numpy=np.__version__,
                             pandas=pd.__version__, scipy=encoding.scipy.__version__),
        scope='ONE_EXPLICIT_TASK_RECOMPUTATION_WITH_ISOLATED_NUMERICAL_CHANGE',
        checkpoint_created=False, prior_results_reused=False, promotion_allowed=False,
        order_generation_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--job-id', required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.context, arguments.job_id), ensure_ascii=False, indent=2))
