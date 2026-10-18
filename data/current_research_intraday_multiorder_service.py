"""Explicit server-owned service for existing V3/V4 paper accounts.

Only same-month continuation is exposed. Providers must supply current, locally
verified evidence and attest the current server receipt tip; there is no default
provider, network capture, selector, account creation, or production singleton.
The injected provider rereads the server-selected current receipt tip and unit
review bytes. It must not silently manufacture continuity or return a stale tip.
"""
from contextlib import ExitStack
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime,timezone
import re
from threading import RLock
from data.current_research_intraday_buy_plan import _require,_time
from data.current_research_intraday_paper_store import IntradayPaperStore
from data.current_research_intraday_multiorder_view import compact_multiorder_account
from data.current_research_intraday_retarget_continuation_chain import (
    review_retarget_continuation_chain,build_retarget_chain_proposal,accept_retarget_chain_proposal)


class IntradayMultiorderService:
    def __init__(self,*,directory=None,store=None,evidence_provider=None,acceptance_guard=None,clock=lambda:datetime.now(timezone.utc)):
        _require((directory is None)!=(store is None),'EXPLICIT_STORE_OR_DIRECTORY_REQUIRED')
        self.store=store if store is not None else IntradayPaperStore(directory)
        self.evidence_provider=evidence_provider;self.clock=clock
        self.acceptance_guard=acceptance_guard
        self.proposals=OrderedDict();self.lock=RLock()

    @staticmethod
    def _id(value):
        _require(isinstance(value,str) and re.fullmatch('[A-Za-z0-9:_-]{1,160}',value),'INVALID_ID')

    @staticmethod
    def _revision(value):
        _require(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value),'INVALID_REVISION')

    def _evidence(self,account_id,payload,now):
        _require(callable(self.evidence_provider),'CURRENT_EXECUTION_EVIDENCE_PROVIDER_UNAVAILABLE')
        evidence=self.evidence_provider(account_id=account_id,payload=deepcopy(payload),now=now)
        _require(isinstance(evidence,dict),'EXECUTION_EVIDENCE_REQUIRED')
        return deepcopy(evidence)

    @staticmethod
    def _compact(proposal):
        binding=proposal['binding']
        return dict(proposal_id=proposal['proposal_id'],account_id=binding['account_id'],account_revision=binding['account_revision'],
            target_month=binding['target_month'],target_quantities=deepcopy(proposal['target_quantities']),orders=deepcopy(proposal['orders']),wait_cash=deepcopy(proposal['wait_cash']),
            actual_cash=proposal['actual_cash'],reserved_buy_cash=proposal['reserved_buy_cash'],unreserved_cash=proposal['unreserved_cash'],
            reference_valid_until=proposal['reference_valid_until'],proposed_at=binding['proposed_at'],action=proposal['action'],
            reference_deadline_is_order_expiry=False,activated=False)

    def _response(self,account_id,*,status,proposal=None,expected_after=None):
        payload=self.store.read_retarget_envelope(account_id)
        account=compact_multiorder_account(payload)
        if expected_after is not None:_require(account['revision']==expected_after,'ACCOUNT_CHANGED_AFTER_OPERATION_RETRY_WITH_SAME_ID')
        return dict(status=status,research_only=True,execution_blocked=True,real_account=False,
            account=account,proposal=self._compact(proposal) if proposal is not None else None,
            scope='SAME_MONTH_CONTINUATION_ONLY_INITIAL_RETARGET_NOT_EXPOSED',
            atomic_evidence_guard_configured=callable(self.acceptance_guard))

    def account(self,account_id):
        self._id(account_id)
        return self._response(account_id,status='ACCOUNT')

    def preview(self,account_id,expected_revision):
        self._id(account_id);self._revision(expected_revision)
        payload=self.store.read_retarget_envelope(account_id)
        state=review_retarget_continuation_chain(payload)['ledger']
        _require(state['account_id']==account_id and state['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
        _require(all(o['closed'] for o in state['orders'].values()) and state['reserved_cash']=='0' and not state['reserved_shares'],'OPEN_ORDERS_OR_RESERVES')
        now=_time(self.clock());evidence=self._evidence(account_id,payload,now)
        now=_time(self.clock())
        proposal=build_retarget_chain_proposal(payload,expected_revision=expected_revision,execution_evidence=evidence,now=now)
        _require(proposal['status']=='READY','CONTINUATION_UNAVAILABLE:'+str(proposal.get('reason')))
        _require(self.store.read(account_id)['revision']==expected_revision,'ACCOUNT_CHANGED_DURING_PREVIEW')
        if proposal['orders']:
            with self.lock:
                existing=next((entry for entry in reversed(list(self.proposals.values())) if entry['account_id']==account_id and entry['revision']==expected_revision and entry['evidence']==evidence),None)
                if existing is not None:
                    proposal=deepcopy(existing['proposal'])
                else:
                    self.proposals[proposal['proposal_id']]=dict(account_id=account_id,revision=expected_revision,proposal=deepcopy(proposal),evidence=evidence)
                    while len(self.proposals)>64:self.proposals.popitem(last=False)
        status='CONTINUATION_PROPOSAL' if proposal['orders'] else proposal['action']
        return self._response(account_id,status=status,proposal=proposal,expected_after=expected_revision)

    def accept(self,account_id,proposal_id,operation_id,expected_revision):
        self._id(account_id);self._id(operation_id);self._revision(proposal_id);self._revision(expected_revision)
        guard_stack=ExitStack()
        def factory(current):
            # Lock order: SQLite write transaction -> source guard -> short cache lock.
            # The provider must reenter the SAME source RLock synchronously. It
            # must never wait for another thread needing that guard, nor take
            # the source guard before this paper SQLite transaction elsewhere.
            # No guard is needed for exact successful retries (no factory).
            _require(callable(self.acceptance_guard),'ATOMIC_EVIDENCE_GUARD_REQUIRED')
            guard_stack.enter_context(self.acceptance_guard(account_id=account_id))
            now=_time(self.clock())
            with self.lock:
                entry=deepcopy(self.proposals.get(proposal_id))
            _require(entry is not None,'PREVIEW_NOT_FOUND')
            _require(entry['account_id']==account_id and entry['revision']==expected_revision,'PREVIEW_ACCOUNT_BINDING_MISMATCH')
            evidence=self._evidence(account_id,current,now)
            now=_time(self.clock())
            _require(evidence==entry['evidence'],'EXECUTION_EVIDENCE_CHANGED_REPREVIEW_REQUIRED')
            return accept_retarget_chain_proposal(current,entry['proposal'],operation_id=operation_id,expected_revision=expected_revision,execution_evidence=evidence,now=now)
        # Entered by factory AFTER BEGIN; released here AFTER commit/rollback.
        # Exact successful retries never invoke factory or acquire source guard.
        with guard_stack:
            after=self.store.accept_retarget_chain(account_id,proposal_id,operation_id,expected_revision,factory)
        return self._response(account_id,status='ACCEPTED',expected_after=after['revision'])

    def event(self,account_id,event):
        self._id(account_id);_require(isinstance(event,dict),'EVENT_OBJECT_REQUIRED')
        extras={'FILL':{'quantity','price','fees','executed_at'},'CANCEL':{'cancelled_at'},'EXPIRE':set()}
        kind=event.get('kind');common={'event_id','kind','expected_revision','order_id'}
        _require(kind in extras and set(event)==common|extras[kind],'CLIENT_EVENT_SCHEMA')
        self._id(event['event_id']);self._revision(event['expected_revision'])
        # Reject legacy accounts before invoking the generic mutating store.
        # The store still performs event revision/idempotency checks under its lock.
        self.store.read_retarget_envelope(account_id)
        after=self.store.record_event(account_id,deepcopy(event),now=self.clock)
        return self._response(account_id,status='RECORDED',expected_after=after['revision'])
