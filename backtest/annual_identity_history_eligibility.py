"""Pure conditional identity/history gate, not coordinate or execution admission.

Evidence references are declarations by the assembly author, not authenticated
here. Callers must pin/review their contents separately. No ticker exemptions.
"""
from fractions import Fraction
from backtest.annual_simple_split_coordinates import canonical_day


def _binding(binding, kind, ticker, security_id, start, end):
    reasons = []
    if not isinstance(binding, dict):
        return [kind + '_BINDING_MISSING']
    if binding.get('ticker') != ticker or binding.get('security_id') != security_id:
        reasons.append(kind + '_IDENTITY_MISMATCH')
    if binding.get('role') != 'SELECTION':
        reasons.append(kind + '_NOT_SELECTION_ADMITTED')
    refs = binding.get('source_references')
    if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or not r.strip() for r in refs):
        reasons.append(kind + '_EVIDENCE_MISSING')
    mode = binding.get('mode')
    if mode not in ('DATED_EVIDENCE', 'DECLARED_CONDITIONAL_LINK'):
        reasons.append(kind + '_MODE_INVALID')
    if mode == 'DECLARED_CONDITIONAL_LINK' and not str(binding.get('assumption') or '').strip():
        reasons.append(kind + '_CONDITIONAL_ASSUMPTION_MISSING')
    try:
        valid_from = canonical_day(binding.get('valid_from'))
        valid_through = canonical_day(binding.get('valid_through'))
        known_asof = canonical_day(binding.get('known_asof'))
        if valid_from > start or valid_through < end or valid_from > valid_through:
            reasons.append(kind + '_DATE_SCOPE_INSUFFICIENT')
        if known_asof > end and mode != 'DECLARED_CONDITIONAL_LINK':
            reasons.append(kind + '_FUTURE_EVIDENCE_REQUIRES_CONDITIONAL_DECLARATION')
    except (ValueError, TypeError):
        reasons.append(kind + '_DATE_INVALID')
    return reasons


def assess_eligibility(*, ticker, security_id, decision_date, regular_way_start,
                       sessions, closes, identity_binding, channel_binding):
    """Evaluate the last 253 supplied exchange sessions through decision close.

    sessions is an externally validated, complete exchange calendar, not the
    dates observed in a ticker's quotes. closes maps ISO dates to prices.
    Future sessions/quotes cannot contribute. A missing session never causes
    the window to reach further back. Reevaluate on each decision date.
    """
    decision_date = canonical_day(decision_date)
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError('TICKER_REQUIRED')
    calendar = [canonical_day(day) for day in sessions]
    if calendar != sorted(set(calendar)):
        raise ValueError('ORDERED_UNIQUE_CALENDAR_REQUIRED')
    if decision_date not in calendar:
        raise ValueError('DECISION_NOT_IN_CALENDAR')
    reasons = []
    if not isinstance(security_id, str) or not security_id.strip():
        reasons.append('SECURITY_ID_UNRESOLVED')
    try:
        ordinary_start = canonical_day(regular_way_start)
    except (TypeError, ValueError):
        ordinary_start = None
        reasons.append('REGULAR_WAY_START_UNRESOLVED')
    past = [d for d in calendar if d <= decision_date]
    window = past[-253:]
    valid, missing, before_ordinary = [], [], []
    for day in window:
        if ordinary_start is None or day < ordinary_start:
            before_ordinary.append(day)
            continue
        try:
            value = closes.get(day)
            if isinstance(value, bool) or Fraction(str(value)) <= 0:
                raise ValueError('INVALID_CLOSE')
        except (ValueError, TypeError, ZeroDivisionError):
            missing.append(day)
        else:
            valid.append(day)
    if len(valid) != 253:
        reasons.append('INSUFFICIENT_253_REGULAR_SESSION_CLOSES')
    scope_start = max(window[0], ordinary_start) if ordinary_start else window[0]
    for kind, binding in [('IDENTITY', identity_binding), ('CHANNEL', channel_binding)]:
        reasons.extend(_binding(binding, kind, ticker, security_id, scope_start, decision_date))
    if isinstance(identity_binding, dict) and identity_binding.get('regular_way_start') != ordinary_start:
        reasons.append('REGULAR_START_NOT_BOUND_TO_IDENTITY_EVIDENCE')
    if isinstance(channel_binding, dict):
        if channel_binding.get('channel') != 'ORDINARY_REGULAR_WAY':
            reasons.append('CHANNEL_NOT_ORDINARY_REGULAR_WAY')
        if channel_binding.get('currency') != 'USD':
            reasons.append('CHANNEL_NOT_USD')
        if not str(channel_binding.get('source_id') or '').strip():
            reasons.append('CHANNEL_SOURCE_UNBOUND')
    return dict(ticker=ticker, security_id=security_id, decision_date=decision_date,
                status='BLOCKED_IDENTITY_HISTORY' if reasons else 'READY_CONDITIONAL_IDENTITY_HISTORY',
                reasons=list(dict.fromkeys(reasons)), required_closes=253,
                valid_regular_closes=len(valid), window_dates=window,
                missing_or_invalid_dates=missing, pre_regular_dates=before_ordinary,
                observed_domain_retained=True, reevaluate_each_decision=True,
                execution_admitted=False, price_coordinate_admitted=False,
                point_in_time_certified=False)


def assess_observed_domain(*, members, records, decision_date, sessions):
    """Preserve every declared member; missing records stay explicitly blocked."""
    if len(members) != len(set(members)):
        raise ValueError('DUPLICATE_OBSERVED_MEMBER')
    results = []
    for ticker in members:
        record = records.get(ticker, {})
        results.append(assess_eligibility(ticker=ticker, decision_date=decision_date,
            sessions=sessions, security_id=record.get('security_id'),
            regular_way_start=record.get('regular_way_start'), closes=record.get('closes', {}),
            identity_binding=record.get('identity_binding'), channel_binding=record.get('channel_binding')))
    return dict(observed_domain_count=len(members), rows=results,
                ready_identity_history_count=sum(not r['reasons'] for r in results),
                execution_admitted=False)
