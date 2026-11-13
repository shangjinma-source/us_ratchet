"""Locked transfer reconciliation adapter; no account or money mutations."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from hashlib import sha256
import json
from fractions import Fraction
from core.broker_reconciliation_store import TransferReconciliationStore
from core.broker_transfer_cash_reconciliation import reconcile_transfer_cash
from core.strategy_account_ledger import apply_event
from data.roa_cash_flow.audit import audit_cash_changes
from data.roa_cash_flow.profit import amount_profit
from data.roa_cash_flow.validation import validate_classification


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
        audit=deepcopy(audit)
        state=old;revisions={}
        for event in current['events'][len(old['events']):]:
            before=state['revision'];state,_=apply_event(state,event['payload'],expected_revision=before)
            revisions[event['payload']['event_id']]=(before,state['revision'])
        for row in audit['confirmations']:
            row['before_revision'],row['after_revision']=revisions[row['event_id']]
            row['received_at']=receipts[row['event_id']]
        result=dict(status='RECONCILIATION_REQUIRED',account_id=current['account_id'],account_revision=current['revision'],
            transfer_revision=transfers['revision'],reconciliation_revision=record['revision'],
            document=record['document'],confirmations=audit['confirmations'],
            transfer_events=transfers['events'],confirmation_times=receipts,baseline_at=baseline['effective_at'],
            reconciliation=None,profit=None,profit_valid_until=None,account_mutated=False)
        document=record['document']
        # With no transfer facts, the original cash classification workflow
        # remains usable without asking the user to create an empty association.
        if document is None and not transfers['events']:
            document=dict(account_revision=current['revision'],transfer_revision=transfers['revision'],links={},classifications={})
        classifications=dict(legacy)
        if document is not None:
            classifications.update(document['classifications'])
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
        result['classifications']=classifications
        result['classifications_sha256']=sha256(json.dumps(
            [classifications,record['revision'],transfers['revision']],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        # Network valuation must not hold locks. Revalidate all evidence after it.
        with self.broker_cash.snapshot() as (raw_after,transfers_after):
            if self.evidence(raw_after,transfers_after)!=evidence or self.store.read()!=record or self.flow.records()!=legacy:
                raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
        if result['profit_valid_until'] is not None and datetime.fromisoformat(result['profit_valid_until'])<=self.clock():
            raise ValueError('VALUATION_TIME_INVALID')
        return result

    def cash_view(self, *, include_profit=False):
        """Same front-end cash panel contract, including explicit transfer facts."""
        # No transfer facts: retain the established legacy editing behavior,
        # but reject a transfer added while its network valuation was running.
        with self.broker_cash.snapshot() as (raw,transfers):
            initial=(raw,transfers)
        if not transfers['events']:
            result=self.flow.current(include_profit=include_profit,_transfer_checked=True)
            with self.broker_cash.snapshot() as (raw_after,transfers_after):
                if (raw_after,transfers_after)!=initial:raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
            return result
        value=self.read()
        residuals={row['cash_event_id']:row for row in (value['reconciliation'] or {}).get('rows',[])}
        unresolved=[];classified=[]
        reason='TRANSFER_RECONCILIATION_REQUIRED'
        if value['status']=='SAVED_REQUIRES_VALUATION':
            reason='UNLINKED_TRANSFER_EVENTS' if value['reconciliation']['unlinked_transfer_events'] else None
        with self.broker_cash.snapshot() as (raw,transfers):
            baseline,old,current,transfers,receipts,_=self.evidence(raw,transfers)
            if current['revision']!=value['account_revision'] or transfers['revision']!=value['transfer_revision']:
                raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
            for original in value['confirmations']:
                row=dict(original)
                row['original_net_change']=row['unexplained_net_change']
                row['unexplained_net_change']=residuals.get(row['event_id'],{}).get('residual_cash_change',row['unexplained_net_change'])
                document=value['classifications'].get(row['event_id'])
                if document is not None:
                    row.update(document=document,document_sha256=sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest(),classification_state='CLASSIFIED')
                    try:
                        if value['status']!='SAVED_REQUIRES_VALUATION':raise ValueError('TRANSFER_RECONCILIATION_REQUIRED')
                        now=self.clock()
                        checked=validate_classification(baseline=old,current=current,document=document,now=now,
                            transfer_context=dict(transfer_state=transfers,expected_transfer_revision=transfers['revision'],
                                links=value['document']['links'],confirmation_times=receipts,baseline_at=baseline['effective_at'],valued_at=now))
                        if checked['performance_blocked']:raise ValueError('ACCOUNT_FACT_REPAIR_REQUIRED')
                        start=datetime.fromisoformat(baseline['effective_at']);end=datetime.fromisoformat(receipts[row['event_id']])
                        if any(not start<=datetime.fromisoformat(item['effective_at'])<=end for item in document['items']):
                            raise ValueError('FLOW_OUTSIDE_CONFIRMATION_INTERVAL')
                    except ValueError as error:
                        row['classification_state']='REPAIR_REQUIRED';reason=str(error)
                    classified.append(row)
                elif Fraction(row['unexplained_net_change']):unresolved.append(row)
        if unresolved and reason is None:reason='UNCLASSIFIED_CASH_CHANGE'
        profit=None;valid_until=None
        if reason is None:
            reason='VALUATION_PENDING'
            if include_profit:
                fresh=self.profit()
                if any(fresh[key]!=value[key] for key in ('account_revision','transfer_revision','reconciliation_revision','classifications_sha256')):
                    raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
                profit=fresh['profit'];valid_until=fresh['profit_valid_until'];reason=None
        if self.read()!=value:raise ValueError('STALE_PERFORMANCE_SNAPSHOT')
        if valid_until is not None and datetime.fromisoformat(valid_until)<=self.clock():
            raise ValueError('VALUATION_TIME_INVALID')
        return dict(account_id=value['account_id'],revision=value['account_revision'],
            classifications_sha256=value['classifications_sha256'],unresolved=unresolved,classified=classified,
            profit=profit,profit_valid_until=valid_until,performance_reason=reason,
            transfer_review=value,account_mutated=False,return_fraction=None,maximum_drawdown_fraction=None)

    def profit(self):
        if not self.profit_lock.acquire(blocking=False):raise ValueError('VALUATION_ALREADY_RUNNING')
        try:return self.read(include_profit=True)
        finally:self.profit_lock.release()
