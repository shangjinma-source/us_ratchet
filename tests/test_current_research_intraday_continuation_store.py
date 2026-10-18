import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import timedelta
import test_current_research_intraday_continuation as fixtures
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_paper_ledger import _initial
from data.current_research_intraday_paper_store import IntradayPaperStore
from data.current_research_intraday_continuation_ledger import build_continuation_proposal,accept_continuation_proposal

class ContinuationStoreTests(unittest.TestCase):
    def fixture(self,root):
        _,state,args=fixtures.ContinuationTests().setup(str(Path(root)/'journal'))
        store=IntradayPaperStore(Path(root)/'store');initial=_initial(state['acceptance'])
        store.accept(state['account_id'],initial['acceptance']['proposal']['proposal_id'],'initial',lambda:initial)
        for event in state['events']:store.record_event(state['account_id'],event,now=NOW)
        proposal=build_continuation_proposal(state,**args)
        inputs={k:v for k,v in args.items() if k not in ('journal_root','now')}
        def factory(current):return accept_continuation_proposal(current,proposal,operation_id='next',journal_root=args['journal_root'],current_inputs=inputs,now=NOW)
        return store,state,proposal,factory
    def test_cycle_retry_initial_separation_and_event_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            store,before,p,factory=self.fixture(root);a=before['account_id'];revision=before['revision']
            after=store.accept_continuation(a,p['proposal_id'],'next',revision,factory)
            event=dict(event_id='nextfill',kind='FILL',expected_revision=after['revision'],order_id=after['order']['order_id'],quantity=1,price='1400',fees='1',executed_at=NOW.isoformat())
            filled=store.record_event(a,event,now=lambda:NOW)
            self.assertEqual(filled['shares'],{'sndk':3});self.assertEqual(filled['cash'],'15799')
            self.assertEqual(store.accept_continuation(a,p['proposal_id'],'next',revision,lambda _:self.fail('retry factory')),filled)
            self.assertEqual(store.accept(a,before['acceptance']['proposal']['proposal_id'],'initial',lambda:self.fail('initial retry')),filled)
            self.assertEqual(IntradayPaperStore(store.path.parent).read(a),filled)
            for operation in ('initial','next'):
                with self.assertRaises(ValueError):store.accept_continuation(a,'wrong',operation,revision,factory)
    def test_failed_factory_and_revision_rollback(self):
        with tempfile.TemporaryDirectory() as root:
            store,state,p,factory=self.fixture(root);a=state['account_id']
            def corrupt(s):
                value=factory(s);value['cash']='999';return value
            with self.assertRaises(ValueError):store.accept_continuation(a,p['proposal_id'],'next',state['revision'],corrupt)
            self.assertEqual(store.read(a),state)
            with self.assertRaises(ValueError):store.accept_continuation(a,p['proposal_id'],'next','stale',lambda _:self.fail('called stale'))
            self.assertEqual(store.accept_continuation(a,p['proposal_id'],'next',state['revision'],factory)['shares'],state['shares'])
    def test_sql_failure_rolls_back_state_and_operation_together(self):
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as root:
            store,state,p,factory=self.fixture(root)
            with closing(sqlite3.connect(store.path)) as db:
                db.execute("CREATE TRIGGER reject_continuation BEFORE INSERT ON intraday_continuations BEGIN SELECT RAISE(ABORT,'test abort'); END")
                db.commit()
            with self.assertRaises(sqlite3.Error):store.accept_continuation(state['account_id'],p['proposal_id'],'next',state['revision'],factory)
            self.assertEqual(store.read(state['account_id']),state)
            with closing(sqlite3.connect(store.path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM intraday_continuations').fetchone()[0],0)
                db.execute('DROP TRIGGER reject_continuation');db.commit()
            store.accept_continuation(state['account_id'],p['proposal_id'],'next',state['revision'],factory)
            with self.assertRaises(ValueError):store.accept_continuation(state['account_id'],p['proposal_id'],'another',state['revision'],lambda _:self.fail('stale factory'))

    def test_two_calls_one_factory(self):
        with tempfile.TemporaryDirectory() as root:
            store,state,p,factory=self.fixture(root);entered=Event();release=Event();calls=[]
            def guarded(s):calls.append(1);entered.set();self.assertTrue(release.wait(5));return factory(s)
            args=(state['account_id'],p['proposal_id'],'next',state['revision'],guarded)
            with ThreadPoolExecutor(2) as pool:
                first=pool.submit(store.accept_continuation,*args);self.assertTrue(entered.wait(5))
                second=pool.submit(store.accept_continuation,*args);release.set()
                self.assertEqual(first.result(),second.result())
            self.assertEqual(calls,[1])

if __name__=='__main__':unittest.main()
