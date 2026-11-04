"""Bind unit conversion to an unchanged native target and saved frontier.

This produces a separate transition document, not a replacement native target.
Source admission, risk-history persistence and atomic activation remain external.
"""
from hashlib import sha256
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_split_v1 import moment
from core.strategy_split_risk_projection_v1 import project_split_risk


def project_native_split(*, account_after, action_id, risk_before, target, expected_proposal_id):
    proposal = build_frontier_proposal(target=target)
    require(proposal['proposal_id'] == expected_proposal_id, 'SPLIT_STALE_PROPOSAL')
    require(target['payload']['account_id'] == account_after['account_id'], 'SPLIT_TARGET_ACCOUNT_MISMATCH')
    projected = project_split_risk(account_after=account_after, action_id=action_id,
        risk_before=risk_before, quantities_before=proposal['payload']['proposed_target_quantities'])
    action = next(row['payload'] for row in account_after['events']
                  if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id)
    effective = moment(action['effective_at'])
    require(moment(target['payload']['created_at']) < effective, 'SPLIT_TARGET_ALREADY_POST_ACTION')
    require(target['payload']['target_month'] == effective.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m'),
            'SPLIT_TARGET_MONTH_REQUIRES_REVIEW')
    original_quantities = dict(target['payload']['target_quantities'])
    if action['security_id'] in original_quantities:
        original_quantities[action['security_id']] *= action['ratio']
    payload = dict(schema='NATIVE_TARGET_SPLIT_TRANSITION_V1',
        account_revision=account_after['revision'], original_target_id=target['target_id'],
        original_proposal_id=proposal['proposal_id'], action_id=action_id,
        projected_original_quantities=original_quantities, risk_projection=projected,
        executable=False, orders_created=False, production_activated=False)
    return dict(transition_id=sha256(canonical(payload)).hexdigest(), payload=payload)
