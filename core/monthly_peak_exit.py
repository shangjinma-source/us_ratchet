"""Serializable close-only risk state. Caller authenticates complete daily bars.

This module does not place orders or persist account changes. The owning service
must atomically save the returned state before publishing a derived suggestion.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction


def advance_monthly_exit(*, state, account_id, decision_date, session_date,
                         closes, unit_ids, baseline_targets):
    """Apply the frozen 20% monthly peak exit to an already sized target.

    New capital/target revisions within a month MUST retain decision_date.
    closes includes every tracked security, including previously exited names.
    Session completeness, market calendar, freshness and source authentication
    are responsibilities of the evidence adapter, not inferred from a date.
    """
    decision = date.fromisoformat(decision_date)
    session = date.fromisoformat(session_date)
    if not account_id or decision > session:
        raise ValueError('INVALID_RISK_BINDING')
    if not closes or set(closes) != set(unit_ids):
        raise ValueError('RISK_PRICE_DOMAIN_REQUIRED')
    prices = {sid: Fraction(value) for sid, value in closes.items()}
    if any(value <= 0 for value in prices.values()) or not all(unit_ids.values()):
        raise ValueError('INVALID_RISK_PRICE_OR_UNITS')
    if any(type(q) is not int or q < 0 for q in baseline_targets.values()):
        raise ValueError('INVALID_RISK_TARGET')
    if not set(baseline_targets) <= set(prices):
        raise ValueError('RISK_TARGET_PRICE_MISSING')
    previous = deepcopy(state)
    if previous is not None:
        if previous['schema'] != 'MONTHLY_PEAK_EXIT_V1' or previous['account_id'] != account_id:
            raise ValueError('RISK_STATE_BINDING_MISMATCH')
        if decision_date < previous['decision_date'] or session_date < previous['session_date']:
            raise ValueError('RISK_CLOCK_BACKWARDS')
    resetting = previous is None or decision_date != previous['decision_date']
    if resetting:
        if session != decision:
            raise ValueError('RISK_REQUIRES_DECISION_CLOSE_REPLAY')
        previous = dict(schema='MONTHLY_PEAK_EXIT_V1', account_id=account_id,
                        decision_date=decision_date, session_date=None,
                        peaks={}, exited=[], unit_ids={}, last_closes={})
    else:
        if set(prices) - set(previous['peaks']):
            raise ValueError('RISK_NEW_SECURITY_REQUIRES_MONTHLY_HISTORY_REPLAY')
        if not set(previous['peaks']) <= set(prices):
            raise ValueError('RISK_TRACKED_PRICE_MISSING')
        if any(unit_ids[sid] != units for sid, units in previous['unit_ids'].items()):
            raise ValueError('RISK_UNIT_CHANGE_REQUIRES_REVIEW')
        if session_date == previous['session_date']:
            normalized = {sid: str(value) for sid, value in prices.items()}
            if normalized != previous['last_closes']:
                raise ValueError('RISK_SAME_SESSION_SOURCE_CHANGED')
    peaks = dict(previous['peaks'])
    exited = set(previous['exited'])
    for sid, close in prices.items():
        peak = max(Fraction(peaks.get(sid, close)), close)
        peaks[sid] = str(peak)
        if close <= peak * Fraction(4, 5):
            exited.add(sid)
    effective = {sid: 0 if sid in exited else quantity
                 for sid, quantity in baseline_targets.items()}
    updated = dict(previous, session_date=session_date, peaks=peaks,
                   exited=sorted(exited), unit_ids=dict(unit_ids),
                   last_closes={sid: str(value) for sid, value in prices.items()})
    return dict(state=updated, effective_target_quantities=effective,
                reasons={sid: 'MONTHLY_PEAK_EXIT_LATCHED' if sid in exited
                         else 'BASELINE_TARGET_RETAINED' for sid in effective})
