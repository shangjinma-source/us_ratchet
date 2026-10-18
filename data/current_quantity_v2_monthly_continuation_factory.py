"""Explicit scope dispatcher preserving the existing guarded initial service.

No global callback replacement, default source or production instance. Configure
once before requests. The original paper service remains the delegate for initial
acceptance, events and monthly retarget acceptance.
"""
from contextlib import ExitStack
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge

MONTHLY='MONTHLY_CURRENT_QUOTE_ALLOCATION'
CASH='NEW_CASH_CURRENT_QUOTE_ALLOCATION'


class MonthlyContinuationPaperService:
    def __init__(self,*,paper_service,monthly_sources):
        self.original=paper_service;self.store=paper_service.store;self.clock=paper_service.clock
        self.monthly_sources=monthly_sources
        self.bridge=QuantityV2ContinuationSourceBridge(store=self.store,resolver=monthly_sources.resolve,clock=self.clock) if monthly_sources else None

    def __getattr__(self,name):return getattr(self.original,name)

    @staticmethod
    def _scope(state):return active_proposal(review_chain(state)['ledger']).get('target_scope')

    def _response(self,state):return self._decorate(self.original._response(state))

    def _decorate(self,result):
        if result.get('target_scope')==MONTHLY:
            ready=self.bridge is not None
            result['capabilities']['continuation']=dict(configured=ready,
                reason=None if ready else 'CONTINUATION_SOURCE_UNAVAILABLE',
                policy=getattr(getattr(self.monthly_sources,'review_reader',None),'policy','EXPLICIT_UNIT_REVIEW'))
        return result

    def account(self,account_id):return self._response(self.store.read(account_id))

    def accept(self,**request):return self._decorate(self.original.accept(**request))
    def event(self,**request):return self._decorate(self.original.event(**request))
    def accept_monthly_retarget(self,**request):return self._decorate(self.original.accept_monthly_retarget(**request))

    def continuation_preview(self,*,account_id,expected_revision):
        state=review_chain(self.store.read(account_id));ledger=state['ledger']
        require(ledger['account_id']==account_id and ledger['revision']==expected_revision,'STALE_REVISION')
        scope=self._scope(state)
        if scope==MONTHLY:
            require(self.bridge is not None,'CONTINUATION_SOURCE_UNAVAILABLE')
            decision=active_proposal(ledger)['capital_decision_id']
            captured=self.monthly_sources.capture(state,expected_decision_id=decision)
            require(captured['decision_id']==decision,'DECISION_BINDING_MISMATCH')
            return self.bridge.preview(account_id=account_id,expected_revision=expected_revision)
        require(scope==CASH,'CONTINUATION_SCOPE_UNSUPPORTED')
        return self.original.continuation_preview(account_id=account_id,expected_revision=expected_revision)

    def accept_continuation(self,*,account_id,proposal_id,operation_id,expected_revision):
        with ExitStack() as held:
            def factory(state,_before_source_lock):
                scope=self._scope(state)
                if scope==MONTHLY:
                    require(self.bridge is not None,'CONTINUATION_SOURCE_UNAVAILABLE')
                    source=self.monthly_sources;resolver=self.bridge.continuation_resolver
                else:
                    require(scope==CASH,'CONTINUATION_SCOPE_UNSUPPORTED')
                    source=getattr(self.original,'continuation_sources',None)
                    resolver=self.original.continuation_resolver
                    require(source is not None and callable(resolver),'CONTINUATION_SOURCE_UNAVAILABLE')
                held.enter_context(source.lock)
                return resolver(state,proposal_id,self.clock())
            state=self.store.accept_continuation(account_id=account_id,proposal_id=proposal_id,
                operation_id=operation_id,expected_revision=expected_revision,factory=factory,clock=self.clock)
        return self._response(state)


def attach_monthly_continuation(paper_service,*,monthly_sources):
    """Return a scope-aware facade; preserve all callbacks on the given service."""
    require(monthly_sources is None or (callable(getattr(monthly_sources,'capture',None))
        and callable(getattr(monthly_sources,'resolve',None)) and hasattr(monthly_sources,'lock')),
        'INVALID_MONTHLY_CONTINUATION_SOURCE')
    paper=MonthlyContinuationPaperService(paper_service=paper_service,monthly_sources=monthly_sources)
    return dict(paper=paper,sources=monthly_sources,bridge=paper.bridge)
