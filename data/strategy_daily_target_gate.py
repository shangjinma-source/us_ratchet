"""Experimental pure daily-signal boundary, NOT wired into production.

The owning server must authenticate the policy release and the underlying market
evidence before calling. This validates binding and availability, not the truth
of a strategy signal. No indicator, risk parameter, quote, order or fill is
invented here. Monthly desired holdings alone never authorize a daily trade.
"""
from copy import deepcopy
from zoneinfo import ZoneInfo

from core.strategy_account_difference import number, quantities, require, timestamp


def resolve_daily_target(*, account_id, account_revision, target_id, target_month,
                         monthly_quantities, strategy_shares, available_cash,
                         pending_orders, now, expected_policy_id, signal=None):
    """Return a validated effective target for the existing difference engine.

    BUY/SELL are directional intents only: fresh prices, affordability, existing
    reservations and order conflicts still belong to build_strategy_difference.
    A WAIT never supplies an executable target or automatically cancels orders.
    """
    held = quantities(strategy_shares)
    monthly = quantities(monthly_quantities)
    cash = number(available_cash)
    current = timestamp(now)
    require(type(account_id) is str and bool(account_id), 'ACCOUNT_ID_REQUIRED')
    require((type(account_revision) is int and account_revision >= 0)
            or (type(account_revision) is str and bool(account_revision.strip())),
            'ACCOUNT_REVISION_REQUIRED')
    require(type(target_id) is str and bool(target_id), 'TARGET_ID_REQUIRED')
    require(type(pending_orders) is list, 'PENDING_ORDERS_REQUIRED')
    pending = {}
    for order in pending_orders:
        require(type(order) is dict and order.get('account_id') == account_id
                and order.get('scope') == 'STRATEGY', 'PENDING_SCOPE_MISMATCH')
        sid = order.get('security_id')
        require(type(sid) is str and bool(sid) and order.get('side') in {'BUY', 'SELL'}
                and type(order.get('remaining_quantity')) is int
                and order['remaining_quantity'] > 0, 'INVALID_PENDING_ORDER')
        pending.setdefault(sid, []).append(deepcopy(order))
    domain = set(held) | set(monthly) | set(pending)

    def waiting(reason):
        return dict(status=reason, effective_target_quantities=None,
                    rows=[dict(security_id=sid, action='WAIT', reason=reason,
                               held=held.get(sid, 0)) for sid in sorted(domain)],
                    execution_allowed=False, orders_created=False)

    if target_month != current.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m'):
        return waiting('WAIT_MONTHLY_TARGET')
    if expected_policy_id is None or expected_policy_id == '':
        return waiting('WAIT_POLICY_RELEASE')
    require(type(expected_policy_id) is str and bool(expected_policy_id.strip()),
            'POLICY_ID_REQUIRED')
    if signal is None:
        return waiting('WAIT_SIGNAL')
    require(type(signal) is dict, 'INVALID_DAILY_SIGNAL')
    for key, expected in (('account_id', account_id), ('account_revision', account_revision),
                          ('target_id', target_id), ('policy_id', expected_policy_id)):
        require(type(signal.get(key)) is type(expected) and signal[key] == expected,
                'DAILY_SIGNAL_BINDING_MISMATCH')
    available = timestamp(signal['available_at'])
    observed = timestamp(signal['observed_at'])
    valid_from = timestamp(signal['valid_from'])
    valid_until = timestamp(signal['valid_until'])
    require(observed <= available <= valid_from < valid_until, 'INVALID_SIGNAL_CLOCK')
    if not valid_from <= current < valid_until:
        return waiting('WAIT_FRESH_SIGNAL')
    require(type(signal.get('evidence_id')) is str and bool(signal['evidence_id']),
            'SIGNAL_EVIDENCE_REQUIRED')
    effective = quantities(signal['effective_target_quantities'])
    require(set(effective) == domain, 'DAILY_SIGNAL_DOMAIN_MISMATCH')
    rows = []
    for sid in sorted(domain):
        gap = effective[sid] - held.get(sid, 0)
        intent = 'BUY' if gap > 0 else 'SELL' if gap < 0 else 'HOLD'
        # Pending orders require the existing exact reservation/conflict engine;
        # this new boundary cannot guess whether they fill or cancel them.
        action = 'WAIT' if sid in pending or (gap > 0 and cash == 0) else intent
        reason = ('PENDING_RECONCILIATION_REQUIRED' if sid in pending else
                  'NO_AVAILABLE_CASH' if gap > 0 and cash == 0 else 'BOUND_DAILY_TARGET')
        rows.append(dict(security_id=sid, action=action, intent=intent, reason=reason,
                         held=held.get(sid, 0), effective_target=effective[sid]))
    return dict(status='DAILY_TARGET_READY', effective_target_quantities=effective,
                rows=rows, execution_allowed=False, orders_created=False,
                requires_difference_and_fresh_limits=True)
