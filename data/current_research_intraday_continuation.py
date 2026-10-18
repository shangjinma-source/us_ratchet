"""Same-month BUY continuation proposal only; never activates a V1 ledger."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo
from data.current_research_intraday_paper_ledger import review_intraday_paper_ledger
from data.current_research_intraday_buy_plan import build_intraday_initial_buy_proposal,_require,_time


def build_intraday_continuation_proposal(state,*,expected_revision,journal_root,session,event_path,
        expected_event_hashes,research_snapshot,market_session,source_hashes,unit_continuity,now,
        state_reviewer=review_intraday_paper_ledger,journal=None):
    flags=dict(research_only=True,execution_blocked=True,source_authenticated=False,
               legacy_ledger_compatible=False,account_mutated=False,order_lifecycle='UNACTIVATED',
               schema='INTRADAY_SAME_MONTH_BUY_CONTINUATION_PROPOSAL_V1')
    try:
        verified=state_reviewer(state);now=_time(now)
        _require(expected_revision==verified['revision'],'STALE_ACCOUNT_REVISION')
        order=verified['order'];original=verified['acceptance']['proposal'];initial=original['causal_inputs']
        first=_time(verified['acceptance']['accepted_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        _require(session[:7]==first[:7],'RESELECT_REQUIRED')
        _require(session>=first,'SESSION_BEFORE_ACCEPTANCE')
        _require(Fraction(verified['reserved_cash'])==0 and (verified['closed'] is not None or verified['filled_quantity']==order['quantity']),'PRIOR_ORDER_NOT_SETTLED')
        _require(not verified['events'] or now>=_time(verified['events'][-1]['recorded_at']),'NOW_PRECEDES_ACCOUNT_HISTORY')
        _require(research_snapshot==initial['research_snapshot'],'FROZEN_RESEARCH_BINDING_CHANGED')
        # Reuse the existing quote/receipt verifier with its original cash identity;
        # its fresh-cash quantity is deliberately NOT used for the continuation.
        reference=build_intraday_initial_buy_proposal(journal_root=journal_root,session=session,event_path=event_path,
            expected_event_hashes=expected_event_hashes,research_snapshot=research_snapshot,
            available_cash=initial['available_cash'],shares={},reserved_cash='0',open_orders=[],
            account_id=verified['account_id'],account_revision=expected_revision,expected_revision=expected_revision,
            market_session=market_session,source_hashes=source_hashes,now=now,journal=journal)
        _require(reference['status']=='READY','REFERENCE_UNAVAILABLE:'+str(reference.get('reason')))
        current=reference['causal_inputs'];sid=order['security_id'];unit=unit_continuity
        _require(current['security']==initial['security'] and current['security']['security_id']==sid,'SECURITY_CHANGED')
        _require(current['observation']['source']==initial['observation']['source'],'QUOTE_SOURCE_UNIT_KIND_CHANGED')
        _require(isinstance(unit,dict) and unit.get('security_id')==sid and unit.get('from_session')==first
                 and unit.get('to_session')==session and unit.get('status')=='NO_UNPROCESSED_ACTIONS'
                 and unit.get('price_basis')=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'
                 and unit.get('initial_event_sha256')==initial['event_sha256']
                 and unit.get('current_event_sha256')==current['event_sha256'],'EXPLICIT_BOUND_UNIT_CONTINUITY_REQUIRED')
        def pins(refs):
            _require(isinstance(refs,list) and refs and all(isinstance(p,str) and p in source_hashes and re.fullmatch('[0-9a-f]{64}',source_hashes[p]) for p in refs),'CONTINUITY_SOURCE_NOT_PINNED')
        pins(unit.get('source_references'))
        _require(_time(unit['covered_from'])<=_time(initial['observation']['checked_at'])
                 and _time(unit['covered_through'])>=_time(current['observation']['checked_at'])
                 and _time(unit['covered_through'])<=_time(unit['reviewed_asof'])<=now,'CONTINUITY_TIME_COVERAGE_INVALID')
        if session!=first:
            action=unit.get('action_review',{})
            _require(action.get('covered_from')==first and action.get('covered_through')==session
                     and action.get('status')=='NO_UNPROCESSED_ACTIONS','CROSS_SESSION_ACTION_REVIEW_REQUIRED')
            pins(action.get('source_references'))
            _require(_time(current['observation']['checked_at'])<=_time(action['reviewed_asof'])<=now,'ACTION_REVIEW_TIME_INVALID')
        _require(set(verified['shares'])<={sid},'UNSUPPORTED_OTHER_HOLDINGS')
        held=verified['shares'].get(sid,0);target=original['quantity'];delta=max(0,target-held)
        cash=Fraction(verified['cash']);cap=Fraction(reference['limit_price']);quantity=min(delta,int(cash//cap))
        action='NO_ACTION' if delta==0 else 'WAIT_CASH' if quantity==0 else 'PROPOSE_BUY'
        causal=dict(schema=flags['schema'],account_id=verified['account_id'],account_revision=expected_revision,
            initial_acceptance_id=verified['acceptance_id'],initial_target_quantity=target,
            shares=deepcopy(verified['shares']),cash=str(cash),recorded_fees=verified['fees'],
            reference=deepcopy(current),unit_continuity=deepcopy(unit),source_hashes=deepcopy(source_hashes),
            quantity=quantity,remaining_deficit=delta-quantity,limit_price=str(cap),proposal_created_at=now.isoformat())
        identifier=sha256(json.dumps(causal,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return dict(flags,status='READY',action=action,proposal_id=identifier,causal_inputs=causal,
            research_id=original['research_id'],security=deepcopy(current['security']),target_quantity=target,held_quantity=held,
            quantity=quantity,remaining_deficit=delta-quantity,available_cash=str(cash),limit_price=str(cap),
            notional=str(quantity*cap),residual_cash=str(cash-quantity*cap),side='BUY',time_in_force=None,
            accept_before=reference['accept_before'],reference_valid_until=reference['reference_valid_until'],
            fee_scope=dict(commission='0',other_fees='UNKNOWN_NOT_RESERVED'),
            limitations=['Continuation proposal only; V1 ledger cannot accept it.',
                'Continuity is an explicitly pinned caller review, not automatic source or corporate-action certification.',
                'Original accepted target is fixed; no SELL, migration, external cash, or fresh-cash rescaling.'])
    except (ValueError,KeyError,TypeError,OSError,ZeroDivisionError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),proposal_id=None)
