"""Locked transfer reconciliation adapter; no account or money mutations."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Lock
from core.broker_reconciliation_store import TransferReconciliationStore
from core.broker_transfer_cash_reconciliation import reconcile_transfer_cash
from data.roa_cash_flow.audit import audit_cash_changes
from data.roa_cash_flow.profit import amount_profit


class TransferReconciliationService:
    def __init__(self, *, flow, broker_cash, path, clock):
        self.flow=flow;self.broker_cash=broker_cash;self.clock=clock
        self.profit_lock=Lock()
        self.store=TransferReconciliationStore(path=path,account_id=flow.account.account_id,
            operation=self.operation,clock=clock)

    def evidence(self, raw_account, transfers):
        baseline,old=self.flow.baseline()
        current=self.flow.account.audit_state()
        if current['revision']!=raw_account['revision']:raise ValueError('STALE_ACCOUNT_REVISION')
        audit=audit_cash_changes(baseline=old,current=current)
        receipts={}
        for row in audit['confirmations']:
            receipt=self.flow.receipt(current['account_id'],row['event_id'])
            if receipt is None or receipt.utcoffset() is None:raise ValueError('TRUSTED_CONFIRMATION_RECEIPT_REQUIRED')
            receipts[row['event_id']]=receipt.isoformat()
        return baseline,old,current,transfers,receipts,audit

    @contextmanager
    def operation(self):
        # The shared ROA lock and account DELETE-journal read lock also block
        # sanctioned fill corrections, which require an exclusive account lock.
        with self.broker_cash.snapshot() as (raw_account,transfers):
            baseline,old,current,transfers,receipts,_=self.evidence(raw_account,transfers)
            yield old,current,transfers,receipts,baseline['effective_at']

    def save(self,body):
        if type(body)is not dict or set(body)!={'event_id','expected_revision','document'}:raise ValueError('RECONCILIATION_REQUEST_FIELDS')
        return self.store.save(**body)

    def read(self, *, include_profit=False):
        with self.broker_cash.snapshot() as (raw,transfers):
            evidence=self.evidence(raw,transfers)
            record=self.store.read();legacy=self.flow.records()
        baseline,old,current,transfers,receipts,audit=evidence
        result=dict(status='RECONCILIATION_REQUIRED',account_id=current['account_id'],account_revision=current['revision'],
            transfer_revision=transfers['revision'],reconciliation_revision=record['revision'],
            document=record['document'],confirmations=audit['confirmations'],
            transfer_events=transfers['events'],confirmation_times=receipts,
            reconciliation=None,profit=None,profit_valid_until=None,account_mutated=False)
        document=record['document']
        if document is not None:
            if document['account_revision']!=current['revision'] or document['transfer_revision']!=transfers['revision']:
                result['status']='STALE_RECONCILIATION'
            else:
                now=self.clock()
                result['reconciliation']=reconcile_transfer_cash(
                    transfer_state=transfers,expected_transfer_revision=transfers['revision'],
                    baseline_account=old,current_account=current,baseline_at=baseline['effective_at'],
                    valued_at=now,now=now,links=document['links'],confirmation_times=receipts)
                result['status']='SAVED_REQUIRES_VALUATION'
            if result['status']=='SAVED_REQUIRES_VALUATION' and include_profit:
                classifications=dict(legacy)
                for key,value in document['classifications'].items():
                    if key in classifications and classifications[key]!=value:raise ValueError('CLASSIFICATION_SOURCE_CONFLICT')
                    classifications[key]=value
                value=self.flow.account.valuation()
                result['profit']=amount_profit(baseline=baseline,baseline_account=old,current_account=current,
                    valuation=value,classifications=classifications,now=self.clock(),transfer_context=dict(
                        transfer_state=transfers,expected_transfer_revision=transfers['revision'],
                        links=document['links'],confirmation_times=receipts))
                result['status']='AMOUNT_ONLY_RECONCILED'
                times=[datetime.fromisoformat(value['valued_at'])]+[
                    datetime.fromisoformat(row['observed_at'].replace('Z','+00:00'))
                    for row in value['holdings']]
                result['profit_valid_until']=(min(times)+timedelta(seconds=120)).isoformat()
        # Network valuation must not hold locks. Revalidate all evidence after it.
        with self.broker_cash.snapshot() as (raw_after,transfers_after):
            if self.evidence(raw_after,transfers_after)!=evidence or self.store.read()!=record or self.flow.records()!=legacy:
                raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
        if result['profit_valid_until'] is not None and datetime.fromisoformat(result['profit_valid_until'])<=self.clock():
            raise ValueError('VALUATION_TIME_INVALID')
        return result

    def profit(self):
        if not self.profit_lock.acquire(blocking=False):raise ValueError('VALUATION_ALREADY_RUNNING')
        try:return self.read(include_profit=True)
        finally:self.profit_lock.release()
