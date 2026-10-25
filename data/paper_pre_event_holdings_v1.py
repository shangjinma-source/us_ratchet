"""Read historical paper holdings for later corporate-action review.

Formal replay is mandatory. This does not certify a dividend entitlement,
share-unit continuity, ex-date, payment, or any account posting.
"""
from datetime import datetime, timezone
from backtest.current_strategy_prospective_paper_book_v1 import replay, _context, digest
from data.strategy_paper_application_descriptor_v1 import sessions, stamp, require


def holdings_before_session(*, book, authority, admitted_decisions,
                            session_date, admitted_settlements=None, clock=None):
    now = stamp((clock or (lambda: datetime.now(timezone.utc)))())
    app = _context(authority, now)
    checked = replay(book, authority=authority, admitted_decisions=admitted_decisions,
                     admitted_settlements=admitted_settlements)
    require(stamp(checked['last_available_at']) <= now, 'PAPER_HOLDINGS_FUTURE_BOOK')
    calendar = sessions(authority['descriptor_arguments']['calendar_bytes'], app['calendar_sha256'])
    matches = [s for s in calendar if s['date'] == session_date]
    require(len(matches) == 1, 'PAPER_HOLDINGS_SESSION_REQUIRED')
    boundary = stamp(matches[0]['open'])
    require(boundary <= now, 'PAPER_HOLDINGS_FUTURE_BOUNDARY')
    # An unresolved prior DAY order may still change historical ownership.
    unresolved = [oid for oid, order in checked['orders'].items()
                  if stamp(order['accepted_at']) < boundary and order['closed'] is None]
    if unresolved:
        return dict(status='WAIT_PRIOR_ORDER_SETTLEMENT', unresolved_order_ids=sorted(unresolved),
                    account_mutated=False, entitlement_verified=False)
    shares, contributions = {}, []
    for operation in checked['operations']:
        if operation['request']['kind'] != 'SETTLE':
            continue
        for oid, outcome in operation['outcome'].items():
            event = outcome.get('event_proposal')
            if not event or event['type'] != 'FILL' or stamp(event['executed_at']) >= boundary:
                continue
            order = checked['orders'][oid]
            require(order['closed'] == 'FILLED', 'PAPER_HOLDINGS_UNCOMMITTED_FILL')
            quantity = event['quantity'] * (1 if order['side'] == 'BUY' else -1)
            sid = order['security_id']
            shares[sid] = shares.get(sid, 0) + quantity
            contributions.append(dict(order_id=oid, security_id=sid, quantity=quantity,
                                      executed_at=event['executed_at'],
                                      operation_revision=operation['revision']))
    require(all(q >= 0 for q in shares.values()), 'PAPER_HOLDINGS_NEGATIVE')
    return dict(status='REPLAYED_PRE_SESSION_HOLDINGS_NOT_ENTITLEMENT',
                account_id=checked['account_id'], book_revision=checked['revision'],
                session_date=session_date, boundary=boundary.isoformat(),
                shares={sid: q for sid, q in shares.items() if q}, contributions=contributions,
                book_sha256=digest(checked), observed_at=now.isoformat(),
                account_mutated=False, entitlement_verified=False,
                share_unit_continuity_verified=False, payment_verified=False)
