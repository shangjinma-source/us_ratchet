"""HTTP composition for monthly dispatch, without changing the pinned legacy API.

The small pin-check facade is only for the historical-bars API's existing
contract; it exposes no selection engine. Deployment must admit this module.
"""
from types import SimpleNamespace
from api.strategy_monthly_target import create_router
from data.strategy_monthly_target_charts import StrategyMonthlyTargetCharts


class MonthlyTargetHTTPAdapter:
    def __init__(self, service):
        self._service = service
        self.accounts = service.accounts
        self.selection = SimpleNamespace(_pins=service.validate_current_target_pins)

    def _month(self):
        return self._service._month()

    def current(self):
        return self._service.current()

    def generate(self, **request):
        return self._service.generate(**request)

    def preview(self):
        return self._service.preview()


def create_dynamic_monthly_target_router(*, service):
    charts = StrategyMonthlyTargetCharts(root=service.root, target_service=service)
    return create_router(service=MonthlyTargetHTTPAdapter(service), charts=charts)


def create_dynamic_account_router(*, service):
    """Bind fill identity and valuation to the same server-owned monthly router."""
    from api.strategy_account import create_router as create_account_router
    from data.strategy_account_runtime import ACCOUNT_ID
    return create_account_router(database_path=service.accounts.path, account_id=ACCOUNT_ID,
        resolver=service.resolve_identity, clock=service.clock, valuation_provider=service.valuation)


def create_dynamic_holding_charts_router(*, service, validate_runtime, bootstrap_configuration=None,
                                       display_sources=None):
    """Require a deployment-owned source gate even when there is no target."""
    from core.strategy_account_ledger import require
    from data.strategy_account_runtime import ACCOUNT_ID
    from data.strategy_account_archived_holding_charts import ArchivedHoldingCharts
    from api.strategy_account_charts import create_router as create_charts_router
    require(callable(validate_runtime), 'HOLDING_CHART_SOURCE_GATE_REQUIRED')
    charts = ArchivedHoldingCharts(root=service.root,account_store=service.accounts,
        account_id=ACCOUNT_ID,target_store=service.targets,archive_path=service.archive_path,
        archive_sha256=service.archive_sha256,shared_lock=service.lock,
        bootstrap_configuration=bootstrap_configuration, display_sources=display_sources)
    return create_charts_router(charts=charts,validate_runtime=validate_runtime)
