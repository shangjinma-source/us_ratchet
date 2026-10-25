"""Proposal-aware daily composition; explicit release wiring, no target writes.

The V7 retry and sell-only contracts are retained in separate versioned preview
helpers whose gate receives explicit proposal quantities. Bridges always receive
the unchanged original monthly target for historical source authentication.
"""
from contextlib import nullcontext
from copy import deepcopy
import time
from uuid import uuid4
from core.strategy_account_ledger import canonical
from core.strategy_account_difference import timestamp
from data.strategy_recent_minute_retry_v1 import RecentClosedMinuteUnavailable

from core.strategy_account_difference import number, require
from data.saved_frontier_preview_service_v1 import SavedFrontierPreviewService
from data.strategy_daily_execution_bridge import DailyExecutionBridge
from data.saved_frontier_zero_cash_preview_v1 import preview_zero_cash_mixed
from data.saved_frontier_buy_data_wait_preview_v1 import preview_buy_data_wait_mixed


class SavedFrontierDailyComposition:
    def __init__(self, *, monthly_service, monthly_view, evidence_reader, execution_provider, clock,
                 policy_execution_enabled=False, policy_id=None, fee_bps=None, sleep=None, monotonic=None):
        require(type(policy_execution_enabled) is bool, "DAILY_ENABLED_FLAG_REQUIRED")
        require(callable(evidence_reader), "FRONTIER_READER_REQUIRED")
        self.monthly_view = monthly_view
        self.monthly, self.reader = monthly_service, evidence_reader
        self.provider, self.clock = execution_provider, clock
        self.enabled, self.policy_id = policy_execution_enabled, policy_id
        self.fees = fee_bps
        self.sleep = time.sleep if sleep is None else sleep
        self.monotonic = time.monotonic if monotonic is None else monotonic

    def preview(self, *, expected_revision, target_id, expected_proposal_id):
        scope = getattr(self.monthly, "snapshot_operation", nullcontext)
        with scope():
            self.monthly.validate_current_target_pins()
            state, target = deepcopy(self.monthly.accounts.read()), deepcopy(self.monthly.current())
            require(state is not None and state["revision"] == expected_revision, "STALE_REVISION")
            require(target is not None and target["target_id"] == target_id, "STALE_TARGET")
            require(target["payload"]["account_id"] == state["account_id"], "TARGET_ACCOUNT_MISMATCH")

            proposal = self.monthly_view.require_proposal(target_id=target_id, expected_proposal_id=expected_proposal_id)
            require(number(self.fees) == number(proposal['payload']['fee_bps']), 'FRONTIER_FEE_MISMATCH')
            signal = None

            def unchanged():
                require(self.monthly_view.require_proposal(target_id=target_id, expected_proposal_id=expected_proposal_id) == proposal, "FRONTIER_PROPOSAL_CHANGED")
                self.monthly.validate_current_target_pins()
                require(self.monthly.accounts.read() == state, "ACCOUNT_CHANGED_DURING_PREVIEW")
                require(self.monthly.current() == target, "TARGET_CHANGED_DURING_PREVIEW")

            if not self.enabled:
                result = dict(status="DAILY_PREVIEW_DISABLED", new_orders=[], reference_quotes={})
            else:
                evidence = self.reader(deepcopy(state), deepcopy(target), self.clock(), proposal=deepcopy(proposal))
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
                    require(signal.get("proposal_id") == expected_proposal_id, "FRONTIER_SIGNAL_PROPOSAL_BINDING")
                    quantities = proposal['payload']['proposed_target_quantities']
                    effective = signal['effective_target_quantities']
                    require(set(quantities) <= set(effective), 'FRONTIER_SIGNAL_DOMAIN')
                    monthly_quantities = {sid: quantities.get(sid, 0) for sid in effective}
                    verifier = lambda *args: deepcopy(signal)
                    if number(state["available_cash"]) == 0:
                        result = preview_zero_cash_mixed(account_store=self.monthly.accounts,
                            target_store=self.monthly, signal_verifier=verifier,
                            execution_provider=self.provider,
                            validate_sources=self.monthly.validate_current_target_pins,
                            policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees, monthly_quantities=monthly_quantities)
                    else:
                        def full_preview():
                            # Each call owns a fresh bridge/directory. Captured old sources
                            # and failed.json remain untouched; the cap store is shared.
                            fresh_bridge = DailyExecutionBridge(base_target=target, execution_provider=self.provider,
                                validate_sources=self.monthly.validate_current_target_pins, signal=signal)
                            answer = SavedFrontierPreviewService(account_store=self.monthly.accounts,
                                target_store=self.monthly, signal_verifier=verifier, execution_provider=fresh_bridge,
                                policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees,
                                maximum_mark_age_seconds=120, monthly_quantities=monthly_quantities).preview()
                            answer["execution_binding"] = getattr(fresh_bridge, "last_binding", None)
                            return answer
                        recapture = None
                        try:
                            try:
                                result = full_preview()
                            except RecentClosedMinuteUnavailable as transient:
                                unchanged()
                                started, monotonic_started = self.clock(), self.monotonic()
                                require(timestamp(signal['valid_from']) <= started < timestamp(signal['valid_until']),
                                    'DAILY_SIGNAL_EXPIRED_BEFORE_RECAPTURE')
                                require(transient.evidence['account_revision']==state['revision'], 'RECAPTURE_ACCOUNT_MISMATCH')
                                recapture = dict(schema='DAILY_ONE_MINUTE_RECAPTURE_V1', attempt=1,
                                    target_id=target_id, account_revision=state['revision'],
                                    evidence_id=signal['evidence_id'], eligibility=deepcopy(transient.evidence),
                                    wait_started_at=started.isoformat(), wait_seconds=2)
                                audit_path = self.provider.__self__.output / ('minute-recapture-' + uuid4().hex + '.json')
                                with audit_path.open('xb') as stream: stream.write(canonical(recapture))
                                self.sleep(2)
                                finished, elapsed = self.clock(), self.monotonic()-monotonic_started
                                require(finished >= started and 2 <= elapsed <= 5
                                    and 2 <= (finished-started).total_seconds() <= 5, 'RECAPTURE_WAIT_CLOCK_INVALID')
                                unchanged()
                                require(timestamp(signal['valid_from']) <= finished < timestamp(signal['valid_until']),
                                    'DAILY_SIGNAL_EXPIRED_BEFORE_RECAPTURE')
                                recapture.update(wait_finished_at=finished.isoformat(), monotonic_elapsed=elapsed,
                                    audit_path=str(audit_path))
                                # Exactly one recapture. A second typed failure falls
                                # through the existing conservative WAIT/sell path.
                                result = full_preview()
                        except ValueError as error:
                            if str(error) not in {'RAW_NUMERIC_REQUIRED', 'MINUTE_GAP', 'UNEXPLAINED_NULL_MINUTE', 'RAW_NOT_MINUTE_ALIGNED', 'HALT_ACTIVE_OR_RESUME_UNCONFIRMED', 'HALT_EXECUTION_EVIDENCE_REQUIRED', 'HALT_SOURCE_CLOCK_OR_STALE', 'POST_RESUMPTION_COMPLETE_BAR_REQUIRED', 'NONCONTIGUOUS_OR_FUTURE_MINUTE', 'INCOMPLETE_SESSION_MINUTES', 'PARTIAL_NULL_MINUTE', 'ZERO_VOLUME_MINUTE_UNAVAILABLE'}:
                                raise
                            result = preview_buy_data_wait_mixed(account_store=self.monthly.accounts,
                                target_store=self.monthly, signal_verifier=verifier,
                                execution_provider=self.provider,
                                validate_sources=self.monthly.validate_current_target_pins,
                                policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees, monthly_quantities=monthly_quantities)
                            result['buy_data_failure'] = str(error)
                            for row in result.get('waiting_data', []):
                                row['data_failure'] = str(error)
                    if number(state["available_cash"]) != 0 and recapture is not None:
                        complete = dict(recapture, final_status=result['status'],
                            execution_binding=result.get('execution_binding'),
                            buy_data_failure=result.get('buy_data_failure'))
                        with audit_path.with_suffix('.complete.json').open('xb') as stream: stream.write(canonical(complete))
                        for quote in result.get('reference_quotes',{}).values():
                            require(self.clock()<timestamp(quote['reference_valid_until']), 'REQUOTE_REQUIRED')
                        result['minute_recapture'] = recapture
                    result["evidence_archive"] = evidence["evidence_archive"]
            unchanged()
            if signal is not None:
                require(timestamp(signal['valid_from']) <= self.clock() < timestamp(signal['valid_until']),
                        'DAILY_SIGNAL_EXPIRED_DURING_PREVIEW')
            for quote in result.get('reference_quotes', {}).values():
                require(self.clock() < timestamp(quote['reference_valid_until']), 'REQUOTE_REQUIRED')
            detail = result["status"]
            ready = detail in {"CONDITIONAL_PREVIEW_READY","CONDITIONAL_SELL_PREVIEW",
                               "CONDITIONAL_SELL_PREVIEW_BUYS_WAIT"}
            require(ready or not result.get("new_orders"), "WAIT_CANNOT_CONTAIN_ORDERS")
            for order in result.get('new_orders', []):
                order.update(source_target_id=target_id, proposal_id=expected_proposal_id)
            return dict(result, status="READY" if ready else "HOLD" if detail == "HOLD" else "WAIT",
                detail_status=detail, account_revision=state["revision"], target_id=target_id,
                proposal_id=expected_proposal_id,
                policy_id=self.policy_id,
                risk_monthly_targets=deepcopy(proposal['payload']['proposed_target_quantities']),
                risk_valid_from=signal.get('valid_from') if signal else None,
                risk_valid_until=signal.get('valid_until') if signal else None,
                target_month=target["payload"]["target_month"],
                reference_quotes=result.get("reference_quotes", {}) if ready else {},
                waiting_cash=result.get("waiting_cash", []),
                orders_created=False, account_mutated=False, target_mutated=False)
