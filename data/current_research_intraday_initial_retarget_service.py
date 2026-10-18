"""DI-only first TOP1 monthly retarget; no production provider or account creation.

Execution bytes are replayed; historical selection source authenticity remains
with the trusted server provider. All writers share DB -> source guard order.
"""
from collections import OrderedDict
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from data.current_research_intraday_buy_plan import _require, _time
from data.current_research_intraday_continuation_ledger import review_continuation_ledger
from data.current_research_intraday_paper_store import IntradayPaperStore
from data.current_research_intraday_multiorder_service import IntradayMultiorderService
from data.current_research_intraday_multiorder_view import compact_multiorder_account
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing
from data.current_research_intraday_retarget_ledger import accept_retarget_proposal, SCHEMA as RETARGET_SCHEMA
from data.current_research_intraday_retarget_continuation_chain import LEDGER_SCHEMA as CHAIN_SCHEMA
from data.current_research_intraday_retarget_evidence import SCHEMA, replay_execution_evidence, review_source_verified_retarget


class InitialRetargetNotApplied(ValueError):
    """Factory validation failed before the store can persist this acceptance."""


class IntradayInitialRetargetService:
    def __init__(self, *, directory=None, store=None, evidence_provider=None,
                 acceptance_guard=None, clock=lambda: datetime.now(timezone.utc)):
        _require((directory is None) != (store is None), 'EXPLICIT_STORE_OR_DIRECTORY_REQUIRED')
        self.store = store if store is not None else IntradayPaperStore(directory)
        self.evidence_provider = evidence_provider
        self.acceptance_guard = acceptance_guard
        self.clock = clock
        self.lock = RLock()
        self.proposals = OrderedDict()
        self.contexts = OrderedDict()

    def _bundle(self, account_id, state, now):
        _require(callable(self.evidence_provider), 'CURRENT_RETARGET_PROVIDER_UNAVAILABLE')
        bundle = deepcopy(self.evidence_provider(account_id=account_id, state=deepcopy(state), now=now))
        _require(isinstance(bundle, dict) and set(bundle) == {'sizing_inputs', 'execution_evidence', 'market_session'}, 'RETARGET_PROVIDER_SCHEMA')
        evidence = bundle['execution_evidence']; inputs = bundle['sizing_inputs']
        refs = replay_execution_evidence(evidence)
        _require(refs == inputs['execution_references'] and evidence['units'] == inputs['execution_unit_continuity'], 'RETARGET_EXECUTION_BINDING_MISMATCH')
        _require(all(inputs['source_hashes'].get(name) == digest for name, digest in evidence['source_hashes'].items()), 'RETARGET_EXECUTION_PIN_MISMATCH')
        return bundle

    @staticmethod
    def _flags():
        return dict(research_only=True, execution_blocked=True, real_account=False,
                    scope='FIRST_TOP1_MONTHLY_RETARGET_ONLY_NOT_GLOBAL_OPTIMUM',
                    selection_source_bytes_reverified=False, source_authenticated=False)

    def context(self, account_id):
        """Server-owned UI binding from the exact verified preview and ledger.

        Does not create an account or admit source data. The supplied provider
        must already cover the held securities and selected monthly target.
        """
        IntradayMultiorderService._id(account_id)
        state = self.store.read(account_id)
        if state.get('schema') in (RETARGET_SCHEMA, CHAIN_SCHEMA):
            account = compact_multiorder_account(self.store.read_retarget_envelope(account_id))
            _require(account['account_id'] == account_id and account['revision'] == state['revision'],
                     'ACCOUNT_CHANGED_DURING_CONTEXT')
            return dict(self._flags(), status='MULTIORDER_CONTEXT', scope='EXISTING_MULTIORDER_ACCOUNT', account=account)
        state = review_continuation_ledger(state)
        preview = self.preview(account_id, state['revision'])
        proposal = preview['proposal']
        # No-order previews are still legitimate, but no acceptance cache exists.
        # Their identity domain is obtained from the already reconstructed result
        # through a short-lived cache shared with ordinary previews.
        with self.lock:
            context = deepcopy(self.contexts.get(proposal['proposal_id']))
        _require(context is not None, 'CONTEXT_PREVIEW_NOT_FOUND')
        _require(context['revision'] == state['revision'], 'CONTEXT_REVISION_MISMATCH')
        _require(self.store.read(account_id)['revision'] == state['revision'], 'ACCOUNT_CHANGED_DURING_CONTEXT')
        return dict(self._flags(), status='RETARGET_CONTEXT', binding=context['binding'], preview=preview)

    def preview(self, account_id, expected_revision):
        IntradayMultiorderService._id(account_id); IntradayMultiorderService._revision(expected_revision)
        state = review_continuation_ledger(self.store.read(account_id))
        _require(state['account_id'] == account_id and state['revision'] == expected_revision, 'STALE_ACCOUNT_REVISION')
        _require((state['closed'] is not None or state['filled_quantity'] == state['order']['quantity']) and state['reserved_cash'] == '0', 'OPEN_ORDERS_OR_RESERVES')
        bundle = self._bundle(account_id, state, _time(self.clock()))
        proposal = build_intraday_retarget_sizing(state, **bundle['sizing_inputs'], now=_time(self.clock()))
        _require(proposal['status'] == 'READY', 'RETARGET_UNAVAILABLE:' + str(proposal.get('reason')))
        # Validate session boundaries and the complete envelope before offering it.
        if proposal['orders']:
            self._envelope(state, proposal, bundle, 'preview-validation', _time(self.clock()))
        _require(self.store.read(account_id)['revision'] == expected_revision, 'ACCOUNT_CHANGED_DURING_PREVIEW')
        with self.lock:
            if proposal['orders']: self.proposals[proposal['proposal_id']] = dict(account_id=account_id, revision=expected_revision,
                bundle=deepcopy(bundle), proposal=deepcopy(proposal))
            while len(self.proposals) > 64: self.proposals.popitem(last=False)
            references = bundle['sizing_inputs']['execution_references']
            binding = dict(account_id=account_id, revision=expected_revision,
                original_acceptance_id=state['acceptance_id'], cash=state['cash'],
                target_month=proposal['binding']['selection']['target_month'],
                positions=[dict(security_id=sid, ticker=references[sid]['ticker'], quantity=quantity)
                           for sid, quantity in state['shares'].items() if quantity > 0],
                securities=[dict(security_id=sid, ticker=reference['ticker']) for sid, reference in references.items()])
            self.contexts[proposal['proposal_id']] = dict(revision=expected_revision, binding=binding)
            while len(self.contexts) > 64: self.contexts.popitem(last=False)
        compact={name:deepcopy(proposal[name]) for name in ('proposal_id','target_quantities','orders','wait_cash','actual_cash','reserved_buy_cash','unreserved_cash','reference_valid_until','action','selection_equity','sizing_equity')}
        compact.update(account_id=account_id,account_revision=expected_revision,
            target_month=proposal['binding']['selection']['target_month'],
            proposed_at=proposal['binding']['proposed_at'],activated=False,reference_deadline_is_order_expiry=False)
        return dict(self._flags(), status='RETARGET_PROPOSAL' if proposal['orders'] else proposal['action'], account_id=account_id,
                    expected_revision=expected_revision, proposal=compact)

    @staticmethod
    def _envelope(state, proposal, bundle, operation_id, now):
        ledger = accept_retarget_proposal(state, proposal, sizing_inputs=bundle['sizing_inputs'],
            market_session=bundle['market_session'], operation_id=operation_id, now=now)
        envelope = dict(schema=SCHEMA, ledger=ledger, retarget_acceptance_id=ledger['retarget_acceptance_id'],
            execution_evidence=deepcopy(bundle['execution_evidence']), execution_source_bytes_verified=True,
            selection_source_bytes_reverified=False, source_authenticated=False, real_account=False)
        return review_source_verified_retarget(envelope)

    def accept(self, account_id, proposal_id, operation_id, expected_revision):
        for value in (account_id, operation_id): IntradayMultiorderService._id(value)
        for value in (proposal_id, expected_revision): IntradayMultiorderService._revision(value)
        with ExitStack() as stack:
            def prepare(current):
                _require(callable(self.acceptance_guard), 'ATOMIC_EVIDENCE_GUARD_REQUIRED')
                stack.enter_context(self.acceptance_guard(account_id=account_id))
                with self.lock: entry = deepcopy(self.proposals.get(proposal_id))
                _require(entry is not None, 'PREVIEW_NOT_FOUND')
                _require(entry['account_id'] == account_id and entry['revision'] == expected_revision, 'PREVIEW_ACCOUNT_BINDING_MISMATCH')
                bundle = self._bundle(account_id, current, _time(self.clock()))
                _require(bundle == entry['bundle'], 'RETARGET_EVIDENCE_CHANGED_REPREVIEW_REQUIRED')
                return self._envelope(current, entry['proposal'], bundle, operation_id, _time(self.clock()))
            def factory(current):
                try:
                    return prepare(current)
                except ValueError as error:
                    # Store rolls back a failed factory before propagating this
                    # typed result. Post-commit response failures never use it.
                    raise InitialRetargetNotApplied(str(error)) from error
            after = self.store.accept_retarget(account_id, proposal_id, operation_id, expected_revision, factory)
        payload = self.store.read_retarget_envelope(account_id)
        view = compact_multiorder_account(payload)
        _require(view['revision'] == after['revision'], 'ACCOUNT_CHANGED_AFTER_OPERATION_RETRY_WITH_SAME_ID')
        return dict(self._flags(), status='ACCEPTED', account=view)
