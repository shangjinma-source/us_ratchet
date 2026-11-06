"""Isolated target-weight bridge; never writes accounts or activates a strategy.
Caller must authenticate signals, security identity, corporate actions and quotes.
"""
from fractions import Fraction
from copy import deepcopy
from core.strategy_account_difference import require, timestamp
from data.strategy_account_preview import preview_scoped_account


def preview_target_weights(*, account, expected_revision, weights, marks, limits,
                           signal_at, valid_from, valid_until, now, contract_hash):
    require(account['revision'] == expected_revision, 'STALE_REVISION')
    require(len(contract_hash) == 64 and all(c in '0123456789abcdef' for c in contract_hash), 'CONTRACT_HASH_REQUIRED')
    require(timestamp(signal_at) < timestamp(valid_from) <= timestamp(now) < timestamp(valid_until), 'SIGNAL_EXECUTION_WINDOW')
    require(type(weights) is dict, 'EXPLICIT_WEIGHTS_REQUIRED')
    allocation = {sid: Fraction(value) for sid, value in weights.items()}
    require(all(0 <= weight <= 1 for weight in allocation.values()) and sum(allocation.values()) <= 1, 'INVALID_WEIGHTS')
    needed = {sid for sid, q in account['shares'].items() if q} | set(allocation)
    needed |= {order['security_id'] for order in account['orders'].values() if order['status'] == 'OPEN'}
    require(needed <= set(marks) and needed <= set(limits), 'HELD_TARGET_PENDING_QUOTE_REQUIRED')
    # Total cash includes reservations; spendability is enforced by original engine.
    equity = Fraction(account['total_uninvested_cash'])
    for sid, quantity in account['shares'].items():
        if quantity:
            equity += quantity * Fraction(marks[sid]['price'])
    require(equity > 0, 'POSITIVE_TRADABLE_EQUITY_REQUIRED')
    targets = {sid: int(equity * weight / Fraction(marks[sid]['price'])) for sid, weight in allocation.items()}
    execution_domain = {sid for sid, q in account['shares'].items() if q} | {sid for sid, q in targets.items() if q}
    execution_domain |= {order['security_id'] for order in account['orders'].values() if order['status'] == 'OPEN'}
    difference = preview_scoped_account(state=account, legacy_shares={}, marks={sid: marks[sid] for sid in execution_domain},
        limits={sid: limits[sid] for sid in execution_domain}, target_quantities=targets, now=now, maximum_mark_age_seconds=120, fee_bps='0')
    return dict(schema='TARGET_WEIGHT_ACCOUNT_BRIDGE_RESEARCH_V1', account_revision=expected_revision,
        strategy_contract_sha256=contract_hash, tradable_equity=str(equity), target_quantities=targets,
        difference=deepcopy(difference), production_activated=False, executable=False, orders_created=False,
        limitation='Isolated migration/difference test only; authenticated live signal and economic admission required.')
