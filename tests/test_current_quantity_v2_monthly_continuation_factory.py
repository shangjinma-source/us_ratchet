"""Scope composition with actual temporary guarded services; no production IO."""
from tempfile import TemporaryDirectory
from datetime import timedelta
import unittest
import sqlite3
from contextlib import closing
from fractions import Fraction
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_paper import create_router,PREFIX
from test_current_quantity_v2_monthly_continuation_sources import fixture as monthly_fixture
import test_current_quantity_v2_continuation_factory as cash_tests
from data.current_quantity_v2_monthly_continuation_factory import attach_monthly_continuation


class FactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cash_tests.ContinuationFactoryTests.setUpClass()
    @classmethod
    def tearDownClass(cls):cash_tests.ContinuationFactoryTests.tearDownClass()

    def test_currentcash_subclass_callbacks_and_guarded_retry_preserved(self):
        case=cash_tests.ContinuationFactoryTests()
        with TemporaryDirectory() as folder:
            services,clock,calls=case.fixture(folder);original=services['paper']
            callbacks=(original.initial_resolver,original.continuation_previewer,original.continuation_resolver)
            facade=attach_monthly_continuation(original,monthly_sources=None)['paper']
            services['paper']=facade;before=case.closed(services,clock)
            self.assertIs(facade.original,original);self.assertIs(facade.store,original.store)
            self.assertEqual(callbacks,(original.initial_resolver,original.continuation_previewer,original.continuation_resolver))
            clock[0]+=timedelta(seconds=60)
            request,proposal=case.proposal(services,before)
            accepted=facade.accept_continuation(**request)
            self.assertEqual(accepted['cash'],before['cash'])
            old=list(calls)
            original.continuation_resolver=lambda *a: self.fail('exact retry resolver')
            facade.clock=lambda:self.fail('exact retry clock')
            self.assertEqual(facade.accept_continuation(**request),accepted)
            self.assertEqual(calls,old)

    def test_actual_monthly_daily_sell_buy_and_lost_response_retry(self):
        with TemporaryDirectory() as folder:
            source,original,state,clock,quotes,rss=monthly_fixture(folder)
            paper=attach_monthly_continuation(original,monthly_sources=source)['paper'];aid=state['ledger']['account_id']
            app=FastAPI();app.include_router(create_router(service=paper))
            with TestClient(app) as client:
                response=client.post(PREFIX+'/continuation/preview',json=dict(account_id=aid,expected_revision=state['ledger']['revision']))
                self.assertEqual(response.status_code,200,response.text);proposal=response.json()
                request=dict(account_id=aid,proposal_id=proposal['proposal_id'],operation_id='daily',expected_revision=state['ledger']['revision'])
                with patch.object(paper,'_response',side_effect=OSError('response lost')):
                    self.assertEqual(client.post(PREFIX+'/continuation/accept',json=request).status_code,503)
                accepted=client.post(PREFIX+'/continuation/accept',json=request).json()
                self.assertTrue(accepted['capabilities']['continuation']['configured'])
                self.assertEqual(accepted['target_quantities'],state['ledger']['target_quantities'])
                cash=Fraction(accepted['cash']);fees=Fraction(accepted['recorded_fees'])
                # Existing buy authorization is fixed; actual sell cash is credited only at fill.
                for side in ('SELL','BUY'):
                    order=next(o for o in accepted['orders'] if o['side']==side)
                    amount=Fraction(order['limit_price'])
                    response=client.post(PREFIX+'/event',json=dict(account_id=aid,event=dict(type='FILL',event_id='daily-'+side,
                        order_id=order['order_id'],expected_revision=accepted['revision'],quantity=1,price=order['limit_price'],fees='0',executed_at=clock[0].isoformat())))
                    self.assertEqual(response.status_code,200,response.text);accepted=response.json()
                    cash+=amount if side=='SELL' else -amount
                    self.assertEqual(Fraction(accepted['cash']),cash);self.assertEqual(Fraction(accepted['recorded_fees']),fees)
                before=(list(quotes),list(rss));source._current=None;paper.bridge._proposals.clear()
                paper.clock=lambda:self.fail('exact retry clock')
                replay=client.post(PREFIX+'/continuation/accept',json=request)
                self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json(),accepted)
                self.assertEqual((quotes,rss),before)
                self.assertEqual(paper.store.read(aid)['genesis'],state['genesis'])

    def test_monthly_guard_held_through_actual_commit(self):
        with TemporaryDirectory() as folder:
            source,original,state,clock,_,_=monthly_fixture(folder)
            paper=attach_monthly_continuation(original,monthly_sources=source)['paper'];aid=state['ledger']['account_id']
            proposal=paper.continuation_preview(account_id=aid,expected_revision=state['ledger']['revision'])
            request=dict(account_id=aid,proposal_id=proposal['proposal_id'],operation_id='guard',expected_revision=state['ledger']['revision'])
            with closing(sqlite3.connect(paper.store.path,isolation_level=None)) as db:
                db.execute("CREATE TRIGGER reject_operation BEFORE INSERT ON v2_accept_operations BEGIN SELECT RAISE(ABORT,'fixture'); END")
            with self.assertRaises(sqlite3.IntegrityError):paper.accept_continuation(**request)
            self.assertEqual(paper.store.read(aid),state)
            def take_lock():
                with source.lock:return True
            with ThreadPoolExecutor(1) as pool:self.assertTrue(pool.submit(take_lock).result(timeout=3))
            with closing(sqlite3.connect(paper.store.path,isolation_level=None)) as db:db.execute('DROP TRIGGER reject_operation')
            entered=Event();release=Event();attempted=Event();acquired=Event();transaction=paper.store.transaction
            @contextmanager
            def paused(**kwargs):
                with transaction(**kwargs) as db:
                    yield db
                    entered.set();self.assertTrue(release.wait(5))
                    self.assertFalse(acquired.is_set())
                self.assertFalse(acquired.is_set())
            def competing_capture():
                attempted.set()
                with source.lock:acquired.set()
            with ThreadPoolExecutor(2) as pool,patch.object(paper.store,'transaction',paused):
                accepted=pool.submit(paper.accept_continuation,**request)
                self.assertTrue(entered.wait(5));competitor=pool.submit(competing_capture)
                self.assertTrue(attempted.wait(3));self.assertFalse(acquired.wait(.1))
                release.set();accepted.result();competitor.result()
            self.assertTrue(acquired.is_set())

if __name__=='__main__':unittest.main()
