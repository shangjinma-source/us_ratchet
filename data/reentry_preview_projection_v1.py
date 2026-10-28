"""Isolated reference projection with the original ledger and execution evidence.

Source/identity authentication and atomic recovery precede this layer. No IO,
model calls, persistence or production routing. Cash is allocated after gating.
"""
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction

from core.reentry_buy_scope_v1 import build_buy_scope_gate, digest, require
from core.news_investment_review_v1 import moment
from data.strategy_account_preview import preview_scoped_account


def project_reference_preview(*, account, original_preview, reference_state,
                              decision_session, scope_proofs, now):
    original = original_preview
    current = moment(now)
    require(original.get('status') == 'READY', 'REFERENCE_ORIGINAL_NOT_READY')
    require(original['account_revision'] == account['revision'], 'REFERENCE_ACCOUNT_CHANGED')
    require(moment(original['risk_valid_from']) <= current < moment(original['risk_valid_until']),
            'REFERENCE_ORIGINAL_RISK_EXPIRED')
    require(not any(o.get('status') == 'OPEN' for o in account['orders'].values()),
            'REFERENCE_PENDING_RECONCILIATION')
    proof = original['difference']['binding']
    targets = original['effective_target_quantities']
    require(proof['target_quantities'] == targets and proof['legacy_shares'] == {},
            'REFERENCE_ORIGINAL_TARGET_CHANGED')
    require(proof['limits'] == original['reference_quotes'], 'REFERENCE_QUOTE_BINDING')
    age = proof['maximum_mark_age_seconds']
    require(type(age) is int and 0 < age <= 120, 'REFERENCE_MARK_AGE_POLICY')
    require(moment(proof['now']) <= current, 'REFERENCE_PROJECTION_BEFORE_ORIGINAL')
    original_check = preview_scoped_account(
        state=account, legacy_shares={}, marks=proof['marks'], limits=proof['limits'],
        target_quantities=targets, now=proof['now'], maximum_mark_age_seconds=age,
        fee_bps=proof['fee_bps'])
    # The real daily composition annotates the same order objects also held in
    # difference.new_orders. Authenticate those exact two provenance fields
    # before comparing the underlying ledger result; never discard other fields.
    provenance = dict(source_target_id=original['target_id'], proposal_id=original['proposal_id'])
    tagged = any(set(provenance) & set(order) for order in original['new_orders'])

    def ledger_orders(orders):
        normalized = deepcopy(orders)
        for order in normalized:
            if tagged:
                require(all(order.get(k) == v for k, v in provenance.items()),
                        'REFERENCE_ORDER_PROVENANCE_CHANGED')
                for key in provenance:
                    del order[key]
            else:
                require(not (set(provenance) & set(order)), 'REFERENCE_ORDER_PROVENANCE_CHANGED')
        return normalized

    normalized_difference = deepcopy(original['difference'])
    normalized_difference['new_orders'] = ledger_orders(normalized_difference['new_orders'])
    require(original_check == normalized_difference, 'REFERENCE_ORIGINAL_PROOF_CHANGED')
    require(original_check['new_orders'] == ledger_orders(original['new_orders']),
            'REFERENCE_ORIGINAL_ORDERS_CHANGED')
    deadlines = [moment(original['risk_valid_until'])]
    for sid, quote in proof['limits'].items():
        mark = proof['marks'][sid]
        require(quote['evaluated_account_revision'] == account['revision'] and
                quote['evaluated_net_gap'] == targets.get(sid, 0) - account['shares'].get(sid, 0),
                'REFERENCE_QUOTE_ACCOUNT_TARGET_CHANGED')
        hashes = mark.get('source_hashes')
        require(type(hashes) is dict and bool(hashes) and
                all(quote.get('source_hashes', {}).get(k) == v for k, v in hashes.items()),
                'REFERENCE_QUOTE_SOURCE_BINDING')
        deadline = moment(quote['reference_valid_until'])
        require(current < deadline, 'REFERENCE_REQUOTE_REQUIRED')
        mark_deadline = moment(mark['observed_at']) + timedelta(seconds=age)
        require(current < mark_deadline, 'REFERENCE_MARK_EXPIRED')
        deadlines.extend((deadline, mark_deadline))
    binding = dict(account_id=account['account_id'], account_revision=account['revision'],
                   target_id=original['target_id'], proposal_id=original['proposal_id'])
    gate = build_buy_scope_gate(reference_state=reference_state, original_binding=binding,
        decision_session=decision_session, effective_targets=targets,
        actual_shares=account['shares'], scope_proofs=scope_proofs)
    derived_targets = gate['execution_targets']
    needed = {sid for sid in set(account['shares']) | set(derived_targets)
              if account['shares'].get(sid, 0) > 0 or derived_targets.get(sid, 0) > 0}
    difference = preview_scoped_account(
        state=account, legacy_shares={}, marks={s: proof['marks'][s] for s in needed},
        limits={s: proof['limits'][s] for s in needed}, target_quantities=derived_targets,
        now=now, maximum_mark_age_seconds=age, fee_bps=proof['fee_bps'])
    original_sells = [o for o in original_check['new_orders'] if o['side'] == 'SELL']
    derived_sells = [o for o in difference['new_orders'] if o['side'] == 'SELL']
    require(derived_sells == original_sells, 'REFERENCE_ORIGINAL_SELL_CHANGED')
    for order in difference['new_orders']:
        if order['side'] == 'BUY':
            sid = order['security_id']
            require(gate['buy_status'][sid] == 'ALLOW' and
                    order['quantity'] <= targets[sid] - account['shares'].get(sid, 0),
                    'REFERENCE_BUY_TARGET_EXCEEDED')
    require(Fraction(difference['new_buy_cash_required']) <= Fraction(difference['spendable_cash']),
            'REFERENCE_CASH_EXCEEDED')
    candidate_orders = deepcopy(difference['new_orders'])
    if tagged:
        for order in candidate_orders:
            order.update(provenance)
    require([o for o in candidate_orders if o['side'] == 'SELL'] ==
            [o for o in original['new_orders'] if o['side'] == 'SELL'],
            'REFERENCE_ORIGINAL_SELL_CHANGED')
    lineage = dict(original_preview_sha256=digest(original),
        reference_state_sha256=digest(reference_state), reference_version=reference_state['version'],
        gate_binding_sha256=gate['binding_sha256'], original_binding=binding,
        derived_account_proof_sha256=difference['binding_sha256'])
    return dict(schema='REFERENCE_PREVIEW_PROJECTION_V1',
        status='WAIT_BUY_REFERENCE' if gate['status'] == 'WAIT_BUY_REFERENCE' else 'REFERENCE_PROJECTION_CHECKED',
        generated_at=now, valid_until=min(deadlines).isoformat(),
        original_effective_targets=deepcopy(targets), execution_targets=deepcopy(derived_targets),
        buy_reference_gate=gate, difference=difference,
        candidate_orders=candidate_orders, binding=lineage,
        binding_sha256=digest(lineage), original_sell_orders_preserved=True,
        cash_allocated_after_reference_gate=True, sell_proceeds_assumed=False,
        executable=False, orders_created=False, account_mutated=False,
        source_authentication_performed=False)
