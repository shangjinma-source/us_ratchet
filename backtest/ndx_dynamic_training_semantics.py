"""Content-bound comparison cohort, independent of portfolio k and weights."""
import hashlib
import json
import math
from numbers import Real
import numpy as np
import pandas as pd


def training_semantics(*, inputs, decision_data_end, source_batch, universe_track):
    if set(inputs) != {'returns','nominal_prices','target_returns','universe','contract','incumbent_weights'}:
        raise ValueError('Complete training inputs required')
    cutoff = pd.Timestamp(decision_data_end)
    if (type(decision_data_end) is not str or cutoff.tzinfo is not None or pd.isna(cutoff)
            or decision_data_end != cutoff.date().isoformat()):
        raise ValueError('Canonical cutoff required')
    for value in (source_batch,universe_track):
        if type(value) is not str or not value or value != value.strip():
            raise ValueError('Explicit source scope required')

    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

    def numeric(value):
        if isinstance(value,(bool,np.bool_)) or not isinstance(value,Real) or not math.isfinite(value):
            raise ValueError('Finite nonboolean training data required')
        return float(value)

    def panel(value):
        if isinstance(value,pd.Series):
            value=value.to_frame('value')
        if (not isinstance(value,pd.DataFrame) or value.empty or not value.columns.is_unique
                or not isinstance(value.index,pd.DatetimeIndex) or value.index.hasnans
                or value.index.tz is not None or not value.index.is_unique
                or not value.index.is_monotonic_increasing or not value.index.equals(value.index.normalize())
                or value.index[-1] != cutoff):
            raise ValueError('Invalid training calendar/cutoff')
        ordered=value.sort_index(axis=1)
        return dict(dates=[str(day.date()) for day in ordered.index], columns=list(ordered.columns),
                    values=[[numeric(item) for item in row] for row in ordered.to_numpy()])
    returns=panel(inputs['returns'])
    nominal=panel(inputs['nominal_prices'])
    target=panel(inputs['target_returns'])
    if returns['dates'] != nominal['dates'] or returns['dates'] != target['dates']:
        raise ValueError('Training panel calendars differ')
    universe=inputs['universe']
    if (not isinstance(universe,pd.DataFrame) or universe.empty or not universe.columns.is_unique
            or 'ticker' not in universe or universe['ticker'].duplicated().any()):
        raise ValueError('Explicit unique training universe required')
    universe_records=universe.sort_values('ticker').to_dict('records')
    # Canonical JSON catches missing/nonfinite universe facts rather than hiding them.
    payload=dict(schema='ndx_dynamic_training_semantics_v1', source_batch=source_batch,
        universe_track=universe_track,decision_data_end=decision_data_end,
        contract=inputs['contract'],incumbent_weights=inputs['incumbent_weights'],
        returns_sha256=digest(returns),nominal_prices_sha256=digest(nominal),
        target_returns_sha256=digest(target),universe_sha256=digest(universe_records))
    return dict(training_semantics_sha256=digest(payload),payload=payload,
                task_specific_k_tickers_weight_spec_included=False,
                technology_scope_verified=False,point_in_time_verified=False,promotion_allowed=False)
