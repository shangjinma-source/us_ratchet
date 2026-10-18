"""Explicit monthly capture composition. No default readers or production wiring."""
from copy import deepcopy
from datetime import datetime,timezone
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_difference_service import document
from data.current_quantity_v2_monthly_sources import QuantityV2MonthlySources
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_chain import review_chain
from data.current_research_intraday_execution import fetch_intraday_chart


def attach_monthly_services(paper_service,*,storage_root,decision_reader=None,review_reader=None,
                    fetch=fetch_intraday_chart,clock=None,pullback_policy=None,pullback_cap_store=None):
    """Server-owned callbacks only; configure before serving requests. Construction performs no IO.

    Preview loads the account before capture; it never reads the DB under the
    source lock. Acceptance takes DB then the same source lock through commit.
    Caller must provide registered decision/review bytes; no review is invented.
    """
    store=paper_service.store
    clock=paper_service.clock if clock is None else clock
    require(decision_reader is None or callable(decision_reader),'INVALID_DECISION_READER')
    require(review_reader is None or callable(review_reader),'INVALID_REVIEW_READER')
    sources=bridge=None;preview=None
    if callable(decision_reader) and callable(review_reader):
        sources=QuantityV2MonthlySources(storage_root=storage_root,decision_reader=decision_reader,
            review_reader=review_reader,fetch=fetch,clock=clock,
            pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store)
        bridge=QuantityV2MonthlySourceBridge(store=store,resolver=sources.resolve,clock=clock)
        def preview(*,account_id,decision_id,expected_revision):
            state=review_chain(store.read(account_id))
            require(state['ledger']['account_id']==account_id and state['ledger']['revision']==expected_revision,'STALE_REVISION')
            # Reject wrong requested identity before any new capture invalidates
            # the existing authority or fetches quotes. Provider rechecks later.
            base=deepcopy(decision_reader(deepcopy(state)));sources._identity(base)
            decision=document(base['files'][base['documents']['capital_decision']])
            require(decision['decision_id']==decision_id,'DECISION_BINDING_MISMATCH')
            capture=sources.capture(state,expected_decision_id=decision_id)
            require(capture['decision_id']==decision_id,'DECISION_BINDING_MISMATCH')
            return bridge.preview(account_id=account_id,decision_id=decision_id,expected_revision=expected_revision)
    # Preserve existing initial/continuation callbacks and subclass guards.
    # Caller supplies the same authoritative clock used by the existing service.
    require(paper_service.clock is clock,'MONTHLY_CLOCK_MUST_MATCH_SERVICE')
    paper_service.monthly_previewer=preview
    paper_service.monthly_resolver=bridge.monthly_resolver if bridge else None
    paper_service.monthly_source_guard=(lambda:sources.lock) if sources else None
    return dict(paper=paper_service,sources=sources,bridge=bridge)


def create_services(*,store,storage_root,decision_reader=None,review_reader=None,
                    fetch=fetch_intraday_chart,clock=lambda:datetime.now(timezone.utc),
                    pullback_policy=None,pullback_cap_store=None):
    paper=QuantityV2PaperService(store=store,clock=clock)
    return attach_monthly_services(paper,storage_root=storage_root,decision_reader=decision_reader,
        review_reader=review_reader,fetch=fetch,clock=clock,
            pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store)
