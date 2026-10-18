"""Compact verified paper-account view; stored orders are not fresh quotes."""
from copy import deepcopy
from fractions import Fraction

from data.current_research_intraday_buy_plan import _require
from data.current_research_intraday_paper_ledger import _hash
from data.current_research_intraday_retarget_continuation_chain import review_retarget_continuation_chain


def compact_multiorder_account(value):
    """Consume full frozen proof, omit raw sources, and keep BUY/SELL accounting separate."""
    chain = review_retarget_continuation_chain(value)
    state = chain['ledger']
    original = chain['genesis']['ledger']
    prior = original['genesis']
    security = prior['acceptance']['proposal']['security']
    identities = {security['security_id']: security['ticker']}
    identities.update({sid: ref['ticker'] for sid, ref in
                       original['retarget_acceptance']['sizing_inputs']['execution_references'].items()})
    # V1/V2 have only BUY orders in the original security; their full replay above
    # establishes this, including historical orders replaced by V2 continuations.
    orders = {event['order_id']: dict(side='BUY', security_id=security['security_id'], ticker=security['ticker'])
              for event in prior['events']}
    orders.update(original['orders'])
    for operation in chain['operations']:
        if operation['kind'] == 'ACCEPT':
            prefix = _hash(operation)
            for index, order in enumerate(operation['proposal']['orders']):
                orders[prefix + ':' + str(index)] = order

    bought = Fraction(0)
    sold = Fraction(0)
    recent = []
    for event in state['events']:
        order = orders[event['order_id']]
        if event['kind'] == 'FILL':
            amount = event['quantity'] * Fraction(event['price'])
            if order['side'] == 'BUY':
                bought += amount
            else:
                sold += amount
        item = deepcopy(event)
        item.update(side=order['side'], security_id=order['security_id'], ticker=identities[order['security_id']])
        recent.append(item)
    initial = Fraction(prior['acceptance']['proposal']['causal_inputs']['available_cash'])
    _require(initial - bought + sold - Fraction(state['fees']) == Fraction(state['cash']),
             'MULTIORDER_CASH_CONSERVATION_FAILED')

    positions = []
    for sid in sorted(set(state['shares']) | set(state['target_quantities'])):
        held = state['shares'].get(sid, 0)
        reserved = state['reserved_shares'].get(sid, 0)
        target = state['target_quantities'].get(sid, 0)
        positions.append(dict(security_id=sid, ticker=identities[sid], quantity=held,
                              reserved_quantity=reserved, available_quantity=held-reserved,
                              target_quantity=target, remaining_difference=target-held))
    current_orders = []
    for order in state['orders'].values():
        item = deepcopy(order)
        item['ticker'] = identities[order['security_id']]
        item['remaining_quantity'] = order['quantity'] - order['filled_quantity']
        item['status'] = order['closed'] or 'OPEN'
        item['price_is_current_quote'] = False
        current_orders.append(item)
    return dict(schema='INTRADAY_MULTIORDER_ACCOUNT_VIEW_V1', research_only=True,
                execution_blocked=True, real_account=False, price_is_current_quote=False,
                account_id=state['account_id'], revision=state['revision'],
                original_acceptance_id=state['acceptance_id'], retarget_acceptance_id=state['retarget_acceptance_id'],
                target_month=original['retarget_acceptance']['proposal']['binding']['selection']['target_month'],
                initial_cash=str(initial), cash=state['cash'], reserved_cash=state['reserved_cash'],
                available_cash=str(Fraction(state['cash'])-Fraction(state['reserved_cash'])), fees=state['fees'],
                recorded_buy_notional=str(bought), recorded_sell_notional=str(sold),
                positions=positions, orders=current_orders, events=recent[-20:],
                event_count=len(recent), has_more_events=len(recent)>20,
                fee_scope=dict(commission='0', other_fees='UNKNOWN_NOT_RESERVED'))
