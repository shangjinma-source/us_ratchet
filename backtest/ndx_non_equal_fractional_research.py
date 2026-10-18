"""Private v3 fractional evaluation; no continuous whole-lot result reuse.

The existing six-input validator and certified reconstruction chain run intact.
Only the validated portfolio call's execution_prices channel is disabled. The
legacy cheap independent floor diagnostics still run internally and are omitted.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from backtest import ndx_joint_weight_evaluation_v2 as binding
from backtest import ndx_joint_weight_evaluation_v3 as full

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _sources():
    full._validate_loaded_sources()
    if hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _LOADED_SHA:
        raise ValueError('Non-equal fractional source drift')
    return {str(full.ROOT / name): digest for name, digest in full._LOADED_SOURCES.items()} | {
        str(_SOURCE): _LOADED_SHA}


def evaluate_non_equal_fractional(*, task, inputs):
    """Evaluate one explicit non-equal specification, without publishing files.

    Returned window weights are the actual historical fits, not cutoff targets.
    Solver failures propagate; no zero/fallback metric or false completion is
    returned. No existing module globals are patched, even temporarily.
    """
    sources = _sources()
    if type(inputs) is not dict or set(inputs) != {
            'universe', 'returns', 'target_returns', 'nominal_prices',
            'incumbent_weights', 'contract'}:
        raise ValueError('Exactly six explicit training inputs required')
    windows = []
    portfolio_calls = []

    def private_bind(function, **dependencies):
        dependencies = dict(dependencies)
        if function is binding._PORTFOLIO:
            fitter = dependencies['constrained_fixed_shrinkage_weights']

            def observed_fit(history, combo, **parameters):
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

            dependencies['constrained_fixed_shrinkage_weights'] = observed_fit
        elif function is binding._EVALUATE:
            portfolio = dependencies['evaluate_synthetic_portfolio']

            def fractional_portfolio(*arguments, **parameters):
                # The original validator has already validated nominal_prices
                # and forwards its private copy here. Do not bypass validation.
                if parameters.get('execution_prices') is None:
                    raise ValueError('Validated nominal channel unexpectedly absent')
                portfolio_calls.append(True)
                parameters = dict(parameters, execution_prices=None)
                return portfolio(*arguments, **parameters)

            dependencies['evaluate_synthetic_portfolio'] = fractional_portfolio
        return binding._bind(function, **dependencies)

    evaluator_proxy = SimpleNamespace(**dict(vars(binding), _bind=private_bind))
    reconstructed = binding._bind(full.probe.evaluate_reconstructed, evaluator=evaluator_proxy)
    probe_proxy = SimpleNamespace(**dict(vars(full.probe), evaluate_reconstructed=reconstructed))
    evaluate = binding._bind(full.evaluate_joint_weight_task_v3, probe=probe_proxy)
    evaluated = evaluate(deepcopy(task), **inputs)
    if len(portfolio_calls) != 1 or len(windows) != evaluated['rolling_fit_window_count']:
        raise ValueError('Unexpected fractional execution/fit coverage')
    audit = evaluated['projection_reconstruction_audit']
    excluded = {'declared_constraints_passed', 'constraint_failure_reasons', 'projection_reconstruction_audit'}
    result = {key: value for key, value in evaluated.items()
              if not key.startswith('whole_lot_') and key not in excluded}
    _sources()
    return dict(schema='ndx_non_equal_fractional_research_v1', result=result,
        historical_window_weights=windows, projection_reconstruction_audit=audit,
        source_hashes=sources, whole_lot_status='NOT_EVALUATED',
        continuous_whole_lot_executed=False, independent_floor_diagnostics_discarded=True,
        aggregate_declared_gate_available=False, historical_minimum_weight_verified=False,
        saved_weights_are_current_targets=False, full_legacy_result_compatible=False,
        source_authenticity_verified=False, point_in_time_verified=False, promotion_allowed=False)
