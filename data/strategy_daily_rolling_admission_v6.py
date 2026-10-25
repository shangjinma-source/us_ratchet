"""Target-bound operation admission; never caches a monthly execution provider."""
from copy import copy
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_action_capture_v5 import StrategyAccountActionCaptureV5
from core.strategy_account_ledger import require
from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from data.strategy_account_monthly_release import validate_account_identity_coverage
from data.strategy_daily_composition_v3 import DailyCompositionV3


class RollingDailyAdmissionV6:
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
            actions = provider.actions
            provider.actions = StrategyAccountActionCaptureV5(fetch=actions.fetch,
                rss_fetch=actions.rss_fetch, clock=actions.clock, max_workers=actions.workers)
            service = DailyCompositionV3(monthly_service=self.monthly, evidence_reader=self.reader,
                execution_provider=provider.execution, fee_bps=runtime.selection.fees,
                clock=self.clock, policy_execution_enabled=self.enabled, policy_id=self.policy_id)
            result = service.preview(expected_revision=expected_revision, target_id=target_id)
            self.validate_code()
            return result
