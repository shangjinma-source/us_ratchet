import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.broker_internal_transfers import create_router
from core.broker_transfer_store import TransferStore


class TransferHttpTests(unittest.TestCase):
    url='/api/strategy-account/internal-transfers'

    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.store=TransferStore(Path(folder.name)/'test.sqlite3','isolated',
            clock=lambda:datetime(2026,11,15,tzinfo=timezone.utc))
        app=FastAPI();app.include_router(create_router(store=self.store))
        self.client=TestClient(app)
        self.body=dict(expected_revision=self.store.read()['revision'],event=dict(
            event_id='send',transfer_id='t',kind='SENT',source='HSBC',destination='USMART',
            principal='600',fee='5',occurred_at='2026-11-14T00:00:00+08:00'))

    def test_record_and_receive_without_cash_write(self):
        sent=self.client.post(self.url,json=self.body)
        self.assertEqual(sent.status_code,200)
        self.assertEqual(sent.json()['summary']['in_transit_usd'],'600')
        received=self.client.post(self.url,json=dict(expected_revision=sent.json()['state']['revision'],
            event=dict(event_id='receipt',transfer_id='t',kind='RECEIVED',amount='600',
                occurred_at='2026-11-14T01:00:00+08:00')))
        self.assertEqual(received.status_code,200)
        self.assertEqual(received.json()['summary']['in_transit_usd'],'0')
        for flag in ('bank_transfer_initiated','strategy_account_written','buying_power_updated'):
            self.assertFalse(received.json()[flag])

    def test_duplicate_retry_and_conflict(self):
        first=self.client.post(self.url,json=self.body).json()
        self.assertEqual(self.client.post(self.url,json=self.body).json(),first)
        self.body['event']['principal']='700'
        self.assertEqual(self.client.post(self.url,json=self.body).status_code,409)
        self.assertEqual(len(self.store.read()['events']),1)

    def test_malformed_and_oversized_requests_do_not_write(self):
        for raw in ['{"event":{},"event":{}}','x'*4097,'{"expected_revision":NaN}']:
            self.assertEqual(self.client.post(self.url,content=raw).status_code,422)
        self.assertEqual(self.store.read()['events'],[])

    def test_read_restores_saved_state(self):
        self.client.post(self.url,json=self.body)
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['state'],self.store.read())
        self.assertEqual(response.headers['cache-control'],'no-store')


if __name__=='__main__':unittest.main()
