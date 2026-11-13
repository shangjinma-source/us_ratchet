from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
from threading import RLock
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.broker_cash import create_router
from core.broker_cash_allocation import BrokerCashAllocationStore
from core.broker_transfer_store import TransferStore
from core.strategy_account_store import StrategyAccountStore
from data.broker_cash_service import BrokerCashService


class BrokerCashHttpTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.now = datetime(2026, 11, 14, 4, tzinfo=timezone.utc)
        self.account = StrategyAccountStore(root/'account.db', clock=lambda: self.now)
        state = self.account.initialize('test', operation_id='initialize')
        self.account.append(dict(event_id='cash', kind='CASH_CONFIRM', amount='1000',
            cash_basis='AVAILABLE_AFTER_RESERVATIONS'), expected_revision=state['revision'])
        self.transfers = TransferStore(root/'transfers.db', 'test', clock=lambda: self.now)
        self.allocations = BrokerCashAllocationStore(root/'split.db')
        self.service = BrokerCashService(account_store=self.account, transfer_store=self.transfers,
            allocation_store=self.allocations, lock=RLock(), clock=lambda: self.now, validate_sources=lambda: None)
        app = FastAPI(); app.include_router(create_router(service=self.service))
        self.client = TestClient(app)
        self.url = '/api/strategy-account/broker-cash'
        current = self.client.get(self.url).json()
        self.document = {key: current[key] for key in ('account_id','account_revision','transfer_revision')}
        self.document['balances'] = {key: dict(available_cash=value, reserved_cash='0',
            observed_at=self.now.isoformat()) for key,value in [('HSBC','400'),('USMART','600')]}
        self.body = dict(event_id='split', document=self.document)

    def test_http_round_trip_does_not_write_account(self):
        before = self.account.path.read_bytes()
        self.assertEqual(self.client.post(self.url, json=self.body).status_code, 200)
        result = self.client.get(self.url).json()
        self.assertEqual(result['document'], self.document)
        self.assertEqual(before, self.account.path.read_bytes())
        self.assertTrue(self.client.post(self.url, json=self.body).json()['already_recorded'])

    def test_cash_change_before_save_rejects_old_body(self):
        self.account.append(dict(event_id='cash2', kind='CASH_CONFIRM', amount='900',
            cash_basis='AVAILABLE_AFTER_RESERVATIONS'), expected_revision=self.document['account_revision'])
        response = self.client.post(self.url, json=self.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['status'], 'STALE_BROKER_CASH_BINDING')

    def test_external_writers_cannot_commit_during_snapshot(self):
        with self.service.snapshot():
            for path, statement in [(self.account.path, "UPDATE strategy_meta SET revision='changed'"),
                                    (self.transfers.path, "INSERT INTO transfer_events(account_id,event_id,payload,recorded_at,resulting_revision) VALUES ('x','x','{}','x','x')")]:
                with closing(sqlite3.connect(path, timeout=0.02)) as writer:
                    writer.execute(statement)
                    with self.assertRaises(sqlite3.OperationalError):
                        writer.commit()
                    writer.rollback()
        self.assertEqual(self.client.post(self.url, json=self.body).status_code, 200)

    def test_transfer_change_invalidates_saved_split(self):
        self.assertEqual(self.client.post(self.url, json=self.body).status_code, 200)
        self.transfers.append(dict(event_id='sent',transfer_id='t',kind='SENT',source='HSBC',destination='USMART',
            principal='100',fee='0',occurred_at=self.now.isoformat()), expected_revision=self.document['transfer_revision'])
        self.assertIsNone(self.client.get(self.url).json()['balances'])

    def test_duplicate_json_and_oversized_payload_rejected(self):
        self.assertEqual(self.client.post(self.url, content='{"event_id":"a","event_id":"b"}').status_code, 422)
        self.assertEqual(self.client.post(self.url, content='x'*4097).status_code, 422)

    def test_source_change_after_commit_requires_readback(self):
        calls = []
        def gate():
            calls.append(1)
            if len(calls) == 2:
                raise ValueError('SOURCE_CHANGED')
        self.service.validate_sources = gate
        response = self.client.post(self.url, json=self.body)
        self.assertTrue(response.json()['save_requires_readback'])
        self.service.validate_sources = lambda: None
        self.assertEqual(self.client.get(self.url).json()['document'], self.document)


if __name__ == '__main__':
    unittest.main()
