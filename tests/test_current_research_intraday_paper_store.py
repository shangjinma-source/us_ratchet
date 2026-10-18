import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import timedelta
from copy import deepcopy
import test_current_research_intraday_paper_ledger as fixtures
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_paper_store import IntradayPaperStore

class StoreTests(unittest.TestCase):
    def fixture(self,root):
        _,_,_,state=fixtures.AcceptanceTests().fixture(str(Path(root)/'journal'))
        return IntradayPaperStore(Path(root)/'store'),state
    def test_read_and_constructor_do_not_create(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'absent';store=IntradayPaperStore(directory)
            with self.assertRaises(ValueError):store.read('none')
            self.assertFalse(directory.exists())
    def test_accept_retry_bindings_and_restore(self):
        with tempfile.TemporaryDirectory() as root:
            store,s=self.fixture(root);a=s['account_id'];p=s['acceptance']['proposal']['proposal_id'];calls=[]
            def factory():calls.append(1);return deepcopy(s)
            self.assertEqual(store.accept(a,p,'operation',factory),s)
            self.assertEqual(store.accept(a,p,'operation',lambda:(_ for _ in ()).throw(AssertionError('retry'))),s)
            self.assertEqual(len(calls),1)
            for args in ((a,p,'another'),(a,'other','operation'),('other',p,'operation')):
                with self.assertRaises(ValueError):store.accept(*args,factory)
            self.assertEqual(IntradayPaperStore(store.path.parent).read(a),s)
    def test_factory_failure_rollback_then_accept(self):
        with tempfile.TemporaryDirectory() as root:
            store,s=self.fixture(root);a=s['account_id'];p=s['acceptance']['proposal']['proposal_id']
            with self.assertRaises(RuntimeError):store.accept(a,p,'op',lambda:(_ for _ in ()).throw(RuntimeError('fail')))
            with self.assertRaises(ValueError):store.read(a)
            wrong=deepcopy(s);wrong['cash']='1'
            with self.assertRaises(ValueError):store.accept(a,p,'op',lambda:wrong)
            self.assertEqual(store.accept(a,p,'op',lambda:s),s)
    def test_concurrent_accept_factory_once(self):
        with tempfile.TemporaryDirectory() as root:
            store,s=self.fixture(root);entered=Event();release=Event();calls=[]
            def factory():calls.append(1);entered.set();self.assertTrue(release.wait(5));return deepcopy(s)
            args=(s['account_id'],s['acceptance']['proposal']['proposal_id'],'op')
            with ThreadPoolExecutor(2) as pool:
                first=pool.submit(store.accept,*args,factory);self.assertTrue(entered.wait(5))
                second=pool.submit(store.accept,*args,factory);release.set()
                self.assertEqual(first.result(),second.result())
            self.assertEqual(len(calls),1)
    def test_server_recorded_time_and_retry_without_retimestamp(self):
        with tempfile.TemporaryDirectory() as root:
            store,s=self.fixture(root);a=s['account_id'];store.accept(a,s['acceptance']['proposal']['proposal_id'],'op',lambda:s)
            e=fixtures.AcceptanceTests().event(s);del e['recorded_at'];calls=[]
            def clock():calls.append(1);return NOW+timedelta(minutes=6)
            saved=store.record_event(a,e,now=clock)
            self.assertEqual(saved['events'][0]['recorded_at'],(NOW+timedelta(minutes=6)).isoformat())
            self.assertEqual(store.record_event(a,e,now=lambda:(_ for _ in ()).throw(AssertionError('no retimestamp'))),saved)
            self.assertEqual(calls,[1])
            bad=deepcopy(e);bad['quantity']=2
            with self.assertRaises(ValueError):store.record_event(a,bad,now=clock)
            self.assertEqual(store.read(a),saved)

    def test_concurrent_revision_and_event_idempotence(self):
        with tempfile.TemporaryDirectory() as root:
            store,s=self.fixture(root);a=s['account_id'];store.accept(a,s['acceptance']['proposal']['proposal_id'],'op',lambda:s)
            e=fixtures.AcceptanceTests().event(s);f=deepcopy(e);f['event_id']='other'
            def call(event):
                try:return store.record_event(a,event,now=lambda:NOW+timedelta(minutes=6))
                except ValueError:return None
            with ThreadPoolExecutor(2) as pool:results=list(pool.map(call,[e,f]))
            self.assertEqual(sum(r is not None for r in results),1)
            saved=store.read(a);winner=saved['events'][0]
            self.assertEqual(store.record_event(a,winner,now=NOW+timedelta(days=1)),saved)
            bad=deepcopy(winner);bad['price']='1399'
            with self.assertRaises(ValueError):store.record_event(a,bad,now=NOW+timedelta(days=1))
            self.assertEqual(store.read(a),saved)

if __name__=='__main__':unittest.main()
