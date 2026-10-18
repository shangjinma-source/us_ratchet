"""Nominal close jump diagnostics, never inferred corporate-action accounting."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.ndx_split_accounting_research import apply_split_session

_PATHS = (Path(__file__).resolve(), Path(__file__).with_name('ndx_split_accounting_research.py'))


def _hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in _PATHS}


_LOADED_SOURCES = _hashes()


def diagnose_nominal_events(*, prices, execution_calendar, split_events, jump_ratio_threshold):
    """Flag min(current/previous, previous/current) below the supplied threshold.

    Split-adjusted returns use only explicitly declared event ratios. They are
    diagnostic arithmetic, not total returns or evidence of a correct ratio.
    Absence of flagged jumps does not establish corporate-action completeness.
    """
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    sources = _hashes()
    require(sources == _LOADED_SOURCES, 'Diagnostic sources changed since import')
    require(type(jump_ratio_threshold) in (int, float) and math.isfinite(jump_ratio_threshold)
            and 0 < jump_ratio_threshold < 1, 'Explicit diagnostic threshold must lie in (0,1)')
    require(isinstance(prices, pd.DataFrame) and not prices.empty and prices.columns.is_unique
            and all(type(t) is str and t and t.strip() == t for t in prices), 'Unique ticker price panel required')
    require(isinstance(execution_calendar, pd.DatetimeIndex) and len(execution_calendar) > 0
            and execution_calendar.tz is None and not execution_calendar.hasnans
            and execution_calendar.is_unique and execution_calendar.is_monotonic_increasing
            and execution_calendar.equals(execution_calendar.normalize()), 'Complete ordered daily calendar required')
    require(isinstance(prices.index, pd.DatetimeIndex) and prices.index.equals(execution_calendar),
            'Price rows must exactly match declared calendar')
    values = prices.to_numpy()
    require(all(isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))
                for v in values.flat) and np.isfinite(values.astype(float)).all()
            and (values.astype(float) > 0).all(), 'Prices must be finite and positive')
    require(type(split_events) in (list, tuple), 'Explicit split event list required')
    names = list(prices)
    calendar_sessions = [str(d.date()) for d in execution_calendar]
    grouped = {}
    for event in split_events:
        require(isinstance(event, dict) and type(event.get('session')) is str
                and event['session'] in calendar_sessions[1:], 'Event session absent or first session')
        require(type(event.get('ticker')) is str and event['ticker'] in names, 'Unknown event ticker')
        grouped.setdefault(event['session'], []).append(deepcopy(event))
    event_lookup = {}
    for session, events in grouped.items():
        apply_split_session(session=session, shares={t: 0 for t in names}, cash_usd=0.,
                            pending_plan=None, events=events)
        for event in events:
            event_lookup[(event['ticker'], session)] = event
    jumps, declared = [], []
    for index in range(1, len(execution_calendar)):
        for ticker in names:
            previous = float(prices.iloc[index-1][ticker])
            current = float(prices.iloc[index][ticker])
            ratio = current/previous
            require(math.isfinite(ratio) and ratio > 0, 'Nominal ratio arithmetic overflow/underflow')
            symmetric = min(ratio, 1./ratio)
            session = calendar_sessions[index]
            event = event_lookup.get((ticker, session))
            adjusted = None
            if event is not None:
                adjusted = ratio*(event['new_shares']/event['old_shares'])-1.
                require(math.isfinite(adjusted), 'Declared event arithmetic overflow')
            row = dict(ticker=ticker, previous_session=calendar_sessions[index-1], session=session,
                       previous_nominal_close=previous, nominal_close=current, nominal_ratio=ratio,
                       symmetric_nominal_ratio=symmetric, nominal_return=ratio-1.,
                       jump_flagged=symmetric < jump_ratio_threshold,
                       declared_event_present=event is not None, declared_event=deepcopy(event),
                       declared_ratio_adjusted_return=adjusted,
                       declared_event_ratio_verified=False)
            if row['jump_flagged']:
                jumps.append(row)
            if event is not None:
                declared.append(deepcopy(row))
    require(_hashes() == sources, 'Diagnostic sources changed during evaluation')
    return dict(schema='ndx_nominal_event_diagnostics_research_v1',
        scope='NOMINAL_JUMP_SCREEN_NOT_CORPORATE_ACTION_COVERAGE_PROOF',
        jump_ratio_threshold=jump_ratio_threshold, threshold_is_diagnostic_only=True,
        tickers=names, date_start=calendar_sessions[0], date_end=calendar_sessions[-1],
        pair_count=(len(execution_calendar)-1)*len(names), jumps=jumps,
        unmatched_jumps=[deepcopy(row) for row in jumps if not row['declared_event_present']],
        declared_event_diagnostics=declared, source_hashes=sources,
        corporate_action_coverage_verified=False, inferred_events_used_for_accounting=False,
        external_event_authenticity_verified=False, execution_calendar_authenticity_verified=False,
        adjusted_return_is_total_return=False, generated_events=[],
        promotion_allowed=False, order_generation_allowed=False)
