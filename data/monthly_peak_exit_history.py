"""Validate a full monthly close window before constructing store observations.

Pure structural validation only. The source admission service still authenticates
the calendar, normalized units and source receipts before calling this function.
"""
from hashlib import sha256
import json
from copy import deepcopy
from datetime import datetime, time
from zoneinfo import ZoneInfo

from backtest.current_quantity_v2_risk_overlays import _validated, _stamp


def monthly_exit_observations(*, base_target, signal_date, observed_at,
                              session_dates, session_close_times, histories):
    decision = base_target['monthly_decision_date']
    if decision not in session_dates or signal_date not in session_dates:
        raise ValueError('MONTHLY_WINDOW_NOT_IN_CALENDAR')
    count = session_dates.index(signal_date) - session_dates.index(decision) + 1
    if count <= 0:
        raise ValueError('INVALID_MONTHLY_WINDOW')
    # Keep zero-target securities in the historical domain: an exited or sold
    # name must not lose its peak/latch just because its desired quantity is zero.
    validation_target = deepcopy(base_target)
    quantities = validation_target['quantities']
    if any(type(quantity) is not int or quantity < 0 for quantity in quantities.values()):
        raise ValueError('WHOLE_NONNEGATIVE_TARGET_REQUIRED')
    if set(quantities) != set(histories):
        raise ValueError('EXACT_TRACKED_HISTORY_DOMAIN_REQUIRED')
    validation_target['quantities'] = {sid: 1 for sid in quantities}
    current = _stamp(observed_at)
    completed = [day for day in session_dates
                 if _stamp(session_close_times['closes'][day]) <= current]
    if not completed or completed[-1] != signal_date:
        raise ValueError('LATEST_COMPLETED_SIGNAL_REQUIRED')
    # The legacy validator uses a market-asof clock on the signal date. Actual
    # receipt/observation can be the following morning; never falsify that time.
    signal_end = datetime.combine(datetime.fromisoformat(signal_date).date(),
                                  time.max, ZoneInfo('America/New_York'))
    market_cutoff = min(current, signal_end)
    targets, prices = _validated(base_target=validation_target, signal_date=signal_date,
        observed_at=market_cutoff.isoformat(), session_dates=session_dates,
        session_close_times=session_close_times, histories=histories, count=count)
    if not targets:
        raise ValueError('EMPTY_MONTHLY_WINDOW_REQUIRES_TRACKED_HOLDINGS')
    dates = session_dates[session_dates.index(decision):session_dates.index(signal_date)+1]
    observations = []
    for index, day in enumerate(dates):
        row = dict(decision_date=decision, session_date=day,
                   closes={sid: str(values[index]) for sid, values in prices.items()},
                   unit_ids={sid: histories[sid]['units']['basis_id'] for sid in prices})
        # Content identifier only; do not call this source authentication.
        row['evidence_sha256'] = sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        observations.append(row)
    return observations
