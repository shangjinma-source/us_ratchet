"""Explicit isolated account composition; never registered in production mount."""
from pathlib import Path
from fastapi import APIRouter
from api.strategy_account import StrategyAccountService, create_router as account_router
from api.strategy_frontier_daily_preview_v1 import create_router as preview_router
from core.strategy_account_difference import require
from docs.candidates.frozen_target_builder_20261106 import FrozenTargetBuilder
from docs.candidates.cash_advice_coordinator_20261106 import CashAdviceCoordinator
from docs.candidates.cash_advice_router_20261106 import create_router as cash_router


def build_isolated_composition(*, directory, account_id, resolver, policy,
                               contract_sha256, expected_epoch, quote_provider, clock):
    directory=Path(directory).absolute()
    require(not any(p.is_symlink() for p in [directory,*directory.parents]), 'ISOLATED_PATH_LINK_REFUSED')
    # No production database path can be injected by the caller.
    database=directory/'research_account.sqlite3'
    require('target_quantities' in policy, 'FROZEN_QUANTITIES_REQUIRED')
    account=StrategyAccountService(database_path=database, account_id=account_id,
        resolver=resolver,clock=clock)
    builder=FrozenTargetBuilder(directory=directory/'targets',policy=policy,
        contract_sha256=contract_sha256,expected_epoch=expected_epoch,account_id=account_id,
        store=account.store,quote_provider=quote_provider,clock=clock)
    coordinator=CashAdviceCoordinator(account_service=account,builder=builder)
    router=APIRouter()
    router.include_router(account_router(database_path=database,account_id=account_id,resolver=resolver,clock=clock))
    router.include_router(cash_router(coordinator=coordinator))
    router.include_router(preview_router(service=builder))
    return dict(router=router,account_service=account,builder=builder,
        coordinator=coordinator,production_activated=False)
