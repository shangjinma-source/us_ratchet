"""Pure prospective reference latch; source authentication belongs to server adapter."""
from copy import deepcopy
from datetime import date,datetime,timezone
from fractions import Fraction as F
from hashlib import sha256
import json

def require(ok,reason):
 if not ok:raise ValueError(reason)
def digest(value):return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def timestamp(value):
 t=datetime.fromisoformat(value.replace('Z','+00:00'));require(t.tzinfo is not None,'REFERENCE_AWARE_TIME_REQUIRED');return t.astimezone(timezone.utc)
def activate(*,account_id,activation_id,activation_at,activation_session,risk_state):
 date.fromisoformat(activation_session);timestamp(activation_at);require(bool(account_id) and digest(activation_id),'REFERENCE_ACTIVATION_REQUIRED')
 require(not risk_state or risk_state['account_id']==account_id,'REFERENCE_ACCOUNT_MISMATCH')
 require(not risk_state or risk_state['session_date']<=activation_session,'REFERENCE_ACTIVATION_BEFORE_RISK')
 return dict(schema='REENTRY_REFERENCE_V1',account_id=account_id,activation_id=activation_id,activation_at=activation_at,activation_session=activation_session,version=0,locks={},processed=[],releases=[])
def advance(*,state,risk_before,risk_after,held_evidence=None,completed_at=None,risk_evidence_sha256=None):
 result=deepcopy(state);require(result['schema']=='REENTRY_REFERENCE_V1' and result['account_id']==risk_after['account_id'],'REFERENCE_ACCOUNT_MISMATCH')
 session=risk_after['session_date'];epoch=risk_after['decision_date'];prior=set(risk_before['exited']) if risk_before and risk_before['decision_date']==epoch else set()
 for sid in sorted(set(risk_after['exited'])-prior):
  key=epoch+'|'+sid
  if key in result['processed']:continue
  require(completed_at is not None,'REFERENCE_COMPLETED_TIME_REQUIRED')
  require(timestamp(completed_at).date().isoformat()==session,'REFERENCE_COMPLETED_SESSION_CLOCK')
  if timestamp(completed_at)<=timestamp(result['activation_at']):continue
  require(isinstance(held_evidence,dict) and held_evidence.get('session_date')==session and held_evidence.get('account_id')==state['account_id'] and digest(held_evidence.get('evidence_sha256')) and isinstance(held_evidence.get('account_revision'),str) and bool(held_evidence['account_revision']),'REFERENCE_EXIT_HOLDINGS_EVIDENCE_REQUIRED')
  require(held_evidence.get('unit_ids',{}).get(sid)==risk_after['unit_ids'][sid] and digest(held_evidence.get('event_boundary_sha256')) and digest(risk_evidence_sha256),'REFERENCE_EXIT_SOURCE_UNIT_BINDING')
  held=held_evidence.get('shares',{}).get(sid)
  require(type(held) is int and held>=0,'REFERENCE_EXIT_HELD_QUANTITY_REQUIRED')
  result['processed'].append(key)
  if not held:continue
  reference=F(risk_after['last_closes'][sid]);require(reference>0 and risk_after['unit_ids'].get(sid),'REFERENCE_EXIT_PRICE_UNIT_REQUIRED')
  result['locks'][sid]=dict(security_id=sid,current_security_id=sid,current_unit_id=risk_after['unit_ids'][sid],verified_through=session,exit_session=session,epoch=epoch,reference_price=str(reference),unit_id=risk_after['unit_ids'][sid],held_quantity_at_exit=held,account_revision=held_evidence['account_revision'],holdings_evidence_sha256=held_evidence['evidence_sha256'],risk_evidence_sha256=risk_evidence_sha256)
 if result!=state:result['version']=state['version']+1
 return result

def recover(*,state,security_id,evidence,decision_session):
 result=deepcopy(state);lock=result['locks'].get(security_id);require(lock is not None,'REFERENCE_LOCK_REQUIRED')
 require(evidence.get('status')=='AUTHENTICATED_COMPLETE_REFERENCE_INTERVAL' and digest(evidence.get('evidence_sha256')) and evidence.get('exit_session')==lock['exit_session'] and evidence.get('origin_security_id')==security_id and evidence.get('origin_unit_id')==lock['unit_id'],'REFERENCE_INTERVAL_BINDING')
 require(evidence.get('completed_through')==decision_session and decision_session>=lock.get('verified_through',lock['exit_session']),'REFERENCE_DECISION_COVERAGE_REQUIRED')
 days=evidence.get('expected_sessions');rows=evidence.get('rows');require(isinstance(days,list) and bool(days) and isinstance(rows,list) and [x['session_date'] for x in rows]==days and days==sorted(set(days)) and days[0]>lock['exit_session'] and days[-1]==evidence.get('completed_through'),'REFERENCE_CONTIGUOUS_INTERVAL_REQUIRED')
 reference=F(lock['reference_price']);sid=security_id;unit=lock['unit_id'];first=None
 as_of=timestamp(evidence['as_of'])
 for row in rows:
  require(timestamp(row['completed_at'])<=as_of,'REFERENCE_FUTURE_CLOSE')
  date.fromisoformat(row['session_date']);require(row.get('completed') is True,'REFERENCE_COMPLETED_CLOSE_REQUIRED')
  action=row.get('conversion')
  if action:
   require(action.get('kind')=='REVIEWED_INTEGER_SPLIT' and action.get('timing')=='BEFORE_OPEN' and action.get('old_security_id')==sid and action.get('old_unit_id')==unit and digest(action.get('evidence_sha256')),'REFERENCE_UNIT_CHANGE_UNREVIEWED')
   ratio=F(action['ratio']);require(ratio>0 and ratio.denominator==1 and action.get('new_security_id') and action.get('new_unit_id'),'REFERENCE_SPLIT_RATIO')
   reference/=ratio;sid=action['new_security_id'];unit=action['new_unit_id']
  require(row.get('security_id')==sid and row.get('unit_id')==unit and F(row['close'])>0,'REFERENCE_PRICE_UNIT_MISMATCH')
  if first is None and F(row['close'])>=reference:first=row['session_date']
 if not first:
  # Revalidation clocks and receipt digests may change without changing the
  # decision. Keep the first authenticated receipt for identical semantics;
  # callers still validate and retain this call's fresh source evidence.
  semantic={key:evidence[key] for key in ('origin_security_id','origin_unit_id','exit_session','completed_through','expected_sessions','rows')}
  semantic_hash=sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if lock.get('interval_semantics_sha256')==semantic_hash:
   return result
  result['locks'][security_id].update(current_security_id=sid,current_unit_id=unit,verified_through=evidence['completed_through'],interval_evidence_sha256=evidence['evidence_sha256'],interval_semantics_sha256=semantic_hash)
  if result!=state:result['version']=state['version']+1
 if first:
  del result['locks'][security_id];result['releases'].append(dict(security_id=security_id,recovered_session=first,evidence_sha256=evidence['evidence_sha256']));result['version']+=1
 return result

def execution_targets(*,state,effective_targets,actual_shares,decision_date):
 require(all(type(q) is int and q>=0 for q in effective_targets.values()) and all(type(q) is int and q>=0 for q in actual_shares.values()),'REFERENCE_TARGET_QUANTITY')
 out=dict(effective_targets)
 for lock in state['locks'].values():
  require(lock.get('verified_through')==decision_date,'REFERENCE_CURRENT_IDENTITY_COVERAGE_REQUIRED')
  sid=lock['current_security_id']
  require(sid in actual_shares,'REFERENCE_CURRENT_HOLDINGS_REQUIRED')
  if sid in out:out[sid]=min(out[sid],actual_shares[sid])
 return out
