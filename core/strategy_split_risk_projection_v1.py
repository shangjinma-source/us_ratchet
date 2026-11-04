"""Pure pre-publication unit projection; not a target or risk-store migration.

Consumes a split already recorded in an authenticated account snapshot. Original
monthly targets/proposals remain immutable. The caller must bind the supplied
quantity map to them and coordinate persistence before publishing any orders.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require, _revision
from core.strategy_account_split_v1 import moment


def project_split_risk(*, account_after, action_id, risk_before, quantities_before):
    require(account_after.get('revision') == _revision(account_after), 'SPLIT_ACCOUNT_INTEGRITY')
    events = [row for row in account_after['events']
              if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id]
    require(len(events) == 1, 'SPLIT_RECORDED_ACTION_REQUIRED')
    event = events[0]['payload']
    sid, ratio = event['security_id'], event['ratio']
    same_security_actions = [row['payload'] for row in account_after['events']
                             if row['payload']['kind'] == 'SPLIT_CONFIRMED'
                             and row['payload']['security_id'] == sid]
    require(same_security_actions[-1] == event, 'SPLIT_LATER_ACCOUNT_ACTION_REQUIRES_REVIEW')
    require(type(ratio) is int and ratio > 1, 'INTEGER_FORWARD_SPLIT_REQUIRED')
    require(risk_before['schema'] == 'MONTHLY_PEAK_EXIT_V1'
            and risk_before['account_id'] == account_after['account_id'], 'SPLIT_RISK_ACCOUNT_MISMATCH')
    require(sid in risk_before['peaks'] and sid in risk_before['last_closes'], 'SPLIT_RISK_DOMAIN_MISSING')
    require(risk_before['unit_ids'][sid] == event['old_unit_id'], 'SPLIT_RISK_OLD_UNIT_REQUIRED')
    effective_day = moment(event['effective_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(risk_before['session_date'] < effective_day, 'SPLIT_RISK_ALREADY_PAST_BOUNDARY')
    require(type(quantities_before) is dict and all(type(q) is int and q >= 0 for q in quantities_before.values()),
            'SPLIT_TARGET_QUANTITIES_INVALID')
    require(set(quantities_before) <= set(risk_before['peaks']), 'SPLIT_TARGET_RISK_DOMAIN')
    transformed = deepcopy(risk_before)
    for field in ('peaks', 'last_closes'):
        old = Fraction(risk_before[field][sid])
        require(old > 0, 'SPLIT_RISK_PRICE_INVALID')
        transformed[field][sid] = str(old / ratio)
    transformed['unit_ids'][sid] = event['new_unit_id']
    quantities = deepcopy(quantities_before)
    if sid in quantities:
        quantities[sid] *= ratio
    # Keeping exited and the decision epoch prevents a corporate action from
    # accidentally resetting the same-month exit rule.
    binding = dict(account_id=account_after['account_id'], account_revision=account_after['revision'],
                   action_sha256=sha256(canonical(event)).hexdigest(),
                   risk_before_sha256=sha256(canonical(risk_before)).hexdigest(),
                   quantities_before_sha256=sha256(canonical(quantities_before)).hexdigest())
    result = dict(schema='SPLIT_RISK_UNIT_PROJECTION_V1', binding=binding,
                  risk_state=transformed, target_quantities=quantities,
                  effective_at=event['effective_at'], orders_created=False,
                  production_activated=False, requires_coordinated_publication=True)
    result['projection_sha256'] = sha256(canonical(result)).hexdigest()
    return result
