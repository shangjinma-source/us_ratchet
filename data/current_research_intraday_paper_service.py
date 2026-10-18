"""Server-owned intraday paper proposals. No import-time storage or activation."""
from collections import OrderedDict
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import re
from threading import RLock

from data.current_research_intraday_buy_plan import build_intraday_initial_buy_proposal
from data.current_research_intraday_paper_ledger import accept_intraday_proposal
from data.current_research_intraday_paper_store import IntradayPaperStore
from data.current_research_intraday_session import load_intraday_market_session
from data.current_research_intraday_continuation_ledger import build_continuation_proposal,accept_continuation_proposal


def require(value, reason):
    if not value:
        raise ValueError(reason)


class IntradayPaperService:
    def __init__(self, *, root, directory, reference_service, snapshot_reader,
                 clock=lambda: datetime.now(timezone.utc), calendar_config=None, continuity_reader=None):
        self.root = Path(root)
        self.store = IntradayPaperStore(directory)
        self.reference = reference_service
        self.snapshot = snapshot_reader
        self.clock = clock
        self.calendar_config = deepcopy(calendar_config)
        self.continuity_reader = continuity_reader
        self.pending_unit_reviews = OrderedDict()
        self.continuation_proposals = OrderedDict()
        self.proposals = OrderedDict()
        self.lock = RLock()

    @staticmethod
    def account_id(research_id):
        require(isinstance(research_id, str) and re.fullmatch('[0-9a-f]{24}', research_id), 'INVALID_RESEARCH_ID')
        return 'intraday-' + research_id

    def _inputs(self, research_id, receipt, now):
        snapshot = self.snapshot(research_id)
        config = self.calendar_config
        if config is None:
            config = json.loads((self.root / 'data/research_paper/performance_source_config.json').read_bytes())
        session = load_intraday_market_session(root=self.root, calendar_path=config['calendar_path'],
                                              source_hashes=config['calendar_source_hashes'], now=now)
        require(receipt.get('status') == 'SAVED', 'SAVED_OBSERVATION_REQUIRED')
        return dict(session=session['market_session']['date'], event_path=receipt['event_path'],
                    expected_event_hashes={receipt['event_path']:receipt['event_sha256']},
                    research_snapshot=snapshot, available_cash=snapshot['budget_identity_exact']['entered_cash'],
                    shares={}, reserved_cash='0', open_orders=[], account_id=self.account_id(research_id),
                    account_revision='INTRADAY_INITIAL_CASH_V1', expected_revision='INTRADAY_INITIAL_CASH_V1',
                    market_session=session['market_session'], source_hashes=session['source_hashes'])

    def _current_observation(self, proposal):
        causal = proposal['causal_inputs']
        observation = self.reference.journal.read_event(causal['event_path'], expected_sha256=causal['event_sha256'])
        # Sequence is global to this reference process. Another refresh, even for
        # another cash input, requires a new preview before initial acceptance.
        require(observation['process_boot_id'] == self.reference.process_boot_id,
                'REFERENCE_PROCESS_CHANGED')
        require(observation['observation_sequence'] == self.reference.observation_sequence,
                'REFERENCE_REFRESHED')
        # A newer request is pending before it has an observation sequence.
        # Initial cash entry needs no cross-period unit review, but must still
        # bind the latest successful attempt rather than the last saved success.
        current = self.reference.current_reference(observation['research_id'])
        require(current['status'] == 'AVAILABLE', 'CURRENT_REFERENCE_UNAVAILABLE')
        receipt = current['current_receipt']
        require(receipt['event_path'] == causal['event_path']
                and receipt['event_sha256'] == causal['event_sha256'], 'REFERENCE_REFRESHED')

    def preview(self, research_id):
        account_id = self.account_id(research_id)
        try:
            state = self.store.read(account_id)
        except ValueError as error:
            if str(error) != 'INTRADAY_PAPER_ACCOUNT_NOT_FOUND':
                raise
        else:
            return dict(research_only=True, execution_blocked=True, account_id=account_id,
                        status='EXISTING_ACCOUNT', state=state, proposal=None)
        reference = self.reference.preview(research_id)
        with self.reference.lock:
            now = self.clock()
            inputs = self._inputs(research_id, reference['observation_record'], now)
            proposal = build_intraday_initial_buy_proposal(journal_root=self.reference.journal.root, now=now, **inputs)
            require(proposal['status'] == 'READY', 'PROPOSAL_UNAVAILABLE:'+str(proposal.get('reason')))
            self._current_observation(proposal)
            with self.lock:
                self.proposals[proposal['proposal_id']] = (deepcopy(proposal), deepcopy(reference['observation_record']))
                while len(self.proposals) > 64:
                    self.proposals.popitem(last=False)
        return dict(research_only=True, execution_blocked=True, status='PROPOSAL', account_id=account_id, proposal=proposal)

    def accept(self, research_id, proposal_id, operation_id):
        account_id = self.account_id(research_id)
        require(isinstance(proposal_id, str) and re.fullmatch('[0-9a-f]{64}', proposal_id), 'INVALID_PROPOSAL_ID')
        # Lock order: storage transaction, then source; release after commit.
        with ExitStack() as guard:
            def create():
                # Called only for a new acceptance, inside the storage transaction.
                guard.enter_context(self.reference.lock)
                with self.lock:
                    require(proposal_id in self.proposals, 'PROPOSAL_NOT_CACHED_RELOAD_REQUIRED')
                    proposal, receipt = deepcopy(self.proposals[proposal_id])
                require(proposal['research_id'] == research_id, 'PROPOSAL_RESEARCH_MISMATCH')
                self._current_observation(proposal)
                now = self.clock()
                inputs = self._inputs(research_id, receipt, now)
                return accept_intraday_proposal(proposal, journal_root=self.reference.journal.root,
                                                current_inputs=inputs, now=now)
            return self.store.accept(account_id, proposal_id, operation_id, create)

    def _continuation_inputs(self,research_id,state,receipt,now):
        initial=self._inputs(research_id,receipt,now)
        reader=self.continuity_reader
        if reader is None:
            from data.current_research_intraday_continuity_sources import load_continuation_unit_evidence
            reader=load_continuation_unit_evidence
        evidence=reader(root=self.root,state=deepcopy(state),event_path=receipt['event_path'],event_sha256=receipt['event_sha256'],now=now)
        require(isinstance(evidence,dict) and isinstance(evidence.get('source_hashes'),dict),'CONTINUITY_EVIDENCE_REQUIRED')
        pins=deepcopy(initial['source_hashes'])
        for path,digest in evidence['source_hashes'].items():
            require(path not in pins or pins[path]==digest,'CONTINUITY_SOURCE_PIN_CONFLICT')
            pins[path]=digest
        return dict(expected_revision=state['revision'],session=initial['session'],event_path=initial['event_path'],
            expected_event_hashes=initial['expected_event_hashes'],research_snapshot=initial['research_snapshot'],
            market_session=initial['market_session'],source_hashes=pins,unit_continuity=deepcopy(evidence['unit_continuity']))

    def _validate_pending_reference(self,pending,state,now):
        require(pending['revision']==state['revision'],'PENDING_REVIEW_ACCOUNT_CHANGED')
        receipt=pending['receipt']
        event=self.reference.journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
        self._current_observation({'causal_inputs':dict(event_path=receipt['event_path'],event_sha256=receipt['event_sha256'])})
        rows=event['response']['stocks']
        require(len(rows)==1 and rows[0]['status']=='AVAILABLE','PENDING_REFERENCE_UNAVAILABLE')
        row=rows[0]
        from data.current_research_intraday_buy_plan import _time
        require(_time(event['request_finished_at'])<=now<_time(row['refresh_by']),'PENDING_REFERENCE_EXPIRED')
        from zoneinfo import ZoneInfo
        require(now.astimezone(ZoneInfo('America/New_York')).date().isoformat()==row['session'],'PENDING_REFERENCE_SESSION_CHANGED')
        return dict(event_sha256=receipt['event_sha256'],checked_at=row['checked_at'],accept_before=row['refresh_by'])

    def continuation_preview(self,research_id):
        account_id=self.account_id(research_id)
        state=self.store.read(account_id)
        with self.lock:pending=deepcopy(self.pending_unit_reviews.get(research_id))
        if pending is not None:
            with self.reference.lock:
                try:self._validate_pending_reference(pending,state,self.clock())
                except Exception:
                    with self.lock:self.pending_unit_reviews.pop(research_id,None)
                    raise
            receipt=pending['receipt']
        else:
            require(Fraction(state['reserved_cash'])==0 and (state['closed'] is not None or state['filled_quantity']==state['order']['quantity']),'PRIOR_ORDER_NOT_SETTLED')
            reference=self.reference.preview(research_id)
            receipt=reference['observation_record']
        with self.reference.lock:
            state=self.store.read(account_id);now=self.clock()
            candidate=pending or dict(revision=state['revision'],receipt=deepcopy(receipt))
            try:
                review_reference=self._validate_pending_reference(candidate,state,now)
                inputs=self._continuation_inputs(research_id,state,receipt,now)
            except ValueError as error:
                if str(error) in ('CONTINUITY_EVIDENCE_NOT_REGISTERED','CONTINUITY_REVIEW_NOT_FOUND'):
                    with self.lock:
                        self.pending_unit_reviews[research_id]=deepcopy(candidate)
                        while len(self.pending_unit_reviews)>64:self.pending_unit_reviews.popitem(last=False)
                    return dict(research_only=True,execution_blocked=True,status='PENDING_UNIT_REVIEW',account_id=account_id,
                                state=state,proposal=None,review_reference=review_reference)
                with self.lock:self.pending_unit_reviews.pop(research_id,None)
                raise
            proposal=build_continuation_proposal(state,journal_root=self.reference.journal.root,now=now,**inputs)
            require(proposal['status']=='READY','CONTINUATION_UNAVAILABLE:'+str(proposal.get('reason')))
            self._current_observation({'causal_inputs':proposal['causal_inputs']['reference']})
            with self.lock:
                self.pending_unit_reviews.pop(research_id,None)
                self.continuation_proposals[proposal['proposal_id']]=(deepcopy(proposal),deepcopy(receipt))
                while len(self.continuation_proposals)>64:self.continuation_proposals.popitem(last=False)
        return dict(research_only=True,execution_blocked=True,status='CONTINUATION_PROPOSAL',account_id=account_id,state=state,proposal=proposal)

    def accept_continuation(self,research_id,proposal_id,operation_id,expected_revision):
        account_id=self.account_id(research_id)
        require(isinstance(proposal_id,str) and re.fullmatch('[0-9a-f]{64}',proposal_id),'INVALID_PROPOSAL_ID')
        # Lock order: storage transaction, then source; release after commit.
        with ExitStack() as guard:
            def create(state):
                guard.enter_context(self.reference.lock)
                with self.lock:
                    require(proposal_id in self.continuation_proposals,'CONTINUATION_NOT_CACHED_RELOAD_REQUIRED')
                    proposal,receipt=deepcopy(self.continuation_proposals[proposal_id])
                require(proposal['research_id']==research_id and proposal['causal_inputs']['account_revision']==expected_revision,'CONTINUATION_RESEARCH_OR_REVISION_MISMATCH')
                self._current_observation({'causal_inputs':proposal['causal_inputs']['reference']})
                now=self.clock()
                inputs=self._continuation_inputs(research_id,state,receipt,now)
                return accept_continuation_proposal(state,proposal,operation_id=operation_id,journal_root=self.reference.journal.root,current_inputs=inputs,now=now)
            return self.store.accept_continuation(account_id,proposal_id,operation_id,expected_revision,create)

    def account(self, research_id):
        return self.store.read(self.account_id(research_id))

    def record_event(self, research_id, event):
        require(isinstance(event, dict) and 'recorded_at' not in event, 'RECORDING_TIME_IS_SERVER_OWNED')
        return self.store.record_event(self.account_id(research_id), deepcopy(event), now=self.clock)
