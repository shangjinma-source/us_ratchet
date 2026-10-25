"""Target-bound operation admission; never caches a monthly execution provider."""
from core.strategy_account_ledger import require
from data.strategy_account_monthly_release import validate_account_identity_coverage
from data.strategy_daily_composition_v3 import DailyCompositionV3


class RollingDailyAdmissionV3:
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
            service = DailyCompositionV3(monthly_service=self.monthly, evidence_reader=self.reader,
                execution_provider=runtime.execution_provider, fee_bps=runtime.selection.fees,
                clock=self.clock, policy_execution_enabled=self.enabled, policy_id=self.policy_id)
            result = service.preview(expected_revision=expected_revision, target_id=target_id)
            self.validate_code()
            return result
