"""Assemble configured monthly, daily and news routes before worker startup.

Candidate only: no production activation or service lifecycle ownership implied.
"""
from core.strategy_account_ledger import require
from docs.candidates.split_runtime_routes_20261105 import build_routes
from docs.candidates.split_native_monthly_routes_20261105 import attach_monthly_routes
from docs.candidates.split_configured_news_calendar_20261105 import attach_configured_event_calendar
from docs.candidates.split_native_news_hold_20261105 import install_native_hold_risk_plan


def build_configured_routes(*, daily_service, validate_sources, **arguments):
    validate_sources()
    prepared = build_routes(daily_service=daily_service,
                            validate_sources=validate_sources, **arguments)
    prepared = attach_monthly_routes(prepared=prepared, validate_sources=validate_sources)
    prepared = attach_configured_event_calendar(prepared=prepared, service=daily_service)
    news = prepared['news_service']
    installed = install_native_hold_risk_plan(service=news, configured=daily_service,
                                            validate=validate_sources)
    require(installed is news and callable(news.risk_plan_provider),
            'NATIVE_NEWS_HOLD_INSTALL_REQUIRED')
    require(prepared.get('calendar_enabled') is True and
            prepared.get('monthly_generation_enabled') is True and
            prepared['event_pipeline'].service is news and
            prepared['observed_daily'].service is daily_service,
            'NATIVE_CONFIGURED_ROUTE_BINDING_REQUIRED')
    validate_sources()
    return dict(prepared, native_hold_enabled=True, production_activated=False)
