"""A source-only checkout has no authority to initialize legacy research accounts."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse


LOCAL_DEPLOYMENT_PATHS = (
    "tmp/tri98_runtime_execution_admission_20261016_v10",
    "data/quantity_v2_paper",
    "data/quantity_v2_observations",
    "data/quantity_v2_pullback",
    "data/quantity_v2_monthly",
    "data/quantity_v2_isolated_trial_20261016",
)


def legacy_quantity_research_configured(*, root, environment):
    """Any partial deployment must still pass the original strict constructors."""
    if any(key.startswith("QUANTITY_V2_") for key in environment):
        return True
    root = Path(root)
    return any((root/name).exists() or (root/name).is_symlink()
               for name in LOCAL_DEPLOYMENT_PATHS)


def unconfigured_quantity_research_router():
    router = APIRouter()

    async def unavailable():
        return JSONResponse(status_code=503, content={
            "status": "UNCONFIGURED",
            "message": "尚未配置历史研究所需的本地资料。",
            "research_only": True,
            "execution_blocked": True,
            "real_account": False,
            "orders_created": False,
        })

    prefix = "/api/current_portfolio_research"
    for path in (prefix, prefix+"/{unconfigured_path:path}"):
        for method in ("GET", "POST"):
            router.add_api_route(path, unavailable, methods=[method])
    return router
