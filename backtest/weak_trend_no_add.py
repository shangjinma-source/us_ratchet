"""Predeclared research overlay in already-adjusted current share coordinates."""
from copy import deepcopy


def no_add_target(*, risk, shares, pending_orders=()):
    if pending_orders:
        raise ValueError('CARRIED_PENDING_ORDERS_UNSUPPORTED_BY_NEXT_OPEN_MODEL')
    result = deepcopy(risk)
    if any(type(q) is not int or q < 0 for q in shares.values()):
        raise ValueError('INVALID_CURRENT_HOLDINGS')
    for sid, diagnostic in result['diagnostics'].items():
        ceiling = diagnostic['monthly_ceiling']
        if type(ceiling) is not int or ceiling < 0 or type(diagnostic['on']) is not bool:
            raise ValueError('INVALID_RISK_DIAGNOSTIC')
        held = shares.get(sid, 0)
        target = ceiling if diagnostic['on'] else min(ceiling // 2, held)
        result['target_quantities'][sid] = target
        diagnostic.update(no_add_current_shares=held, no_add_target=target,
                          rounding='FLOOR_FULL_MONTHLY_CEILING_NOT_CURRENT_HOLDINGS')
    result['policy'] = 'SMA20_HALF_WEAK_NO_ADDITIONS_RESEARCH'
    return result
