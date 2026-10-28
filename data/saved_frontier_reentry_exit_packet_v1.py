"""Unrouted cap/exit adapter with atomic risk and reference-lock persistence.

The caller owns source admission, monthly epoch authorization and freshness.
In particular, historical training cutoff is NOT the monthly selection date.
"""
from copy import deepcopy
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_ledger import require,canonical
from hashlib import sha256
from data.monthly_peak_exit_history import monthly_exit_observations


def prepare_frontier_reentry_exit_packet(*, target, proposal, inputs, risk_store, account_id,
                                        decision_date, expected_previous_session,
                                        authorized_monthly_reset=None):
    """Read-only authenticated observations, not a simulated or committed risk state.

    The store alone owns replay/expansion and transaction semantics. A reader may
    archive PRECOMMIT intent using this result's final session/unit domain before
    obtaining journal snapshots. No historical holding or decision time is invented.
    """
    require(proposal == build_frontier_proposal(target=target), 'FRONTIER_PROPOSAL_CHANGED')
    view = dict(target_quantities=dict(proposal['payload']['proposed_target_quantities']),
                base_target_id=target['target_id'], proposal_id=proposal['proposal_id'])
    previous = risk_store.read(account_id)
    if previous is not None:
        require(set(previous['peaks']) | set(previous['exited']) <= set(inputs['histories']),
                'FRONTIER_RISK_DOMAIN_INCOMPLETE')
        if previous['target_month'] == target['payload']['target_month']:
            require(decision_date == previous['decision_date'], 'FRONTIER_SAME_MONTH_EPOCH_CHANGED')
        else:
            require(authorized_monthly_reset == decision_date and
                    decision_date[:7] == target['payload']['target_month'],
                    'FRONTIER_MONTHLY_RESET_BINDING')
    require(inputs['base_target']['monthly_decision_date'] == decision_date,
            'FRONTIER_INPUT_EPOCH_MISMATCH')
    require(inputs['base_target']['quantities'] == {
        sid: view['target_quantities'].get(sid, 0) for sid in inputs['histories']},
        'FRONTIER_INPUT_QUANTITIES_CHANGED')
    require({sid for sid, quantity in view['target_quantities'].items() if quantity}
            <= set(inputs['histories']), 'FRONTIER_PROPOSAL_DOMAIN_INCOMPLETE')
    normalized = deepcopy(inputs)
    if normalized['base_target']['origin_reference'] != proposal['proposal_id']:
        raise ValueError('CAP_EXIT_PACKET_TARGET_MISMATCH')
    if target['payload'].get('account_id') != account_id:
        raise ValueError('CAP_EXIT_ACCOUNT_MISMATCH')
    normalized['base_target']['monthly_decision_date'] = decision_date
    normalized['base_target']['quantities'] = dict(view['target_quantities'])
    domain = set(normalized['histories'])
    # Retain held/exited names even after monthly selection gives them zero.
    for sid in domain:
        normalized['base_target']['quantities'].setdefault(sid, 0)
    saved = risk_store.recorded_prices(account_id, decision_date)
    expected_dates = [day for day in normalized['session_dates']
                      if decision_date <= day <= normalized['signal_date']]
    for sid, history in normalized['histories'].items():
        rows = {row['date']: row for row in history['closes']}
        for day in expected_dates:
            if day not in rows and day in saved.get(sid, {}):
                old = saved[sid][day]
                if old['units'] != history['units']['basis_id']:
                    raise ValueError('CAP_SAVED_HISTORY_UNIT_CHANGED')
                rows[day] = dict(date=day, close=old['close'],
                    completed_at=normalized['session_close_times']['closes'][day])
        if any(day not in rows for day in expected_dates):
            raise ValueError('CAP_COMPLETE_MONTHLY_HISTORY_REQUIRED')
        history['closes'] = [rows[day] for day in expected_dates]
    observations = monthly_exit_observations(**normalized)
    prepared=dict(schema='PREPARED_FRONTIER_REENTRY_EXIT_PACKET_V1',
        account_id=account_id, target_id=target['target_id'], proposal_id=proposal['proposal_id'],
        decision_date=decision_date, expected_previous_session=expected_previous_session,
        authorized_monthly_reset=authorized_monthly_reset,
        target_month=target['payload'].get('target_month'),
        normalized=normalized, observations=observations, view=view, previous_risk=previous,
        final_session=observations[-1]['session_date'],
        final_unit_ids=deepcopy(observations[-1]['unit_ids']),
        risk_projection_performed=False, risk_committed=False, orders_created=False)
    prepared['preparation_sha256']=sha256(canonical(prepared)).hexdigest()
    return prepared


def apply_frontier_reentry_exit_packet(*, target, proposal, inputs, risk_store, account_id,
                          decision_date, expected_previous_session,
                          expected_reference_version, activation_id, session_contexts,
                          recovery_evidence=(), authorized_monthly_reset=None,
                          expected_preparation_sha256=None):
    # Source/decision/snapshot authentication belongs to the server caller.
    # Re-prepare and optionally bind its exact PRECOMMIT record, then perform the
    # sole atomic advance. Never run legacy advance and subsequently add a lock.
    prepared=prepare_frontier_reentry_exit_packet(target=target,proposal=proposal,inputs=inputs,
        risk_store=risk_store,account_id=account_id,decision_date=decision_date,
        expected_previous_session=expected_previous_session,
        authorized_monthly_reset=authorized_monthly_reset)
    if expected_preparation_sha256 is not None:
        require(prepared['preparation_sha256']==expected_preparation_sha256,
                'FRONTIER_PRECOMMIT_PREPARATION_CHANGED')
    normalized=prepared['normalized'];observations=prepared['observations'];view=prepared['view']
    result = risk_store.advance(account_id=account_id,
        expected_previous_session=expected_previous_session, observations=observations,
        baseline_targets=normalized['base_target']['quantities'],
        expected_reference_version=expected_reference_version, activation_id=activation_id,
        session_contexts=session_contexts, recovery_evidence=recovery_evidence,
        authorized_monthly_reset=authorized_monthly_reset,
        target_month=target['payload'].get('target_month'))
    return dict(result, policy_id='SAVED_FRONTIER_CAP50_EXIT20_V1', monthly_cap_view=view,
                signal_date=normalized['signal_date'],
                signal_explanations={sid: dict(
                    policy='SAVED_FRONTIER_CAP50_EXIT20_V1', signal_date=normalized['signal_date'],
                    monthly_target=normalized['base_target']['quantities'][sid],
                    effective_target=result['effective_target_quantities'][sid],
                    close=result['state']['last_closes'][sid],
                    peak=result['state']['peaks'][sid],
                    exited=sid in result['state']['exited'])
                    for sid in result['effective_target_quantities']},
                orders_created=False, production_released=False)
