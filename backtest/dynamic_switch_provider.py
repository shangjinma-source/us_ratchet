"""Causal adapter for first-version dynamic signals in the next-open book.

Research only. Inherits that book's immediate modeled sale proceeds; never use
this adapter for live orders. Input builder must authenticate daily evidence.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from data.dynamic_switch_decision import decide_dynamic_switch
from backtest.dynamic_risk_units import reviewed_split_schedule, migrate_risk_splits
from backtest.dynamic_reentry_journal import advance_journal, comparison_journal
from backtest.dynamic_post_close_snapshot import decision_snapshot


def build_dynamic_provider(input_builder, *, authorized_risk_reset_dates=(), reviewed_risk_splits=(),
                           nontradable_policy='REJECT', reentry_policy='MONTHLY_ONLY',
                           reviewed_post_close_distributions=()):
    """Reset dates come from a separately reviewed, frozen monthly schedule."""
    reset_dates = tuple(authorized_risk_reset_dates)
    risk_splits = reviewed_split_schedule(reviewed_risk_splits)
    post_close_events = deepcopy(list(reviewed_post_close_distributions))
    if nontradable_policy not in ('REJECT', 'SELECT_TRADABLE_REPORT_TOTAL'):
        raise ValueError('EXPLICIT_NONTRADABLE_POLICY_REQUIRED')
    if reentry_policy not in ('MONTHLY_ONLY', 'LATER_CLOSE'):
        raise ValueError('FIXED_REENTRY_POLICY_REQUIRED')
    if list(reset_dates) != sorted(set(reset_dates)) or any(date.fromisoformat(day).isoformat() != day for day in reset_dates):
        raise ValueError('ORDERED_REVIEWED_RISK_RESET_DATES_REQUIRED')
    risk_state = None
    previous_day = None
    audit = []
    journal = dict(orders={}, seen_fills={}, exits={}, entries=[])

    def provider(*, decision_date, active_date, state):
        nonlocal risk_state, previous_day, journal
        if state['asof'] != decision_date or active_date <= decision_date:
            raise ValueError('DYNAMIC_CAUSAL_DATES_REQUIRED')
        if previous_day is not None and decision_date <= previous_day:
            raise ValueError('DYNAMIC_SESSION_MUST_ADVANCE')
        actual_state = state
        post_close_ids = []
        if state.get('pending_post_close_coordinates'):
            if nontradable_policy != 'SELECT_TRADABLE_REPORT_TOTAL':
                raise ValueError('DYNAMIC_UNSETTLED_ACTION_NOT_SUPPORTED')
            state, post_close_ids = decision_snapshot(state, decision_date=decision_date,
                                                      reviewed_events=post_close_events)
        pending = bool(state.get('merger_entitlements') or state.get('distribution_rights')
                       or Fraction(state.get('receivable', '0')))
        excluded_value = Fraction(0)
        close_ledger = None
        if pending:
            if nontradable_policy != 'SELECT_TRADABLE_REPORT_TOTAL':
                raise ValueError('DYNAMIC_UNSETTLED_ACTION_NOT_SUPPORTED')
            ledger = state.get('daily_ledger', [])
            if not ledger or ledger[-1]['date'] != decision_date:
                raise ValueError('CURRENT_ENTITLEMENT_VALUATION_REQUIRED')
            close_ledger = ledger[-1]
            for key, empty in (('cash', '0'), ('shares', {}), ('receivable', '0'),
                               ('distribution_rights', []), ('merger_entitlements', [])):
                if close_ledger.get(key, empty) != state.get(key, empty):
                    raise ValueError('ENTITLEMENT_ACCOUNT_SNAPSHOT_MISMATCH')
            amounts = [Fraction(close_ledger[key]) for key in
                       ('receivable', 'distribution_entitlement_value', 'nontradable_entitlement_value')]
            if any(value < 0 for value in amounts):
                raise ValueError('INVALID_ENTITLEMENT_VALUATION')
            excluded_value = sum(amounts, Fraction(0))
            if Fraction(close_ledger['equity']) != (Fraction(state['cash'])
                    + Fraction(close_ledger['stock_value']) + excluded_value):
                raise ValueError('ENTITLEMENT_EQUITY_RECONCILIATION_FAILED')
        revision = sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        inputs = input_builder(decision_date=decision_date, state=deepcopy(state),
                               prior_risk_state=deepcopy(risk_state))
        if inputs['history_inputs']['signal_date'] != decision_date:
            raise ValueError('DYNAMIC_INPUT_DATE_MISMATCH')
        if {'cash', 'holdings', 'prior_risk_state', 'account_revision', 'pending_orders',
            'eligible_reentries', 'executed_reentries'} & set(inputs):
            raise ValueError('DYNAMIC_ACCOUNT_OVERRIDE_FORBIDDEN')
        anchor = inputs['history_inputs']['base_target']['monthly_decision_date']
        resetting = risk_state is not None and anchor != risk_state['decision_date']
        if resetting and (decision_date not in reset_dates or anchor != decision_date):
            raise ValueError('UNAUTHORIZED_DYNAMIC_RISK_RESET')
        if risk_state is not None and decision_date in reset_dates and anchor != decision_date:
            raise ValueError('SCHEDULED_RISK_RESET_NOT_APPLIED')
        migrated_risk, migrated_events = migrate_risk_splits(
            None if resetting else risk_state, through_date=decision_date, events=risk_splits)
        terminated = set(state.get('terminated_security_ids', []))
        if any(state['shares'].get(sid, 0) for sid in terminated):
            raise ValueError('TERMINATED_SECURITY_STILL_HAS_SHARES')
        if any(inputs['candidate'].get(sid, 0) for sid in terminated):
            raise ValueError('TERMINATED_SECURITY_CANNOT_BE_SELECTED')
        # Keep the original account in the audit. Zero predecessor rows are
        # bookkeeping tombstones, not holdings requiring a current market price.
        holdings = {sid: quantity for sid, quantity in state['shares'].items()
                    if sid not in terminated}
        updated_journal = journal
        reentry_inputs = {}
        if reentry_policy == 'LATER_CLOSE':
            updated_journal = advance_journal(journal, state=state, decision_date=decision_date, events=risk_splits)
            reentry_inputs = comparison_journal(updated_journal, anchor=anchor, decision_date=decision_date,
                                                holdings=holdings, events=risk_splits)
        signal = decide_dynamic_switch(account_revision=revision, pending_orders=[],
            cash=state['cash'], holdings=holdings, prior_risk_state=migrated_risk, **reentry_inputs, **inputs)
        tradable_equity = Fraction(signal['comparison']['candidate_comparison']['equity'])
        if close_ledger is not None and tradable_equity + excluded_value != Fraction(close_ledger['equity']):
            raise ValueError('TRADABLE_MARKS_DISAGREE_WITH_ACCOUNT_VALUATION')
        orders = [dict(id='dynamic:' + decision_date + ':' + row['security_id'],
                       decision_date=decision_date, active_date=active_date,
                       decision_mark=inputs['prices'][row['security_id']], **row)
                  for row in signal['target_differences']]
        risk_state = deepcopy(signal['comparison']['risk_state'])
        if reentry_policy == 'LATER_CLOSE':
            for order in orders:
                sid = order['security_id']
                # An old-epoch risk sell may fill on the new monthly anchor.
                # Only a currently latched candidate is a true reentry; an
                # ordinary buy must not later attempt to release a stale latch.
                updated_journal['orders'][order['id']] = dict(order,
                    unit_id=risk_state['unit_ids'][sid],
                    risk_exit=order['side'] == 'SELL' and sid in risk_state['exited'],
                    reentry_exit_date=reentry_inputs['eligible_reentries'].get(sid)
                        if (order['side'] == 'BUY'
                            and sid in signal['comparison']['reentry_candidates']) else None)
            journal = updated_journal
        previous_day = decision_date
        audit.append(dict(input_account=deepcopy(actual_state), decision_account=deepcopy(state),
                          post_close_events_replayed=post_close_ids, signal=deepcopy(signal),
                          risk_unit_events_applied=migrated_events,
                          reentry_policy=reentry_policy, reentry_execution_inputs=deepcopy(reentry_inputs),
                          capital_basis=dict(policy=nontradable_policy, tradable_equity=str(tradable_equity),
                                             nontradable_equity_excluded_from_selection=str(excluded_value)),
                          authorized_risk_reset_applied=resetting))
        return dict(status='READY', orders=orders, research_only=True)

    return provider, audit
