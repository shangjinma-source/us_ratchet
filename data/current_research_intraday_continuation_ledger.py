"""Repeatable same-month continuation ledger; independent of V1 storage/API."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from data.current_research_intraday_paper_ledger import (
    review_intraday_paper_ledger, _capture, _MemoryPath, _hash, _apply)
from data.current_research_intraday_buy_plan import _require, _time
from data.current_research_intraday_continuation import build_intraday_continuation_proposal

SCHEMA='INTRADAY_CONTINUATION_PAPER_LEDGER_V2'


class _Journal:
    def __init__(self,files):self.root=_MemoryPath(files)
    def read_event(self,path,expected_sha256=None):
        raw=(self.root/path).read_bytes()
        _require(expected_sha256 is None or sha256(raw).hexdigest()==expected_sha256,'EVENT_HASH_MISMATCH')
        event=json.loads(raw)
        for row in event['captures']:
            _require(row['path']=='raw/'+row['sha256']+'.bin','RAW_PATH_INVALID')
            _require(sha256((self.root/row['path']).read_bytes()).hexdigest()==row['sha256'],'RAW_HASH_MISMATCH')
        return event


def _build(state,inputs,files,now):
    # State is already independently replayed by the caller/replay loop.
    return build_intraday_continuation_proposal(state,journal_root='',journal=_Journal(files),
        state_reviewer=lambda s:deepcopy(s),now=now,**inputs)


def _base(genesis):
    state=review_intraday_paper_ledger(genesis)
    result=deepcopy(state);result.update(schema=SCHEMA,genesis=deepcopy(state),operations=[],
        revision=state['revision'])
    return result


def _accept(state,evidence):
    original=evidence['proposal'];created=original['causal_inputs']['proposal_created_at']
    rebuilt=_build(state,evidence['original_inputs'],evidence['original_files'],created)
    _require(rebuilt==original,'CONTINUATION_PROPOSAL_RECONSTRUCTION_MISMATCH')
    _require(_time(created)<=_time(evidence['accepted_at']),'ACCEPTANCE_BEFORE_PROPOSAL')
    current=_build(state,evidence['current_inputs'],evidence['files'],evidence['accepted_at'])
    _require(current['status']=='READY' and current['quantity']>0,'CONTINUATION_NOT_ACCEPTABLE:'+str(current.get('reason',current.get('action'))))
    old=original['causal_inputs'];new=current['causal_inputs']
    for field in ('account_id','account_revision','initial_acceptance_id','initial_target_quantity','shares','cash','recorded_fees','unit_continuity','source_hashes','quantity','remaining_deficit','limit_price'):
        _require(old[field]==new[field],'CURRENT_CONTINUATION_BINDING_CHANGED:'+field)
    for field in ('research_snapshot','event_path','event_sha256','market_session','security'):
        _require(old['reference'][field]==new['reference'][field],'CURRENT_REFERENCE_BINDING_CHANGED:'+field)
    result=deepcopy(state);acceptance_id=_hash(evidence)
    result.update(order=dict(order_id=acceptance_id+':BUY',side='BUY',security_id=current['security']['security_id'],quantity=current['quantity'],limit=current['limit_price'],accepted_at=evidence['accepted_at'],session_close=new['reference']['market_session']['close_at'],time_in_force='DAY'),
        filled_quantity=0,closed=None,reserved_cash=current['notional'])
    return result


def _event(state,event):
    # V1 event arithmetic and limits reused; restore cumulative holdings because
    # V1's one-order position equals its filled_quantity, unlike a continuation.
    result=_apply(state,event)
    if result==state:return result
    if event['kind']=='FILL':
        sid=state['order']['security_id']
        result['shares'][sid]=state['shares'].get(sid,0)+event['quantity']
    return result


def _step(state,operation):
    kind=operation['kind']
    if kind=='ACCEPT':
        _require(set(operation)=={'kind','operation_id','expected_revision','evidence'},'ACCEPT_OPERATION_SCHEMA')
        _require(isinstance(operation['operation_id'],str) and operation['operation_id'].strip(),'OPERATION_ID_REQUIRED')
        _require(not any(o['kind']=='ACCEPT' and o['operation_id']==operation['operation_id'] for o in state['operations']),'DUPLICATE_ACCEPT_OPERATION')
        _require(operation['expected_revision']==state['revision'],'STALE_REVISION')
        result=_accept(state,operation['evidence'])
    else:
        _require(kind=='EVENT' and set(operation)=={'kind','event'},'OPERATION_SCHEMA')
        _require(not any(e['event_id']==operation['event'].get('event_id') for e in state['events']),'DUPLICATE_EVENT_OPERATION')
        result=_event(state,operation['event'])
    result['operations'].append(deepcopy(operation))
    result['revision']=_hash(dict(previous=state['revision'],operation=operation))
    return result


def review_continuation_ledger(state):
    if state.get('schema')!=SCHEMA:return review_intraday_paper_ledger(state)
    rebuilt=_base(state['genesis'])
    for operation in state['operations']:rebuilt=_step(rebuilt,operation)
    _require(rebuilt==state,'CONTINUATION_STATE_REPLAY_MISMATCH')
    return deepcopy(state)


def build_continuation_proposal(state,**inputs):
    """Public builder for both V1 and repeatable V2 histories."""
    return build_intraday_continuation_proposal(state,state_reviewer=review_continuation_ledger,**inputs)


def accept_continuation_proposal(state,proposal,*,operation_id,journal_root,current_inputs,now):
    verified=review_continuation_ledger(state)
    for old in verified.get('operations',[]):
        if old['kind']=='ACCEPT' and old['operation_id']==operation_id:
            _require(old['evidence']['proposal']==proposal and old['evidence']['current_inputs']==current_inputs,'CONFLICTING_ACCEPT_OPERATION')
            return verified
    _require(not {'journal','journal_root','state_reviewer','now'} & set(current_inputs),'SERVER_INPUT_SCHEMA')
    # A V1 -> V2 transition preserves its revision until the ACCEPT operation.
    base=deepcopy(verified)
    if verified.get('schema')!=SCHEMA:
        base=_base(verified);base['revision']=verified['revision']
    files=_capture(journal_root,current_inputs)
    causal=proposal['causal_inputs'];refs=causal['reference']['reviewed_event_hashes']
    original_files={p:b for p,b in files.items() if p.startswith('raw/') or p in refs}
    original=deepcopy(current_inputs)
    original.update(expected_revision=causal['account_revision'],session=causal['reference']['session'],event_path=causal['reference']['event_path'],expected_event_hashes=refs,research_snapshot=causal['reference']['research_snapshot'],market_session=causal['reference']['market_session'],source_hashes=causal['source_hashes'],unit_continuity=causal['unit_continuity'])
    evidence=dict(proposal=deepcopy(proposal),original_inputs=original,current_inputs=deepcopy(current_inputs),files=files,original_files=original_files,accepted_at=_time(now).isoformat())
    operation=dict(kind='ACCEPT',operation_id=operation_id,expected_revision=base['revision'],evidence=evidence)
    result=_step(base,operation)
    return result


def apply_continuation_event(state,event,*,now):
    verified=review_continuation_ledger(state)
    _require(verified.get('schema')==SCHEMA,'CONTINUATION_ACCEPTANCE_REQUIRED')
    for previous in verified['events']:
        if previous['event_id']==event.get('event_id'):
            _require(previous==event,'CONFLICTING_EVENT_ID');return verified
    _require(_time(event['recorded_at'])<=_time(now),'FUTURE_RECORDING')
    return _step(verified,dict(kind='EVENT',event=deepcopy(event)))
