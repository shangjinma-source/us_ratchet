"""Explicit composition; construction performs no capture, search or account write."""
from datetime import datetime, timezone
from contextlib import ExitStack
from pathlib import Path

from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources, MANIFEST
from data.current_quantity_v2_current_cash_service import CurrentQuantityV2CurrentCashService
from data.current_quantity_v2_paper_service import QuantityV2PaperService, compact
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_research_intraday_execution import fetch_intraday_chart


class _CurrentCashGuardedPaperService(QuantityV2PaperService):
    """DB -> source -> cache. Retain source authority until commit or rollback.

    The provider must not enter the paper database while holding its source lock.
    Successful operation retries return before this callback, even if sources or
    their lock have become unavailable. Event recording uses frozen evidence.
    """
    def __init__(self,*,sources,continuation_sources=None,**kwargs):
        super().__init__(**kwargs);self.sources=sources
        self.continuation_sources=continuation_sources

    def accept(self,*,account_id,proposal_id,operation_id):
        with ExitStack() as held:
            def factory(_before_source_lock):
                held.enter_context(self.sources.lock)
                # Waiting for the source lock may consume the adoption window.
                return self.initial_resolver(account_id,proposal_id,self.clock())
            state=self.store.accept(account_id=account_id,proposal_id=proposal_id,
                operation_id=operation_id,factory=factory,clock=self.clock)
        return self._response(state)

    def accept_continuation(self,*,account_id,proposal_id,operation_id,expected_revision):
        with ExitStack() as held:
            def factory(state,_before_source_lock):
                require(self.continuation_sources is not None and callable(self.continuation_resolver),
                        'CONTINUATION_SOURCE_UNAVAILABLE')
                held.enter_context(self.continuation_sources.lock)
                return self.continuation_resolver(state,proposal_id,self.clock())
            state=self.store.accept_continuation(account_id=account_id,proposal_id=proposal_id,
                operation_id=operation_id,expected_revision=expected_revision,factory=factory,clock=self.clock)
        return self._response(state)


def create_services(*, root, snapshot_service, server_account_id, database_path,
                    fetch=fetch_intraday_chart, clock=lambda: datetime.now(timezone.utc),
                    unit_review_reader=None, execution_month_mandate=None, observation_directory=None,
                    pullback_policy=None,pullback_cap_store=None,audit_storage_root=None,identity_manifest_path=MANIFEST):
    require(unit_review_reader is None or callable(unit_review_reader),'INVALID_UNIT_REVIEW_READER')
    sources = CurrentQuantityV2CurrentCashSources(
        root=root, snapshot_service=snapshot_service, server_account_id=server_account_id,
        fetch=fetch, clock=clock,execution_month_mandate=execution_month_mandate,
        identity_manifest_path=identity_manifest_path,
        pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store,
        audit_storage_root=audit_storage_root if audit_storage_root is not None else
            Path(observation_directory)/'current_cash_captures' if observation_directory is not None else None)
    preview = CurrentQuantityV2CurrentCashService(
        resolver=sources.resolve, account_reader=sources.account_reader,
        prepare=sources.capture, clock=clock)
    if observation_directory is not None:
        from data.current_quantity_v2_preview_observations import ObservedCurrentCashPreview
        from data.current_quantity_v2_followup_provider import FollowupBundleProvider
        followup = FollowupBundleProvider(repository_root=root, clock=clock)
        preview = ObservedCurrentCashPreview(service=preview, directory=observation_directory, clock=clock,
            research_context_reader=lambda decision_id: snapshot_service.snapshot(decision_id[:24]),
            followup_reader=followup.review)
    store = QuantityV2PaperStore(database_path)
    continuation_sources = None
    continuation = None
    continuation_preview = None
    def require_chain_source(state):
        guard = getattr(snapshot_service, 'require_source_hashes_admitted', None)
        if callable(guard):
            ledger = state['ledger']
            original = ledger.get('active_monthly_acceptance', ledger['acceptance'])['proposal']
            guard(original['causal_inputs']['frozen_execution_package']['source_hashes'])
    if unit_review_reader is not None:
        from data.current_quantity_v2_current_cash_continuation_sources import CurrentCashContinuationSources
        continuation_sources = CurrentCashContinuationSources(
            root=root,unit_review_reader=unit_review_reader,fetch=fetch,clock=clock,
            pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store,
            audit_storage_root=Path(audit_storage_root)/'current_cash_continuation_captures' if audit_storage_root is not None else
                Path(observation_directory)/'current_cash_continuation_captures' if observation_directory is not None else None)
        continuation = QuantityV2ContinuationSourceBridge(
            store=store,resolver=continuation_sources.resolve,clock=clock)

        def continuation_preview(*,account_id,expected_revision):
            state=review_chain(store.read(account_id))
            require(state['ledger']['revision']==expected_revision,'STALE_REVISION')
            require_chain_source(state)
            continuation_sources.capture(state)
            return continuation.preview(account_id=account_id,expected_revision=expected_revision)

    def continuation_resolver(state, proposal_id, now):
        require_chain_source(state)
        return continuation.continuation_resolver(state, proposal_id, now)

    paper = _CurrentCashGuardedPaperService(
        sources=sources,continuation_sources=continuation_sources,store=store,
        initial_resolver=preview.initial_resolver,clock=clock,
        continuation_review_policy=getattr(unit_review_reader, 'policy', 'EXPLICIT_UNIT_REVIEW'),
        continuation_previewer=continuation_preview,
        continuation_resolver=continuation_resolver if continuation else None)
    return dict(sources=sources,preview=preview,paper=paper,store=store,
                continuation_sources=continuation_sources,continuation=continuation)
