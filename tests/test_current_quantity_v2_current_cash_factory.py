from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
import sqlite3
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_current_cash_sources import snapshot_fixture,month_config
from test_current_quantity_v2_intraday_reference import NOW,raw
from data.current_quantity_v2_current_cash_factory import create_services
from api.current_quantity_v2_difference import create_router as difference_router
from api.current_quantity_v2_paper import create_router as paper_router,PREFIX


class CashFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.root=Path(cls.temp.name);cls.snapshots,cls.view=snapshot_fixture(cls.root)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def fixture(self,folder):
        calls=[];clock=[NOW]
        def fetch(ticker):calls.append(ticker);return raw(ticker,10)
        services=create_services(root=self.root,snapshot_service=self.snapshots,server_account_id='fixed-pool',
            database_path=Path(folder)/'nested'/'paper.sqlite3',fetch=fetch,clock=lambda:clock[0],execution_month_mandate=month_config(self.root))
        return services,calls,clock

    def test_factory_optional_audit_path_constructor_no_io(self):
        with TemporaryDirectory() as folder:
            observation=Path(folder)/'observations'
            services=create_services(root=self.root,snapshot_service=self.snapshots,server_account_id='fixed-pool',
                database_path=Path(folder)/'paper.sqlite3',observation_directory=observation,unit_review_reader=lambda _:None,
                fetch=lambda ticker:raw(ticker,10),clock=lambda:NOW,execution_month_mandate=month_config(self.root))
            self.assertFalse(observation.exists())
            self.assertTrue(callable(services['preview'].followup_reader))
            self.assertFalse((self.root/'data'/'quantity_v2_followup').exists())
            self.assertEqual(services['sources'].audit_storage_root,observation/'current_cash_captures')
            self.assertEqual(services['continuation_sources'].audit_storage_root,observation/'current_cash_continuation_captures')
            capture=services['sources'].capture(self.view['decision_id'])
            self.assertEqual(services['sources'].audit(capture['capture_id'],'fixed-pool')['status'],'CAPTURED')
            self.assertFalse(services['store'].path.exists())

    def test_constructor_zero_fetch_write_http_preview_once_accept_restore_zero_fetch(self):
        with TemporaryDirectory() as folder:
            with patch.object(self.snapshots,'decision',side_effect=AssertionError('constructor source read')):
                s,calls,clock=self.fixture(folder)
            self.assertEqual(calls,[]);self.assertFalse(s['store'].path.parent.exists())
            create_services(root=self.root,snapshot_service=self.snapshots,server_account_id='explicit',
                database_path=Path(folder)/'not-created'/'other.sqlite3',
                fetch=lambda _:(_ for _ in ()).throw(AssertionError('constructor fetch')),
                clock=lambda:(_ for _ in ()).throw(AssertionError('constructor clock')))
            self.assertFalse((Path(folder)/'not-created').exists())
            app=FastAPI();app.include_router(difference_router(service=s['preview']));app.include_router(paper_router(service=s['paper']))
            with TestClient(app) as client:
                p=client.post('/api/current_portfolio_research/difference',json={'decision_id':self.view['decision_id']})
                self.assertEqual(p.status_code,200,p.text);self.assertEqual(calls,['AAA','BBB']);p=p.json()
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='once')
                accepted=client.post(PREFIX+'/accept',json=request);self.assertEqual(accepted.status_code,200,accepted.text)
                restored=client.get(PREFIX+'/account',params={'account_id':'fixed-pool'})
                self.assertEqual(restored.json(),accepted.json());self.assertEqual(calls,['AAA','BBB'])
                class BrokenLock:
                    def __enter__(self):raise AssertionError('retry lock')
                    def __exit__(self,*a):pass
                s['sources'].lock=BrokenLock();s['paper'].clock=lambda:(_ for _ in ()).throw(AssertionError('retry clock'))
                s['paper'].initial_resolver=lambda *a:(_ for _ in ()).throw(AssertionError('retry resolver'))
                self.assertEqual(client.post(PREFIX+'/accept',json=request).json(),accepted.json())

    def test_source_lock_covers_commit_and_capture_serializes_after(self):
        with TemporaryDirectory() as folder:
            s,calls,clock=self.fixture(folder);p=s['preview'].preview(self.view['decision_id']);self.assertEqual(p['status'],'READY',p)
            before_commit=Event();release=Event();capture_started=Event();real=s['store'].transaction
            @contextmanager
            def paused(*,create=False):
                with real(create=create) as connection:
                    yield connection
                    before_commit.set();self.assertTrue(release.wait(5))
            s['store'].transaction=paused
            request=dict(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='commit')
            def capture():capture_started.set();return s['sources'].capture(self.view['decision_id'])
            with ThreadPoolExecutor(max_workers=2) as pool:
                accepted=pool.submit(s['paper'].accept,**request);self.assertTrue(before_commit.wait(5))
                attempt=s['sources']._attempt
                self.assertFalse(s['sources'].lock.acquire(blocking=False))
                future=pool.submit(capture);self.assertTrue(capture_started.wait(5))
                self.assertEqual(s['sources']._attempt,attempt)
                release.set();result=accepted.result(5);newcapture=future.result(5)
            self.assertEqual(newcapture['attempt'],attempt+1)
            self.assertEqual(s['store'].read('fixed-pool')['ledger']['execution_target_id'],result['execution_target_id'])

    def test_capture_invalidation_before_accept_refuses_old_proposal(self):
        with TemporaryDirectory() as folder:
            s,_,_=self.fixture(folder);p=s['preview'].preview(self.view['decision_id']);entered=Event();release=Event()
            def fetch(ticker):entered.set();self.assertTrue(release.wait(5));return raw(ticker,10)
            s['sources'].fetch=fetch
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(s['sources'].capture,self.view['decision_id']);self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):
                    s['paper'].accept(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='stale')
                release.set();future.result(5)
            with self.assertRaises(ValueError):s['store'].read('fixed-pool')

    def test_commit_failure_rolls_back_and_source_remains_usable(self):
        with TemporaryDirectory() as folder:
            s,_,_=self.fixture(folder);p=s['preview'].preview(self.view['decision_id']);real=s['store'].transaction
            @contextmanager
            def failing(*,create=False):
                with real(create=create) as conn:
                    yield conn
                    raise sqlite3.OperationalError('synthetic commit failure')
            s['store'].transaction=failing
            with self.assertRaises(sqlite3.Error):s['paper'].accept(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='commit-error')
            with self.assertRaises(ValueError):s['store'].read('fixed-pool')
            s['store'].transaction=real
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(s['sources'].capture,self.view['decision_id']).result(5)['status'],'CAPTURED')

    def test_database_wait_does_not_hold_source_lock(self):
        with TemporaryDirectory() as folder:
            s,_,_=self.fixture(folder);p=s['preview'].preview(self.view['decision_id'])
            with s['store'].transaction(create=True):pass
            external=sqlite3.connect(s['store'].path,isolation_level=None);external.execute('BEGIN IMMEDIATE')
            entering=Event();real=s['store'].transaction
            @contextmanager
            def observed(*,create=False):
                entering.set()
                with real(create=create) as conn:yield conn
            s['store'].transaction=observed
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(s['paper'].accept,account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='wait')
                    self.assertTrue(entering.wait(5))
                    got=s['sources'].lock.acquire(blocking=False)
                    if got:s['sources'].lock.release()
                    self.assertTrue(got);external.rollback();self.assertEqual(future.result(5)['status'],'PAPER_ACCOUNT')
            finally:external.close()

    def test_source_guard_released_after_rollback(self):
        with TemporaryDirectory() as folder:
            s,_,clock=self.fixture(folder);p=s['preview'].preview(self.view['decision_id'])
            clock[0]+=timedelta(seconds=121)
            with self.assertRaises(ValueError):s['paper'].accept(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='expired')
            with ThreadPoolExecutor(max_workers=1) as pool:
                def probe():
                    ok=s['sources'].lock.acquire(blocking=False)
                    if ok:s['sources'].lock.release()
                    return ok
                self.assertTrue(pool.submit(probe).result(5))
            with self.assertRaises(ValueError):s['store'].read('fixed-pool')

if __name__=='__main__':unittest.main()
