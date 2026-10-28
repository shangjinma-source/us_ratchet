"""Pure server-side BUY gate; authenticating source certificates is external.
No quotes, order execution, account mutation or implicit lock deletion.
"""
from copy import deepcopy
from hashlib import sha256
import json
from datetime import date

def require(value,reason):
    if not value:raise ValueError(reason)
def digest(value):return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def valid_hash(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def build_buy_scope_gate(*,reference_state,original_binding,decision_session,effective_targets,actual_shares,scope_proofs):
    """Consumes separately authenticated identity/price certificates, never client input.
    RECOVERED must first be committed to the original atomic store and reread.
    Output remains non-executable until existing original account/quote gates pass.
    """
    date.fromisoformat(decision_session)
    require(reference_state.get('schema')=='REENTRY_REFERENCE_V1','BUY_SCOPE_STATE_SCHEMA')
    require(type(reference_state.get('version')) is int and reference_state['version']>=0,'BUY_SCOPE_VERSION')
    require(type(original_binding) is dict and set(original_binding)=={'account_id','account_revision','target_id','proposal_id'} and all(type(v) is str and v for v in original_binding.values()),'BUY_SCOPE_ORIGINAL_BINDING')
    require(original_binding['account_id']==reference_state['account_id'],'BUY_SCOPE_ACCOUNT')
    require(all(type(s) is str and s and type(q) is int and q>=0 for values in (effective_targets,actual_shares) for s,q in values.items()),'BUY_SCOPE_QUANTITIES')
    locks=reference_state['locks'];require(type(locks) is dict and all(k==v['security_id'] for k,v in locks.items()),'BUY_SCOPE_LOCK_KEYS')
    buys=sorted(s for s,q in effective_targets.items() if q>actual_shares.get(s,0))
    sells={s:actual_shares.get(s,0)-effective_targets.get(s,0) for s in set(actual_shares)|set(effective_targets) if actual_shares.get(s,0)>effective_targets.get(s,0)}
    binding=dict(original_binding=deepcopy(original_binding),reference_version=reference_state['version'],reference_state_sha256=digest(reference_state),decision_session=decision_session,buy_security_ids=buys,effective_targets_sha256=digest(effective_targets),actual_shares_sha256=digest(actual_shares))
    output=dict(schema='REFERENCE_BUY_SCOPE_GATE_V1',binding=binding,binding_sha256=digest(binding),original_effective_targets=deepcopy(effective_targets),execution_targets=deepcopy(effective_targets),original_sell_quantities=sells,buy_status={s:'ALLOW' for s in buys},lock_reviews=[],executable=False,orders_created=False,account_mutated=False,source_authentication_performed=False)
    if not buys:
        output.update(status='NO_NEW_BUY_GAP',reason='ORIGINAL_SELL_GATES_STILL_REQUIRED');return output
    require(type(scope_proofs) is list,'BUY_SCOPE_PROOFS_REQUIRED')
    by_sid={}
    for proof in scope_proofs:
        require(type(proof) is dict and proof.get('origin_security_id') in locks,'BUY_SCOPE_UNKNOWN_LOCK')
        old=proof['origin_security_id'];require(old not in by_sid,'BUY_SCOPE_DUPLICATE_LOCK')
        for key in ('reference_version','reference_state_sha256','decision_session','buy_security_ids'):
            require(proof.get(key)==binding[key],'BUY_SCOPE_CERTIFICATE_BINDING')
        require(proof.get('original_binding')==original_binding,'BUY_SCOPE_ACCOUNT_CERTIFICATE_BINDING')
        by_sid[old]=proof
    unresolved=[];blocked=set();waiting=set()
    for old in sorted(locks):
        proof=by_sid.get(old)
        if proof is None or proof.get('status')=='UNRESOLVED_IDENTITY_SCOPE':
            unresolved.append(old);output['lock_reviews'].append(dict(origin_security_id=old,status='UNRESOLVED_IDENTITY_SCOPE',price_reviewed=False));continue
        require(valid_hash(proof.get('identity_evidence_sha256')),'BUY_SCOPE_IDENTITY_EVIDENCE')
        ids=proof.get('current_security_ids');require(type(ids) is list and ids and all(type(s) is str and s for s in ids) and len(set(ids))==len(ids),'BUY_SCOPE_CURRENT_IDENTITY_DOMAIN')
        affected=set(ids)&set(buys);status=proof.get('status')
        if status=='DISJOINT_IDENTITY_CERTIFIED':
            require(not affected,'BUY_SCOPE_FALSE_DISJOINT')
            output['lock_reviews'].append(dict(origin_security_id=old,status=status,current_security_ids=ids,identity_evidence_sha256=proof['identity_evidence_sha256'],price_reviewed=False));continue
        require(status=='INTERSECTS_BUY_SCOPE' and affected,'BUY_SCOPE_INTERSECTION')
        require(proof.get('price_status')!='RECOVERED','BUY_SCOPE_RECOVERY_MUST_BE_COMMITTED')
        reviewed=proof.get('price_status')=='LOCKED'
        if reviewed:
            require(valid_hash(proof.get('price_evidence_sha256')) and proof.get('price_completed_through')==decision_session,'BUY_SCOPE_PRICE_EVIDENCE')
            blocked.update(affected)
        else:waiting.update(affected)
        output['lock_reviews'].append(dict(origin_security_id=old,status=status,current_security_ids=ids,identity_evidence_sha256=proof['identity_evidence_sha256'],price_reviewed=reviewed,price_evidence_sha256=proof.get('price_evidence_sha256') if reviewed else None))
    if unresolved:waiting.update(buys)
    for sid in buys:
        status='WAIT_REFERENCE' if sid in waiting else 'BLOCK_LOCKED' if sid in blocked else 'ALLOW'
        output['buy_status'][sid]=status
        if status!='ALLOW':output['execution_targets'][sid]=actual_shares.get(sid,0)
    derived_sells={s:actual_shares.get(s,0)-output['execution_targets'].get(s,0) for s in set(actual_shares)|set(output['execution_targets']) if actual_shares.get(s,0)>output['execution_targets'].get(s,0)}
    require(derived_sells==sells,'BUY_SCOPE_ORIGINAL_SELL_CHANGED')
    output.update(status='WAIT_BUY_REFERENCE' if waiting else 'REFERENCE_BUY_GATE_CHECKED',unresolved_identity_locks=unresolved,original_sell_quantities_preserved=True)
    return output
