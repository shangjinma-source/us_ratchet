"""Offline diagnosis of current ledger/risk split support; never opens account files."""
from copy import deepcopy
import json

from core.strategy_account_ledger import apply_event, create_account
from core.monthly_peak_exit import advance_monthly_exit


def audit():
    account = create_account('synthetic-split-readiness')
    account, _ = apply_event(account, dict(
        event_id='synthetic-buy', kind='DIRECT_FILL', security_id='SYNTHETIC',
        side='BUY', quantity=14, price='1000', fees='0',
        executed_at='2026-11-02T15:00:00+00:00'), expected_revision=account['revision'])
    original = deepcopy(account)
    split_event = dict(event_id='synthetic-split', kind='SPLIT',
                       security_id='SYNTHETIC', ratio='8')
    try:
        apply_event(account, split_event, expected_revision=account['revision'])
        ledger_result = 'ACCEPTED_REQUIRES_FURTHER_AUDIT'
    except ValueError as error:
        ledger_result = str(error)
    assert account == original, 'DIAGNOSTIC_MUTATED_INPUT'

    arguments = dict(account_id=account['account_id'], decision_date='2026-10-30',
                     closes={'SYNTHETIC': '1000'}, unit_ids={'SYNTHETIC': 'PRE_SPLIT'},
                     baseline_targets={'SYNTHETIC': 10})
    prior = advance_monthly_exit(state=None, session_date='2026-10-30', **arguments)['state']
    before = deepcopy(prior)
    after_arguments = dict(arguments, closes={'SYNTHETIC': '125'},
                           unit_ids={'SYNTHETIC': 'POST_SPLIT'},
                           baseline_targets={'SYNTHETIC': 80})
    try:
        advance_monthly_exit(state=prior, session_date='2026-11-20', **after_arguments)
        risk_result = 'ACCEPTED_REQUIRES_FURTHER_AUDIT'
    except ValueError as error:
        risk_result = str(error)
    # Demonstrates why an adapter must never conceal a unit change: core alone
    # has no corporate-action discovery and treats an unlabelled price fall as risk.
    unlabelled = advance_monthly_exit(state=prior, session_date='2026-11-20',
        **dict(after_arguments, unit_ids={'SYNTHETIC': 'PRE_SPLIT'}))
    assert prior == before, 'DIAGNOSTIC_MUTATED_RISK_INPUT'
    return dict(status='PRODUCTION_SPLIT_TRANSITION_NOT_IMPLEMENTED',
        ledger_event_result=ledger_result, declared_unit_change_result=risk_result,
        unlabelled_unit_change_effective_target=unlabelled['effective_target_quantities'],
        expected_economic_invariant=dict(shares_before=14, shares_after=112,
            price_before='1000', price_after='125', market_value_before='14000',
            market_value_after='14000', target_before=10, target_after=80),
        scope='Pure core diagnosis only; source adapters and production HTTP not exercised',
        real_account_read=False, real_account_written=False, network_requests=0)


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
