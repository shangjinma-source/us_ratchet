"""Read-only identified external capital; not an allocation or trading permission."""
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from core.broker_transfer_cash_reconciliation import reconcile_transfer_cash
from data.roa_cash_flow.validation import validate_classification


def identify_external_capital(*, baseline, current, documents, transfer_context,
                              after_cash_event_id, now):
    """Caller supplies a locked coherent snapshot and trusted receipt timestamps.

    Cutoff is the cash confirmation already included in an allocation. This
    function never consumes money or treats a higher balance as a deposit.
    """
    reconciliation = reconcile_transfer_cash(baseline_account=baseline,
        current_account=current, now=now, **transfer_context)
    if reconciliation['unlinked_transfer_events']:
        raise ValueError('UNLINKED_TRANSFER_EVENTS')
    cash_events = [row['payload']['event_id'] for row in current['events']
                   if row['payload']['kind'] == 'CASH_CONFIRM']
    if after_cash_event_id not in cash_events:
        raise ValueError('CAPITAL_CUTOFF_REQUIRED')
    eligible = set(cash_events[cash_events.index(after_cash_event_id)+1:])
    audited = {row['cash_event_id']:row for row in reconciliation['rows']}
    if not set(documents) <= set(audited):
        raise ValueError('UNKNOWN_CLASSIFICATION_EVENT')
    items = [];net = Fraction(0)
    for cash_id,row in audited.items():
        document = documents.get(cash_id)
        if document is None:
            if Fraction(row['residual_cash_change']):
                raise ValueError('UNCLASSIFIED_CASH_CHANGE')
            continue
        result = validate_classification(baseline=baseline,current=current,
            document=document,now=now,transfer_context=transfer_context)
        if document['cash_event_id'] != cash_id:
            raise ValueError('CLASSIFICATION_EVENT_MISMATCH')
        if result['performance_blocked']:
            raise ValueError('ACCOUNT_FACT_REPAIR_REQUIRED')
        receipt_value = transfer_context['confirmation_times'][cash_id]
        receipt = datetime.fromisoformat(receipt_value) if isinstance(receipt_value,str) else receipt_value
        for item in document['items']:
            effective = datetime.fromisoformat(item['effective_at'])
            baseline_value = transfer_context['baseline_at']
            baseline_at = datetime.fromisoformat(baseline_value) if isinstance(baseline_value,str) else baseline_value
            if effective < baseline_at:
                raise ValueError('PRE_BASELINE_FACT_RECONCILIATION_REQUIRED')
            if effective > receipt:
                raise ValueError('FLOW_AFTER_CASH_CONFIRMATION')
            if cash_id not in eligible or item['kind'] not in ('DEPOSIT','WITHDRAWAL'):
                continue
            identity = [current['account_id'],cash_id,item['item_id']]
            funding_id = sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()
            items.append(dict(funding_id=funding_id,cash_event_id=cash_id,
                item_id=item['item_id'],kind=item['kind'],amount=item['amount'],
                document_sha256=result['document_sha256']))
            net += Fraction(item['amount'])
    return dict(account_id=current['account_id'],account_revision=current['revision'],
        transfer_revision=reconciliation['transfer_revision'],after_cash_event_id=after_cash_event_id,
        items=items,net_external_capital=str(net),positive_external_capital=str(max(Fraction(0),net)),
        executable=False,allocated=False,account_mutated=False,
        limitation='External-flow accounting only, not unspent cash; allocation ledger, reservations, fees and market gates still required.')
