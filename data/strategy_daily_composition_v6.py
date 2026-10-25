"""Isolated unified daily preview composition; default disabled, no target writes."""
from contextlib import nullcontext
from copy import deepcopy

from core.strategy_account_difference import number, require
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
from data.strategy_daily_preview_service import StrategyDailyPreviewService
from data.strategy_daily_execution_bridge import DailyExecutionBridge
from data.strategy_daily_mixed_preview import preview_zero_cash_mixed
from data.strategy_daily_buy_data_wait_preview_v1 import preview_buy_data_wait_mixed


class DailyCompositionV6:
    def __init__(self, *, monthly_service, evidence_reader, execution_provider, clock,
                 policy_execution_enabled=False, policy_id=None, fee_bps=None):
        require(type(policy_execution_enabled) is bool, "DAILY_ENABLED_FLAG_REQUIRED")
        require(isinstance(evidence_reader, ArchivedRebindingDailyEvidenceReader),
                "ARCHIVED_DAILY_READER_REQUIRED")
        self.monthly, self.reader = monthly_service, evidence_reader
        self.provider, self.clock = execution_provider, clock
        self.enabled, self.policy_id = policy_execution_enabled, policy_id
        self.fees = fee_bps

    def preview(self, *, expected_revision, target_id):
        scope = getattr(self.monthly, "snapshot_operation", nullcontext)
        with scope():
            self.monthly.validate_current_target_pins()
            state, target = deepcopy(self.monthly.accounts.read()), deepcopy(self.monthly.current())
            require(state is not None and state["revision"] == expected_revision, "STALE_REVISION")
            require(target is not None and target["target_id"] == target_id, "STALE_TARGET")
            require(target["payload"]["account_id"] == state["account_id"], "TARGET_ACCOUNT_MISMATCH")

            def unchanged():
                self.monthly.validate_current_target_pins()
                require(self.monthly.accounts.read() == state, "ACCOUNT_CHANGED_DURING_PREVIEW")
                require(self.monthly.current() == target, "TARGET_CHANGED_DURING_PREVIEW")

            if not self.enabled:
                result = dict(status="DAILY_PREVIEW_DISABLED", new_orders=[], reference_quotes={})
            else:
                evidence = self.reader(deepcopy(state), deepcopy(target), self.clock())
                unchanged()
                signal = evidence.get("signal")
                if signal is None:
                    require(evidence["status"] in {"WAIT_POLICY_RELEASE","WAIT_SIGNAL",
                            "WAIT_FRESH_SIGNAL","WAIT_MONTHLY_TARGET"}, "DAILY_READER_STATUS_INVALID")
                    result = dict(status=evidence["status"], reason=evidence.get("reason"),
                                  new_orders=[], reference_quotes={})
                else:
                    require(evidence["status"] == "DAILY_SIGNAL_READY"
                            and signal.get("evidence_archive") == evidence.get("evidence_archive")
                            and bool(evidence.get("evidence_archive")), "DAILY_ARCHIVE_REQUIRED")
                    require(self.policy_id is not None and signal["policy_id"] == self.policy_id,
                            "DAILY_POLICY_MISMATCH")
                    require(self.fees is not None, "DAILY_FEE_CONFIGURATION_REQUIRED")
                    verifier = lambda *args: deepcopy(signal)
                    if number(state["available_cash"]) == 0:
                        result = preview_zero_cash_mixed(account_store=self.monthly.accounts,
                            target_store=self.monthly, signal_verifier=verifier,
                            execution_provider=self.provider,
                            validate_sources=self.monthly.validate_current_target_pins,
                            policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees)
                    else:
                        bridge = DailyExecutionBridge(base_target=target, execution_provider=self.provider,
                            validate_sources=self.monthly.validate_current_target_pins, signal=signal)
                        try:
                            result = StrategyDailyPreviewService(account_store=self.monthly.accounts,
                                target_store=self.monthly, signal_verifier=verifier, execution_provider=bridge,
                                policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees,
                                maximum_mark_age_seconds=120).preview()
                            result["execution_binding"] = getattr(bridge, "last_binding", None)
                        except ValueError as error:
                            if str(error) not in {'RAW_NUMERIC_REQUIRED', 'MINUTE_GAP', 'UNEXPLAINED_NULL_MINUTE', 'HALT_ACTIVE_OR_RESUME_UNCONFIRMED', 'HALT_EXECUTION_EVIDENCE_REQUIRED', 'HALT_SOURCE_CLOCK_OR_STALE', 'POST_RESUMPTION_COMPLETE_BAR_REQUIRED', 'NONCONTIGUOUS_OR_FUTURE_MINUTE', 'INCOMPLETE_SESSION_MINUTES', 'PARTIAL_NULL_MINUTE', 'ZERO_VOLUME_MINUTE_UNAVAILABLE'}:
                                raise
                            result = preview_buy_data_wait_mixed(account_store=self.monthly.accounts,
                                target_store=self.monthly, signal_verifier=verifier,
                                execution_provider=self.provider,
                                validate_sources=self.monthly.validate_current_target_pins,
                                policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees)
                            result['buy_data_failure'] = str(error)
                            for row in result.get('waiting_data', []):
                                row['data_failure'] = str(error)
                    result["evidence_archive"] = evidence["evidence_archive"]
            unchanged()
            detail = result["status"]
            ready = detail in {"CONDITIONAL_PREVIEW_READY","CONDITIONAL_SELL_PREVIEW",
                               "CONDITIONAL_SELL_PREVIEW_BUYS_WAIT"}
            require(ready or not result.get("new_orders"), "WAIT_CANNOT_CONTAIN_ORDERS")
            return dict(result, status="READY" if ready else "HOLD" if detail == "HOLD" else "WAIT",
                detail_status=detail, account_revision=state["revision"], target_id=target_id,
                target_month=target["payload"]["target_month"],
                reference_quotes=result.get("reference_quotes", {}) if ready else {},
                waiting_cash=result.get("waiting_cash", []),
                orders_created=False, account_mutated=False, target_mutated=False)


def create_daily_composition_v3(*, monthly_service, execution_provider, clock, root,
                               server_configuration):
    """Configuration is server-owned; no browser-provided release or source paths."""
    config = deepcopy(server_configuration)
    reader = ArchivedRebindingDailyEvidenceReader(root=root, **config["evidence"])
    return DailyCompositionV6(monthly_service=monthly_service, evidence_reader=reader,
        execution_provider=execution_provider, clock=clock,
        policy_execution_enabled=config.get("policy_execution_enabled", False),
        policy_id=config.get("policy_id"), fee_bps=config.get("fee_bps"))
