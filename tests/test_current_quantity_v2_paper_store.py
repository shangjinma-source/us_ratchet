from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from test_current_quantity_v2_paper_ledger import initial,event
from test_current_quantity_v2_paper_chain import inputs
from data.current_quantity_v2_paper_chain import build_continuation
from data.current_quantity_v2_paper_store import QuantityV2PaperStore


def clock(value='2026-10-15T12:00:30-04:00'):
    return lambda:datetime.fromisoformat(value)


def setup(path):
    _,proposal,args=initial();store=QuantityV2PaperStore(path);calls=[]
    def factory(now):
        calls.append(now);return dict(proposal=deepcopy(proposal),account_state=deepcopy(args['account_state']))
    request=dict(account_id=args['account_state']['account_id'],proposal_id=proposal['proposal_id'],operation_id='initial',factory=factory,clock=clock())
    return store,request,args,calls


class StoreTests(unittest.TestCase):
    def test_legacy_database_rejected_without_modifying_bytes(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'legacy.sqlite3'
            with closing(sqlite3.connect(path,isolation_level=None)) as db:
                db.execute('CREATE TABLE legacy_accounts(value TEXT)')
                db.execute("INSERT INTO legacy_accounts VALUES('preserve')")
            original=path.read_bytes();s,r,_,_=setup(path)
            with self.assertRaisesRegex(ValueError,'WRONG_PAPER_DATABASE_SCHEMA'):s.accept(**r)
            self.assertEqual(path.read_bytes(),original)
            with self.assertRaisesRegex(ValueError,'WRONG_PAPER_DATABASE_SCHEMA'):s.read(r['account_id'])

    def test_read_absent_no_side_effect_and_concurrent_accept_retry(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'new'/'ledger.sqlite3';s,r,_,calls=setup(path)
            with self.assertRaises(ValueError):s.read(r['account_id'])
            self.assertFalse(path.parent.exists())
            barrier=Barrier(2)
            def accept():barrier.wait();return s.accept(**r)
            with ThreadPoolExecutor(2) as pool:
                a=pool.submit(accept);b=pool.submit(accept);self.assertEqual(a.result(),b.result())
            self.assertEqual(len(calls),1)
            retry=dict(r,factory=lambda _:self.fail('repeat factory'),clock=lambda:self.fail('repeat clock'))
            self.assertEqual(QuantityV2PaperStore(path).accept(**retry),s.read(r['account_id']))
            with self.assertRaises(ValueError):s.accept(**dict(r,account_id='other'))

    def test_same_revision_events_one_wins_and_retry_latest(self):
        with TemporaryDirectory() as folder:
            s,r,_,_=setup(Path(folder)/'ledger.sqlite3');state=s.accept(**r);barrier=Barrier(2)
            events=[event(state['ledger'],kind='CANCEL',event_id='c'+str(i)) for i in range(2)]
            def submit(e):
                barrier.wait()
                try:return s.record_event(account_id=r['account_id'],event=e,clock=clock('2026-10-15T13:01:00-04:00'))
                except ValueError:return None
            with ThreadPoolExecutor(2) as pool:results=list(pool.map(submit,events))
            self.assertEqual(sum(x is not None for x in results),1)
            latest=s.read(r['account_id']);saved=latest['ledger']['events'][0]
            self.assertEqual(s.record_event(account_id=r['account_id'],event=saved,clock=lambda:self.fail('retry clock')),latest)
            self.assertEqual(s.accept(**dict(r,factory=lambda _:self.fail('retry factory'))),latest)

    def test_continuation_restart_and_insert_failure_atomic_rollback(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.sqlite3';s,r,args,_=setup(path);state=s.accept(**r)
            for side,kind in [('BUY','FILL'),('BUY','CANCEL'),('SELL','FILL')]:
                e=event(state['ledger'],side,kind)
                state=s.record_event(account_id=r['account_id'],event=e,clock=clock('2026-10-15T13:01:00-04:00'))
            proposal=build_continuation(state,execution_inputs=inputs(args),now='2026-10-15T13:03:30-04:00')
            request=dict(account_id=r['account_id'],proposal_id=proposal['proposal_id'],operation_id='next',
                expected_revision=state['ledger']['revision'],factory=lambda current,now:deepcopy(proposal),clock=clock('2026-10-15T13:03:31-04:00'))
            with closing(sqlite3.connect(path,isolation_level=None)) as db:
                db.execute("CREATE TRIGGER abort_op BEFORE INSERT ON v2_accept_operations BEGIN SELECT RAISE(ABORT,'test'); END")
            with self.assertRaises(sqlite3.IntegrityError):s.accept_continuation(**request)
            self.assertEqual(s.read(r['account_id']),state)
            with closing(sqlite3.connect(path,isolation_level=None)) as db:db.execute('DROP TRIGGER abort_op')
            accepted=s.accept_continuation(**request)
            self.assertEqual(accepted['ledger']['cash'],state['ledger']['cash'])
            reopened=QuantityV2PaperStore(path)
            self.assertEqual(reopened.accept_continuation(**dict(request,factory=lambda *_:self.fail('retry'),clock=lambda:self.fail('clock'))),accepted)
            with self.assertRaises(ValueError):reopened.accept_continuation(**dict(request,proposal_id='different'))

    def test_slow_factory_rechecks_expiry_and_rolls_back(self):
        with TemporaryDirectory() as folder:
            s,r,_,_=setup(Path(folder)/'ledger.sqlite3');times=iter([datetime.fromisoformat('2026-10-15T12:00:30-04:00'),datetime.fromisoformat('2026-10-15T12:03:30-04:00')])
            with self.assertRaises(ValueError):s.accept(**dict(r,clock=lambda:next(times)))
            # Entire transaction including schema/operations is rolled back.
            with closing(sqlite3.connect(s.path)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0],0)


if __name__=='__main__':unittest.main()
