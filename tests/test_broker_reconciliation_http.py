import json
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_broker_transfer_profit as fixtures
from core.broker_transfer_store import TransferStore
from data.broker_cash_service import BrokerCashService
from data.broker_reconciliation_service import TransferReconciliationService
from api.broker_reconciliation import create_router

class ReconciliationHttpTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.TransferProfitTests('test_send_partial_and_complete_receipt_fee_once')
        self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.send()
        directory=Path(self.f.directory.name)
        self.transfers=TransferStore(directory/'transfers.sqlite','fixture',clock=lambda:self.f.now)
        self.transfers.append(self.f.transfers['events'][0],expected_revision=self.transfers.read()['revision'])
        def receipt(account_id,key):
            with closing(sqlite3.connect(self.f.account.store.path)) as connection:
                value=connection.execute('SELECT received_at FROM strategy_events WHERE event_id=?',(key,)).fetchone()[0]
            return datetime.fromisoformat(value)
        flow=SimpleNamespace(account=self.f.account,baseline=lambda:(self.f.baseline,self.f.old),receipt=receipt,records=lambda:{})
        cash=BrokerCashService(account_store=self.f.account.store,transfer_store=self.transfers,
            allocation_store=None,lock=RLock(),clock=lambda:self.f.now,validate_sources=lambda:None)
        self.service=TransferReconciliationService(flow=flow,broker_cash=cash,
            path=directory/'reconciliation.sqlite',clock=lambda:self.f.now)
        self.service.store.initialize()
        app=FastAPI();app.include_router(create_router(service=self.service))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.document=dict(schema='TRANSFER_RECONCILIATION_V1',account_id='fixture',
            account_revision=self.f.account.store.read()['revision'],transfer_revision=self.transfers.read()['revision'],
            links={'cash-sent':['sent']},classifications={})
        self.body=dict(event_id='confirm',expected_revision=self.service.store.read()['revision'],document=self.document)

    def test_save_read_profit_and_retry_without_account_write(self):
        before=self.f.account.audit_state()
        path='/api/strategy-account/transfer-reconciliation'
        self.assertEqual(self.client.get(path).json()['status'],'RECONCILIATION_REQUIRED')
        for _ in range(2):self.assertEqual(self.client.post(path,json=self.body).status_code,200)
        self.assertEqual(self.client.get(path).json()['document'],self.document)
        result=self.client.get(path+'/profit')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['profit']['profit_amount'],'-5')
        self.assertEqual(result.json()['account_id'],'fixture')
        self.assertEqual(result.json()['reconciliation']['rows'][0]['residual_cash_change'],'0')
        self.assertGreater(datetime.fromisoformat(result.json()['profit_valid_until']),self.f.now)
        self.assertEqual(len(self.service.store.read()['events']),1)
        self.assertEqual(self.f.account.audit_state(),before)

    def test_profit_expiring_during_final_evidence_check_is_rejected(self):
        path='/api/strategy-account/transfer-reconciliation'
        self.assertEqual(self.client.post(path,json=self.body).status_code,200)
        original=self.service.evidence
        calls=0
        def delayed(*args):
            nonlocal calls
            value=original(*args);calls+=1
            if calls==2:self.f.now+=timedelta(seconds=121)
            return value
        self.service.evidence=delayed
        result=self.client.get(path+'/profit')
        self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(result.json()['status'],'VALUATION_TIME_INVALID')

    def test_changed_transfer_during_valuation_rejects_result(self):
        path='/api/strategy-account/transfer-reconciliation'
        self.assertEqual(self.client.post(path,json=self.body).status_code,200)
        original=self.f.account.valuation
        def changed():
            value=original()
            self.transfers.append(dict(event_id='partial',transfer_id='t',kind='RECEIVED',amount='200',occurred_at=self.f.now.isoformat()),expected_revision=self.transfers.read()['revision'])
            return value
        self.f.account.valuation=changed
        result=self.client.get(path+'/profit')
        self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(result.json()['status'],'STALE_PERFORMANCE_SNAPSHOT')
        self.assertEqual(self.client.get(path).json()['status'],'STALE_RECONCILIATION')

    def test_snapshot_blocks_independent_account_and_transfer_writer(self):
        with self.service.operation():
            for path in [self.f.account.store.path,self.transfers.path]:
                connection=sqlite3.connect(path,timeout=0.05,isolation_level=None)
                try:
                    with self.assertRaises(sqlite3.OperationalError):connection.execute('BEGIN EXCLUSIVE')
                finally:connection.close()

    def test_duplicate_payload_rejected_before_write(self):
        result=self.client.post('/api/strategy-account/transfer-reconciliation',content='{"document":{},"document":{}}')
        self.assertEqual(result.status_code,422)
        self.assertEqual(self.service.store.read()['events'],[])

if __name__=='__main__':unittest.main()
