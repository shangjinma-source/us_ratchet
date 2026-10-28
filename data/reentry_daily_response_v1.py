"""Map a checked reference projection to daily UI fields; not a release gate.

The owning composition must authenticate sources and check the publication seal
after this conversion. This module is not mounted in production.
"""
from copy import deepcopy
from core.reentry_buy_scope_v1 import digest, require

POLICY_ID = 'SAVED_FRONTIER_CAP50_EXIT20_REENTRY_V1'


def format_reference_advice(*, original_preview, projection, account):
    require(original_preview.get('status') == 'READY', 'REFERENCE_RESPONSE_ORIGINAL_NOT_READY')
    require(projection['binding']['original_preview_sha256'] == digest(original_preview),
            'REFERENCE_RESPONSE_ORIGINAL_CHANGED')
    binding = projection['binding']['original_binding']
    require(binding['account_id'] == account['account_id'] and
            binding['account_revision'] == account['revision'], 'REFERENCE_RESPONSE_ACCOUNT_CHANGED')
    gate = projection['buy_reference_gate']
    require(gate['binding']['actual_shares_sha256'] == digest(account['shares']),
            'REFERENCE_RESPONSE_HOLDINGS_CHANGED')
    result = deepcopy(original_preview)
    orders = deepcopy(projection['candidate_orders'])
    targets = deepcopy(projection['execution_targets'])
    ordered = {order['security_id']: order['side'] for order in orders}
    require(len(ordered) == len(orders), 'REFERENCE_RESPONSE_DUPLICATE_ORDER')
    rows = []
    for sid in sorted(set(targets) | set(account['shares'])):
        held = account['shares'].get(sid, 0)
        effective = targets.get(sid, 0)
        review = gate['buy_status'].get(sid)
        gap = effective - held
        intent = 'BUY' if gap > 0 else 'SELL' if gap < 0 else 'HOLD'
        if review in {'BLOCK_LOCKED', 'WAIT_REFERENCE'}:
            action = 'WAIT'
            intent = 'BUY'
            reason = 'WAIT_REENTRY_RECOVERY' if review == 'BLOCK_LOCKED' else 'WAIT_REENTRY_EVIDENCE'
        else:
            action = ordered.get(sid, 'WAIT' if gap else 'HOLD')
            reason = 'BOUND_DAILY_TARGET' if sid in ordered or not gap else 'NO_AVAILABLE_CASH'
        require(sid not in ordered or action == ordered[sid], 'REFERENCE_RESPONSE_ORDER_GATE_CHANGED')
        rows.append(dict(security_id=sid, held=held, effective_target=effective,
                         action=action, intent=intent, reason=reason))
    result.update(policy_id=POLICY_ID, base_policy_id=original_preview.get('policy_id'),
                  status='READY' if orders else 'WAIT',
                  detail_status='REFERENCE_FILTERED_PREVIEW' if orders else 'WAIT_REFERENCE_OR_CASH',
                  effective_target_quantities=targets, new_orders=orders,
                  difference=deepcopy(projection['difference']),
                  reference_quotes={sid: deepcopy(original_preview['reference_quotes'][sid]) for sid in ordered},
                  waiting_cash=deepcopy(projection['difference'].get('waiting_cash', [])),
                  risk_valid_until=projection['valid_until'],
                  daily_gate=dict(status='DAILY_TARGET_READY', effective_target_quantities=targets,
                                  rows=rows, execution_allowed=False, orders_created=False),
                  reference_projection=dict(schema='REFERENCE_PROJECTION_SUMMARY_V1',
                      projection_sha256=digest(projection),
                      reference_version=projection['binding']['reference_version'],
                      reference_state_sha256=projection['binding']['reference_state_sha256'],
                      buy_status=deepcopy(gate['buy_status'])),
                  requires_publication_check=True, production_released=False)
    require(orders or not result['difference']['new_orders'], 'REFERENCE_RESPONSE_WAIT_ORDERS')
    return result
