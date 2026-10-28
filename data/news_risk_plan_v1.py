"""Independent non-executable risk-plan projection from a verified daily preview.

No replacement risk signal, account mutation, quote creation or order submission.
The owning service supplies the freshly authenticated original preview and AI
proposal. HOLD without original execution evidence is deliberately unsupported.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json

from core.news_investment_review_v1 import integer, moment, require
from data.strategy_account_preview import preview_scoped_account


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_risk_plan(*, proposal, original_preview, account, now):
    base = dict(schema='NEWS_AI_RISK_PLAN_V1', status='WAIT', reason='UNVERIFIED_INPUT',
                review_id=proposal.get('review_id'), original_binding=deepcopy(proposal.get('original_binding')),
                generated_at=now, valid_until=None, rows=[], candidate_orders=[], cash=None,
                waiting_cash=[], constraints=[], orders_created=False, executable=False,
                account_mutated=False, target_mutated=False, original_risk_mutated=False,
                limitation='Unadopted risk-plan preview; investment benefit has not been established.')
    try:
        return _build(base, proposal, original_preview, account, now)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        reason = str(error)
        return dict(base, reason=reason if reason.isupper() and len(reason) < 120 else 'RISK_PLAN_EVIDENCE_UNAVAILABLE')


def _build(base, proposal, original, account, now):
    current = moment(now)
    require(proposal.get('schema') == 'NEWS_INVESTMENT_REVIEW_PROPOSAL_V1', 'REVIEW_PROPOSAL_REQUIRED')
    require(proposal.get('status') == 'REVIEW_PROPOSAL_ONLY', 'WAIT_RECONCILIATION')
    require(proposal.get('executable') is False and proposal.get('orders_created') is False, 'NONEXECUTABLE_REVIEW_REQUIRED')
    binding = {key: original[key] for key in ('account_revision', 'target_id', 'proposal_id')}
    require(binding == proposal['original_binding'] and binding['account_revision'] == account['revision'], 'RISK_PLAN_BINDING_CHANGED')
    require(moment(proposal['review_created_at']) <= current < moment(proposal['review_valid_until']), 'REVIEW_EXPIRED')
    require(moment(original['risk_valid_from']) <= current < moment(original['risk_valid_until']), 'ORIGINAL_RISK_EXPIRED')
    require(account.get('cash_confirmation_valid') is True, 'CASH_CONFIRMATION_REQUIRED')
    require(type(account.get('orders')) is dict, 'ORDER_STATE_REQUIRED')
    require(not any(order.get('status') == 'OPEN' for order in account['orders'].values()), 'WAIT_PENDING_RECONCILIATION')
    require(original.get('status') == 'READY', 'WAIT_NEW_QUOTES_REQUIRED')
    original_difference = original.get('difference')
    require(type(original_difference) is dict and type(original_difference.get('binding')) is dict, 'WAIT_NEW_QUOTES_REQUIRED')
    proof = original_difference['binding']
    effective = original['effective_target_quantities']
    held = account['shares']
    require(proof['target_quantities'] == effective, 'WAIT_COMPLETE_EXECUTION_DOMAIN')
    require(proof['limits'] == original.get('reference_quotes'), 'QUOTE_BINDING_MISMATCH')
    require(proof['legacy_shares'] == {}, 'STRATEGY_SCOPE_REQUIRED')
    age = proof['maximum_mark_age_seconds']
    require(type(age) is int and 0 < age <= 120, 'MARK_AGE_POLICY_REQUIRED')
    original_check = preview_scoped_account(state=account, legacy_shares={}, marks=proof['marks'], limits=proof['limits'],
        target_quantities=effective, now=proof['now'], maximum_mark_age_seconds=age, fee_bps=proof['fee_bps'])
    require(original_check['binding_sha256'] == original_difference['binding_sha256'], 'ORIGINAL_ACCOUNT_EVIDENCE_CHANGED')
    def order_values(orders):
        return [{key: row[key] for key in ('security_id', 'side', 'quantity', 'limit_price', 'estimated_cash_change')} for row in orders]
    require(order_values(original_check['new_orders']) == order_values(original.get('new_orders', [])), 'ORIGINAL_ORDER_PROOF_MISMATCH')
    domain = {sid for sid in set(held) | set(effective) if held.get(sid, 0) > 0 or effective.get(sid, 0) > 0}
    rows = proposal['rows']
    require(type(rows) is list and len(rows) == len(domain) and {row['security_id'] for row in rows} == domain, 'RISK_PLAN_EXACT_DOMAIN_REQUIRED')
    if all(row.get('reviewed') is False or row.get('action') == 'ABSTAIN' for row in rows):
        return dict(base, status='ABSTAIN', reason='NO_ADMITTED_AI_OPINION')
    buy_caps = {row['security_id']: integer(row['quantity']) for row in original_check['new_orders'] if row['side'] == 'BUY'}
    targets, output_rows, constraints = {}, [], []
    deadlines = [moment(proposal['review_valid_until']), moment(original['risk_valid_until'])]
    for row in rows:
        sid = row['security_id']
        quantity, original_quantity = integer(held.get(sid, 0)), integer(effective.get(sid, 0))
        desired = integer(row['proposed_target_quantity'])
        require(row['held_quantity'] == quantity and row['original_target_quantity'] == original_quantity, 'AI_TARGET_ANCHOR_CHANGED')
        require(desired <= original_quantity, 'AI_CANNOT_RAISE_ORIGINAL_RISK_TARGET')
        action = row.get('action')
        require(action in ('KEEP', 'ABSTAIN', 'PAUSE_BUY', 'REDUCE_BUY', 'REDUCE_HOLDING', 'EXIT'), 'UNKNOWN_AI_ACTION')
        if row.get('reviewed') is not True or action in ('KEEP', 'ABSTAIN'):
            require(desired == original_quantity, 'UNREVIEWED_TARGET_MUST_REMAIN_ORIGINAL')
        if desired < min(quantity, original_quantity):
            require(row.get('reviewed') is True and action in ('REDUCE_HOLDING', 'EXIT'), 'HOLDING_REDUCTION_REQUIRES_EXPLICIT_ACTION')
        if action == 'EXIT':
            require(desired == 0, 'EXIT_TARGET_MUST_BE_ZERO')
        if action == 'PAUSE_BUY':
            require(desired == min(quantity, original_quantity), 'PAUSE_TARGET_MISMATCH')

        planned = min(desired, quantity+buy_caps.get(sid, 0)) if desired > quantity else desired
        if planned < desired:
            constraints.append(dict(security_id=sid, quantity=desired-planned, reason='BUY_CAPPED_TO_ORIGINAL_PREVIEW'))
        quote, mark = proof['limits'][sid], proof['marks'][sid]
        require(quote['evaluated_account_revision'] == account['revision'], 'QUOTE_ACCOUNT_CHANGED')
        require(quote['evaluated_net_gap'] == original_quantity-quantity, 'QUOTE_ORIGINAL_TARGET_CHANGED')
        require(isinstance(mark.get('source_hashes'), dict) and bool(mark['source_hashes']), 'VERIFIED_MARK_SOURCE_REQUIRED')
        require(all(quote.get('source_hashes', {}).get(path) == value for path, value in mark['source_hashes'].items()), 'QUOTE_SOURCE_BINDING_REQUIRED')
        deadline = moment(quote['reference_valid_until'])
        require(current < deadline, 'REQUOTE_REQUIRED')
        deadlines.append(deadline)
        if planned > quantity:
            require(quote.get('buy_evaluated') is True and Fraction(quote['buy']) > 0, 'BUY_QUOTE_NOT_EVALUATED')
        if planned < quantity:
            # Existing provider explicitly authenticates a near-last sell quote,
            # even when its original net gap was BUY. Never use the buy placeholder.
            last = Fraction(mark['price'])
            rounded_sell = Fraction(-(-last.numerator*100//last.denominator), 100)
            require(Fraction(quote['sell']) == rounded_sell and bool(quote.get('sell_reason')), 'VERIFIED_SELL_QUOTE_REQUIRED')
        targets[sid] = planned
        output_rows.append(dict(security_id=sid, action=row['action'], held_quantity=quantity,
                                original_target_quantity=original_quantity, proposed_target_quantity=desired,
                                desired_target_quantity=desired, planned_target_quantity=planned,
                                execution_buy_cap=buy_caps.get(sid, 0), reviewed=row.get('reviewed') is True))
    # Zero targets may leave the original mark domain. Limit evidence is restricted
    # to exactly the positions still needed by the real ledger difference core.
    needed = {sid for sid in set(held) | set(targets) if held.get(sid, 0) > 0 or targets.get(sid, 0) > 0}
    difference = preview_scoped_account(state=account, legacy_shares={},
        marks={sid: proof['marks'][sid] for sid in needed}, limits={sid: proof['limits'][sid] for sid in needed},
        target_quantities=targets, now=now, maximum_mark_age_seconds=age, fee_bps=proof['fee_bps'])
    require(difference['status'] in ('READY', 'WAIT_CASH'), 'RISK_PLAN_DIFFERENCE_NOT_READY')
    for order in difference['new_orders']:
        if order['side'] == 'BUY':
            require(order['quantity'] <= buy_caps.get(order['security_id'], 0), 'BUY_EXCEEDS_ORIGINAL_EXECUTION_CAP')
    original_sells = {row['security_id']: row['quantity'] for row in original_check['new_orders'] if row['side'] == 'SELL'}
    planned_sells = {row['security_id']: row['quantity'] for row in difference['new_orders'] if row['side'] == 'SELL'}
    require(all(planned_sells.get(sid, 0) >= quantity for sid, quantity in original_sells.items()), 'ORIGINAL_SELL_MUST_NOT_BE_REDUCED')
    lineage = dict(schema='NEWS_AI_RISK_PLAN_BINDING_V1', original_preview_sha256=digest(original),
                   original_policy_id=original.get('policy_id'), original_risk_valid_from=original['risk_valid_from'],
                   original_risk_valid_until=original['risk_valid_until'], original_effective_targets=deepcopy(effective),
                   original_account_proof_sha256=original_difference['binding_sha256'],
                   review_id=proposal['review_id'], review_sha256=digest(proposal),
                   proposed_targets={row['security_id']: row['proposed_target_quantity'] for row in rows},
                   planned_targets=targets, derived_account_proof_sha256=difference['binding_sha256'])
    return dict(base, status='READY', reason='LOWER_TARGET_PREVIEW_ONLY', rows=output_rows,
                candidate_orders=deepcopy(difference['new_orders']), valid_until=min(deadlines).isoformat(),
                waiting_cash=deepcopy(difference['waiting_cash']), constraints=constraints,
                cash={**{key: difference[key] for key in ('spendable_cash', 'new_buy_cash_required', 'unallocated_spendable_cash')},
                      'sell_proceeds_assumed': False},
                original_preview_sha256=digest(original), binding=lineage, binding_sha256=digest(lineage))
