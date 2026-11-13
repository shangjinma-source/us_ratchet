"""Atomic sidecar for explicit transfer links and residual classifications.

The supplied operation must lock account, transfer and correction evidence until
commit. It yields trusted snapshots and journal receipt timestamps. No unlocked
production adapter is provided here; the main account is never written.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
from datetime import datetime
from core.broker_transfer_cash_reconciliation import reconcile_transfer_cash
from data.roa_cash_flow.validation import validate_classification


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def revision(value):
    return sha256(encoded(value).encode()).hexdigest()


class TransferReconciliationStore:
    def __init__(self, *, path, account_id, operation, clock):
        self.path=Path(path)
        self.account_id=account_id
        self.operation=operation
        self.clock=clock

    def initialize(self):
        with self.path.open('xb'):pass
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('CREATE TABLE reconciliation_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,result_revision TEXT NOT NULL,recorded_at TEXT NOT NULL)')
            connection.commit()

    def _read(self,connection):
        events=[]
        for event_id,payload,saved_revision,recorded_at in connection.execute('SELECT event_id,payload,result_revision,recorded_at FROM reconciliation_events ORDER BY sequence'):
            document=json.loads(payload)
            if document['account_id']!=self.account_id:raise ValueError('ACCOUNT_MISMATCH')
            events.append(dict(event_id=event_id,document=document,recorded_at=recorded_at))
            if revision(events)!=saved_revision:raise ValueError('RECONCILIATION_HISTORY_INVALID')
        return dict(events=events,revision=revision(events),
                    document=events[-1]['document'] if events else None,
                    requires_current_evidence_validation=True,account_mutated=False)

    def read(self):
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
            return self._read(connection)

    def save(self, *, event_id, expected_revision, document):
        document=deepcopy(document)
        if type(event_id)is not str or not event_id.strip():raise ValueError('EVENT_ID_REQUIRED')
        fields={'schema','account_id','account_revision','transfer_revision','links','classifications'}
        if type(document)is not dict or set(document)!=fields or document['schema']!='TRANSFER_RECONCILIATION_V1':raise ValueError('RECONCILIATION_FIELDS')
        if document['account_id']!=self.account_id:raise ValueError('ACCOUNT_MISMATCH')
        if type(document['classifications'])is not dict:raise ValueError('CLASSIFICATIONS_REQUIRED')
        with self.operation() as evidence:
            baseline,current,transfers,receipts,baseline_at=evidence
            if current['account_id']!=self.account_id or current['revision']!=document['account_revision']:raise ValueError('STALE_ACCOUNT_REVISION')
            if transfers['revision']!=document['transfer_revision']:raise ValueError('STALE_TRANSFER_REVISION')
            now=self.clock()
            context=dict(transfer_state=transfers,expected_transfer_revision=transfers['revision'],
                links=document['links'],confirmation_times=receipts,baseline_at=baseline_at,valued_at=now)
            reconciliation=reconcile_transfer_cash(baseline_account=baseline,current_account=current,now=now,**context)
            rows={row['cash_event_id']:row for row in reconciliation['rows']}
            if not set(document['classifications'])<=set(rows):raise ValueError('UNKNOWN_CLASSIFICATION_EVENT')
            for cash_id,classification in document['classifications'].items():
                if classification.get('cash_event_id')!=cash_id:raise ValueError('CLASSIFICATION_KEY_MISMATCH')
                result=validate_classification(baseline=baseline,current=current,document=classification,now=now,transfer_context=context)
                if result['performance_blocked']:raise ValueError('ACCOUNT_FACT_REPAIR_REQUIRED')
                receipt=datetime.fromisoformat(receipts[cash_id])
                start=datetime.fromisoformat(baseline_at) if isinstance(baseline_at,str) else baseline_at
                if any(not start<=datetime.fromisoformat(item['effective_at'])<=receipt for item in classification['items']):raise ValueError('FLOW_OUTSIDE_CONFIRMATION_INTERVAL')
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=10)) as connection:
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN IMMEDIATE')
                try:
                    state=self._read(connection)
                    previous=next((row for row in state['events'] if row['event_id']==event_id),None)
                    if previous is not None:
                        if previous['document']!=document:raise ValueError('EVENT_ID_CONFLICT')
                        connection.rollback()
                        return dict(state,status='ALREADY_RECORDED',persisted=True)
                    if state['revision']!=expected_revision:raise ValueError('STALE_RECONCILIATION_REVISION')
                    recorded=now.isoformat()
                    events=state['events']+[dict(event_id=event_id,document=document,recorded_at=recorded)]
                    connection.execute('INSERT INTO reconciliation_events(event_id,payload,result_revision,recorded_at) VALUES(?,?,?,?)',(event_id,encoded(document),revision(events),recorded))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
            return dict(status='RECORDED',revision=revision(events),persisted=True,
                account_mutated=False,requires_current_evidence_validation=True)
