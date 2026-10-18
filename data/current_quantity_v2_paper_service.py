"""Explicit DI paper service; no default store, sources, search or broker writes."""
from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timezone
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_paper_chain import review_chain


def compact(state):
    ledger=review_chain(state)['ledger']
    events=ledger['events']
    initial=ledger['acceptance']['proposal']
    active=ledger.get('active_monthly_acceptance')
    proposal=active['proposal'] if active else initial;inputs=proposal['causal_inputs']
    decision=inputs['capital_decision'];current_cash=proposal.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION'
    securities=proposal['securities'] if current_cash else inputs['securities']
    month=proposal['target_month'] if current_cash or active else inputs['target_mandate']['target_month']
    result=dict(status='PAPER_ACCOUNT',account_id=ledger['account_id'],revision=ledger['revision'],
        capital_decision_id=decision['decision_id'],research_id=decision['research_id'],
        target_month=month,target_scope=proposal.get('target_scope',inputs.get('target_scope')),
        execution_target_id=proposal.get('execution_target_id'),
        historical_target_quantities=deepcopy(decision['target_quantities']),
        research_target_quantities=deepcopy(decision['target_quantities']),
        securities=deepcopy(securities),
        cash=ledger['cash'],shares=deepcopy(ledger['shares']),reserved_cash=ledger['reserved_cash'],
        reserved_shares=deepcopy(ledger['reserved_shares']),recorded_fees=ledger['recorded_fees'],
        target_quantities=deepcopy(ledger['target_quantities']),orders=list(deepcopy(ledger['orders']).values()),
        events=deepcopy(events[-20:]),event_count=len(events),has_more_events=len(events)>20,
        research_only=True,execution_blocked=True,real_account=False,
        source_authenticated=False,record_type='MANUALLY_RECORDED_PAPER_EVENTS_NOT_BROKER_EXECUTIONS')
    original=initial['causal_inputs']['capital_decision']
    result['initial_capital_decision_id']=original['decision_id']
    result['initial_research_id']=original['research_id']
    if active:
        result['active_monthly_accepted_at']=active['accepted_at']
    return result


class QuantityV2PaperService:
    """initial_resolver(account_id,proposal_id,now)->{proposal,account_state}.
    continuation_resolver(current_chain,proposal_id,now)->full proposal.
    Both are server-owned, read-only, called only inside store transactions.
    Missing callbacks fail closed. Successful exact retries need neither source.
    """
    def __init__(self,*,store,initial_resolver=None,continuation_resolver=None,continuation_previewer=None,
                 monthly_previewer=None,monthly_resolver=None,monthly_source_guard=None,
                 continuation_review_policy="EXPLICIT_UNIT_REVIEW",
                 clock=lambda:datetime.now(timezone.utc)):
        require(continuation_review_policy in ("EXPLICIT_UNIT_REVIEW","BOUNDED_PUBLIC_KNOWN_ACTIONS_V1"),"INVALID_CONTINUATION_REVIEW_POLICY")
        self.continuation_review_policy=continuation_review_policy
        self.store=store;self.initial_resolver=initial_resolver
        self.monthly_previewer=monthly_previewer;self.monthly_resolver=monthly_resolver;self.monthly_source_guard=monthly_source_guard
        self.continuation_resolver=continuation_resolver;self.continuation_previewer=continuation_previewer;self.clock=clock

    def _response(self,state):
        result=compact(state)
        configured=callable(self.continuation_previewer) and callable(self.continuation_resolver)
        result['capabilities']={'continuation':{'configured':configured,
            'reason':None if configured else 'UNIT_REVIEW_SOURCE_UNAVAILABLE','policy':self.continuation_review_policy}}
        monthly=all(callable(x) for x in (self.monthly_previewer,self.monthly_resolver,self.monthly_source_guard))
        result['capabilities']['monthly']={'configured':monthly,'reason':None if monthly else 'MONTHLY_SOURCE_UNAVAILABLE'}
        return result

    def account(self,account_id):
        return self._response(self.store.read(account_id))

    def accept(self,*,account_id,proposal_id,operation_id):
        def factory(now):
            require(callable(self.initial_resolver),'INITIAL_SOURCE_UNAVAILABLE')
            return self.initial_resolver(account_id,proposal_id,now)
        return self._response(self.store.accept(account_id=account_id,proposal_id=proposal_id,
            operation_id=operation_id,factory=factory,clock=self.clock))

    def continuation_preview(self,*,account_id,expected_revision):
        require(callable(self.continuation_previewer),'CONTINUATION_SOURCE_UNAVAILABLE')
        return self.continuation_previewer(account_id=account_id,expected_revision=expected_revision)

    def accept_continuation(self,*,account_id,proposal_id,operation_id,expected_revision):
        def factory(state,now):
            require(callable(self.continuation_resolver),'CONTINUATION_SOURCE_UNAVAILABLE')
            return self.continuation_resolver(state,proposal_id,now)
        return self._response(self.store.accept_continuation(account_id=account_id,proposal_id=proposal_id,
            operation_id=operation_id,expected_revision=expected_revision,factory=factory,clock=self.clock))

    def monthly_preview(self,*,account_id,decision_id,expected_revision):
        require(all(callable(x) for x in (self.monthly_previewer,self.monthly_resolver,self.monthly_source_guard)),
                'MONTHLY_SOURCE_UNAVAILABLE')
        return self.monthly_previewer(account_id=account_id,decision_id=decision_id,expected_revision=expected_revision)

    def accept_monthly_retarget(self,*,account_id,proposal_id,operation_id,expected_revision):
        # Store owns DB transaction. Acquire source only after fresh revision;
        # keep it through commit/rollback. Exact retry bypasses this callback.
        with ExitStack() as held:
            def factory(state,now):
                require(callable(self.monthly_resolver) and callable(self.monthly_source_guard),'MONTHLY_SOURCE_UNAVAILABLE')
                held.enter_context(self.monthly_source_guard())
                return self.monthly_resolver(state,proposal_id,self.clock())
            state=self.store.accept_monthly_retarget(account_id=account_id,proposal_id=proposal_id,
                operation_id=operation_id,expected_revision=expected_revision,factory=factory,clock=self.clock)
        return self._response(state)

    def event(self,*,account_id,event):
        require('recorded_at' not in event,'SERVER_RECORDED_TIME_REQUIRED')
        return self._response(self.store.record_event(account_id=account_id,event=event,clock=self.clock))
