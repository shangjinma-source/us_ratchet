"""Real temporary factory/SQLite lifecycle; synthetic quotes and explicit unit review."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import sqlite3
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_current_cash_sources import snapshot_fixture,month_config
import test_current_quantity_v2_current_cash_continuation_sources as source_fixtures
from data.current_quantity_v2_current_cash_factory import create_services
from api.current_quantity_v2_paper import create_router, PREFIX


class ContinuationFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_fixtures.SourcesTests.setUpClass()
        cls.temp=TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.snapshots,cls.view=snapshot_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup();source_fixtures.SourcesTests.tearDownClass()

    def fixture(self,folder,configured=True):
        _,source,clock,calls=source_fixtures.SourcesTests().fixture()
        services=create_services(root=self.root,snapshot_service=self.snapshots,
            server_account_id='fixed-pool',database_path=Path(folder)/'nested'/'paper.sqlite3',
            fetch=source.fetch,clock=lambda:clock[0],execution_month_mandate=month_config(self.root),
            unit_review_reader=source.unit_review_reader if configured else None)
        return services,clock,calls

    def closed(self,services,clock):
        proposal=services['preview'].preview(self.view['decision_id'])
        self.assertEqual(proposal['status'],'READY',proposal)
        paper=services['paper']
        state=paper.accept(account_id='fixed-pool',proposal_id=proposal['proposal_id'],operation_id='initial')
        clock[0]+=timedelta(seconds=1)
        order=next(o for o in state['orders'] if o['security_id']=='A')
        state=paper.event(account_id='fixed-pool',event=dict(type='FILL',event_id='partial',
            order_id=order['order_id'],expected_revision=state['revision'],quantity=2,price='9',fees='1/5',executed_at=clock[0].isoformat()))
        for i,order in enumerate(state['orders']):
            state=paper.event(account_id='fixed-pool',event=dict(type='CANCEL',event_id='cancel'+str(i),
                order_id=order['order_id'],expected_revision=state['revision'],cancelled_at=clock[0].isoformat()))
        return state

    def proposal(self,s,before):
        p=s['paper'].continuation_preview(account_id='fixed-pool',expected_revision=before['revision'])
        self.assertEqual(p['status'],'READY',p)
        return dict(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='continue',expected_revision=before['revision']),p

    def test_constructor_no_io_and_unconfigured_unavailable(self):
        with TemporaryDirectory() as folder:
            fail=lambda *a:(_ for _ in ()).throw(AssertionError('construction IO'))
            with patch.object(self.snapshots,'decision',side_effect=fail):
                s=create_services(root=self.root,snapshot_service=self.snapshots,server_account_id='pool',
                    database_path=Path(folder)/'absent'/'db',fetch=fail,clock=fail,unit_review_reader=fail)
            self.assertFalse((Path(folder)/'absent').exists());self.assertIsNotNone(s['continuation'])
            s,clock,calls=self.fixture(folder,False);before=self.closed(s,clock);old=list(calls)
            with self.assertRaisesRegex(ValueError,'CONTINUATION_SOURCE_UNAVAILABLE'):
                s['paper'].continuation_preview(account_id='fixed-pool',expected_revision=before['revision'])
            self.assertEqual(calls,old);self.assertEqual(s['paper'].account('fixed-pool'),before)

    def test_http_partial_close_preview_delayed_accept_retry_no_fetch(self):
        with TemporaryDirectory() as folder:
            s,clock,calls=self.fixture(folder);before=self.closed(s,clock)
            app=FastAPI();app.include_router(create_router(service=s['paper']))
            with TestClient(app) as client:
                response=client.post(PREFIX+'/continuation/preview',json=dict(account_id='fixed-pool',expected_revision=before['revision']))
                self.assertEqual(response.status_code,200,response.text);p=response.json()
                self.assertEqual(calls,['AAA','BBB','AAA','BBB'])
                self.assertEqual(p['target_quantities'],before['target_quantities'])
                self.assertEqual({o['security_id']:o['quantity'] for o in p['orders']},
                    {'A':before['target_quantities']['A']-2,'B':before['target_quantities']['B']})
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id='fixed-pool',proposal_id=p['proposal_id'],operation_id='continue',expected_revision=before['revision'])
                response=client.post(PREFIX+'/continuation/accept',json=request)
                self.assertEqual(response.status_code,200,response.text);after=response.json()
                for key in ('cash','shares','recorded_fees','target_quantities','execution_target_id'):
                    self.assertEqual(after[key],before[key])
                self.assertEqual(client.get(PREFIX+'/account',params={'account_id':'fixed-pool'}).json(),after)
                fail=lambda *a:(_ for _ in ()).throw(AssertionError('retry callback'))
                s['paper'].clock=fail;s['paper'].continuation_resolver=fail
                class BrokenLock:
                    def __enter__(self):raise AssertionError('retry source lock')
                    def __exit__(self,*args):pass
                s['paper'].continuation_sources.lock=BrokenLock()
                self.assertEqual(client.post(PREFIX+'/continuation/accept',json=request).json(),after)
                self.assertEqual(calls,['AAA','BBB','AAA','BBB'])

    def test_db_then_source_wait_rechecks_clock_and_rolls_back(self):
        with TemporaryDirectory() as folder:
            s,clock,_=self.fixture(folder);before=self.closed(s,clock);request,_=self.proposal(s,before)
            entered=Event();real=s['store'].transaction
            @contextmanager
            def observed(*,create=False):
                with real(create=create) as conn:
                    entered.set();yield conn
            s['store'].transaction=observed
            with ThreadPoolExecutor(max_workers=1) as pool:
                with s['continuation_sources'].lock:
                    future=pool.submit(s['paper'].accept_continuation,**request)
                    self.assertTrue(entered.wait(5));clock[0]+=timedelta(seconds=121)
                with self.assertRaises(ValueError):future.result(5)
            self.assertEqual(s['paper'].account('fixed-pool'),before)

    def test_guard_through_commit_and_capture_cannot_supersede(self):
        with TemporaryDirectory() as folder:
            s,clock,_=self.fixture(folder);before=self.closed(s,clock);request,_=self.proposal(s,before)
            chain=s['store'].read('fixed-pool');source=s['continuation_sources']
            ready=Event();release=Event();started=Event();real=s['store'].transaction
            @contextmanager
            def paused(*,create=False):
                with real(create=create) as conn:
                    yield conn;ready.set();self.assertTrue(release.wait(5))
            s['store'].transaction=paused
            def capture():started.set();return source.capture(chain)
            with ThreadPoolExecutor(max_workers=2) as pool:
                accepted=pool.submit(s['paper'].accept_continuation,**request);self.assertTrue(ready.wait(5))
                attempt=source._attempt;self.assertFalse(source.lock.acquire(blocking=False))
                other=pool.submit(capture);self.assertTrue(started.wait(5));self.assertEqual(source._attempt,attempt)
                release.set();accepted.result(5);other.result(5)
            self.assertEqual(source._attempt,attempt+1)

    def test_commit_failure_rolls_back_releases_guard_and_operation(self):
        with TemporaryDirectory() as folder:
            s,clock,_=self.fixture(folder);before=self.closed(s,clock);request,_=self.proposal(s,before)
            real=s['store'].transaction
            @contextmanager
            def fail(*,create=False):
                with real(create=create) as conn:
                    yield conn;raise sqlite3.OperationalError('synthetic commit failure')
            s['store'].transaction=fail
            with self.assertRaises(sqlite3.Error):s['paper'].accept_continuation(**request)
            self.assertEqual(s['paper'].account('fixed-pool'),before)
            s['store'].transaction=real
            with ThreadPoolExecutor(max_workers=1) as pool:
                def probe():
                    ok=s['continuation_sources'].lock.acquire(blocking=False)
                    if ok:s['continuation_sources'].lock.release()
                    return ok
                self.assertTrue(pool.submit(probe).result(5))
            self.assertEqual(s['paper'].accept_continuation(**request)['cash'],before['cash'])


if __name__=='__main__':unittest.main()
