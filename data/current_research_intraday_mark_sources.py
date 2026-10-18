"""Read-only journal-backed current holding marks, including across month boundaries.

This values the existing BUY ledger; it does not select a new portfolio or sell.
Pinned continuity reviews remain conditional, not proof of action completeness.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from data.current_research_intraday_buy_plan import build_intraday_initial_buy_proposal, _require, _time
from data.current_research_intraday_continuation_ledger import review_continuation_ledger
from data.current_research_intraday_performance import compute_intraday_paper_performance


def review_journal_holding_marks(state, *, root, expected_revision, journal_root,
        session, event_path, expected_event_hashes, market_session, source_hashes,
        unit_continuity, now):
    """Return source-verified marks or raise; no HTTP, writes or inferred fills.

    All paths and conditional continuity declarations must come from a trusted
    server adapter, never a client request. Original research verifies identity
    of the old holding only; its target size and cash are not a new allocation.
    """
    state = review_continuation_ledger(state)
    _require(state['revision'] == expected_revision, 'STALE_ACCOUNT_REVISION')
    now = _time(now)
    base = Path(root).resolve()
    _require(isinstance(source_hashes, dict) and source_hashes, 'SOURCE_PINS_REQUIRED')
    for name, digest in source_hashes.items():
        _require(isinstance(name, str) and name and '\\' not in name, 'INVALID_SOURCE_PATH')
        path = Path(name)
        _require(not path.is_absolute() and not path.drive and '..' not in path.parts, 'SOURCE_OUTSIDE_ROOT')
        full = (base / path).resolve()
        _require(full.is_relative_to(base) and full.stat().st_size <= 32 * 1024 * 1024, 'SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
        _require(sha256(full.read_bytes()).hexdigest() == digest, 'SOURCE_HASH_MISMATCH')
    original = state['acceptance']['proposal']['causal_inputs']
    reference = build_intraday_initial_buy_proposal(
        journal_root=journal_root, session=session, event_path=event_path,
        expected_event_hashes=expected_event_hashes,
        research_snapshot=original['research_snapshot'], available_cash=original['available_cash'],
        shares={}, reserved_cash='0', open_orders=[], account_id=state['account_id'],
        account_revision=expected_revision, expected_revision=expected_revision,
        market_session=market_session, source_hashes=source_hashes, now=now)
    _require(reference['status'] == 'READY', 'REFERENCE_UNAVAILABLE:' + str(reference.get('reason')))
    current = reference['causal_inputs']
    sid = original['security']['security_id']
    _require(current['security'] == original['security'] and set(state['shares']) <= {sid}, 'SECURITY_CHANGED')
    first = _time(state['acceptance']['accepted_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    unit = unit_continuity
    _require(session >= first and isinstance(unit, dict)
        and unit.get('security_id') == sid and unit.get('from_session') == first
        and unit.get('to_session') == session and unit.get('status') == 'NO_UNPROCESSED_ACTIONS'
        and unit.get('price_basis') == 'CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'
        and unit.get('initial_event_sha256') == original['event_sha256']
        and unit.get('current_event_sha256') == current['event_sha256'], 'EXPLICIT_BOUND_UNIT_CONTINUITY_REQUIRED')

    def refs(values):
        _require(isinstance(values, list) and values and all(isinstance(p, str) and p in source_hashes for p in values), 'CONTINUITY_SOURCE_NOT_PINNED')

    refs(unit.get('source_references'))
    _require(_time(unit['covered_from']) <= _time(original['observation']['checked_at'])
        and _time(current['observation']['checked_at']) <= _time(unit['covered_through'])
        <= _time(unit['reviewed_asof']) <= now, 'CONTINUITY_TIME_COVERAGE_INVALID')
    if session != first:
        action = unit.get('action_review', {})
        _require(action.get('covered_from') == first and action.get('covered_through') == session
            and action.get('status') == 'NO_UNPROCESSED_ACTIONS', 'CROSS_SESSION_ACTION_REVIEW_REQUIRED')
        refs(action.get('source_references'))
        _require(_time(current['observation']['checked_at']) <= _time(action['reviewed_asof']) <= now, 'ACTION_REVIEW_TIME_INVALID')
    row = current['observation']
    pins = dict(source_hashes)
    _require(event_path not in pins or pins[event_path] == current['event_sha256'], 'SOURCE_PIN_CONFLICT')
    pins[event_path] = current['event_sha256']
    marks = {sid: dict(security_id=sid, price=row['last_price'], observed_at=row['last_at'],
        received_at=row['quote_response_captured_at'], valid_until=row['refresh_by'],
        price_basis='NOMINAL_PER_CURRENT_SHARE', unit_continuity='NO_UNPROCESSED_ACTIONS',
        source_references=list(pins))} if state['shares'].get(sid, 0) else {}
    valued = compute_intraday_paper_performance(state, now=now, marks=marks, source_hashes=pins)
    _require(valued['status'] == 'COMPLETE', 'CURRENT_MARK_INVALID:' + str(valued['issues']))
    return dict(account_id=state['account_id'], account_revision=expected_revision,
        marks=marks, source_hashes=pins, equity=valued['equity'], cash=valued['cash'],
        unit_continuity=deepcopy(unit), source_bytes_verified=True, source_authenticated=False,
        complete_corporate_actions_verified=False, account_mutated=False,
        research_only=True, execution_blocked=True)


def review_journal_monthly_capital(state, **inputs):
    """Compose saved quote review and capital budget without modifying the account."""
    from data.current_research_monthly_retarget_capital import build_monthly_retarget_capital
    reviewed = review_continuation_ledger(state)
    source = review_journal_holding_marks(reviewed, **inputs)
    proposal = reviewed['acceptance']['proposal']
    identity = dict(account_id=reviewed['account_id'], initial_acceptance_id=reviewed['acceptance_id'],
        initial_proposal_id=proposal['proposal_id'], initial_research_id=proposal['research_id'],
        initial_cash=proposal['causal_inputs']['available_cash'])
    quotes, units = [], {}
    for sid, mark in source['marks'].items():
        quotes.append(dict(security_id=sid, ticker=proposal['security']['ticker'], currency='USD',
            price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS', price_kind='REGULAR_MARKET_LAST',
            price=mark['price'], quoted_at=mark['observed_at'], captured_at=mark['received_at'],
            source_references=mark['source_references']))
        units[sid] = dict(source['unit_continuity'], quote_source_references=mark['source_references'])
    result = build_monthly_retarget_capital(reviewed, expected_revision=inputs['expected_revision'],
        initial_capital_identity=identity, valuation_quotes=quotes, unit_continuity=units,
        source_hashes=source['source_hashes'], market_session=inputs['market_session'], now=inputs['now'])
    if result['status'] == 'READY':
        _require(result['capital']['investable_equity'] == source['equity'], 'VALUATION_DISAGREEMENT')
        result.update(source_bytes_verified=True, complete_corporate_actions_verified=False)
    return result
