# Complete isolated derivative; original source SHA256 389d5f621cfd729e01922667e8e0fb84623ea65a7b0b2ea747aae3216b68c5f1
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
from docs.candidates.strategy_split_frontier_preview_service import SavedFrontierPreviewService
from docs.candidates import strategy_split_daily_execution_bridge as full_bridge
from docs.candidates.split_saved_frontier_daily_evidence_20261105 import verify_transition_ancestry
from data.saved_frontier_zero_cash_preview_v1 import preview_zero_cash_mixed
from data.saved_frontier_buy_data_wait_preview_v1 import preview_buy_data_wait_mixed

# Reuse the original mixed-direction algorithms in private globals; no patching
# of shared production modules and no alteration of cash/proceeds semantics.
from types import FunctionType
from data import saved_frontier_zero_cash_preview_v1 as zero
from data import saved_frontier_buy_data_wait_preview_v1 as waiting
from data import strategy_daily_mixed_execution_bridge as mixed_bridge
from data import strategy_daily_buy_data_wait_bridge_v1 as wait_bridge
from docs.candidates.strategy_account_split_scoped_preview import preview_scoped_account
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider as OriginalSplitProvider
from hashlib import sha256
import json
from data.strategy_daily_session_capture import stamp
from zoneinfo import ZoneInfo

class StrategyAccountEvidenceProvider(OriginalSplitProvider):
    def __init__(self,provider,proof,state):
        self.delegate=provider;self.split_proof=deepcopy(proof)
        self.split_state_revision=state['revision']
    def __getattr__(self,name):return getattr(self.delegate,name)

    def execution(self,state,target,now=None):
        # now is interface compatibility only: all operative timestamps are server-clock reads.
        decision=target['payload']['decision'];payload=decision['payload'];binding=payload['input_binding']
        require(decision['decision_id']==sha256(canonical(payload)).hexdigest()
                and payload['input_id']==sha256(canonical(binding)).hexdigest(),'FROZEN_TARGET_CHANGED')
        require(binding['account_id']==state['account_id'],'TARGET_ACCOUNT_MISMATCH')
        require(binding['documents']['training_manifest']==self.manifest_path
                and binding['source_hashes'].get(self.manifest_path)==self.manifest_hash,'TARGET_TRAINING_BINDING_MISMATCH')
        raw=self._read(self.manifest_path,self.manifest_hash);manifest=json.loads(raw)
        historical=deepcopy(binding['historical_search_arguments'])
        require(manifest['decision_date']==historical['decision_date']==binding['training_cutoff_date']
                ==stamp(self.closed).astimezone(ZoneInfo('America/New_York')).date().isoformat(),'TARGET_TRAINING_DATE_MISMATCH')
        quantities=payload['target_quantities']
        require(decision['status']=='TARGET_READY' and type(quantities)is dict
                and set(quantities)<=set(historical['metadata']) and all(type(q)is int and q>0 for q in quantities.values()),'INVALID_FROZEN_TARGET')
        needed=set(quantities)|{sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
        from core.strategy_account_split_v1 import replay
        require(replay(state['account_id'],[r['payload'] for r in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
        require(state['cash_confirmation_valid'] and state['execution_ready'],'CASH_RECONFIRMATION_REQUIRED')
        proof=self.split_proof
        require(state['revision']==self.split_state_revision,'SPLIT_CURRENT_ACCOUNT_CHANGED')
        transition=proof['transition']
        verify_transition_ancestry(state=state,transition=transition,
            risk_before=proof['original_risk_state'],target=target,
            proposal_id=transition['payload']['original_proposal_id'])
        require(transition['payload']['original_target_id']==target['target_id'],'SPLIT_BASE_TARGET_CHANGED')
        # Old signed decision stays unchanged; current market/action/unit checks
        # remain in the same _assemble path using this separately bound proof.
        if not needed:
            stamp(self.clock().isoformat())
            return dict(marks={},limits={})
        package=dict(files={self.manifest_path:raw},source_hashes={self.manifest_path:self.manifest_hash},documents={})
        return self._assemble(state,package,historical,target_quantities=quantities,execution_only=True)


def _bind(function, **dependencies):
    bound=FunctionType(function.__code__,dict(function.__globals__,**dependencies),function.__name__,function.__defaults__,function.__closure__)
    bound.__kwdefaults__=function.__kwdefaults__
    return bound

class DailyExecutionBridge(full_bridge.DailyExecutionBridge):
    __init__=_bind(full_bridge.DailyExecutionBridge.__init__,StrategyAccountEvidenceProvider=StrategyAccountEvidenceProvider)
    __call__=_bind(full_bridge.DailyExecutionBridge.__call__,StrategyAccountEvidenceProvider=StrategyAccountEvidenceProvider)


class SplitMixedBridge(mixed_bridge.DailyMixedExecutionBridge):
    __init__=_bind(mixed_bridge.DailyMixedExecutionBridge.__init__,StrategyAccountEvidenceProvider=StrategyAccountEvidenceProvider)
    __call__=_bind(mixed_bridge.DailyMixedExecutionBridge.__call__,StrategyAccountEvidenceProvider=StrategyAccountEvidenceProvider)

class SplitWaitBridge(wait_bridge.DailyBuyDataWaitExecutionBridge):
    __init__=_bind(wait_bridge.DailyBuyDataWaitExecutionBridge.__init__,StrategyAccountEvidenceProvider=StrategyAccountEvidenceProvider)
    __call__=_bind(wait_bridge.DailyBuyDataWaitExecutionBridge.__call__,StrategyAccountEvidenceProvider=StrategyAccountEvidenceProvider)

preview_zero_cash_mixed=_bind(zero.preview_zero_cash_mixed,preview_scoped_account=preview_scoped_account,DailyMixedExecutionBridge=SplitMixedBridge)
preview_buy_data_wait_mixed=_bind(waiting.preview_buy_data_wait_mixed,preview_scoped_account=preview_scoped_account,DailyBuyDataWaitExecutionBridge=SplitWaitBridge)


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
                    transition = evidence['transition']
                    verify_transition_ancestry(state=state,transition=transition,risk_before=evidence['original_risk_state'],target=target,proposal_id=expected_proposal_id)
                    require(signal['transition_id'] == transition['transition_id'], 'DAILY_SIGNAL_TRANSITION_BINDING')
                    quantities = transition['payload']['risk_projection']['target_quantities']
                    effective = signal['effective_target_quantities']
                    require(getattr(self.provider,'__func__',None) is OriginalSplitProvider.execution,'SPLIT_ORIGINAL_PROVIDER_REQUIRED')
                    execution_provider=StrategyAccountEvidenceProvider(self.provider.__self__,evidence,state).execution
                    require(set(quantities) <= set(effective), 'FRONTIER_SIGNAL_DOMAIN')
                    monthly_quantities = {sid: quantities.get(sid, 0) for sid in effective}
                    verifier = lambda *args: deepcopy(signal)
                    if number(state["available_cash"]) == 0:
                        result = preview_zero_cash_mixed(account_store=self.monthly.accounts,
                            target_store=self.monthly, signal_verifier=verifier,
                            execution_provider=execution_provider,
                            validate_sources=self.monthly.validate_current_target_pins,
                            policy_id=self.policy_id, clock=self.clock, fee_bps=self.fees, monthly_quantities=monthly_quantities)
                    else:
                        def full_preview():
                            # Each call owns a fresh bridge/directory. Captured old sources
                            # and failed.json remain untouched; the cap store is shared.
                            fresh_bridge = DailyExecutionBridge(base_target=target, execution_provider=execution_provider,
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
                                execution_provider=execution_provider,
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
                risk_monthly_targets=deepcopy(quantities) if signal else None,
                split_transition_id=signal.get('transition_id') if signal else None,
                production_admitted=False,
                risk_valid_from=signal.get('valid_from') if signal else None,
                risk_valid_until=signal.get('valid_until') if signal else None,
                target_month=target["payload"]["target_month"],
                reference_quotes=result.get("reference_quotes", {}) if ready else {},
                waiting_cash=result.get("waiting_cash", []),
                orders_created=False, account_mutated=False, target_mutated=False)
