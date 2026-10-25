"""Explicit current-target proposal registration without changing allocations.

Future monthly selections can choose an improved proposal normally. Adopting
the new runtime mid-month is restricted here to the identical capped basket.
This function neither activates a release nor touches account/risk records.
"""
from copy import deepcopy

from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_ledger import require


def bind_unchanged_current_proposal(*, monthly_view, expected_target_id, expected_revision):
    monthly = monthly_view.monthly
    with monthly.snapshot_operation():
        monthly_view.validate_sources()
        monthly.validate_current_target_pins()
        state = deepcopy(monthly.accounts.read())
        target = deepcopy(monthly.current())
        require(state is not None and state['revision'] == expected_revision, 'STALE_REVISION')
        require(target is not None and target['target_id'] == expected_target_id, 'STALE_TARGET')
        require(target['payload']['account_id'] == state['account_id'], 'TARGET_ACCOUNT_MISMATCH')
        proposal = build_frontier_proposal(target=target)
        payload = proposal['payload']
        require(payload['proof']['strict_improvement'] is False
                and payload['proposed_target_quantities'] == payload['base_capped_target_quantities'],
                'FRONTIER_MIDMONTH_ALLOCATION_CHANGE_REFUSED')
        monthly_view.validate_sources()
        require(monthly.accounts.read() == state and monthly.current() == target,
                'FRONTIER_MIGRATION_SNAPSHOT_CHANGED')
        saved = monthly_view.proposals.bind(target)
        require(saved == proposal, 'FRONTIER_MIGRATION_PROPOSAL_CHANGED')
        monthly_view.validate_sources()
        monthly.validate_current_target_pins()
        require(monthly.accounts.read() == state and monthly.current() == target,
                'FRONTIER_MIGRATION_SNAPSHOT_CHANGED')
        return dict(status='UNCHANGED_CURRENT_FRONTIER_REGISTERED',
                    target_id=target['target_id'], proposal_id=proposal['proposal_id'],
                    account_mutated=False, target_mutated=False, allocation_changed=False,
                    risk_reset=False, release_activated=False)
