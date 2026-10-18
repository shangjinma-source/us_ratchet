"""Repeatable same-month fixed-target paper continuation, pure and IO-free.

Original capital decision is never rebound to changed holdings. Each acceptance
freezes its execution declarations; source authenticity remains upstream.
"""
from copy import deepcopy
from zoneinfo import ZoneInfo
from data.current_quantity_v2_difference_plan import (
    require, stamp, number, validate_execution_inputs, allocate_differences)
from data.current_quantity_v2_paper_ledger import review_ledger, apply, reserves, digest

SCHEMA='QUANTITY_V2_FIXED_MONTH_CONTINUATION_CHAIN_V1'


def create_chain(ledger):
    verified=review_ledger(ledger)
    return dict(schema=SCHEMA,genesis=verified,operations=[],ledger=deepcopy(verified),
        research_only=True,execution_blocked=True,real_account=False,source_authenticated=False)


def proposal_for(ledger,inputs,now):
    original_proposal=ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']
    if original_proposal.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION':
        from data.current_quantity_v2_current_cash_continuation import proposal_for_current_cash
        return proposal_for_current_cash(ledger,inputs,now)
    require(all(o['closed'] in ('FILLED','CANCELLED','EXPIRED') for o in ledger['orders'].values())
            and number(ledger['reserved_cash'])==0 and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
    basic={'securities','execution_references','unit_continuity','source_hashes'}
    extended=set(inputs)==basic|{'held_unit_continuity','account_review'}
    require(set(inputs)==basic or (extended and original_proposal.get('target_scope')=='MONTHLY_CURRENT_QUOTE_ALLOCATION'),'EXECUTION_INPUT_FIELDS')
    now=stamp(now);original=original_proposal['causal_inputs']
    mandate=original['target_mandate'];decision=original['capital_decision']
    require(now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')==mandate['target_month'],'RESELECT_REQUIRED')
    observed=max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))
    require(observed<=now,'LEDGER_FROM_FUTURE')
    require(all(inputs['source_hashes'].get(p)==h for p,h in original['source_hashes'].items()),'ORIGINAL_SOURCE_CHANGED')
    account=dict(account_id=ledger['account_id'],revision=ledger['revision'],cash=ledger['cash'],
        shares=deepcopy(ledger['shares']),observed_at=observed.isoformat())
    bounded=[]
    if original_proposal.get('target_scope')=='MONTHLY_CURRENT_QUOTE_ALLOCATION':
        from data.current_quantity_v2_monthly_bounded_review import STATUS,replay_monthly_review
        require(extended or not any(u.get('status')==STATUS for u in inputs['unit_continuity'].values()),'MONTHLY_CONTINUATION_REVIEW_REQUIRED')
        if extended:
            from data.current_quantity_v2_monthly_retarget import validate_held_continuity
            review=inputs['account_review']
            if review.get('schema')=='QUANTITY_V2_DERIVED_PAPER_REVIEW_V1':
                from data.current_quantity_v2_paper_review import validate_review_ledger_binding
                validate_review_ledger_binding(review,ledger,now)
                validate_derived_review_sources(review,inputs['source_hashes'])
            else:
                require(set(review)=={'account_id','state_revision','pending_rights','reviewed_at','source_references'},'EXPLICIT_ACCOUNT_REVIEW_REQUIRED')
            require(review['account_id']==ledger['account_id'] and review['state_revision']==ledger['revision']
                and review['pending_rights']==[] and observed<=stamp(review['reviewed_at'])<=now
                and (review['source_references'] or review.get('schema')=='QUANTITY_V2_DERIVED_PAPER_REVIEW_V1')
                and all(p in inputs['source_hashes'] for p in review['source_references']), 'EXPLICIT_ACCOUNT_REVIEW_REQUIRED')
            bounded=validate_held_continuity(ledger,dict(inputs,capital_decision=decision),now)
        for sid,unit in inputs['unit_continuity'].items():
            if unit.get('status')==STATUS:
                bounded.append(replay_monthly_review(unit,security=inputs['securities'][sid],current=inputs['execution_references'][sid],
                    source_hashes=inputs['source_hashes'],now=now,capital_decision=decision))
    limits,deadlines=validate_execution_inputs(capital_decision=decision,account_state=account,
        targets=ledger['target_quantities'],now=now,**{k:inputs[k] for k in basic})
    if original_proposal.get('target_scope')=='MONTHLY_CURRENT_QUOTE_ALLOCATION':
        from data.current_quantity_v2_monthly_retarget import apply_monthly_pullback_limits,active_entry_policy
        limits=apply_monthly_pullback_limits(limits,inputs['execution_references'],active_entry_policy(ledger),now,
            sell_only={sid for sid,q in ledger['shares'].items() if q>0 and ledger['target_quantities'].get(sid,0)==0})
    orders,waiting,reserved,factor=allocate_differences(targets=ledger['target_quantities'],
        held=ledger['shares'],cash=number(ledger['cash']),limits=limits)
    binding=dict(account_id=ledger['account_id'],prior_revision=ledger['revision'],
        capital_decision_id=decision['decision_id'],target_month=mandate['target_month'],
        target_quantities=deepcopy(ledger['target_quantities']),cash=ledger['cash'],shares=deepcopy(ledger['shares']),
        recorded_fees=ledger['recorded_fees'],created_at=now.isoformat(),execution_inputs=deepcopy(inputs))
    result=dict(schema='V2_FIXED_MONTH_CONTINUATION_PROPOSAL_V1',proposal_id=digest(binding),binding=binding,
        orders=orders,wait_cash=waiting,reserved_buy_cash=str(reserved),buy_allocation_factor=str(factor),
        action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
        reference_valid_until=min(deadlines).isoformat() if deadlines else None,
        research_only=True,execution_blocked=True,real_account=False,source_authenticated=False)
    if bounded:
        result['unit_review']=dict(bounded[0],limited_name_coverage=any(r['limited_name_coverage'] for r in bounded),
            limitations=list(dict.fromkeys(v for r in bounded for v in r['limitations'])))
    return result



def accept_into(ledger,operation):
    p=operation['proposal'];b=p['binding'];accepted=stamp(operation['accepted_at'])
    require(proposal_for(ledger,b['execution_inputs'],b['created_at'])==p,'PROPOSAL_RECONSTRUCTION_MISMATCH')
    require(stamp(b['created_at'])<=accepted,'ACCEPTANCE_BEFORE_PROPOSAL')
    current=proposal_for(ledger,b['execution_inputs'],accepted)
    require(current['orders']==p['orders'] and p['orders'],'NO_ORDERS_OR_CHANGED_ORDERS')
    identifier=digest(operation);orders={}
    for index,row in enumerate(p['orders']):
        ref=b['execution_inputs']['execution_references'][row['security_id']]
        oid=identifier+':'+str(index)
        orders[oid]=dict(row,order_id=oid,filled_quantity=0,closed=None,time_in_force='DAY',
                        accepted_at=accepted.isoformat(),session_close=ref['session_close'])
    ledger['orders']=orders;ledger['revision']=digest(dict(previous=ledger['revision'],acceptance=operation))
    ledger['last_recorded_at']=accepted.isoformat();ledger['last_effective_at']=accepted.isoformat()
    reserves(ledger)


def replay(genesis,operations):
    state=create_chain(genesis);seen={e['event_id'] for e in genesis['events']}
    seen.add(genesis['revision'])
    for operation in operations:
        require(type(operation)is dict,'INVALID_OPERATION')
        if operation.get('kind') in ('ACCEPT','MONTHLY_RETARGET'):
            require(set(operation)=={'kind','acceptance_id','proposal','accepted_at'},'INVALID_ACCEPTANCE_FIELDS')
            identifier=operation['acceptance_id']
            require(type(identifier)is str and bool(identifier.strip()) and identifier not in seen,'OPERATION_ID_CONFLICT')
            proposal=operation['proposal']
            inputs=proposal['causal_inputs'] if operation['kind']=='MONTHLY_RETARGET' else proposal['binding']['execution_inputs']
            validate_derived_review(state,inputs.get('account_review'),operation['accepted_at'],verified_prefix=True)
            if operation['kind']=='MONTHLY_RETARGET':
                accept_month_into(state['ledger'],operation)
            else:accept_into(state['ledger'],operation)
        else:
            require(set(operation)=={'kind','event'} and operation['kind']=='EVENT','INVALID_OPERATION_FIELDS')
            identifier=operation['event']['event_id'];require(identifier not in seen,'OPERATION_ID_CONFLICT')
            apply(state['ledger'],deepcopy(operation['event']))
        seen.add(identifier);state['operations'].append(deepcopy(operation))
    return state


def review_chain(state):
    require(type(state)is dict and state.get('schema')==SCHEMA,'INVALID_CHAIN')
    rebuilt=replay(state['genesis'],state['operations'])
    require(rebuilt==state,'CHAIN_REPLAY_MISMATCH')
    return rebuilt


def build_continuation(state,*,execution_inputs,now):
    verified=review_chain(state)
    validate_derived_review(verified,execution_inputs.get('account_review'),now,verified_prefix=True)
    return proposal_for(verified['ledger'],execution_inputs,now)


def validate_derived_review(state,review,now,*,verified_prefix=False):
    """Bind automatic rights evidence to the actual pre-operation chain."""
    if review and review.get('schema')=='QUANTITY_V2_DERIVED_PAPER_REVIEW_V1':
        from data.current_quantity_v2_paper_review import validate_paper_review
        validate_paper_review(review,state,now,_verified_prefix=verified_prefix)


def validate_derived_review_sources(review,source_hashes):
    for key in ('baseline_package','action_package'):
        package=review['derived_evidence'][key]
        if package is not None:
            require(all(source_hashes.get(path)==value for path,value in package['source_hashes'].items()),'PAPER_REVIEW_SOURCE_CHANGED')


def accept_continuation(state,proposal,*,acceptance_id,now):
    verified=review_chain(state)
    for operation in verified['operations']:
        if operation.get('acceptance_id')==acceptance_id:
            require(operation['kind']=='ACCEPT' and operation['proposal']==proposal,'ACCEPTANCE_ID_CONFLICT')
            return verified
    operation=dict(kind='ACCEPT',acceptance_id=acceptance_id,proposal=deepcopy(proposal),accepted_at=stamp(now).isoformat())
    return replay(verified['genesis'],verified['operations']+[operation])


def record_chain_event(state,event,*,now):
    verified=review_chain(state)
    for saved in verified['ledger']['events']:
        if saved['event_id']==event.get('event_id'):
            require(saved==event,'EVENT_ID_CONFLICT');return verified
    require(stamp(event['recorded_at'])<=stamp(now),'FUTURE_RECORD_TIME')
    return replay(verified['genesis'],verified['operations']+[dict(kind='EVENT',event=deepcopy(event))])


def accept_month_into(ledger,operation):
    from data.current_quantity_v2_monthly_retarget import proposal_for_month
    p=operation['proposal'];accepted=stamp(operation['accepted_at']);a=p['causal_inputs']
    require(proposal_for_month(ledger,a,a['now'])==p,'PROPOSAL_RECONSTRUCTION_MISMATCH')
    require(stamp(a['now'])<=accepted,'ACCEPTANCE_BEFORE_PROPOSAL')
    current=proposal_for_month(ledger,a,accepted)
    require(current['orders']==p['orders'] and current['target_quantities']==p['target_quantities'],'CHANGED_MONTHLY_TARGET')
    identifier=digest(operation);orders={}
    for index,row in enumerate(p['orders']):
        ref=a['execution_references'][row['security_id']];oid=identifier+':'+str(index)
        orders[oid]=dict(row,order_id=oid,filled_quantity=0,closed=None,time_in_force='DAY',
            accepted_at=accepted.isoformat(),session_close=ref['session_close'])
    ledger.update(orders=orders,target_quantities=deepcopy(p['target_quantities']),
        active_monthly_acceptance=dict(proposal=deepcopy(p),accepted_at=accepted.isoformat()),
        target_scope=p['target_scope'],execution_target_id=p['execution_target_id'],
        subsequent_activation_supported=True,current_execution_bytes_verified=False,source_bytes_verified=False,
        historical_target_quantities=deepcopy(p['historical_target_quantities']))
    ledger['revision']=digest(dict(previous=ledger['revision'],acceptance=operation))
    ledger['last_recorded_at']=accepted.isoformat();ledger['last_effective_at']=accepted.isoformat()
    reserves(ledger)


def accept_monthly_retarget(state,proposal,*,acceptance_id,now):
    verified=review_chain(state)
    for operation in verified['operations']:
        if operation.get('acceptance_id')==acceptance_id:
            require(operation['kind']=='MONTHLY_RETARGET' and operation['proposal']==proposal,'ACCEPTANCE_ID_CONFLICT')
            return verified
    op=dict(kind='MONTHLY_RETARGET',acceptance_id=acceptance_id,proposal=deepcopy(proposal),accepted_at=stamp(now).isoformat())
    return replay(verified['genesis'],verified['operations']+[op])
