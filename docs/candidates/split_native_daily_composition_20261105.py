"""Explicit native-month composition; no implicit fallback to old split targets.

The release builder owns reader authentication and source pins. The original
daily retry, expiry, cash and signal rules are reused in private bindings.
"""
from types import FunctionType
from core.strategy_account_ledger import require
from data import saved_frontier_daily_composition_v1 as original
from data import saved_frontier_zero_cash_preview_v1 as zero
from data import saved_frontier_buy_data_wait_preview_v1 as waiting
from docs.candidates.strategy_split_frontier_preview_service import SavedFrontierPreviewService
from docs.candidates.strategy_account_split_scoped_preview import preview_scoped_account
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyExecutionBridge


def bind(function, **dependencies):
    result = FunctionType(function.__code__, dict(function.__globals__, **dependencies),
        function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def build_composition(*, mixed_execution_bridge, buy_wait_execution_bridge, **arguments):
    # Both sell-only variants must be supplied explicitly by the source-pinned
    # builder. Never silently use the old provider class for either branch.
    require(isinstance(mixed_execution_bridge, type) and isinstance(buy_wait_execution_bridge, type),
            'NATIVE_MIXED_EXECUTION_BRIDGES_REQUIRED')
    zero_preview = bind(zero.preview_zero_cash_mixed,
        preview_scoped_account=preview_scoped_account,
        DailyMixedExecutionBridge=mixed_execution_bridge)
    wait_preview = bind(waiting.preview_buy_data_wait_mixed,
        preview_scoped_account=preview_scoped_account,
        DailyBuyDataWaitExecutionBridge=buy_wait_execution_bridge)

    class NativeDailyComposition(original.SavedFrontierDailyComposition):
        preview = bind(original.SavedFrontierDailyComposition.preview,
            SavedFrontierPreviewService=SavedFrontierPreviewService,
            DailyExecutionBridge=DailyExecutionBridge,
            preview_zero_cash_mixed=zero_preview,
            preview_buy_data_wait_mixed=wait_preview)

    return NativeDailyComposition(**arguments)
