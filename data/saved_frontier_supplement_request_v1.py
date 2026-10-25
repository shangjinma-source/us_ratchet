"""Versioned proposal-domain request preparation preserving original target identity."""
from hashlib import sha256

from core.strategy_account_ledger import canonical, require
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.saved_frontier_supplement_prepare_v1 import prepare_supplement_request


def prepare_frontier_supplement_request(*, root, state, target, proposal, risk_state,
        identity_reference, calendar_reference, unit_source_paths, source_pins,
        decision_date, now):
    """Resolve the complete proposal/held/open/risk domain with existing admissions.

    Risk state is the caller's current store snapshot; no store is advanced here.
    Capture still uses its original four-field binding; subsequent review binds
    the proposal and exact risk snapshot independently.
    """
    require(proposal == build_frontier_proposal(target=target), 'FRONTIER_PROPOSAL_CHANGED')
    quantities = proposal['payload']['proposed_target_quantities']
    extra = set()
    if risk_state is not None:
        require(risk_state['schema'] == 'MONTHLY_PEAK_EXIT_V1' and
                risk_state['account_id'] == state['account_id'], 'FRONTIER_RISK_ACCOUNT')
        if risk_state['target_month'] == target['payload']['target_month']:
            require(decision_date == risk_state['decision_date'], 'FRONTIER_RISK_EPOCH')
        extra.update(risk_state['peaks'])
        extra.update(risk_state['exited'])
    needed = {sid for sid, quantity in quantities.items() if quantity} | extra
    needed.update(sid for sid, quantity in state['shares'].items() if quantity)
    needed.update(order['security_id'] for order in state['orders'].values()
                  if order['status'] == 'OPEN' and order['remaining_quantity'] > 0)
    result = prepare_supplement_request(root=root, state=state, target=target,
        identity_reference=identity_reference, calendar_reference=calendar_reference,
        unit_source_paths=unit_source_paths, source_pins=source_pins,
        security_ids=needed, decision_date=decision_date, now=now,
        monthly_quantities=quantities, extra_security_ids=extra)
    result['proposal_id'] = proposal['proposal_id']
    result['risk_state_sha256'] = sha256(canonical(risk_state)).hexdigest()
    if result['request'] is not None:
        result['review_binding'] = dict(result['binding'], proposal_id=proposal['proposal_id'],
            risk_state_sha256=result['risk_state_sha256'])
    return result
