"""Calculate cap/exit decisions from an already source-admitted daily packet.

The caller owns source admission, monthly epoch authorization and freshness.
In particular, historical training cutoff is NOT the monthly selection date.
"""
from copy import deepcopy
from data.monthly_cap_target_view import capped_target_view
from data.monthly_peak_exit_history import monthly_exit_observations


def apply_cap_exit_packet(*, target, inputs, risk_store, account_id,
                          decision_date, expected_previous_session,
                          authorized_monthly_reset=None):
    view = capped_target_view(target)
    normalized = deepcopy(inputs)
    if normalized['base_target']['origin_reference'] != target['target_id']:
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
    result = risk_store.advance(account_id=account_id,
        expected_previous_session=expected_previous_session, observations=observations,
        baseline_targets=normalized['base_target']['quantities'],
        authorized_monthly_reset=authorized_monthly_reset,
        target_month=target['payload'].get('target_month'))
    return dict(result, policy_id='MONTHLY_CAP50_EXIT20', monthly_cap_view=view,
                signal_date=normalized['signal_date'],
                signal_explanations={sid: dict(
                    policy='MONTHLY_CAP50_EXIT20', signal_date=normalized['signal_date'],
                    monthly_target=normalized['base_target']['quantities'][sid],
                    effective_target=result['effective_target_quantities'][sid],
                    close=result['state']['last_closes'][sid],
                    peak=result['state']['peaks'][sid],
                    exited=sid in result['state']['exited'])
                    for sid in result['effective_target_quantities']},
                orders_created=False, production_released=False)
