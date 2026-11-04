"""Unmounted split-account arithmetic bridge, not source or trading admission."""
from core.strategy_account_split_v1 import replay, moment
from core.strategy_account_ledger import require
from core.strategy_account_difference import build_strategy_difference
from data.strategy_split_native_projection_v1 import project_native_split
from data.strategy_recorded_split_review_v1 import review_recorded_splits
from data.strategy_split_history_projection_v1 import project_history_units
from core.monthly_peak_exit import advance_monthly_exit
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from zoneinfo import ZoneInfo


def preview_split_account(*, state, action_id, target, expected_proposal_id,
                          risk_before, marks, limits, now,
                          maximum_mark_age_seconds, fee_bps, securities, action_package,
                          observations, expected_sessions, risk_completed_at):
    require(replay(state['account_id'], [row['payload'] for row in state['events']]) == state,
            'SPLIT_PREVIEW_ACCOUNT_REPLAY_MISMATCH')
    require(state['cash_confirmation_valid'], 'CASH_RECONFIRMATION_REQUIRED')
    require(state['execution_ready'], 'ACCOUNT_RESERVATIONS_REQUIRE_RECONCILIATION')
    transition = project_native_split(account_after=state, action_id=action_id,
        risk_before=risk_before, target=target, expected_proposal_id=expected_proposal_id)
    projection = transition['payload']['risk_projection']
    action = next(row['payload'] for row in state['events']
                  if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id)
    history = project_history_units(observations=observations, action=action, expected_sessions=expected_sessions)
    completed = moment(risk_completed_at)
    require(completed <= moment(now) and
            completed.astimezone(ZoneInfo('America/New_York')).date().isoformat() == expected_sessions[-1],
            'SPLIT_PREVIEW_UNCOMPLETED_RISK')
    original_quantities = build_frontier_proposal(target=target)['payload']['proposed_target_quantities']
    prefix = [row for row in observations if row['session_date'] <= risk_before['session_date']]
    require(prefix and prefix[-1]['session_date'] == risk_before['session_date'], 'SPLIT_PREVIEW_RISK_PREFIX')
    replayed = None
    for row in prefix:
        replayed = advance_monthly_exit(state=replayed, account_id=state['account_id'],
            baseline_targets=original_quantities,
            **{key: value for key, value in row.items() if key != 'evidence_sha256'})['state']
    if 'target_month' in risk_before:
        replayed['target_month'] = risk_before['target_month']
    require(replayed == risk_before, 'SPLIT_PREVIEW_RISK_PREFIX_MISMATCH')
    replayed = None
    for row in history['payload']['normalized_observations']:
        risk_result = advance_monthly_exit(state=replayed, account_id=state['account_id'],
            baseline_targets=projection['target_quantities'],
            **{key: value for key, value in row.items() if key != 'evidence_sha256'})
        replayed = risk_result['state']
    effective = moment(projection['effective_at'])
    require(effective <= moment(now), 'SPLIT_PREVIEW_BEFORE_EFFECTIVE')
    for sid, mark in marks.items():
        unit = projection['risk_state']['unit_ids'].get(sid)
        require(unit and mark.get('unit_id') == unit and limits[sid].get('unit_id') == unit,
                'SPLIT_PREVIEW_UNIT_MISMATCH')
        require(moment(mark['observed_at']) >= effective, 'SPLIT_PREVIEW_PRE_ACTION_QUOTE')
    require(set(securities) == set(marks), 'SPLIT_PREVIEW_ACTION_DOMAIN')
    action_review = review_recorded_splits(state=state, securities=securities,
        action_package=action_package, now=now)
    difference = build_strategy_difference(account_id=state['account_id'],
        account_revision=state['revision'], holdings_revision=state['holdings_revision'],
        cash_confirmed_for_holdings_revision=state['cash_confirmed_for_holdings_revision'],
        cash_balance=state['total_uninvested_cash'], cash_basis='TOTAL_UNINVESTED',
        strategy_shares=state['shares'], legacy_shares={},
        pending_orders=[order for order in state['orders'].values() if order['status'] == 'OPEN'],
        marks=marks, limits=limits, target_quantities=risk_result['effective_target_quantities'],
        now=now, maximum_mark_age_seconds=maximum_mark_age_seconds, fee_bps=fee_bps)
    return dict(schema='SPLIT_ACCOUNT_ARITHMETIC_PREVIEW_V1', transition=transition,
                candidate_difference=difference, action_review=action_review,
                risk_result=risk_result, history_projection=history,
                executable=False, production_activated=False,
                source_authenticated=False, broker_evidence_authenticated=False,
                requires_current_risk_and_unit_admission=True, account_mutated=False)
