"""Repeatable same-month V3 retarget continuations with frozen source replay.

No service/store activation. Source integrity is local, not broker or action certification.
"""
from copy import deepcopy
from data.current_research_intraday_buy_plan import _require,_time
from data.current_research_intraday_paper_ledger import _hash
from data.current_research_intraday_retarget_evidence import review_source_verified_retarget
from data.current_research_intraday_retarget_continuation import _build_verified_continuation
from data.current_research_intraday_retarget_ledger import _apply,_reserves

SCHEMA='INTRADAY_RETARGET_CONTINUATION_CHAIN_V1'
LEDGER_SCHEMA='INTRADAY_RETARGET_CONTINUATION_LEDGER_V4'


def _base(envelope):
    original=review_source_verified_retarget(envelope)
    ledger=deepcopy(original['ledger']);ledger['schema']=LEDGER_SCHEMA
    ledger['same_month_continuation_supported']=True
    return dict(schema=SCHEMA,genesis=original,ledger=ledger,operations=[],
        latest_execution_evidence=deepcopy(original['execution_evidence']),
        research_only=True,execution_blocked=True,real_account=False,
        source_authenticated=False,latest_tip_authenticated=False,
        subsequent_monthly_retarget_supported=False)


def _proposal(chain,*,expected_revision,execution_evidence,now):
    view=dict(ledger=chain['ledger'],execution_evidence=chain['latest_execution_evidence'])
    result=_build_verified_continuation(view,expected_revision=expected_revision,execution_evidence=execution_evidence,now=now)
    result['compatible_ledger_schema']=LEDGER_SCHEMA
    result['ledger_acceptance_supported']=True
    return result


def _known_accept_ids(chain):
    ids={chain['ledger']['retarget_acceptance']['operation_id']}
    ids.update(o['operation_id'] for o in chain['operations'] if o['kind']=='ACCEPT')
    old=chain['genesis']['ledger']['genesis']
    # V2 embeds its earlier V1 state; only recorded acceptance operations count.
    if old.get('schema')=='INTRADAY_CONTINUATION_PAPER_LEDGER_V2':
        ids.update(o['operation_id'] for o in old['operations'] if o['kind']=='ACCEPT')
    return ids


def _step(chain,operation):
    state=chain['ledger'];result=deepcopy(chain)
    if operation['kind']=='ACCEPT':
        _require(set(operation)=={'kind','operation_id','expected_revision','proposal','execution_evidence','accepted_at'},'ACCEPT_OPERATION_SCHEMA')
        oid=operation['operation_id']
        _require(isinstance(oid,str) and oid.strip(),'OPERATION_ID_REQUIRED')
        _require(oid not in _known_accept_ids(chain) and not any(e['event_id']==oid for e in state['events']),'DUPLICATE_OPERATION_ID')
        _require(operation['expected_revision']==state['revision'],'STALE_REVISION')
        proposal=operation['proposal'];created=_time(proposal['binding']['proposed_at']);accepted=_time(operation['accepted_at'])
        _require(created<=accepted,'ACCEPTANCE_BEFORE_PROPOSAL')
        evidence=operation['execution_evidence']
        rebuilt=_proposal(chain,expected_revision=state['revision'],execution_evidence=evidence,now=created)
        _require(rebuilt==proposal and rebuilt['status']=='READY','CONTINUATION_PROPOSAL_RECONSTRUCTION_MISMATCH')
        current=_proposal(chain,expected_revision=state['revision'],execution_evidence=evidence,now=accepted)
        _require(current['status']=='READY' and current['orders'],'CURRENT_CONTINUATION_NOT_ACCEPTABLE:'+str(current.get('reason',current.get('action'))))
        _require(current['orders']==proposal['orders'] and current['target_quantities']==state['target_quantities'],'TARGET_OR_ORDERS_CHANGED')
        acceptance_id=_hash(operation);orders={};seen=set()
        for i,row in enumerate(current['orders']):
            sid=row['security_id'];_require(sid not in seen,'MULTIPLE_DIRECTIONS_SAME_SECURITY');seen.add(sid)
            ref=evidence['references'][sid];close=_time(ref['session_close'])
            _require(_time(ref['session_open'])<=accepted<close,'INVALID_ACCEPTANCE_SESSION')
            order_id=acceptance_id+':'+str(i)
            orders[order_id]=dict(row,order_id=order_id,accepted_at=accepted.isoformat(),session_close=close.isoformat(),time_in_force='DAY',filled_quantity=0,closed=None)
        newstate=deepcopy(state);newstate['orders']=orders
        newstate['revision']=_hash(dict(previous=state['revision'],operation=operation))
        _reserves(newstate)
        result['ledger']=newstate;result['latest_execution_evidence']=deepcopy(evidence)
    else:
        _require(operation['kind']=='EVENT' and set(operation)=={'kind','event'},'OPERATION_SCHEMA')
        event=operation['event']
        _require(event['event_id'] not in _known_accept_ids(chain),'EVENT_ACCEPT_ID_CONFLICT')
        result['ledger']=_apply(state,event)
    result['operations'].append(deepcopy(operation))
    return result


def review_retarget_continuation_chain(value):
    """Accept an original V3 source envelope or replay every V4 operation exactly."""
    if value.get('schema')!=SCHEMA:return _base(value)
    rebuilt=_base(value['genesis'])
    for operation in value['operations']:rebuilt=_step(rebuilt,operation)
    _require(rebuilt==value,'RETARGET_CONTINUATION_CHAIN_REPLAY_MISMATCH')
    return deepcopy(value)


def build_retarget_chain_proposal(value,*,expected_revision,execution_evidence,now):
    chain=review_retarget_continuation_chain(value)
    return _proposal(chain,expected_revision=expected_revision,execution_evidence=execution_evidence,now=now)


def accept_retarget_chain_proposal(value,proposal,*,operation_id,expected_revision,execution_evidence,now):
    chain=review_retarget_continuation_chain(value)
    for old in chain['operations']:
        if old.get('operation_id')==operation_id:
            _require(old['kind']=='ACCEPT' and old['proposal']==proposal and old['expected_revision']==expected_revision and old['execution_evidence']==execution_evidence,'CONFLICTING_ACCEPT_OPERATION')
            return chain
    operation=dict(kind='ACCEPT',operation_id=operation_id,expected_revision=expected_revision,proposal=deepcopy(proposal),execution_evidence=deepcopy(execution_evidence),accepted_at=_time(now).isoformat())
    return _step(chain,operation)


def apply_retarget_chain_event(value,event,*,now):
    chain=review_retarget_continuation_chain(value)
    for old in chain['ledger']['events']:
        if old['event_id']==event.get('event_id'):
            _require(old==event,'CONFLICTING_EVENT_ID');return chain
    _require(_time(event['recorded_at'])<=_time(now),'FUTURE_RECORDING')
    return _step(chain,dict(kind='EVENT',event=deepcopy(event)))
