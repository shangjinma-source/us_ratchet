"""Read-only daily presentation adapter. No release or executable-policy default."""
from contextlib import nullcontext
from copy import deepcopy

from core.strategy_account_difference import require
from data.strategy_daily_preview_service import StrategyDailyPreviewService
from data.strategy_daily_execution_bridge import DailyExecutionBridge


class StrategyDailyLiveAdapter:
    def __init__(self, *, monthly_service, evidence_reader, clock, enabled=False,
                 policy_id=None, execution_provider=None, fee_bps=None):
        require(type(enabled) is bool, "DAILY_ENABLED_FLAG_REQUIRED")
        self.monthly = monthly_service
        self.evidence_reader = evidence_reader
        self.clock = clock
        self.enabled = enabled
        self.policy_id = policy_id
        self.execution_provider = execution_provider
        self.fee_bps = (fee_bps if fee_bps is not None else
                        getattr(getattr(monthly_service, "selection", None), "fees", None))

    def preview(self, *, expected_revision, target_id):
        scope = getattr(self.monthly, "snapshot_operation", nullcontext)
        with scope():
            self.monthly.validate_current_target_pins()
            state = deepcopy(self.monthly.accounts.read())
            target = deepcopy(self.monthly.current())
            require(state is not None and state["revision"] == expected_revision, "STALE_REVISION")
            require(target is not None and target["target_id"] == target_id, "STALE_TARGET")
            require(target["payload"]["account_id"] == state["account_id"], "TARGET_ACCOUNT_MISMATCH")
            if not self.enabled:
                status = "DAILY_PREVIEW_DISABLED"
            else:
                evidence = self.evidence_reader(deepcopy(state), deepcopy(target), self.clock())
                require(type(evidence) is dict and "status" in evidence, "DAILY_EVIDENCE_CONTRACT")
                status = evidence["status"]
                if evidence.get("signal") is not None:
                    require(self.policy_id is not None and callable(self.execution_provider),
                            "DAILY_EXECUTION_NOT_ADMITTED")
                    require(self.fee_bps is not None, "DAILY_FEE_CONFIGURATION_REQUIRED")
                    require(evidence["signal"]["policy_id"] == self.policy_id, "DAILY_POLICY_MISMATCH")
                    bridge = DailyExecutionBridge(base_target=target,
                        execution_provider=self.execution_provider,
                        validate_sources=self.monthly.validate_current_target_pins,
                        signal=evidence["signal"])
                    service = StrategyDailyPreviewService(account_store=self.monthly.accounts,
                        target_store=self.monthly, signal_verifier=lambda *args: deepcopy(evidence["signal"]),
                        execution_provider=bridge, policy_id=self.policy_id, clock=self.clock,
                        fee_bps=self.fee_bps, maximum_mark_age_seconds=120)
                    result = service.preview()
                    self.monthly.validate_current_target_pins()
                    require(self.monthly.accounts.read() == state, "ACCOUNT_CHANGED_DURING_PREVIEW")
                    require(self.monthly.current() == target, "TARGET_CHANGED_DURING_PREVIEW")
                    return dict(result, account_revision=state["revision"], target_id=target_id,
                                target_month=target["payload"]["target_month"],
                                execution_binding=getattr(bridge, "last_binding", None))
                require(status in {"WAIT_POLICY_RELEASE", "WAIT_SIGNAL", "WAIT_MONTHLY_TARGET", "WAIT_FRESH_SIGNAL"},
                        "DAILY_EXECUTION_NOT_ADMITTED")
            self.monthly.validate_current_target_pins()
            require(self.monthly.accounts.read() == state, "ACCOUNT_CHANGED_DURING_PREVIEW")
            require(self.monthly.current() == target, "TARGET_CHANGED_DURING_PREVIEW")
            domain = set(state["shares"]) | set(target["payload"]["target_quantities"])
            return dict(status=status, account_revision=state["revision"], target_id=target_id,
                        target_month=target["payload"]["target_month"],
                        daily_gate=dict(status=status, rows=[
                            dict(security_id=sid, action="WAIT", reason=status)
                            for sid in sorted(domain)]),
                        new_orders=[], reference_quotes={}, orders_created=False,
                        account_mutated=False, target_mutated=False)
