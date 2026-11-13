"""Explicit transfer-to-cash reconciliation; never infer links or mutate money."""
from datetime import datetime
from fractions import Fraction

from core.broker_internal_transfers import create_transfers, apply_transfer_event
from data.roa_cash_flow.audit import audit_cash_changes


def _instant(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.utcoffset() is None:
        raise ValueError('AWARE_TRANSFER_TIME_REQUIRED')
    return result


def reconcile_transfer_cash(*, transfer_state, expected_transfer_revision,
                            baseline_account, current_account, baseline_at,
                            valued_at, now, links, confirmation_times):
    """Links are explicit user-confirmed cash-event -> transfer-event IDs.

    confirmation_times must come from trusted journal receipt timestamps, not
    caller-entered dates. Residual differences still require separate evidence.
    Asset adjustments are in-transit principal only; fees already reduced cash.
    """
    now, start, end = map(_instant, (now, baseline_at, valued_at))
    if not start <= end <= now:
        raise ValueError('TRANSFER_RECONCILIATION_TIME_INVALID')
    account_id = current_account['account_id']
    if transfer_state['account_id'] != account_id:
        raise ValueError('TRANSFER_ACCOUNT_MISMATCH')
    if expected_transfer_revision != transfer_state['revision']:
        raise ValueError('STALE_TRANSFER_REVISION')
    rebuilt = create_transfers(account_id)
    for event in transfer_state['events']:
        rebuilt = apply_transfer_event(rebuilt, event,
            expected_revision=rebuilt['revision'], now=now)
    if rebuilt != transfer_state:
        raise ValueError('TRANSFER_STATE_INTEGRITY')
    audit = audit_cash_changes(baseline=baseline_account, current=current_account)
    rows = {row['event_id']: row for row in audit['confirmations']}
    if type(links) is not dict or not set(links) <= set(rows):
        raise ValueError('UNKNOWN_TRANSFER_CASH_CONFIRMATION')
    events = {event['event_id']: event for event in transfer_state['events']}

    def pending(at):
        total = Fraction(0)
        for event in events.values():
            if _instant(event['occurred_at']) <= at:
                total += (Fraction(event['principal']) if event['kind'] == 'SENT'
                          else -Fraction(event['amount']))
        return total

    used = set()
    reconciled = []
    previous_confirmation = start
    for cash_id, row in rows.items():
        if cash_id not in confirmation_times:
            raise ValueError('TRUSTED_CONFIRMATION_RECEIPT_REQUIRED')
        receipt = _instant(confirmation_times[cash_id])
        if not previous_confirmation <= receipt <= end:
            raise ValueError('CASH_CONFIRMATION_TIME_INVALID')
        selected = links.get(cash_id, [])
        if type(selected) is not list or any(type(key) is not str for key in selected):
            raise ValueError('TRANSFER_LINK_LIST_REQUIRED')
        change = Fraction(0)
        fees = Fraction(0)
        for event_id in selected:
            if event_id in used:
                raise ValueError('TRANSFER_EVENT_ALREADY_LINKED')
            if event_id not in events:
                raise ValueError('UNKNOWN_TRANSFER_EVENT')
            event = events[event_id]
            if not previous_confirmation < _instant(event['occurred_at']) <= receipt:
                raise ValueError('TRANSFER_OUTSIDE_CASH_CONFIRMATION_INTERVAL')
            used.add(event_id)
            if event['kind'] == 'SENT':
                fee = Fraction(event['fee'])
                change -= Fraction(event['principal']) + fee
                fees += fee
            else:
                change += Fraction(event['amount'])
        residual = Fraction(row['unexplained_net_change']) - change
        reconciled.append(dict(cash_event_id=cash_id, transfer_event_ids=list(selected),
            transfer_cash_change=str(change), confirmed_transfer_fees=str(fees),
            residual_cash_change=str(residual)))
        previous_confirmation = receipt
    required = {key for key, event in events.items()
                if start < _instant(event['occurred_at']) <= end}
    missing = sorted(required - used)
    residuals = any(Fraction(row['residual_cash_change']) for row in reconciled)
    return dict(status='TRANSFER_CASH_RECONCILED' if not missing and not residuals
                else 'TRANSFER_CASH_RECONCILIATION_REQUIRED',
        account_id=account_id, account_revision=current_account['revision'],
        transfer_revision=transfer_state['revision'], rows=reconciled,
        unlinked_transfer_events=missing, initial_in_transit=str(pending(start)),
        current_in_transit=str(pending(end)),
        asset_adjustment_change=str(pending(end)-pending(start)),
        external_capital_flow='0', fees_already_in_cash=True,
        account_mutated=False, buying_power_updated=False,
        limitation='No return or spendable balance computed. Links require explicit confirmation; residuals remain unresolved.')
