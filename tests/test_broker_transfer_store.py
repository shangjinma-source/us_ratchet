import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing
from core.broker_transfer_store import TransferStore
from core.broker_internal_transfers import project_transfers


class TransferStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'test-transfers.sqlite3'
        self.clock = lambda: datetime(2026,11,15,tzinfo=timezone.utc)
        self.store = TransferStore(self.path,'test-account',self.clock)
        self.event = dict(event_id='send', transfer_id='t', kind='SENT',
            source='HSBC',destination='USMART',principal='600',fee='5',
            occurred_at='2026-11-14T00:00:00+08:00')

    def test_restart_retry_and_account_isolation(self):
        old = self.store.read()['revision']
        saved = self.store.append(self.event,expected_revision=old)
        restarted = TransferStore(self.path,'test-account',self.clock)
        self.assertEqual(restarted.read(),saved)
        self.assertEqual(restarted.append(self.event,expected_revision=old),saved)
        self.assertEqual(len(restarted.read()['events']),1)
        self.assertEqual(TransferStore(self.path,'another-account',self.clock).read()['events'],[])

    def test_failed_receipt_does_not_persist(self):
        saved = self.store.append(self.event,expected_revision=self.store.read()['revision'])
        receipt=dict(event_id='receipt',transfer_id='t',kind='RECEIVED',amount='601',
            occurred_at='2026-11-14T01:00:00+08:00')
        with self.assertRaises(ValueError):self.store.append(receipt,expected_revision=saved['revision'])
        self.assertEqual(self.store.read(),saved)
        receipt['amount']='600'
        result=self.store.append(receipt,expected_revision=saved['revision'])
        self.assertEqual(project_transfers(result)['in_transit_usd'],'0')

    def test_concurrent_writers_cannot_spend_one_revision_twice(self):
        revision=self.store.read()['revision']
        def write(index):
            event=dict(self.event,event_id=str(index),transfer_id=str(index))
            try:
                TransferStore(self.path,'test-account',self.clock).append(event,expected_revision=revision)
                return 'saved'
            except ValueError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,[1,2]))
        self.assertCountEqual(results,['saved','STALE_REVISION'])
        self.assertEqual(len(self.store.read()['events']),1)

    def test_tampered_stored_record_rejected(self):
        self.store.append(self.event,expected_revision=self.store.read()['revision'])
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE transfer_events SET resulting_revision='incorrect'")
            connection.commit()
        with self.assertRaisesRegex(ValueError,'STORED_TRANSFER_REVISION_MISMATCH'):self.store.read()


if __name__=='__main__':unittest.main()
