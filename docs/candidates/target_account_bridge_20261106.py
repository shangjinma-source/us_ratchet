"""Isolated target-weight bridge; never writes accounts or activates a strategy.
Caller must authenticate signals, security identity, corporate actions and quotes.
"""
from fractions import Fraction
from copy import deepcopy
from hashlib import sha256
import json
from core.strategy_account_difference import require, timestamp
from data.strategy_account_preview import preview_scoped_account


def sequential_cash_allocation(difference):
    """ROA frozen-target allocation, using only already validated real cash."""
    result=deepcopy(difference)
    if result['status']=='CANCEL_THEN_RECALCULATE':return result
    require(result['status'] in ('READY','WAIT_CASH'), 'DIFFERENCE_STATUS')
    needs={}
    for row in result['new_orders']:
        if row['side']=='BUY':needs[row['security_id']]=row['quantity']
    for row in result['waiting_cash']:
        sid=row['security_id'];needs[sid]=needs.get(sid,0)+row['quantity']
    orders=[row for row in result['new_orders'] if row['side']=='SELL']
    cash=Fraction(result['spendable_cash']);allocated=Fraction(0);waiting=[]
    rate=Fraction(result['binding']['fee_bps'])/10000
    for sid,quantity in sorted(needs.items()):
        price=Fraction(result['binding']['limits'][sid]['buy']);unit=price*(1+rate)
        assigned=min(quantity,int((cash-allocated)//unit))
        if assigned:
            cost=assigned*unit;allocated+=cost
            orders.append(dict(security_id=sid,side='BUY',quantity=assigned,
                limit_price=str(price),estimated_cash_change=str(-cost)))
        if assigned<quantity:
            waiting.append(dict(security_id=sid,quantity=quantity-assigned,
                reason='WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED'))
    result['binding']['buy_allocation_policy']='SORTED_SECURITY_ID_SEQUENTIAL'
    result['binding_sha256']=sha256(json.dumps(result['binding'],sort_keys=True,
        separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    result.update(status='WAIT_CASH' if waiting else 'READY',new_orders=orders,
        waiting_cash=waiting,new_buy_cash_required=str(allocated),
        unallocated_spendable_cash=str(cash-allocated),buy_allocation_fraction=None,
        buy_allocation_policy='SORTED_SECURITY_ID_SEQUENTIAL')
    return result


def preview_target_weights(*, account, expected_revision, weights, marks, limits,
                           signal_at, valid_from, valid_until, now, contract_hash,
                           frozen_quantities=None):
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
    if frozen_quantities is not None:
        require(type(frozen_quantities) is dict and set(frozen_quantities) <= set(allocation), 'FROZEN_TARGET_SCOPE')
        require(all(type(q) is int and q >= 0 for q in frozen_quantities.values()), 'FROZEN_TARGET_INTEGER_REQUIRED')
        targets = deepcopy(frozen_quantities)
    execution_domain = {sid for sid, q in account['shares'].items() if q} | {sid for sid, q in targets.items() if q}
    execution_domain |= {order['security_id'] for order in account['orders'].values() if order['status'] == 'OPEN'}
    difference = preview_scoped_account(state=account, legacy_shares={}, marks={sid: marks[sid] for sid in execution_domain},
        limits={sid: limits[sid] for sid in execution_domain}, target_quantities=targets, now=now, maximum_mark_age_seconds=120, fee_bps='0')
    if frozen_quantities is not None:
        difference=sequential_cash_allocation(difference)
    return dict(schema='TARGET_WEIGHT_ACCOUNT_BRIDGE_RESEARCH_V1', account_revision=expected_revision,
        strategy_contract_sha256=contract_hash, tradable_equity=str(equity), target_quantities=targets,
        difference=deepcopy(difference), production_activated=False, executable=False, orders_created=False,
        limitation='Isolated migration/difference test only; authenticated live signal and economic admission required.')
