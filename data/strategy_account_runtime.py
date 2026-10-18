"""Explicit deployment composition for the real-strategy target service.

Construction validates reviewed pins and creates no accounts, targets or cap
databases. A deployment is admitted for one target month; rolling the calendar
does not turn an old saved training package into a new monthly selection.
"""
from datetime import datetime, timezone
from copy import deepcopy
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo
import re

from core.strategy_account_ledger import require
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.strategy_account_execution_limits import build_execution_limits
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_target_service import StrategyAccountTargetService, MINIMUM_RUNTIME_PATHS
from data.strategy_monthly_target_service import StrategyMonthlyTargetService, LIFECYCLE_PATHS
from data.strategy_account_live_pullback_runtime import LazyPullbackCapStore


RUNTIME_PATHS = MINIMUM_RUNTIME_PATHS | LIFECYCLE_PATHS | {
    'data/strategy_account_runtime.py', 'data/strategy_account_identity.py',
    'data/strategy_account_market_capture.py', 'data/strategy_account_action_capture.py',
    'data/strategy_account_execution_limits.py', 'data/strategy_account_evidence_provider.py',
    'data/strategy_account_unit_review.py', 'data/current_research_intraday_execution.py',
    'data/strategy_account_mark_reference.py',
    'data/current_quantity_v2_paper_action_sources.py',
    'data/current_quantity_v2_pullback_runtime.py', 'data/current_quantity_v2_pullback_cap_store.py',
    'data/current_quantity_v2_pullback_sources.py', 'data/current_quantity_v2_pullback_entry.py',
    'api/strategy_monthly_target.py',
    'data/strategy_account_live_pullback_entry.py',
    'data/strategy_account_live_pullback_sources.py',
    'data/strategy_account_live_pullback_cap_store.py',
    'data/strategy_account_live_pullback_runtime.py',
    'data/strategy_account_quote_clock.py',
    'data/strategy_account_notice_review.py',
}
ACCOUNT_ID = 'real-strategy-account-v1'
# Selection valuation is not an executable quote; execution remains 120 seconds.
SELECTION_VALUATION_MAX_AGE_SECONDS = 900
EXECUTION_MARK_MAX_AGE_SECONDS = 120


class ScopedAccountStore(StrategyAccountStore):
    def read(self):
        state = super().read()
        require(state is None or state['account_id'] == ACCOUNT_ID, 'ACCOUNT_SCOPE_MISMATCH')
        return state


def build_runtime(*, root, configuration, clock=None):
    """Use a server-owned configuration, never an HTTP request document."""
    root = Path(root).resolve()
    configuration = deepcopy(configuration)
    clock = clock or (lambda: datetime.now(timezone.utc))
    fields = {'schema', 'target_month', 'training_manifest', 'training_sha256',
              'training_closed_at', 'identity_manifest', 'identity_sha256', 'runtime_pins'}
    require(type(configuration) is dict and set(configuration) == fields, 'RUNTIME_CONFIGURATION_FIELDS')
    require(configuration['schema'] == 'REAL_STRATEGY_RUNTIME_V1', 'RUNTIME_CONFIGURATION_SCHEMA')
    require(type(configuration['target_month']) is str and
            re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', configuration['target_month']), 'TARGET_MONTH_REQUIRED')
    require(type(configuration['runtime_pins']) is dict and
            RUNTIME_PATHS <= set(configuration['runtime_pins']), 'RUNTIME_COMPOSITION_PINS_REQUIRED')
    for key in ('training_sha256', 'identity_sha256'):
        require(type(configuration[key]) is str and re.fullmatch('[0-9a-f]{64}', configuration[key]), 'SOURCE_HASH_REQUIRED')
    storage = root/'data'/'strategy_account'
    require(not any(p.is_symlink() for p in [storage, *storage.parents]), 'RUNTIME_STORAGE_SYMLINK_REFUSED')
    identity = PinnedStrategyIdentity(root, configuration['identity_manifest'], configuration['identity_sha256'])
    caps = LazyPullbackCapStore(storage/'live_pullback_caps_v1.sqlite3', clock=lambda: clock().isoformat(),
                               max_history_rows=10000, max_history_bytes=128*1024*1024)
    provider = StrategyAccountEvidenceProvider(root=root,
        manifest_path=configuration['training_manifest'], manifest_sha256=configuration['training_sha256'],
        training_closed_at=configuration['training_closed_at'],
        market_capture=StrategyAccountMarketCapture(identity_resolver=identity, clock=clock,
            max_mark_age=SELECTION_VALUATION_MAX_AGE_SECONDS),
        action_capture=StrategyAccountActionCapture(clock=clock),
        limits_builder=partial(build_execution_limits, cap_store=caps),
        output_root=storage/'evidence', runtime_pins=configuration['runtime_pins'], clock=clock)

    def admitted_selection(state):
        now = clock()
        require(isinstance(now, datetime) and now.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
        require(now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m') == configuration['target_month'],
                'CURRENT_MONTH_TRAINING_DEPLOYMENT_REQUIRED')
        return provider.selection(state)

    selection = StrategyAccountTargetService(store=ScopedAccountStore(storage/'real_strategy.sqlite3', clock=clock),
        evidence_provider=admitted_selection, runtime_root=root, runtime_pins=configuration['runtime_pins'],
        maximum_mark_age_seconds=SELECTION_VALUATION_MAX_AGE_SECONDS, execution_fee_bps='0', clock=clock)
    selection._pins()
    # Every explicitly composed module must be the executing source as well as
    # the reviewed deployment file. This is not a full import-closure certificate.
    from hashlib import sha256
    executing_root = Path(__file__).resolve().parents[1]
    for name in RUNTIME_PATHS:
        require(sha256((executing_root/name).read_bytes()).hexdigest() == configuration['runtime_pins'][name],
                'EXECUTING_COMPOSITION_SOURCE_CHANGED')
    monthly = StrategyMonthlyTargetService(selection_service=selection,
        target_store=StrategyMonthlyTargetStore(storage/'monthly_targets.sqlite3'),
        execution_provider=provider.execution, clock=clock)
    def valuation(state):
        selection._pins()
        current=selection.store.read()
        require(current is not None and current['revision']==state['revision'],'STALE_REVISION')
        marks=provider.valuation(deepcopy(state))
        selection._pins()
        require(selection.store.read()['revision']==state['revision'],'STALE_REVISION')
        return marks
    monthly.valuation=valuation
    return monthly
