from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event, RLock
import sqlite3
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
import test_current_research_intraday_retarget_chain_store as fixtures
import test_current_research_intraday_retarget_continuation_chain as chains
from data.current_research_intraday_multiorder_service import IntradayMultiorderService

class MultiorderServiceTests(unittest.TestCase):
    def fixture(self,root):
        store,before,p,evidence,now,call,factory,initial,genesis=fixtures.ChainStoreTests().fixture(root)
        clock=[now];current=[deepcopy(evidence)];calls=[]
        def provider(**kwargs):
            calls.append(kwargs['now']);return deepcopy(current[0])
        source_lock=RLock()  # Synthetic source authority lock; real wiring must share execution.lock.
        service=IntradayMultiorderService(store=store,evidence_provider=provider,acceptance_guard=lambda **_:source_lock,clock=lambda:clock[0])
        return service,before,clock,current,calls
    def test_preview_accept_events_restart_and_retry_without_provider(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=self.fixture(root);account=before['account_id']
            preview=service.preview(account,before['revision']);proposal=preview['proposal']
            self.assertEqual(preview['status'],'CONTINUATION_PROPOSAL')
            self.assertNotIn('execution_evidence',proposal);self.assertNotIn('binding',proposal)
            clock[0]+=timedelta(seconds=1)
            self.assertEqual(service.preview(account,before['revision'])['proposal']['proposal_id'],proposal['proposal_id'])
            accepted=service.accept(account,proposal['proposal_id'],'service-accept',before['revision'])
            self.assertEqual(accepted['account']['cash'],before['cash'])
            order=accepted['account']['orders'][0];clock[0]+=timedelta(seconds=1)
            fill=dict(event_id='service-fill',kind='FILL',expected_revision=accepted['account']['revision'],order_id=order['order_id'],quantity=100,price='37',fees='1',executed_at=clock[0].isoformat())
            recorded=service.event(account,fill)
            self.assertEqual(recorded['account']['cash'],'16499');self.assertEqual(recorded['account']['events'][-1]['recorded_at'],clock[0].isoformat())
            def forbidden(**kwargs):self.fail('successful retry must not read provider')
            restarted=IntradayMultiorderService(store=service.store,evidence_provider=forbidden,clock=lambda:self.fail('successful retry clock'))
            self.assertEqual(restarted.account(account)['account'],recorded['account'])
            self.assertEqual(restarted.accept(account,proposal['proposal_id'],'service-accept',before['revision'])['account'],recorded['account'])
            self.assertEqual(restarted.event(account,fill)['account'],recorded['account'])
    def test_expired_changed_source_and_stale_revision_do_not_write(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=self.fixture(root);account=before['account_id']
            p=service.preview(account,before['revision'])['proposal'];original=service.store.read_retarget_envelope(account)
            clock[0]+=timedelta(seconds=120)
            with self.assertRaisesRegex(ValueError,'CURRENT_CONTINUATION_NOT_ACCEPTABLE'):
                service.accept(account,p['proposal_id'],'expired',before['revision'])
            self.assertEqual(service.store.read_retarget_envelope(account),original)
            clock[0]-=timedelta(seconds=60)
            current[0]=chains.ChainTests().append_quote(current[0],clock[0],39,37)
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHANGED'):
                service.accept(account,p['proposal_id'],'changed',before['revision'])
            fresh=service.preview(account,before['revision'])['proposal']
            self.assertNotEqual(p['proposal_id'],fresh['proposal_id'])
            service.accept(account,fresh['proposal_id'],'new',before['revision'])
            with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_REVISION'):
                service.accept(account,fresh['proposal_id'],'other',before['revision'])
    def test_missing_provider_bad_source_and_client_recorded_at(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=self.fixture(root);account=before['account_id']
            disabled=IntradayMultiorderService(store=service.store)
            with self.assertRaisesRegex(ValueError,'PROVIDER_UNAVAILABLE'):disabled.preview(account,before['revision'])
            p=service.preview(account,before['revision'])['proposal']
            state=service.accept(account,p['proposal_id'],'a',before['revision'])['account'];o=state['orders'][0]
            event=dict(event_id='client-time',kind='CANCEL',expected_revision=state['revision'],order_id=o['order_id'],cancelled_at=clock[0].isoformat(),recorded_at=clock[0].isoformat())
            with self.assertRaisesRegex(ValueError,'CLIENT_EVENT_SCHEMA'):service.event(account,event)
            self.assertEqual(service.account(account)['account']['revision'],state['revision'])
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=self.fixture(root)
            current[0]['files'][next(iter(current[0]['files']))]='YQ=='
            with self.assertRaisesRegex(ValueError,'FROZEN_SOURCE_HASH_MISMATCH'):service.preview(before['account_id'],before['revision'])
    def test_acceptance_clock_after_sqlite_wait_rejects_expired_quote(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=self.fixture(root);account=before['account_id']
            proposal=service.preview(account,before['revision'])['proposal'];entered=Event()
            def request():
                entered.set();return service.accept(account,proposal['proposal_id'],'locked',before['revision'])
            with closing(sqlite3.connect(service.store.path,isolation_level=None)) as lock:
                lock.execute('BEGIN IMMEDIATE')
                with ThreadPoolExecutor(max_workers=1) as pool:
                    task=pool.submit(request);self.assertTrue(entered.wait(5))
                    clock[0]+=timedelta(seconds=121);lock.commit()
                    with self.assertRaisesRegex(ValueError,'CURRENT_CONTINUATION_NOT_ACCEPTABLE'):task.result(10)
            self.assertEqual(service.store.read(account),before)

    def test_legacy_v1_event_is_rejected_before_any_write(self):
        from data.current_research_intraday_paper_ledger import _initial
        from data.current_research_intraday_paper_store import IntradayPaperStore
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=self.fixture(root)
            original=_initial(before['acceptance'])
            legacy_store=IntradayPaperStore(Path(root)/'legacy')
            legacy_store.accept(original['account_id'],original['acceptance']['proposal']['proposal_id'],'legacy-initial',lambda:original)
            isolated=IntradayMultiorderService(store=legacy_store,clock=lambda:clock[0])
            event=dict(event_id='must-not-write',kind='CANCEL',expected_revision=original['revision'],order_id=original['order']['order_id'],cancelled_at=original['order']['accepted_at'])
            before_bytes=legacy_store.path.read_bytes()
            with self.assertRaisesRegex(ValueError,'RETARGET_ACCEPTANCE_REQUIRED'):isolated.event(original['account_id'],event)
            self.assertEqual(legacy_store.read(original['account_id']),original)
            self.assertEqual(legacy_store.path.read_bytes(),before_bytes)

    def test_read_missing_account_does_not_create_store(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'not-created';service=IntradayMultiorderService(directory=directory)
            with self.assertRaises(ValueError):service.account('missing')
            self.assertFalse(directory.exists())

if __name__=='__main__':unittest.main()
