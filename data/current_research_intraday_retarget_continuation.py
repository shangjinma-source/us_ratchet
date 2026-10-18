"""Read-only same-month remaining-target proposal; not accepted by the V3 ledger."""
from copy import deepcopy
from fractions import Fraction
from zoneinfo import ZoneInfo
from data.current_research_intraday_buy_plan import _require,_time
from data.current_research_intraday_paper_ledger import _hash
from data.current_research_intraday_retarget_evidence import review_source_verified_retarget,replay_execution_evidence


def _same_session_source_history(prior_inputs, current_inputs, prior_reference, reference):
    prior_kind = prior_inputs.get('source_kind')
    _require(current_inputs.get('source_kind') == prior_kind, 'SAME_SESSION_SOURCE_KIND_CHANGED')
    if prior_kind == 'INTRADAY_JOURNAL_OBSERVATION_V1':
        _require(current_inputs['binding'] == prior_inputs['binding'], 'SAME_SESSION_JOURNAL_BINDING_CHANGED')
        old = prior_inputs['current_reference']; new = current_inputs['current_reference']
        if old['process_boot_id'] == new['process_boot_id']:
            _require(new['attempt_token'] >= old['attempt_token'], 'JOURNAL_ATTEMPT_MOVED_BACKWARD')
            if new['attempt_token'] == old['attempt_token']:
                _require(new == old, 'JOURNAL_ATTEMPT_REPLACED')
        _require(_time(reference['checked_at']) >= _time(prior_reference['checked_at'])
                 and Fraction(reference['buy_limit']) <= Fraction(prior_reference['buy_limit']),
                 'SAME_SESSION_JOURNAL_CAP_OR_TIME_REGRESSED')
        _require(all(current_inputs['event_hashes'].get(path) == digest
                     for path, digest in prior_inputs['event_hashes'].items()), 'JOURNAL_ACCEPTED_HISTORY_REMOVED')
    else:
        old_paths = prior_inputs['receipt_paths']; new_paths = current_inputs['receipt_paths']
        _require(new_paths[:len(old_paths)] == old_paths, 'SAME_SESSION_RECEIPT_CHAIN_RESET')
    _require(all(current_inputs['source_hashes'].get(path) == digest
                 for path, digest in prior_inputs['source_hashes'].items()), 'SAME_SESSION_SOURCE_HISTORY_CHANGED')


def _build_verified_continuation(verified,*,expected_revision,execution_evidence,now):
    flags=dict(schema='INTRADAY_RETARGET_CONTINUATION_PROPOSAL_V1',research_only=True,execution_blocked=True,activated=False,ledger_acceptance_supported=False,source_authenticated=False,complete_corporate_actions_verified=False)
    try:
        state=verified['ledger'];now=_time(now)
        _require(expected_revision==state['revision'],'STALE_REVISION')
        _require(all(o['closed'] for o in state['orders'].values()) and Fraction(state['reserved_cash'])==0 and not state['reserved_shares'],'OPEN_ORDERS_OR_RESERVES')
        acceptance=state['retarget_acceptance'];accepted=_time(acceptance['accepted_at'])
        month=acceptance['proposal']['binding']['selection']['target_month']
        session=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        _require(session[:7]==month,'RESELECT_REQUIRED')
        targets=deepcopy(state['target_quantities']);held={s:q for s,q in state['shares'].items() if q}
        needed=set(held)|{s for s,q in targets.items() if q>0}
        observation_floor=max([accepted]+[_time(e['recorded_at']) for e in state['events']])
        _require(observation_floor<=now,'LEDGER_OBSERVATION_AFTER_NOW')
        if not needed:
            _require(execution_evidence==dict(execution_inputs={},units={},source_hashes={},files={},references={}),'EMPTY_EVIDENCE_REQUIRED')
            refs={}
        else:
            refs=replay_execution_evidence(execution_evidence)
        _require(set(refs)==needed,'COMPLETE_HELD_AND_TARGET_REFERENCES_REQUIRED')
        original=acceptance['sizing_inputs']['execution_references'];units=execution_evidence['units'];deadlines=[]
        for sid,ref in refs.items():
            unit=units[sid];checked=_time(ref['checked_at']);deadline=_time(ref['valid_until']);tick=_time(ref['last_at'])
            prior_inputs=verified['execution_evidence']['execution_inputs'].get(sid)
            prior_reference = verified['execution_evidence']['references'].get(sid)
            if prior_inputs is not None and prior_reference['session']==session:
                current_inputs=execution_evidence['execution_inputs'][sid]
                _same_session_source_history(prior_inputs,current_inputs,prior_reference,ref)
            _require(sid in original and ref['ticker']==original[sid]['ticker'] and ref['security_id']==sid,'SECURITY_IDENTITY_CHANGED')
            _require(ref['scope_id']==state['account_id']+':'+month and ref['session']==session,'EXECUTION_SCOPE_MISMATCH')
            _require(observation_floor<=tick<=checked<=now<deadline and _time(ref['session_open'])<=now<_time(ref['session_close']),'STALE_EXECUTION_REFERENCE')
            _require(unit['security_id']==sid and unit['retarget_acceptance_id']==state['retarget_acceptance_id'] and unit['status']=='NO_UNPROCESSED_ACTIONS','UNIT_ACCEPTANCE_BINDING_MISMATCH')
            _require(unit['original_reference_source_hashes']==original[sid]['source_hashes'] and unit['reference_source_hashes']==ref['source_hashes'],'UNIT_REFERENCE_BINDING_MISMATCH')
            _require(unit['price_basis']=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS','UNIT_PRICE_BASIS_MISMATCH')
            _require(_time(unit['covered_from'])<=_time(original[sid]['checked_at'])<=accepted<=checked<=_time(unit['covered_through'])<=_time(unit['reviewed_asof'])<=now,'UNIT_COVERAGE_INCOMPLETE')
            _require(unit['source_references'],'UNIT_SOURCE_REQUIRED')
            if session!=accepted.astimezone(ZoneInfo('America/New_York')).date().isoformat():
                _require(unit.get('action_review_scope')=='FULL_INTERVAL_IDENTITY_AND_CORPORATE_ACTIONS','CROSS_SESSION_ACTION_REVIEW_REQUIRED')
            deadlines.append(deadline)
        cash=Fraction(state['cash']);remaining=cash;orders=[];wait=[]
        for sid in sorted(needed):
            delta=targets.get(sid,0)-held.get(sid,0)
            if delta<0:orders.append(dict(security_id=sid,ticker=refs[sid]['ticker'],side='SELL',quantity=-delta,limit_price=refs[sid]['sell_limit']))
            if delta>0:
                limit=Fraction(refs[sid]['buy_limit']);quantity=min(delta,int(remaining//limit))
                if quantity:orders.append(dict(security_id=sid,ticker=refs[sid]['ticker'],side='BUY',quantity=quantity,limit_price=str(limit)));remaining-=quantity*limit
                if quantity<delta:wait.append(dict(security_id=sid,remaining_deficit=delta-quantity,reason='WAIT_CASH'))
        binding=dict(account_id=state['account_id'],account_revision=state['revision'],retarget_acceptance_id=state['retarget_acceptance_id'],target_month=month,target_quantities=targets,cash=state['cash'],shares=deepcopy(state['shares']),fees=state['fees'],execution_evidence=deepcopy(execution_evidence),proposed_at=now.isoformat(),orders=orders,wait_cash=wait)
        return dict(flags,status='READY',proposal_id=_hash(binding),binding=binding,target_quantities=targets,orders=orders,wait_cash=wait,actual_cash=str(cash),reserved_buy_cash=str(cash-remaining),unreserved_cash=str(remaining),unfilled_sell_proceeds_available='0',reference_valid_until=min(deadlines).isoformat() if deadlines else None,action='PROPOSE_DIFFERENCES' if orders else 'WAIT_CASH' if wait else 'NO_ACTION',execution_source_bytes_verified=bool(needed),limitations=['Source integrity is local; unit reviews are explicit caller-reviewed declarations, not complete corporate-action certification.','Reference deadline is proposal acceptance validity, not an automatic cancellation time.','No selection, cash injection or target expansion; subsequent ledger acceptance is not implemented.'])
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),proposal_id=None)


def build_retarget_continuation_proposal(envelope,*,expected_revision,execution_evidence,now):
    """Public V3 entry always verifies the complete source envelope first."""
    try:
        verified=review_source_verified_retarget(envelope)
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        return dict(schema='INTRADAY_RETARGET_CONTINUATION_PROPOSAL_V1',research_only=True,execution_blocked=True,activated=False,ledger_acceptance_supported=False,source_authenticated=False,complete_corporate_actions_verified=False,status='BLOCKED',reason=str(error),proposal_id=None)
    return _build_verified_continuation(verified,expected_revision=expected_revision,execution_evidence=execution_evidence,now=now)
