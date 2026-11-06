"""Isolated classification sidecar. Does not write the account journal."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from .validation import validate_classification


class ClassificationService:
    """read_accounts returns trusted (baseline,current); caller owns account lock.

    account_operation must hold the SAME serialization boundary as every account
    write until this sidecar transaction commits. A revision reread alone is not
    atomic across two databases. No default unlocked production path is supplied.
    """
    def __init__(self, *, path, account_id, read_accounts, account_operation, receipt_resolver, performance_baseline_at, clock=None):
        self.path=Path(path);self.account_id=account_id;self.read_accounts=read_accounts
        self.receipt_resolver=receipt_resolver;self.performance_baseline_at=performance_baseline_at
        self.account_operation=account_operation;self.clock=clock or (lambda:datetime.now(timezone.utc))
    def initialize(self):
        # Explicit isolated setup, never implicit while servicing a save/read.
        with self.path.open('xb'):pass
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('CREATE TABLE classifications(account_id TEXT NOT NULL,cash_event_id TEXT NOT NULL,payload TEXT NOT NULL,recorded_at TEXT NOT NULL,saved_revision TEXT NOT NULL,PRIMARY KEY(account_id,cash_event_id))')
            con.execute('CREATE TABLE classification_history(sequence INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL,cash_event_id TEXT NOT NULL,payload TEXT NOT NULL,document_sha256 TEXT NOT NULL,recorded_at TEXT NOT NULL,saved_revision TEXT NOT NULL)')
            con.commit()
    def read(self, cash_event_id, *, expected_revision):
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
            row=con.execute('SELECT payload,recorded_at FROM classifications WHERE account_id=? AND cash_event_id=?',(self.account_id,cash_event_id)).fetchone()
        with self.account_operation():
            _,current=self.read_accounts()
            if current['account_id']!=self.account_id or current['revision']!=expected_revision:raise ValueError('STALE_REVISION')
        return None if row is None else dict(document=json.loads(row[0]),document_sha256=sha256(row[0].encode()).hexdigest(),recorded_at=row[1],recorded_at_scope='CLASSIFICATION_RECORDING_TIME_NOT_FLOW_TIME',requires_current_evidence_validation=True,performance_ready=False)
    def save(self, *, expected_revision, document, expected_document_sha256=None):
        document=deepcopy(document)
        if document.get('account_id')!=self.account_id:raise ValueError('ACCOUNT_MISMATCH')
        with self.account_operation():
            baseline,current=self.read_accounts()
            if baseline['account_id']!=self.account_id or current['account_id']!=self.account_id:raise ValueError('ACCOUNT_MISMATCH')
            if current['revision']!=expected_revision:raise ValueError('STALE_REVISION')
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=10)) as con:
                con.execute('BEGIN IMMEDIATE')
                try:
                    row=con.execute('SELECT payload FROM classifications WHERE account_id=? AND cash_event_id=?',(self.account_id,document['cash_event_id'])).fetchone()
                    old=json.loads(row[0]) if row else None
                    old_hash=sha256(row[0].encode()).hexdigest() if row else None
                    if expected_document_sha256 is not None and expected_document_sha256!=old_hash:
                        known=con.execute('SELECT 1 FROM classification_history WHERE account_id=? AND cash_event_id=? AND document_sha256=?',(self.account_id,document['cash_event_id'],expected_document_sha256)).fetchone()
                        if old!=document or known is None:raise ValueError('STALE_CLASSIFICATION_DOCUMENT')
                    replacing=old is not None and old!=document
                    if replacing and expected_document_sha256 is None:raise ValueError('CASH_EVENT_CLASSIFICATION_CONFLICT')
                    result=validate_classification(baseline=baseline,current=current,document=document,now=self.clock(),existing=old if not replacing else None)
                    received=self.receipt_resolver(self.account_id,document['cash_event_id'])
                    if received is None or received.utcoffset() is None:raise ValueError('TRUSTED_CONFIRMATION_RECEIPT_REQUIRED')
                    if self.performance_baseline_at.utcoffset() is None:raise ValueError('AWARE_BASELINE_REQUIRED')
                    times=[datetime.fromisoformat(item['effective_at']) for item in document['items']]
                    if any(at>received for at in times):raise ValueError('FLOW_AFTER_CASH_CONFIRMATION')
                    if any(at<self.performance_baseline_at for at in times):
                        result.update(performance_blocked=True,performance_reason='PRE_BASELINE_FACT_RECONCILIATION_REQUIRED',net_external_flow=None)
                    raw=json.dumps(document,sort_keys=True,separators=(',',':'));recorded=self.clock().isoformat()
                    if replacing:
                        con.execute('UPDATE classifications SET payload=?,recorded_at=?,saved_revision=? WHERE account_id=? AND cash_event_id=?',(raw,recorded,current['revision'],self.account_id,document['cash_event_id']))
                    if not row:
                        con.execute('INSERT INTO classifications VALUES(?,?,?,?,?)',(self.account_id,document['cash_event_id'],json.dumps(document,sort_keys=True,separators=(',',':')),self.clock().isoformat(),current['revision']))
                    if not row or replacing:
                        con.execute('INSERT INTO classification_history(account_id,cash_event_id,payload,document_sha256,recorded_at,saved_revision) VALUES(?,?,?,?,?,?)',(self.account_id,document['cash_event_id'],raw,sha256(raw.encode()).hexdigest(),recorded,current['revision']))
                    baseline_after,current_after=self.read_accounts()
                    if baseline_after!=baseline or current_after!=current:raise ValueError('ACCOUNT_CHANGED_DURING_CLASSIFICATION')
                    con.commit()
                except BaseException:
                    con.rollback();raise
            return dict(result,status='REVISED_CLASSIFICATION' if replacing else result['status'],document_sha256=sha256(raw.encode()).hexdigest(),persisted=True,account_revision=current['revision'],account_mutated=False)
