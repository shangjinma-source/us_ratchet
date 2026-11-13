import copy
import unittest
from contextlib import contextmanager
from pathlib import Path
from core.broker_reconciliation_store import TransferReconciliationStore
import test_broker_transfer_profit as fixtures

class ReconciliationStoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.TransferProfitTests('test_send_partial_and_complete_receipt_fee_once')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.send()
        @contextmanager
        def operation():
            yield (self.fixture.old,self.fixture.account.audit_state(),self.fixture.transfers,
                   self.fixture.times,self.fixture.baseline['effective_at'])
        self.arguments=dict(path=Path(self.fixture.directory.name)/'links.sqlite',account_id='fixture',
            operation=operation,clock=lambda:self.fixture.now)
        self.store=TransferReconciliationStore(**self.arguments);self.store.initialize()
        self.document=dict(schema='TRANSFER_RECONCILIATION_V1',account_id='fixture',
            account_revision=self.fixture.account.store.read()['revision'],
            transfer_revision=self.fixture.transfers['revision'],links=self.fixture.links,classifications={})

    def test_atomic_save_retry_and_restart(self):
        before=self.fixture.account.audit_state()
        old=self.store.read()['revision']
        self.store.save(event_id='one',expected_revision=old,document=self.document)
        restarted=TransferReconciliationStore(**self.arguments)
        self.assertEqual(restarted.read()['document'],self.document)
        self.assertEqual(restarted.save(event_id='one',expected_revision=old,document=self.document)['status'],'ALREADY_RECORDED')
        self.assertEqual(len(restarted.read()['events']),1)
        self.assertEqual(self.fixture.account.audit_state(),before)

    def test_conflict_and_stale_sources_do_not_write(self):
        old=self.store.read()['revision']
        for field,reason in [('account_revision','STALE_ACCOUNT'),('transfer_revision','STALE_TRANSFER')]:
            bad=dict(self.document);bad[field]='old'
            with self.assertRaisesRegex(ValueError,reason):self.store.save(event_id='one',expected_revision=old,document=bad)
            self.assertEqual(self.store.read()['events'],[])
        self.store.save(event_id='one',expected_revision=old,document=self.document)
        with self.assertRaisesRegex(ValueError,'STALE_RECONCILIATION'):
            self.store.save(event_id='two',expected_revision=old,document=self.document)
        bad=copy.deepcopy(self.document);bad['links']={}
        with self.assertRaisesRegex(ValueError,'EVENT_ID_CONFLICT'):
            self.store.save(event_id='one',expected_revision=old,document=bad)
        self.assertEqual(len(self.store.read()['events']),1)

    def test_links_and_residual_document_persist_together(self):
        before=self.fixture.account.store.read()['revision']
        self.fixture.cash('deposit','495')
        self.fixture.times['deposit']=self.fixture.now.isoformat()
        self.document['account_revision']=self.fixture.account.store.read()['revision']
        classification=dict(schema='CASH_CHANGE_CLASSIFICATION_V1',account_id='fixture',
            cash_event_id='deposit',before_revision=before,after_revision=self.document['account_revision'],
            net_change='100',items=[dict(item_id='d',kind='DEPOSIT',amount='100',effective_at=self.fixture.now.isoformat())])
        self.document['classifications']={'deposit':classification}
        self.store.save(event_id='combined',expected_revision=self.store.read()['revision'],document=self.document)
        saved=TransferReconciliationStore(**self.arguments).read()['document']
        self.assertEqual(saved['links'],self.fixture.links)
        self.assertEqual(saved['classifications']['deposit'],classification)

    def test_invalid_classification_rolls_back_whole_bundle(self):
        bad=copy.deepcopy(self.document)
        bad['classifications']={'unknown':{}}
        with self.assertRaisesRegex(ValueError,'UNKNOWN_CLASSIFICATION_EVENT'):
            self.store.save(event_id='one',expected_revision=self.store.read()['revision'],document=bad)
        self.assertEqual(self.store.read()['events'],[])

if __name__=='__main__':unittest.main()
