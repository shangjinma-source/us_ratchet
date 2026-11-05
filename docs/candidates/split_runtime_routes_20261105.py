"""Fresh isolated route assembly; no existing prepared router or worker is reused.

The caller supplies an already authenticated split monthly/view and daily service.
This does not authenticate a release, enable selection, or activate production.
"""
from inspect import getclosurevars
from pathlib import Path

from fastapi import APIRouter
from core.strategy_account_ledger import require
from api.strategy_frontier_daily_preview_v1 import create_router as daily_router
from data.news_investment_composition_v1 import compose
from data.strategy_observed_frontier_daily_admission_v1 import ObservedFrontierDailyAdmission
from data.strategy_unified_server_preparation_v32 import attach_current_preview
from docs.candidates.split_account_runtime_20261105 import create_router, attach_bound_snapshot


def build_routes(*, root, monthly_view, daily_service, journal, clock,
                 validate_sources, policy_references, timing_bundles,
                 account_arguments):
    """Construct all closures against one generation before composing news.

    Intentionally excludes monthly generation routes: their authenticated
    split-aware selection/release factory is a separate required dependency.
    """
    root = Path(root)
    validate_sources()
    require(daily_service.monthly_view is monthly_view,
            'SPLIT_RUNTIME_VIEW_MISMATCH')
    require(daily_service.monthly.accounts is monthly_view.accounts,
            'SPLIT_RUNTIME_ACCOUNT_STORE_MISMATCH')
    require(Path(account_arguments['database_path']).resolve() ==
            monthly_view.accounts.path.resolve(), 'SPLIT_RUNTIME_ACCOUNT_PATH_MISMATCH')
    for name in ('snapshot_operation', 'current', '_month', 'require_proposal'):
        require(callable(getattr(monthly_view, name, None)),
                'SPLIT_RUNTIME_VIEW_INTERFACE_REQUIRED')
    require(callable(getattr(daily_service.monthly, 'validate_current_target_pins', None)),
            'SPLIT_RUNTIME_TARGET_PIN_VALIDATOR_REQUIRED')
    observed = ObservedFrontierDailyAdmission(service=daily_service,
        monthly=monthly_view, journal=journal, clock=clock,
        validate_sources=validate_sources, policy_references=policy_references)
    router = APIRouter()
    router.include_router(create_router(timing_bundles=timing_bundles,
                                        **account_arguments))
    router.include_router(daily_router(service=observed))
    # New NewsInvestmentService and EventNewsPipeline, never old prepared closures.
    news = compose(root=root, monthly_view=monthly_view, observed_daily=observed,
                   validate=validate_sources)
    service_route = next(r for r in news.routes
                        if r.path == '/api/news/investment-review')
    news_service = getclosurevars(service_route.endpoint).nonlocals['service']
    require(news_service.preview.__self__ is observed,
            'SPLIT_RUNTIME_NEWS_OBSERVER_MISMATCH')
    # FastAPI include_router copies event hooks AND merges the child's default
    # lifespan, which would execute this worker twice. Transfer its lifespan
    # once; all previously constructed routes are hook-free.
    combined = APIRouter(lifespan=news.lifespan_context)
    combined.routes.extend(router.routes)
    combined.routes.extend(news.routes)
    router = combined
    prepared = dict(router=router, monthly=monthly_view,
                    observed_daily=observed, news_service=news_service,
                    monthly_generation_enabled=False, production_activated=False)
    prepared = attach_bound_snapshot(prepared=prepared,
                                     validate_sources=validate_sources)
    prepared = attach_current_preview(prepared=prepared,
                                      validate_sources=validate_sources)
    validate_sources()
    return prepared
