"""Derive reentry eligibility only from this provider's executed book orders."""
from copy import deepcopy
from fractions import Fraction


def _convert(sid, unit, price, *, after, through, events):
    for event in events:
        if after < event['date'] <= through and event['security_id'] == sid:
            if unit != event['old_unit_id']:
                raise ValueError('REENTRY_JOURNAL_UNIT_MISMATCH')
            price *= Fraction(event['old_shares']) / Fraction(event['new_shares'])
            sid = event.get('new_security_id', sid)
            unit = event['new_unit_id']
    return sid, unit, price


def advance_journal(journal, *, state, decision_date, events):
    updated = deepcopy(journal)
    observed = set()
    for fill in state.get('order_log', []):
        if fill.get('event') != 'ASSUMED_NEXT_OPEN_FILLED':
            continue
        identifier = fill['id']
        if identifier in observed:
            raise ValueError('DUPLICATE_BOOK_FILL_ID')
        observed.add(identifier)
        if fill['date'] > decision_date:
            raise ValueError('FUTURE_BOOK_FILL')
        if identifier in updated['seen_fills']:
            if updated['seen_fills'][identifier] != fill:
                raise ValueError('PREVIOUS_BOOK_FILL_CHANGED')
            continue
        updated['seen_fills'][identifier] = deepcopy(fill)
        order = updated['orders'].get(identifier)
        if order is None:
            continue
        if fill['date'] != order['active_date'] or fill['side'] != order['side']:
            raise ValueError('REENTRY_FILL_ORDER_MISMATCH')
        sid, unit, _ = _convert(order['security_id'], order['unit_id'], Fraction(1),
                                after=order['decision_date'], through=fill['date'], events=events)
        if fill['security_id'] != sid or type(fill['quantity']) is not int or fill['quantity'] <= 0:
            raise ValueError('REENTRY_FILL_SECURITY_OR_QUANTITY_MISMATCH')
        if order['risk_exit'] and state['shares'].get(sid, 0) == 0:
            updated['exits'][sid] = dict(date=fill['date'], unit_id=unit)
        if order['reentry_exit_date'] is not None:
            if not order['reentry_exit_date'] < fill['date'] or Fraction(fill['price']) <= 0:
                raise ValueError('INVALID_EXECUTED_REENTRY_FILL')
            updated['entries'].append(dict(security_id=sid, date=fill['date'], price=fill['price'],
                execution_id=identifier, unit_id=unit, exit_date=order['reentry_exit_date']))
            for prior_sid, prior_exit in list(updated['exits'].items()):
                current_sid, _, _ = _convert(prior_sid, prior_exit['unit_id'], Fraction(1),
                    after=prior_exit['date'], through=fill['date'], events=events)
                if current_sid == sid:
                    del updated['exits'][prior_sid]
    if not set(updated['seen_fills']) <= observed:
        raise ValueError('PREVIOUS_BOOK_FILL_MISSING')
    return updated


def comparison_journal(journal, *, anchor, decision_date, holdings, events):
    exits = {}
    for sid, record in journal['exits'].items():
        converted, _, _ = _convert(sid, record['unit_id'], Fraction(1),
            after=record['date'], through=decision_date, events=events)
        if anchor <= record['date'] < decision_date and not holdings.get(converted, 0):
            if converted in exits:
                raise ValueError('REENTRY_EXIT_IDENTITY_COLLISION')
            exits[converted] = record['date']
    entries = []
    for record in journal['entries']:
        if record['exit_date'] < anchor:
            continue
        sid, unit, price = _convert(record['security_id'], record['unit_id'], Fraction(record['price']),
            after=record['date'], through=decision_date, events=events)
        entries.append(dict(record, security_id=sid, unit_id=unit, price=str(price)))
    return dict(eligible_reentries=exits, executed_reentries=entries)
