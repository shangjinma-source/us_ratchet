"""Conditional proposal-bound monthly source review; no storage or policy authority.

The caller supplies validated target/proposal and admitted identity/unit inputs.
Capture uses the existing monthly-supplement byte contract. Public notice checks
remain conditional, including when the complete monthly price window is present.
"""
from copy import deepcopy
from hashlib import sha256

from core.strategy_account_ledger import canonical, replay, require
from data.monthly_peak_raw_history import review_monthly_supplement
from data.strategy_daily_session_capture import stamp


def review_proposal_monthly_sources(*, target, proposal, state, risk_state,
        inputs, identities, capture, request, execution_session, now):
    """Review fresh capture bytes at real review time, never at historical time.

    Target/proposal authenticity and prior constant-unit admission are caller
    responsibilities. This returns source evidence, never a policy approval.
    """
    current = stamp(now)
    require(stamp(execution_session['open']) <= current < stamp(execution_session['close']),
            'WAIT_FRONTIER_CURRENT_EXECUTION_SESSION')
    require(replay(state['account_id'], [row['payload'] for row in state['events']]) == state,
            'FRONTIER_ACCOUNT_REPLAY')
    require(target['payload']['account_id'] == state['account_id'], 'FRONTIER_ACCOUNT_BINDING')
    require(execution_session['date'][:7] == target['payload']['target_month'],
            'FRONTIER_TARGET_MONTH')
    quantities = proposal['payload']['proposed_target_quantities']
    needed = {sid for sid, quantity in quantities.items() if quantity}
    needed.update(sid for sid, quantity in state['shares'].items() if quantity)
    needed.update(order['security_id'] for order in state['orders'].values()
                  if order['status'] == 'OPEN' and order['remaining_quantity'] > 0)
    if risk_state is not None:
        require(risk_state['account_id'] == state['account_id'], 'FRONTIER_RISK_ACCOUNT')
        needed.update(risk_state['peaks'])
        needed.update(risk_state['exited'])
    require(needed and set(identities) == set(inputs['histories']) == needed,
            'FRONTIER_COMPLETE_REQUIRED_DOMAIN')
    base = inputs['base_target']
    require(base['origin_reference'] == proposal['proposal_id'] and
            base['quantities'] == {sid: quantities.get(sid, 0) for sid in needed},
            'FRONTIER_PROPOSAL_BASE_BINDING')
    require(inputs['signal_date'] < execution_session['date'], 'FRONTIER_COMPLETED_SIGNAL')
    binding = dict(target_id=target['target_id'], proposal_id=proposal['proposal_id'],
        account_id=state['account_id'], account_revision=state['revision'],
        risk_state_sha256=sha256(canonical(risk_state)).hexdigest(),
        session=execution_session['date'])
    capture_binding = {key: binding[key] for key in
                       ('account_id', 'account_revision', 'target_id', 'session')}
    reviewed = review_monthly_supplement(capture=capture, request=request,
        binding=capture_binding, inputs=inputs, identities=identities, now=current)
    result = dict(schema='SAVED_FRONTIER_CONDITIONAL_SOURCE_REVIEW_V1',
        status='CONDITIONAL_PROPOSAL_MONTHLY_SOURCES_REVIEWED', binding=binding,
        inputs=reviewed['inputs'], source_sha256=deepcopy(capture['source_hashes']),
        capture_id=capture['capture_id'], reviewed_at=current.isoformat(),
        source_received_at=capture['finished_at'], valid_from=current.isoformat(),
        valid_until=execution_session['close'], full_price_window_verified=True,
        conditional_action_review=True, coverage_complete=False,
        source_authenticated=False, policy_approved=False, production_admitted=False,
        limitations=['Finite public known-action checks may miss events.'])
    result['review_id'] = sha256(canonical(result)).hexdigest()
    return result
