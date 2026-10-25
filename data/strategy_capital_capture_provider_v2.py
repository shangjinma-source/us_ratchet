"""Explicit per-operation provider composition; shared runtime stays immutable."""
from copy import copy
from core.strategy_account_ledger import require
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_market_capture_v2 import StrategyAccountMarketCaptureV2
from data.strategy_account_action_capture_v4 import StrategyAccountActionCaptureV4

def capital_capture_provider(runtime):
    bound=runtime.execution_provider
    require(getattr(bound,'__func__',None) is StrategyAccountEvidenceProvider.execution,'CAPITAL_REAL_PROVIDER_REQUIRED')
    original=bound.__self__;provider=copy(original)
    market=original.market;actions=original.actions
    provider.market=StrategyAccountMarketCaptureV2(identity_resolver=market.identity,fetch=market.fetch,clock=market.clock,max_workers=4,max_mark_age=market.max_mark_age)
    provider.actions=StrategyAccountActionCaptureV4(fetch=actions.fetch,rss_fetch=actions.rss_fetch,clock=actions.clock,max_workers=4)
    return provider.selection
