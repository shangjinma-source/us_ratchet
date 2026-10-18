"""Temporary-DB adversarial audit, including explicitly documented current gaps."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
import os
import unittest
from api.strategy_account import StrategyAccountService


class IndependentBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'account.db';self.sid='SID-1'
        self.service=StrategyAccountService(database_path=self.path,account_id='s',
            resolver=lambda t:dict(ticker=t,security_id=self.sid,source_references=['id.json'],source_hashes={'id.json':'a'*64}),
            clock=lambda:datetime(2026,10,16,15,tzinfo=timezone.utc))
    def submit(self,event,revision=None):
        return self.service.append(dict(event=event,expected_revision=revision or self.service.read()['account']['revision']))
    def init(self):self.service.initialize({'event_id':'init'})
    def cash(self,amount,basis='AVAILABLE_AFTER_RESERVATIONS'):
        return self.submit(dict(event_id='cash',kind='CASH_CONFIRM',amount=amount,cash_basis=basis))
    def fill(self,event_id='fill',time='2026-10-16T14:00:00Z'):
        return dict(event_id=event_id,kind='DIRECT_FILL',ticker='AAA',side='BUY',quantity=1,price='10',fees='0',executed_at=time)
    def test_frozen_retry_and_ticker_sid_reuse_rejection(self):
        self.init();self.cash('100');old=self.service.read()['account']['revision'];event=self.fill()
        self.submit(event);self.sid='SID-2'
        retry=self.submit(event,old)
        self.assertEqual(retry['account']['holdings'][0]['security_id'],'SID-1')
        with self.assertRaisesRegex(ValueError,'IDENTITY_MAPPING_CHANGED'):self.submit(self.fill('second'))
        self.assertEqual(len(self.service.store.read()['events']),2)
    def test_future_linked_fill_rolls_back_and_receipts_are_preserved(self):
        self.init();self.cash('100')
        self.submit(dict(event_id='open',kind='ORDER_OPEN',order_id='o',ticker='AAA',side='BUY',quantity=2,limit_price='10',fee_per_share='0'))
        before=self.service.store.read()
        event=dict(event_id='linked',kind='FILL',order_id='o',quantity=1,price='10',fees='0',executed_at='2026-10-16T16:00:00Z')
        with self.assertRaisesRegex(ValueError,'FUTURE_EXECUTED_AT'):self.submit(event)
        self.assertEqual(before,self.service.store.read())
        event['executed_at']='2026-10-16T14:00:00Z';self.submit(event)
        self.assertEqual(self.service.store.read()['events'][-1]['payload']['executed_at'],event['executed_at'])
        self.assertFalse(self.service.read()['account']['cash_confirmation_valid'])
    def test_existing_order_after_available_cash_requires_new_confirmation(self):
        self.init();self.cash('400')  # Broker already froze 600 for an existing order.
        self.submit(dict(event_id='existing',kind='ORDER_OPEN',order_id='o',ticker='AAA',side='BUY',quantity=6,limit_price='100',fee_per_share='0'))
        pending=self.service.read()['account']
        self.assertFalse(pending['cash_confirmation_valid'])
        self.assertIsNone(pending['cash_confirmed_for_holdings_revision'])
        self.assertEqual(pending['reserved_cash'],'600')
        self.submit(dict(event_id='cash-again',kind='CASH_CONFIRM',amount='400',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
        confirmed=self.service.read()['account']
        self.assertEqual(confirmed['total_uninvested_cash'],'1000')
        self.assertEqual(confirmed['available_cash'],'400')
        self.assertTrue(confirmed['cash_confirmation_valid'])
    def test_initialization_publishes_only_complete_database(self):
        ready,release=Event(),Event();real_link=os.link
        def paused_link(*args,**kwargs):
            ready.set();self.assertTrue(release.wait(5));return real_link(*args,**kwargs)
        with ThreadPoolExecutor(max_workers=1) as pool,patch('core.strategy_account_store.os.link',side_effect=paused_link):
            future=pool.submit(self.service.initialize,{'event_id':'init'})
            self.assertTrue(ready.wait(5))
            self.assertEqual(self.service.read()['status'],'NOT_INITIALIZED')
            release.set();first=future.result(timeout=5)
        self.assertEqual(self.service.initialize({'event_id':'init'}),first)
        self.assertEqual(list(self.path.parent.glob('.*initialize-*')),[])
    def test_competing_initializers_and_failed_publication(self):
        from threading import Barrier
        barrier=Barrier(2);real_link=os.link
        def simultaneous(*args,**kwargs):
            barrier.wait(5);return real_link(*args,**kwargs)
        with ThreadPoolExecutor(max_workers=2) as pool,patch('core.strategy_account_store.os.link',side_effect=simultaneous):
            futures=[pool.submit(self.service.initialize,{'event_id':'init'}) for _ in range(2)]
            self.assertEqual(futures[0].result(timeout=5),futures[1].result(timeout=5))
        with self.assertRaisesRegex(ValueError,'INITIALIZATION_CONFLICT'):self.service.initialize({'event_id':'other'})
        self.assertEqual(list(self.path.parent.glob('.*initialize-*')),[])
        other=type(self.service.store)(self.path.parent/'other.db')
        with patch('core.strategy_account_store.os.link',side_effect=OSError('publication failed')):
            with self.assertRaisesRegex(OSError,'publication failed'):other.initialize('s',operation_id='x')
        self.assertIsNone(other.read())
        self.assertEqual(list(self.path.parent.glob('.*initialize-*')),[])
        self.assertEqual(other.initialize('s',operation_id='x')['account_id'],'s')


if __name__=='__main__':unittest.main()
