"""Pure account-equity V2 differences; rejects cash-only display snapshots.

Inputs are server-verified declarations. This module verifies consistency, not raw
source authenticity, and creates neither accepted orders nor account mutations.
"""
from copy import deepcopy
from datetime import datetime, timedelta, date
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from data.current_quantity_projection_v2 import project_capital_decision_v2


def require(ok, reason):
    if not ok: raise ValueError(reason)


def number(value):
    require(type(value) in (str, int), 'EXACT_NUMBER_REQUIRED')
    return Fraction(value)


def stamp(value):
    result=datetime.fromisoformat(value) if isinstance(value,str) else value
    require(isinstance(result,datetime) and result.tzinfo is not None,'AWARE_TIME_REQUIRED')
    return result


def calendar_day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat() == value,
            'CANONICAL_DATE_REQUIRED')
    return value



def validate_execution_inputs(*, capital_decision, account_state, securities, execution_references,
        unit_continuity, source_hashes, targets, now):
    b=capital_decision['binding'];held=account_state['shares']
    require(isinstance(targets,dict) and all(type(q)is int and q>=0 for q in targets.values()),'INVALID_TARGETS')
    needed={s for m in (held,targets) for s,q in m.items() if q}
    require(set(execution_references)==set(unit_continuity)==set(securities)==needed,'COMPLETE_HELD_TARGET_DOMAIN_REQUIRED')
    limits={};deadlines=[]
    for sid in sorted(needed):
        ref=execution_references[sid];unit=unit_continuity[sid];security=securities[sid]
        require(ref['security_id']==sid and ref['ticker']==security['ticker'],'QUOTE_IDENTITY_MISMATCH')
        require(ref['currency']=='USD' and ref['price_basis']=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS','QUOTE_BASIS_REQUIRED')
        if sid in b['search_arguments']['metadata']:
            require(security==b['search_arguments']['metadata'][sid],'SELECTION_SECURITY_MISMATCH')
        require(security.get('issuer_id'),'SECURITY_ISSUER_REQUIRED')
        if sid in b['valuation_quotes']:
            original=b['valuation_quotes'][sid]
            references=original['source_references']
            require(isinstance(references,list) and bool(references)
                    and all(p in source_hashes for p in references)
                    and unit['valuation_source_references']==references,
                    'VALUATION_IDENTITY_SOURCE_MISMATCH')
        captured,checked,tick,start,end,deadline,opening,closing=map(stamp,[ref[k] for k in
            ('captured_at','checked_at','last_at','minute_start','minute_end','valid_until','session_open','session_close')])
        require(opening<=tick<=captured<=checked<=now<deadline<=closing and opening<=start
                and start.second==0 and start.microsecond==0 and end-start==timedelta(minutes=1)
                and end<=captured and deadline<=min(tick+timedelta(seconds=120),end+timedelta(seconds=120))
                and tick>=stamp(account_state['observed_at']),'STALE_OR_INVALID_QUOTE')
        require(all(t.astimezone(ZoneInfo('America/New_York')).date().isoformat()==ref['session']
                for t in (now,opening,closing,start,end,tick)),'QUOTE_SESSION_MISMATCH')
        last,low=number(ref['last_price']),number(ref['minute_low'])
        require(min(last,low)>0,'INVALID_PRICE')
        buy=Fraction(min(last,low)*100//1,100);sell=Fraction(-(-last*100//1),100)
        require(buy>0,'NONPOSITIVE_LIMIT')
        pins=ref['source_hashes'];require(pins and all(source_hashes.get(p)==h for p,h in pins.items()),'QUOTE_SOURCE_MISMATCH')
        if unit.get('status')=='NO_KNOWN_UNIT_CHANGE_UNDER_BOUNDED_PUBLIC_REVIEW':
            from data.current_quantity_v2_monthly_bounded_review import replay_monthly_review
            replay_monthly_review(unit,security=security,current=ref,source_hashes=source_hashes,
                now=now,capital_decision=capital_decision)
        else:
            require(unit['security_id']==sid and unit['ticker']==security['ticker']
                    and unit['price_basis']==ref['price_basis']
                    and unit['capital_decision_id']==capital_decision['decision_id']
                    and unit['status']=='NO_UNPROCESSED_ACTIONS' and unit['reference_source_hashes']==pins
                    and unit['source_references'] and all(p in source_hashes for p in unit['source_references'])
                    and calendar_day(unit['covered_from_date'])<=b['decision_date']
                    and captured<=stamp(unit['covered_through'])<=stamp(unit['reviewed_at'])<=now,'UNIT_CONTINUITY_REQUIRED')
        limits[sid]=(buy,sell);deadlines.append(deadline)
    return limits,deadlines


def allocate_differences(*, targets, held, cash, limits):
    needed=set(limits)
    deficits=[];orders=[]
    for sid in sorted(needed):
        delta=targets.get(sid,0)-held.get(sid,0)
        if delta<0:orders.append(dict(security_id=sid,side='SELL',quantity=-delta,limit_price=str(limits[sid][1])))
        elif delta>0:deficits.append((sid,delta,limits[sid][0]))
    proposed=sum((q*p for _,q,p in deficits),Fraction())
    factor=min(Fraction(1),cash/proposed) if proposed else Fraction(1)
    waiting=[];reserved=Fraction()
    for sid,q,price in deficits:
        assigned=int(q*factor)
        if assigned:orders.append(dict(security_id=sid,side='BUY',quantity=assigned,limit_price=str(price)));reserved+=assigned*price
        if assigned<q:waiting.append(dict(security_id=sid,remaining_deficit=q-assigned,reason='WAIT_CASH'))
    require(reserved<=cash,'RESERVE_EXCEEDS_CASH')
    return orders,waiting,reserved,factor

def build_account_difference_plan(*, capital_decision, account_state, securities,
        execution_references, unit_continuity, source_hashes, now, target_scope, target_mandate,
        genesis_declaration=None):
    flags=dict(research_only=True,execution_blocked=True,orders_created=False,
               account_mutated=False,source_bytes_verified=False,
               schema='V2_ACCOUNT_EQUITY_DIFFERENCE_PROPOSAL_V1')
    try:
        require(target_scope in ('ACCOUNT_EQUITY_TARGET','NEW_CASH_STRATEGY_INITIAL_TARGET'),'ACCOUNT_EQUITY_SCOPE_REQUIRED')
        require(target_scope!='ACCOUNT_EQUITY_TARGET' or genesis_declaration is None,'GENESIS_NOT_FOR_EXISTING_ACCOUNT')
        view=project_capital_decision_v2(capital_decision)
        require(view['status'] in ('AVAILABLE','ALL_CASH'),'COMPLETE_CAPITAL_DECISION_REQUIRED')
        require(isinstance(now,str),'ISO_NOW_REQUIRED')
        b=capital_decision['binding'];now=stamp(now)
        cash=number(account_state['cash']);held=account_state['shares']
        require(cash>=0 and isinstance(held,dict) and all(type(q)is int and q>=0 for q in held.values()),'INVALID_ACCOUNT_ASSETS')
        require(account_state['revision']==b['state_revision'] and cash==number(b['available_cash'])
                and held==b['shares'],'CAPITAL_ACCOUNT_MISMATCH')
        require(account_state['open_orders']==[] and number(account_state['reserved_cash'])==0
                and not any(account_state['reserved_shares'].values()),'OPEN_ORDERS_MUST_BE_SETTLED')
        require(account_state['pending_rights']==[],'UNSUPPORTED_PENDING_RIGHTS')
        require(stamp(account_state['observed_at'])<=now,'ACCOUNT_FROM_FUTURE')
        account_id=account_state['account_id']
        require(type(account_id) is str and bool(account_id.strip())
                and target_mandate['account_id']==account_id,'ACCOUNT_ID_MISMATCH')
        if target_scope=='NEW_CASH_STRATEGY_INITIAL_TARGET':
            g=genesis_declaration
            require(type(g)is dict and set(g)=={'purpose','account_id','research_id','decision_id',
                'capital_origin_revision','initial_cash_exact','target_month','declared_at','source_references'},'EXPLICIT_CASH_GENESIS_REQUIRED')
            require(g['purpose']=='PAPER_INITIALIZATION_NOT_BROKER_BALANCE'
                    and g['account_id']==account_id and g['research_id']==capital_decision['research_id']
                    and g['decision_id']==capital_decision['decision_id']
                    and g['capital_origin_revision']==b['state_revision']
                    and g['target_month']==target_mandate['target_month']
                    and held==b['shares']=={}
                    and cash==number(g['initial_cash_exact'])==number(b['investable_equity'])
                        ==number(b['search_arguments']['entered_cash'])
                    and stamp(g['declared_at'])==stamp(account_state['observed_at'])<=now
                    and type(g['source_references'])is list and g['source_references']
                    and all(p in source_hashes for p in g['source_references']), 'CASH_GENESIS_BINDING_MISMATCH')
        today=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        calendar_day(target_mandate['active_date'])
        require(calendar_day(b['decision_date'])<=today,'FUTURE_DECISION_DATE')
        require(target_mandate['capital_decision_id']==capital_decision['decision_id']
                and target_mandate['target_month']==today[:7]
                and b['decision_date']<=target_mandate['active_date']<=today
                and target_mandate['active_date'][:7]==target_mandate['target_month']
                and target_mandate['source_references']
                and all(p in source_hashes for p in target_mandate['source_references']), 'RESELECT_REQUIRED_OR_INVALID_TARGET_MANDATE')
        require(number(b['search_arguments']['fee_bps'])==0,'UNSUPPORTED_COMMISSION_MODEL')
        require(all(source_hashes.get(p)==h for p,h in b['source_hashes'].items()),'CAPITAL_SOURCE_CHANGED')
        targets=capital_decision['target_quantities']
        limits,deadlines=validate_execution_inputs(capital_decision=capital_decision,account_state=account_state,
            securities=securities,execution_references=execution_references,unit_continuity=unit_continuity,
            source_hashes=source_hashes,targets=targets,now=now)
        orders,waiting,reserved,factor=allocate_differences(targets=targets,held=held,cash=cash,limits=limits)
        inputs=dict(capital_decision=deepcopy(capital_decision),account_state=deepcopy(account_state),
            securities=deepcopy(securities),execution_references=deepcopy(execution_references),
            unit_continuity=deepcopy(unit_continuity),source_hashes=deepcopy(source_hashes),now=now.isoformat(),target_scope=target_scope,
            target_mandate=deepcopy(target_mandate))
        if target_scope=='NEW_CASH_STRATEGY_INITIAL_TARGET':
            inputs['genesis_declaration']=deepcopy(genesis_declaration)
        identifier=sha256(json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return dict(flags,status='READY',proposal_id=identifier,account_id=account_id,causal_inputs=inputs,orders=orders,
            target_quantities=deepcopy(targets),actual_cash=str(cash),reserved_buy_cash=str(reserved),
            target_as_of=b['decision_date'],target_month=target_mandate['target_month'],reference_as_of=now.isoformat(),
            remaining_cash=str(cash-reserved),unfilled_sell_proceeds='0',wait_cash=waiting,
            buy_allocation_factor=str(factor),reference_valid_until=min(deadlines).isoformat() if deadlines else None,
            action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
            fee_scope='COMMISSION_ZERO_OTHER_FEES_UNKNOWN_NOT_RESERVED',
            limitations=['SELL ceil(last) is a minimum-acceptance reference, not an optimal exit or guaranteed fill.',
                'Account/source declarations require server verification; this pure proposal is not accepted by existing ledgers.'])
    except (KeyError,ValueError,TypeError,ArithmeticError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),orders=[],proposal_id=None)
