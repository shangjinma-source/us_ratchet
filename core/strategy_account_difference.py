"""Pure strategy-only differences; no persistence, broker calls or inferred fills.

Caller supplies verified, current-unit positions/marks and strategy pending orders.
Legacy quantities are explicitly excluded even when their SID overlaps. Cash is a
fresh absolute user balance, never a fill-derived running balance. A broker-wide
snapshot with additional non-strategy reservations must be reconciled by caller;
it must not be silently passed as this strategy's pending-order domain.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json

CASH_BASES={'AVAILABLE_AFTER_RESERVATIONS','TOTAL_UNINVESTED'}


def require(condition,reason):
    if not condition:raise ValueError(reason)


def number(value):
    require(type(value) in (str,int),'EXACT_NUMBER_REQUIRED')
    result=Fraction(value);require(result>=0,'NEGATIVE_AMOUNT');return result


def timestamp(value):
    require(type(value)is str,'ISO_TIMESTAMP_REQUIRED')
    result=datetime.fromisoformat(value)
    require(result.tzinfo is not None and result.utcoffset() is not None,'AWARE_TIMESTAMP_REQUIRED')
    return result


def quantities(value):
    require(type(value)is dict,'EXPLICIT_SHARE_MAP_REQUIRED')
    require(all(type(s)is str and bool(s.strip()) and type(q)is int and q>=0 for s,q in value.items()),'INVALID_WHOLE_SHARES')
    return deepcopy(value)


def build_strategy_difference(*,account_id,account_revision,holdings_revision,cash_confirmed_for_holdings_revision,cash_balance,cash_basis,
        strategy_shares,legacy_shares,pending_orders,marks,limits,target_quantities,
        now,maximum_mark_age_seconds,fee_bps):
    require(type(account_id)is str and bool(account_id.strip()),'ACCOUNT_ID_REQUIRED')
    require((type(account_revision)is int and account_revision>=0) or (type(account_revision)is str and bool(account_revision.strip())),'ACCOUNT_REVISION_REQUIRED')
    require((type(holdings_revision)is int and holdings_revision>=0) or (type(holdings_revision)is str and bool(holdings_revision.strip())),'HOLDINGS_REVISION_REQUIRED')
    require(type(cash_confirmed_for_holdings_revision)is type(holdings_revision) and cash_confirmed_for_holdings_revision==holdings_revision,'CASH_RECONFIRMATION_REQUIRED')
    require(cash_basis in CASH_BASES,'EXPLICIT_CASH_BASIS_REQUIRED')
    require(type(maximum_mark_age_seconds)is int and maximum_mark_age_seconds>0,'EXPLICIT_MARK_AGE_REQUIRED')
    held=quantities(strategy_shares);legacy=quantities(legacy_shares);targets=quantities(target_quantities)
    current=timestamp(now);cash=number(cash_balance);rate=number(fee_bps)/10000
    require(rate<=1,'INVALID_FEE_RATE')
    require(type(pending_orders)is list,'EXPLICIT_PENDING_ORDERS_REQUIRED')
    reserved=Fraction(0);buys={};sells={};seen=set();normalized=[]
    for raw in pending_orders:
        require(type(raw)is dict and raw.get('scope')=='STRATEGY','STRATEGY_PENDING_SCOPE_REQUIRED')
        require(raw.get('account_id')==account_id,'PENDING_ACCOUNT_MISMATCH')
        oid=raw.get('order_id');sid=raw.get('security_id');side=raw.get('side')
        require(type(oid)is str and bool(oid) and oid not in seen,'DUPLICATE_OR_INVALID_ORDER_ID');seen.add(oid)
        require(type(sid)is str and bool(sid.strip()) and side in ('BUY','SELL'),'INVALID_PENDING_SECURITY_OR_SIDE')
        q,filled,remaining=(raw.get(k) for k in ('quantity','filled_quantity','remaining_quantity'))
        require(all(type(n)is int and n>=0 for n in (q,filled,remaining)) and q>0 and remaining>0 and q==filled+remaining,'INVALID_PENDING_REMAINING')
        price=number(raw['limit_price']);require(price>0,'NONPOSITIVE_PENDING_LIMIT')
        reservation=number(raw['reserved_cash'])
        if side=='BUY':
            fee=number(raw['remaining_fee_reserve'])
            require(reservation==price*remaining+fee,'PENDING_RESERVATION_MISMATCH')
            reserved+=reservation;buys[sid]=buys.get(sid,0)+remaining
        else:
            require(reservation==0,'SELL_CANNOT_RESERVE_CASH');sells[sid]=sells.get(sid,0)+remaining
        normalized.append(deepcopy(raw))
    require(all(q<=held.get(sid,0) for sid,q in sells.items()),'PENDING_SELL_EXCEEDS_STRATEGY_HOLDINGS')
    total_cash=cash+reserved if cash_basis=='AVAILABLE_AFTER_RESERVATIONS' else cash
    spendable=cash if cash_basis=='AVAILABLE_AFTER_RESERVATIONS' else cash-reserved
    require(spendable>=0,'RESERVATION_EXCEEDS_TOTAL_CASH')
    needed={sid for mapping in (held,targets,buys,sells) for sid,q in mapping.items() if q}
    require(type(marks)is dict and set(marks)==needed,'EXACT_STRATEGY_MARK_DOMAIN_REQUIRED')
    require(type(limits)is dict and set(limits)==needed,'EXACT_STRATEGY_LIMIT_DOMAIN_REQUIRED')
    market=Fraction(0);prices={};buy_limits={};sell_limits={}
    for sid in sorted(needed):
        mark=marks[sid]
        require(mark['security_id']==sid and mark['currency']=='USD' and type(mark['price_basis'])is str and bool(mark['price_basis']),'MARK_IDENTITY_OR_BASIS_MISMATCH')
        at=timestamp(mark['observed_at']);require(current-timedelta(seconds=maximum_mark_age_seconds)<=at<=current,'STALE_OR_FUTURE_MARK')
        price=number(mark['price']);require(price>0,'NONPOSITIVE_MARK');prices[sid]=price;market+=price*held.get(sid,0)
        ref=limits[sid]
        require(ref['security_id']==sid and ref['price_basis']==mark['price_basis'],'LIMIT_UNIT_OR_IDENTITY_MISMATCH')
        require(ref['observed_at']==mark['observed_at'],'LIMIT_MARK_TIME_MISMATCH')
        buy_limits[sid]=number(ref['buy']);sell_limits[sid]=number(ref['sell'])
        require(buy_limits[sid]>0 and sell_limits[sid]>0,'NONPOSITIVE_LIMIT')
    conflicts=[]
    for sid in sorted(needed):
        gap=targets.get(sid,0)-held.get(sid,0);buy=buys.get(sid,0);sell=sells.get(sid,0)
        if (buy and (gap<=0 or buy>gap)) or (sell and (gap>=0 or sell>-gap)) or (buy and sell):
            conflicts.append(dict(security_id=sid,reason='PENDING_DIRECTION_OR_QUANTITY_CONFLICT',order_ids=sorted(o['order_id'] for o in normalized if o['security_id']==sid)))
    binding=dict(account_id=account_id,account_revision=account_revision,holdings_revision=holdings_revision,
        cash_confirmed_for_holdings_revision=cash_confirmed_for_holdings_revision,cash_balance=str(cash),cash_basis=cash_basis,
        strategy_shares=held,legacy_shares=legacy,pending_orders=normalized,marks=deepcopy(marks),limits=deepcopy(limits),
        target_quantities=targets,now=now,maximum_mark_age_seconds=maximum_mark_age_seconds,fee_bps=str(number(fee_bps)))
    digest=sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    result=dict(schema='STRATEGY_MANUAL_CASH_DIFFERENCE_V1',account_id=account_id,account_revision=account_revision,binding=binding,binding_sha256=digest,
        cash_basis=cash_basis,manual_cash_balance=str(cash),total_uninvested_cash=str(total_cash),pending_buy_reserved_cash=str(reserved),
        spendable_cash=str(spendable),strategy_market_value=str(market),strategy_equity=str(total_cash+market),legacy_shares_excluded=legacy,
        source_authenticity_verified=False,unit_continuity_verified=False,cash_auto_updated=False,orders_created=False,account_mutated=False,
        new_orders=[],waiting_cash=[],cancel_before_recalculate=conflicts,
        cash_semantics='Absolute latest user cash; AVAILABLE excludes the listed BUY reservations already, TOTAL includes them. SELL proceeds are unavailable until reflected in a later user cash snapshot.')
    if conflicts:return dict(result,status='CANCEL_THEN_RECALCULATE')
    deficits=[];orders=[]
    for sid in sorted(needed):
        gap=targets.get(sid,0)-held.get(sid,0)-buys.get(sid,0)+sells.get(sid,0)
        if gap<0:
            quantity=-gap;require(quantity<=held.get(sid,0)-sells.get(sid,0),'NEW_SELL_EXCEEDS_AVAILABLE_STRATEGY_SHARES')
            orders.append(dict(security_id=sid,side='SELL',quantity=quantity,limit_price=str(sell_limits[sid]),estimated_cash_change=str(quantity*sell_limits[sid]*(1-rate))))
        elif gap>0:
            require(limits[sid].get('buy_evaluated',True) is True,'BUY_LIMIT_NOT_EVALUATED')
            deficits.append((sid,gap,buy_limits[sid]*(1+rate)))
    required=sum((q*unit for _,q,unit in deficits),Fraction(0));factor=min(Fraction(1),spendable/required) if required else Fraction(1)
    allocated=Fraction(0)
    for sid,q,unit in deficits:
        assigned=int(q*factor)
        if assigned:
            cost=assigned*unit;allocated+=cost
            orders.append(dict(security_id=sid,side='BUY',quantity=assigned,limit_price=str(buy_limits[sid]),estimated_cash_change=str(-cost)))
        if assigned<q:result['waiting_cash'].append(dict(security_id=sid,quantity=q-assigned,reason='WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED'))
    require(allocated<=spendable,'NEW_BUY_BUDGET_EXCEEDED')
    result.update(status='WAIT_CASH' if result['waiting_cash'] else 'READY',new_orders=orders,
        new_buy_cash_required=str(allocated),unallocated_spendable_cash=str(spendable-allocated),buy_allocation_fraction=str(factor))
    return result
