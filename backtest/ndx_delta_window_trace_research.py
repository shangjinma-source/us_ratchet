"""Observe complete v3 fitted windows without changing its numerical channels."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from backtest import ndx_joint_weight_evaluation_v2 as binding
from backtest import ndx_joint_weight_evaluation_v3 as full

SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def source_hashes():
    full._validate_loaded_sources()
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != LOADED:
        raise ValueError('Delta window observer source drift')
    return {str(full.ROOT / path): sha for path, sha in full._LOADED_SOURCES.items()} | {str(SOURCE): LOADED}


def evaluate_with_window_trace(*, task, inputs):
    """Run one real evaluation, retaining actual fits; this is not no-fit reuse.

    The caller must bind historical inputs and compare an old-input recovery to
    its externally authenticated checkpoint before using any recovered trace.
    """
    sources = source_hashes()
    if type(inputs) is not dict or set(inputs) != {
            'universe', 'returns', 'target_returns', 'nominal_prices',
            'incumbent_weights', 'contract'}:
        raise ValueError('Exactly six explicit training inputs required')
    windows = []
    calls = []

    def private_bind(function, **dependencies):
        dependencies = dict(dependencies)
        if function is binding._PORTFOLIO:
            fitter = dependencies['constrained_fixed_shrinkage_weights']

            def observe(history, combo, **parameters):
                fitted = fitter(history, combo, **parameters)
                anchor = parameters.get('anchor_weights')
                windows.append(dict(
                    fit_start=str(history.index[0].date()),
                    fit_end=str(history.index[-1].date()), fit_row_count=len(history),
                    tickers=list(combo), weights={name: float(fitted[name]) for name in combo},
                    anchor_weights=None if anchor is None else anchor.to_dict(),
                    turnover_anchor_strength=parameters.get('turnover_anchor_strength'),
                    risk_chain_projection_relaxed=bool(fitted.attrs.get('risk_chain_projection_relaxed', False))))
                return fitted

            dependencies['constrained_fixed_shrinkage_weights'] = observe
        elif function is binding._EVALUATE:
            portfolio = dependencies['evaluate_synthetic_portfolio']

            def observe_call(*arguments, **parameters):
                if parameters.get('execution_prices') is None:
                    raise ValueError('Validated nominal execution channel absent')
                calls.append(True)
                return portfolio(*arguments, **parameters)

            dependencies['evaluate_synthetic_portfolio'] = observe_call
        return binding._bind(function, **dependencies)

    proxy = SimpleNamespace(**dict(vars(binding), _bind=private_bind))
    reconstructed = binding._bind(full.probe.evaluate_reconstructed, evaluator=proxy)
    evaluator = binding._bind(full.evaluate_joint_weight_task_v3,
        probe=SimpleNamespace(**dict(vars(full.probe), evaluate_reconstructed=reconstructed)))
    try:
        result = evaluator(deepcopy(task), **inputs)
        if len(calls) != 1 or len(windows) != result['rolling_fit_window_count']:
            raise ValueError('Incomplete observed window coverage')
        if 'whole_lot_path_return_net' not in result:
            raise ValueError('Legacy nominal continuous result missing')
        return dict(schema='ndx_delta_window_trace_research_v1', result=result,
            historical_window_weights=windows, source_hashes=sources,
            fitted_window_observation_count=len(windows),
            numerical_evaluation_performed=True, no_fit_reuse=False,
            original_checkpoint_equivalence_verified=False,
            nominal_execution_semantics='ORIGINAL_V3_UNCHANGED',
            saved_weights_are_current_targets=False,
            source_authenticity_verified=False, point_in_time_verified=False,
            promotion_allowed=False)
    finally:
        source_hashes()
