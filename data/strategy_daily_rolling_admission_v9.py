"""Target-bound operation admission; never caches a monthly execution provider."""
from copy import copy
from functools import partial
from data.strategy_halt_market_capture_v1 import HaltMarketCaptureV1
from data.strategy_halt_aware_execution_limits_v1 import build_execution_limits
from data.strategy_halt_aware_pullback_cap_store_v1 import PullbackCapStore
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_action_capture_v6 import StrategyAccountActionCaptureV6
from core.strategy_account_ledger import require
from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from data.strategy_account_monthly_release import validate_account_identity_coverage
from data.strategy_daily_composition_v5 import DailyCompositionV5


class RollingDailyAdmissionV9:
    def __init__(self, *, monthly, reader, clock, validate_code,
                 policy_execution_enabled=False, policy_id=None):
        require(type(policy_execution_enabled) is bool, "DAILY_ENABLED_FLAG_REQUIRED")
        self.monthly, self.reader, self.clock = monthly, reader, clock
        self.validate_code = validate_code
        self.enabled, self.policy_id = policy_execution_enabled, policy_id

    def preview(self, *, expected_revision, target_id):
        with self.monthly.snapshot_operation():
            self.validate_code()
            target = self.monthly.current()
            require(target is not None and target["target_id"] == target_id, "STALE_TARGET")
            state = self.monthly.accounts.read()
            require(state is not None and state["revision"] == expected_revision, "STALE_REVISION")
            # _for_target authenticates the archived configuration bound to this
            # exact target, then verifies its actual executing runtime sources.
            runtime, configuration = self.monthly._for_target(target)
            validate_account_identity_coverage(self.monthly.root, configuration, state)
            original = runtime.execution_provider
            require(getattr(original, '__func__', None) is StrategyAccountEvidenceProvider.execution,
                    'DAILY_REAL_PROVIDER_REQUIRED')
            provider = copy(original.__self__)
            market = provider.market
            provider.market = DailyMarketCaptureV3(identity_resolver=market.identity,
                fetch=market.fetch,clock=market.clock,max_workers=market.workers,max_mark_age=market.max_mark_age)
            provider.market = HaltMarketCaptureV1(provider.market, clock=self.clock)
            require(isinstance(provider.limits, partial) and 'cap_store' in provider.limits.keywords,
                    'HALT_ORIGINAL_CAP_STORE_REQUIRED')
            legacy = provider.limits.keywords['cap_store']
            require(legacy.path.is_file(), 'HALT_LEGACY_CAP_STORE_MISSING')
            caps = PullbackCapStore(legacy.path.with_name('halt_pullback_caps_v1.sqlite3'),
                legacy_path=legacy.path, clock=legacy.clock,
                max_history_rows=legacy.max_history_rows, max_history_bytes=legacy.max_history_bytes)
            provider.limits = partial(build_execution_limits, cap_store=caps)
            actions = provider.actions
            provider.actions = StrategyAccountActionCaptureV6(fetch=actions.fetch,
                rss_fetch=actions.rss_fetch, clock=actions.clock, max_workers=actions.workers)
            service = DailyCompositionV5(monthly_service=self.monthly, evidence_reader=self.reader,
                execution_provider=provider.execution, fee_bps=runtime.selection.fees,
                clock=self.clock, policy_execution_enabled=self.enabled, policy_id=self.policy_id)
            result = service.preview(expected_revision=expected_revision, target_id=target_id)
            self.validate_code()
            return result
