"""Unmounted split-aware read-only bridge from the scoped real ledger to account differences.

Quotes, identities, corporate actions and targets must be verified by the owning
server provider. This adapter does not convert a cash-only research snapshot
into an account target or treat a research price as a live quote.
"""
from core.strategy_account_split_v1 import replay, moment
from core.strategy_account_difference import build_strategy_difference


def preview_scoped_account(*, state, legacy_shares, marks, limits,
                           target_quantities, now, maximum_mark_age_seconds,
                           fee_bps):
    reconstructed = replay(state['account_id'],
                           [record['payload'] for record in state['events']])
    if reconstructed != state:
        raise ValueError('ACCOUNT_REPLAY_MISMATCH')
    if not state['cash_confirmation_valid']:
        raise ValueError('CASH_RECONFIRMATION_REQUIRED')
    if not state['execution_ready']:
        raise ValueError('ACCOUNT_RESERVATIONS_REQUIRE_RECONCILIATION')
    latest = {row['payload']['security_id']: row['payload'] for row in state['events']
              if row['payload']['kind'] == 'SPLIT_CONFIRMED'}
    needed = {sid for sid, quantity in state['shares'].items() if quantity} | {sid for sid, quantity in target_quantities.items() if quantity}
    needed |= {order['security_id'] for order in state['orders'].values() if order['status'] == 'OPEN'}
    for sid in needed & set(latest):
        action = latest[sid]
        for quotes in (marks, limits):
            quote = quotes.get(sid, {})
            if quote.get('unit_id') != action['new_unit_id']:
                raise ValueError('SPLIT_PREVIEW_UNIT_MISMATCH')
            if moment(quote['observed_at']) < moment(action['effective_at']):
                raise ValueError('SPLIT_PREVIEW_PRE_ACTION_QUOTE')
    return build_strategy_difference(
        account_id=state['account_id'], account_revision=state['revision'],
        holdings_revision=state['holdings_revision'],
        cash_confirmed_for_holdings_revision=state['cash_confirmed_for_holdings_revision'],
        # Normalize from the ledger projection, not the original manual entry.
        # Its original AVAILABLE value may predate a cancellation or new order.
        cash_balance=state['total_uninvested_cash'], cash_basis='TOTAL_UNINVESTED',
        strategy_shares=state['shares'], legacy_shares=legacy_shares,
        pending_orders=[order for order in state['orders'].values() if order['status']=='OPEN'],
        marks=marks, limits=limits, target_quantities=target_quantities,
        now=now, maximum_mark_age_seconds=maximum_mark_age_seconds, fee_bps=fee_bps)
