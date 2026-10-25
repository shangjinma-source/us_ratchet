"""Isolated, server-injected daily preview orchestration; no production wiring.

signal_verifier must authenticate policy release, source bytes, complete historical
sessions and units before returning a signal (or None). It is not an HTTP field.
Execution provider receives effective_quantities, never the monthly target.
"""
from copy import deepcopy

from core.strategy_account_difference import require, timestamp
from data.strategy_account_preview import preview_scoped_account
from data.strategy_daily_target_gate import resolve_daily_target


class SavedFrontierPreviewService:
    def __init__(self, *, account_store, target_store, signal_verifier,
                 execution_provider, policy_id, clock, fee_bps,
                 maximum_mark_age_seconds, monthly_quantities):
        self.monthly_quantities = deepcopy(monthly_quantities)
        self.accounts = account_store
        self.targets = target_store
        self.signal_verifier = signal_verifier
        self.execution_provider = execution_provider
        self.policy_id = policy_id
        self.clock = clock
        self.fee_bps = fee_bps
        self.maximum_mark_age_seconds = maximum_mark_age_seconds

    def preview(self):
        state = deepcopy(self.accounts.read())
        target = deepcopy(self.targets.current())
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        if target is None:
            return dict(status='WAIT_MONTHLY_TARGET', effective_target_quantities=None,
                        new_orders=[], reference_quotes={}, orders_created=False)
        require(target['payload']['account_id'] == state['account_id'], 'TARGET_ACCOUNT_MISMATCH')
        now = self.clock().isoformat()
        signal = self.signal_verifier(deepcopy(state), deepcopy(target), timestamp(now))
        gate = resolve_daily_target(
            account_id=state['account_id'], account_revision=state['revision'],
            target_id=target['target_id'], target_month=target['payload']['target_month'],
            monthly_quantities=self.monthly_quantities,
            strategy_shares=state['shares'], available_cash=state['available_cash'],
            pending_orders=[o for o in state['orders'].values() if o['status'] == 'OPEN'],
            now=now, expected_policy_id=self.policy_id, signal=signal)

        def unchanged():
            require(self.accounts.read()['revision'] == state['revision'], 'ACCOUNT_CHANGED_DURING_PREVIEW')
            require(self.targets.current() == target, 'TARGET_CHANGED_DURING_PREVIEW')

        unchanged()
        rows = gate['rows']
        reason = gate['status']
        if reason == 'DAILY_TARGET_READY':
            if any(row['reason'] == 'PENDING_RECONCILIATION_REQUIRED' for row in rows):
                reason = 'WAIT_PENDING_RECONCILIATION'
            elif any(row['action'] == 'WAIT' for row in rows):
                # Do not ask a provider to generate a buy price for a WAIT row.
                # Mixed intents need a versioned side-specific provider contract.
                reason = 'WAIT_EXECUTION_ELIGIBILITY'
            elif all(row['action'] == 'HOLD' for row in rows):
                reason = 'HOLD'
        if reason != 'DAILY_TARGET_READY':
            return dict(status=reason, daily_gate=gate, effective_target_quantities=None,
                        new_orders=[], reference_quotes={}, orders_created=False)
        require(state['cash_confirmation_valid'], 'CASH_RECONFIRMATION_REQUIRED')
        effective = deepcopy(gate['effective_target_quantities'])
        provider_target = deepcopy(effective)
        evidence = self.execution_provider(deepcopy(state), provider_target, timestamp(now))
        require(provider_target == effective, 'EXECUTION_PROVIDER_MUTATED_TARGET')
        require(type(evidence) is dict and set(evidence) == {'marks', 'limits'},
                'EXECUTION_PROVIDER_FIELDS')
        finished = self.clock().isoformat()
        require(timestamp(finished) >= timestamp(now), 'SERVER_CLOCK_MOVED_BACKWARDS')
        # The signal may expire while market data is being captured. Do not call
        # the gate twice or regenerate a new decision mid-preview.
        require(timestamp(signal['valid_from']) <= timestamp(finished) <
                timestamp(signal['valid_until']), 'DAILY_SIGNAL_EXPIRED_DURING_PREVIEW')
        for limit in evidence['limits'].values():
            require(timestamp(finished) < timestamp(limit['reference_valid_until']),
                    'REQUOTE_REQUIRED')
        result = preview_scoped_account(
            state=state, legacy_shares={}, target_quantities=effective,
            marks=evidence['marks'], limits=evidence['limits'], now=finished,
            maximum_mark_age_seconds=self.maximum_mark_age_seconds, fee_bps=self.fee_bps)
        unchanged()
        return dict(status='CONDITIONAL_PREVIEW_READY', daily_gate=gate,
                    effective_target_quantities=effective, difference=result,
                    new_orders=result['new_orders'], reference_quotes=deepcopy(evidence['limits']),
                    orders_created=False, account_mutated=False)
