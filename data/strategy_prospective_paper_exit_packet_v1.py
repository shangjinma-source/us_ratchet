"""Paper-only cap/exit stage for an already admitted monthly history packet.

Caller authenticates history receipts, calendar, freshness and monthly reset.
This module neither admits raw market data nor authorizes executable orders.
"""
from copy import deepcopy
from hashlib import sha256

from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_history import monthly_exit_observations
from data.strategy_prospective_paper_cap_target_v1 import capped_paper_target, CODE_PATHS as CAP_PINS

CODE_PATHS = CAP_PINS | {
    'data/strategy_prospective_paper_exit_packet_v1.py',
    'data/monthly_peak_exit_history.py', 'data/monthly_peak_exit_store.py',
    'core/monthly_peak_exit.py', 'backtest/current_quantity_v2_risk_overlays.py',
}


def apply_paper_exit_packet(*, selection_result, selection_arguments, inputs,
                           risk_store, decision_date, expected_previous_session,
                           authorized_monthly_reset=None):
    view = capped_paper_target(selection_result=selection_result,
                               selection_arguments=selection_arguments)
    code_bytes = selection_arguments['authority']['descriptor_arguments']['code_bytes']
    if not CODE_PATHS <= set(code_bytes):
        raise ValueError('PAPER_EXIT_CODE_SCOPE')
    # Never share real-account state, nor another registration's exit latch.
    namespace = 'paper-cap-exit:' + sha256(canonical(dict(
        account_id=view['account_id'], registration=view['registration_sha256'],
        descriptor=view['descriptor_sha256']))).hexdigest()
    previous = risk_store.read(namespace)
    if previous and previous.get('target_month') == view['target_month']:
        if decision_date != previous['decision_date']:
            raise ValueError('PAPER_EXIT_SAME_MONTH_RESET_FORBIDDEN')
    normalized = deepcopy(inputs)
    if normalized['base_target']['origin_reference'] != view['base_target_id']:
        raise ValueError('PAPER_EXIT_TARGET_MISMATCH')
    normalized['base_target']['monthly_decision_date'] = decision_date
    normalized['base_target']['quantities'] = dict(view['target_quantities'])
    for sid in normalized['histories']:
        normalized['base_target']['quantities'].setdefault(sid, 0)
    # Require the complete epoch, including dropped/exited names. The store
    # rejects lost domains and any changed recorded prices atomically.
    observations = monthly_exit_observations(**normalized)
    result = risk_store.advance(account_id=namespace,
        expected_previous_session=expected_previous_session,
        observations=observations, baseline_targets=normalized['base_target']['quantities'],
        authorized_monthly_reset=authorized_monthly_reset,
        target_month=view['target_month'])
    return dict(result, monthly_cap_view=view, risk_namespace=namespace,
                policy_id='MONTHLY_CAP50_EXIT20', base_target_id=view['base_target_id'],
                source_admission_required=True, orders_created=False,
                account_mutated=False, automatic_acceptance_allowed=False)
