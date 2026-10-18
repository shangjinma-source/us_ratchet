"""Read-only, explicitly injected fixed-month execution evidence bridge.

No default sources, account creation, search or source-review fabrication.
Accept callbacks use the store-provided verified chain, never reopen its database.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from fractions import Fraction
from data.current_quantity_v2_difference_service import (
    CurrentQuantityV2DifferenceService, decode_execution_package, document)
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_paper_chain import review_chain, build_continuation
from data.current_quantity_v2_monthly_retarget import active_proposal


class QuantityV2ContinuationSourceBridge:
    """resolver(account_id, decision_id)->pinned package; store is explicit.

    Package may retain original historical files but quote_receipts must address
    current positive holdings/targets only. Unit review is supplied, never guessed.
    """
    def __init__(self, *, store, resolver, clock):
        self.store=store;self.resolver=resolver;self.clock=clock
        self._lock=RLock();self._proposals=OrderedDict()

    def _evidence(self, state, now):
        ledger=review_chain(state)['ledger']
        original=active_proposal(ledger)['causal_inputs']['capital_decision']
        package=deepcopy(self.resolver(ledger['account_id'],original['decision_id']))
        identity=CurrentQuantityV2DifferenceService._package_identity(package)
        paths=package['documents']
        require(document(package['files'][paths['capital_decision']])==original,'DECISION_BINDING_MISMATCH')
        needed={sid for mapping in (ledger['shares'],ledger['target_quantities']) for sid,q in mapping.items() if q>0}
        sell_only={sid for sid,q in ledger['shares'].items() if q>0 and ledger['target_quantities'].get(sid,0)==0} if active_proposal(ledger).get('target_scope')=='MONTHLY_CURRENT_QUOTE_ALLOCATION' else set()
        inputs=decode_execution_package(package,needed=needed,now=stamp(now),sell_only=sell_only)
        if active_proposal(ledger).get('target_scope')=='MONTHLY_CURRENT_QUOTE_ALLOCATION':
            for key in ('held_unit_continuity','account_review'):
                require(key in paths,'MONTHLY_CONTINUATION_REVIEW_REQUIRED')
                inputs[key]=document(package['files'][paths[key]])
        require(CurrentQuantityV2DifferenceService._package_identity(
            self.resolver(ledger['account_id'],original['decision_id']))==identity,'PROPOSAL_SOURCE_CHANGED')
        return inputs,identity

    def preview(self, *, account_id, expected_revision):
        state=review_chain(self.store.read(account_id));ledger=state['ledger']
        require(ledger['revision']==expected_revision,'STALE_REVISION')
        inputs,identity=self._evidence(state,self.clock())
        require(self.store.read(account_id)==state,'ACCOUNT_CHANGED')
        proposal=build_continuation(state,execution_inputs=inputs,now=self.clock())
        b=proposal['binding'];decision=active_proposal(ledger)['causal_inputs']['capital_decision']
        with self._lock:
            if proposal['orders']:
                self._proposals[proposal['proposal_id']]=dict(proposal=deepcopy(proposal),package_identity=identity)
                self._proposals.move_to_end(proposal['proposal_id'])
                while len(self._proposals)>32:self._proposals.popitem(last=False)
        result = dict(status='READY',scope='FIXED_MONTH_CONTINUATION',account_id=account_id,
            capital_decision_id=decision['decision_id'],research_id=decision['research_id'],
            prior_revision=expected_revision,target_month=b['target_month'],target_quantities=deepcopy(b['target_quantities']),
            actual_cash=b['cash'],remaining_cash=str(Fraction(b['cash'])-Fraction(proposal['reserved_buy_cash'])),created_at=b['created_at'],shares=deepcopy(b['shares']),recorded_fees=b['recorded_fees'],
            securities=deepcopy(inputs['securities']),orders=deepcopy(proposal['orders']),
            wait_cash=deepcopy(proposal['wait_cash']),reserved_buy_cash=proposal['reserved_buy_cash'],
            reference_valid_until=proposal['reference_valid_until'],action=proposal['action'],
            proposal_id=proposal['proposal_id'] if proposal['orders'] else None,
            research_only=True,execution_blocked=True,real_account=False,source_bytes_verified=True,
            source_authenticated=False,orders_created=False,account_mutated=False)
        initial = active_proposal(ledger)
        if initial.get('target_scope') in ('NEW_CASH_CURRENT_QUOTE_ALLOCATION','MONTHLY_CURRENT_QUOTE_ALLOCATION'):
            result.update(target_scope=initial['target_scope'],
                execution_target_id=initial['execution_target_id'],
                historical_target_quantities=deepcopy(decision['target_quantities']),
                execution_references=deepcopy(inputs['execution_references']),
                corporate_actions_complete=False)
        result["unit_review"]=deepcopy(proposal.get("unit_review",dict(
            policy="EXPLICIT_UNIT_REVIEW",coverage_complete=False,source_authenticated=False,
            limitations=["显式审阅仅验证已提供来源，不认证公司行动完整性"])))
        return result

    def continuation_resolver(self, state, proposal_id, now):
        """Called only after store BEGIN IMMEDIATE/revision/retry checks."""
        state=review_chain(state);ledger=state['ledger'];now=stamp(now)
        with self._lock:
            require(proposal_id in self._proposals,'PROPOSAL_UNKNOWN_OR_EVICTED')
            cached=deepcopy(self._proposals[proposal_id]);proposal=cached['proposal'];b=proposal['binding']
        require(b['account_id']==ledger['account_id'],'PROPOSAL_ACCOUNT_MISMATCH')
        require(b['prior_revision']==ledger['revision'],'STALE_REVISION')
        require(stamp(b['created_at'])<=now,'ACCEPTANCE_BEFORE_PROPOSAL')
        inputs,identity=self._evidence(state,now)
        require(identity==cached['package_identity'],'PROPOSAL_SOURCE_CHANGED')
        # Decoder checked_at is the validation clock, not changed market evidence.
        for sid,ref in inputs['execution_references'].items():
            ref['checked_at']=b['execution_inputs']['execution_references'][sid]['checked_at']
        require(inputs==b['execution_inputs'],'PROPOSAL_SOURCE_CHANGED')
        current=build_continuation(state,execution_inputs=inputs,now=now)
        require(current['orders']==proposal['orders'] and proposal['orders'],'REFERENCE_NOT_ACCEPTABLE')
        return proposal
