"""Independent cash/attribution arithmetic review, not source or strategy approval."""
from fractions import Fraction


def review_news_cash(book):
    if book.get('status') != 'COMPLETE':
        raise ValueError('COMPLETE_BOOK_REQUIRED')
    attribution = {}
    for audit in book['provider_audit']:
        if audit.get('status') != 'READY':
            raise ValueError('READY_AUDIT_REQUIRED')
        original = audit.get('risk_overlay', {}).get('effective_target_quantities', {})
        final = audit.get('target_shares', {})
        expected = {}
        for order in audit['orders']:
            if order['side'] != 'SELL':
                continue
            sid, quantity = order['security_id'], order['quantity']
            # Filled-book stock conservation and original risk audit remain
            # separate review obligations; this rechecks target attribution.
            implied_held = final.get(sid, 0) + quantity
            baseline_sale = max(0, implied_held - original.get(sid, 0))
            extra = quantity - baseline_sale
            if extra < 0:
                raise ValueError('NEGATIVE_EXTRA_SALE')
            if extra:
                expected[order['id']] = str(Fraction(extra, quantity))
                if order['id'] in attribution:
                    raise ValueError('DUPLICATE_SALE_ID')
                attribution[order['id']] = Fraction(extra, quantity)
        if expected != audit.get('news_sale_fractions', {}):
            raise ValueError('TARGET_ATTRIBUTION_MISMATCH')
    reserve = Fraction(0)
    filled, reserved_ids, by_day = {}, set(), {}
    allocation_dates = {row['decision_date'] for row in book['selection_account_states']}
    released_epochs = set()
    for entry in book['order_log']:
        kind = entry['event']
        effective_day = entry['date']
        if kind == 'NEWS_CASH_RELEASED':
            epoch = entry['allocation_epoch']
            if epoch not in allocation_dates or epoch in released_epochs or Fraction(entry['amount']) != reserve:
                raise ValueError('INVALID_CASH_RELEASE')
            released_epochs.add(epoch)
            effective_day = entry['active_date']
            if epoch != entry['date'] or effective_day <= epoch:
                raise ValueError('INVALID_RELEASE_CLOCK')
            reserve = Fraction(0)
        elif kind == 'ASSUMED_NEXT_OPEN_FILLED' and entry['side'] == 'SELL':
            if entry['id'] in filled:
                raise ValueError('DUPLICATE_SELL_FILL')
            filled[entry['id']] = entry
        elif kind == 'NEWS_NET_PROCEEDS_RESERVED':
            identifier = entry['order_id']
            if identifier in reserved_ids or identifier not in filled or identifier not in attribution:
                raise ValueError('UNBOUND_RESERVATION')
            fill = filled[identifier]
            expected = (fill['quantity'] * Fraction(fill['price']) - Fraction(fill['fee'])) * attribution[identifier]
            if (fill['date'] != effective_day or Fraction(entry['fraction']) != attribution[identifier]
                    or Fraction(entry['amount']) != expected or expected < 0):
                raise ValueError('NET_PROCEEDS_MISMATCH')
            reserve += expected
            reserved_ids.add(identifier)
            if Fraction(entry['reserved_total']) != reserve:
                raise ValueError('RESERVATION_TOTAL_MISMATCH')
        if kind in {'NEWS_CASH_RELEASED', 'NEWS_NET_PROCEEDS_RESERVED'}:
            by_day[effective_day] = reserve
    if reserved_ids != set(filled) & set(attribution):
        raise ValueError('MISSING_FILLED_NEWS_RESERVATION')
    closing = Fraction(0)
    for row in book['daily_ledger']:
        closing = by_day.get(row['date'], closing)
        cash = Fraction(row['cash'])
        if (not 0 <= closing <= cash or Fraction(row['news_reserved_cash']) != closing
                or Fraction(row['news_spendable_cash']) != cash-closing):
            raise ValueError('DAILY_NEWS_CASH_MISMATCH')
    if Fraction(book['news_cash_reservation']['amount']) != reserve:
        raise ValueError('TERMINAL_NEWS_CASH_MISMATCH')
    return dict(status='CASH_ATTRIBUTION_REVIEW_PASS', reservations=len(reserved_ids),
                source_authenticity_checked=False, full_stock_risk_review=False,
                economic_effectiveness_proven=False)
