"""Research execution cadence independent of forward-statistics window length."""
import math
import hashlib
from pathlib import Path

import pandas as pd

from backtest.ndx_joint_weight_evaluation import _numeric_values
from backtest import ndx_joint_weight_evaluation_v2 as evaluation

PARAMETERS = frozenset({'shrinkage_intensity', 'max_single_weight', 'min_single_weight',
    'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap', 'turnover_anchor_strength'})
_CLOCK_SOURCE = Path(__file__).resolve()
_LOADED_CLOCK_SHA = hashlib.sha256(_CLOCK_SOURCE.read_bytes()).hexdigest()


def build_periodic_execution_schedule(*, returns, tickers, fit_days, step_days,
        execution_end, weight_spec, risk_chain_by_ticker, projection_parameters):
    """Fit only preceding rows at every execution point through an explicit end.

    No forward window is needed to generate an execution target. Targets are
    research signals, not orders; external point-in-time data is caller-owned.
    """
    if (not isinstance(returns, pd.DataFrame) or returns.empty or not returns.columns.is_unique
            or not isinstance(returns.index, pd.DatetimeIndex) or returns.index.tz is not None
            or returns.index.hasnans or not returns.index.is_unique
            or not returns.index.is_monotonic_increasing
            or not returns.index.equals(returns.index.normalize())):
        raise ValueError('Invalid return panel/calendar')
    if (not isinstance(tickers, (list, tuple)) or not tickers
            or any(not isinstance(t, str) or not t or t != t.strip() for t in tickers)
            or len(set(tickers)) != len(tickers) or not set(tickers) <= set(returns)):
        raise ValueError('Invalid explicit ticker set')
    names = sorted(tickers)
    if (_numeric_values(returns[names], 'execution clock returns') < -1).any():
        raise ValueError('Return below -100 percent')
    if type(fit_days) is not int or fit_days <= 0 or type(step_days) is not int or step_days <= 0:
        raise ValueError('Positive explicit fit/cadence required')
    end = pd.Timestamp(execution_end)
    if end not in returns.index or end.tzinfo is not None or end != end.normalize():
        raise ValueError('Explicit execution end absent from calendar')
    end_index = returns.index.get_loc(end)
    if end_index < fit_days:
        raise ValueError('Insufficient preceding fit history')
    if weight_spec not in ('equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor'):
        raise ValueError('Unknown weight model')
    if (not isinstance(projection_parameters, dict) or set(projection_parameters) != PARAMETERS
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
                   for v in projection_parameters.values())):
        raise ValueError('Explicit finite projection contract required')
    risk_fields = PARAMETERS - {'shrinkage_intensity', 'turnover_anchor_strength'}
    if (any(projection_parameters[k] <= 0 for k in risk_fields)
            or projection_parameters['min_single_weight'] > projection_parameters['max_single_weight']):
        raise ValueError('Invalid risk bounds')
    if (not isinstance(risk_chain_by_ticker, dict) or not set(names) <= set(risk_chain_by_ticker)
            or any(not isinstance(risk_chain_by_ticker[t], str) or not risk_chain_by_ticker[t].strip() for t in names)):
        raise ValueError('Missing risk-chain identity')
    sources = evaluation.source_hashes()
    if sources != evaluation._LOADED_SOURCES or hashlib.sha256(_CLOCK_SOURCE.read_bytes()).hexdigest() != _LOADED_CLOCK_SHA:
        raise ValueError('Execution evaluator source drift')
    schedule = []
    last = None
    anchored = weight_spec == 'constrained_fixed_shrinkage_turnover_anchor'
    for start in range(fit_days, end_index + 1, step_days):
        history = returns.iloc[start-fit_days:start]
        if weight_spec == 'equal_weight':
            weights = pd.Series(1. / len(names), index=names)
        else:
            parameters = dict(projection_parameters)
            parameters['turnover_anchor_strength'] = parameters['turnover_anchor_strength'] if anchored else 0.
            weights = evaluation._SHRINKAGE(history, tuple(names),
                risk_chain_by_ticker=risk_chain_by_ticker, anchor_weights=last if anchored else None,
                **parameters)
        schedule.append(dict(execution_date=str(returns.index[start].date()),
            fit_start=str(history.index[0].date()), fit_end=str(history.index[-1].date()),
            weights={t: float(weights[t]) for t in names},
            risk_chain_projection_relaxed=bool(weights.attrs.get('risk_chain_projection_relaxed', False))))
        last = weights.copy()
    if (evaluation.source_hashes() != sources
            or hashlib.sha256(_CLOCK_SOURCE.read_bytes()).hexdigest() != _LOADED_CLOCK_SHA):
        raise ValueError('Execution evaluator source changed during fit')
    return dict(schema='ndx_periodic_execution_clock_research_v1', schedule=schedule,
        source_hashes={**sources, 'backtest/ndx_periodic_execution_clock.py': _LOADED_CLOCK_SHA},
        fit_days=fit_days, step_days=step_days, execution_end=str(end.date()),
        forward_window_required=False, fit_strictly_precedes_execution=True,
        external_point_in_time_data_verified=False, promotion_allowed=False)
