from copy import deepcopy
import unittest
from core.strategy_account_ledger import create_account, apply_event, replay


class LedgerTests(unittest.TestCase):
    def setUp(self):self.state=create_account('real-strategy');self.sequence=0
    def event(self,kind,**fields):
        self.sequence+=1
        if kind=='FILL':fields.setdefault('executed_at','2026-10-16T14:00:00+00:00')
        event=dict(event_id=str(self.sequence),kind=kind,**fields)
        self.state,effect=apply_event(self.state,event,expected_revision=self.state['revision'])
        return event,effect
    def cash(self,amount='1000',basis='TOTAL_UNINVESTED'):
        return self.event('CASH_CONFIRM',amount=amount,cash_basis=basis)
    def order(self,side='BUY',quantity=6,oid='one'):
        return self.event('ORDER_OPEN',order_id=oid,security_id='SID-A',side=side,quantity=quantity,limit_price='100',fee_per_share='1')
    def test_partial_fill_manual_cash_and_reconfirmation(self):
        self.cash();self.order()
        self.assertEqual(self.state['reserved_cash'],'606')
        _,effect=self.event('FILL',order_id='one',quantity=2,price='99',fees='2')
        self.assertEqual(effect['cash_delta'],'-200');self.assertEqual(self.state['cash'],'1000')
        self.assertEqual(self.state['shares'],{'SID-A':2});self.assertFalse(self.state['execution_ready'])
        self.assertEqual(self.state['orders']['one']['remaining_quantity'],4)
        self.assertEqual(self.state['reserved_cash'],'404')
        self.assertIsNone(self.state['cash_confirmed_for_holdings_revision'])
        self.cash('800')
        self.assertEqual(self.state['available_cash'],'396')
        self.assertEqual(self.state['holdings_revision'],self.state['cash_confirmed_for_holdings_revision'])
        self.event('CANCEL',order_id='one')
        self.assertEqual(self.state['available_cash'],'800')
        self.assertEqual(self.state['orders']['one']['cancelled_quantity'],4)
    def test_cash_bases_no_double_reserve_and_replacement(self):
        self.cash();self.order()
        self.cash('394','AVAILABLE_AFTER_RESERVATIONS')
        self.assertEqual(self.state['total_uninvested_cash'],'1000');self.assertEqual(self.state['available_cash'],'394')
        self.cash('394','AVAILABLE_AFTER_RESERVATIONS')
        self.assertEqual(self.state['total_uninvested_cash'],'1000')
        self.event('CANCEL',order_id='one')
        self.assertEqual(self.state['available_cash'],'1000')
        self.cash('0');self.assertEqual(self.state['total_uninvested_cash'],'0')
    def test_existing_order_before_any_balance_and_each_new_order_invalidates(self):
        self.order(quantity=2)
        self.assertFalse(self.state['execution_ready'])
        self.assertIsNone(self.state['cash_confirmed_for_holdings_revision'])
        self.cash('798','AVAILABLE_AFTER_RESERVATIONS')
        self.assertEqual(self.state['total_uninvested_cash'],'1000')
        self.order(quantity=1,oid='another')
        self.assertFalse(self.state['execution_ready'])
        self.assertIsNone(self.state['cash_confirmed_for_holdings_revision'])
        self.cash('1000','TOTAL_UNINVESTED')
        self.assertEqual(self.state['available_cash'],'697')
        self.assertTrue(self.state['execution_ready'])
    def test_legacy_cannot_be_sold_and_reserve_prevents_oversell(self):
        self.cash()
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_STRATEGY_SHARES'):self.order(side='SELL',quantity=1)
        self.order(quantity=2)
        self.event('FILL',order_id='one',quantity=2,price='100',fees='0');self.cash('800')
        self.order(side='SELL',quantity=2,oid='sell')
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_STRATEGY_SHARES'):self.order(side='SELL',quantity=1,oid='oversell')
        _,effect=self.event('FILL',order_id='sell',quantity=2,price='110',fees='1')
        self.assertEqual(effect['cash_delta'],'219');self.assertEqual(self.state['cash'],'800');self.assertEqual(self.state['shares']['SID-A'],0)
    def test_idempotency_conflict_stale_revision_and_replay(self):
        old=self.state['revision'];event,effect=self.cash()
        state,same=apply_event(self.state,event,expected_revision=old)
        self.assertEqual(state,self.state);self.assertEqual(same,effect)
        bad=dict(event,amount='2000')
        with self.assertRaisesRegex(ValueError,'EVENT_ID_CONFLICT'):apply_event(self.state,bad,expected_revision=old)
        new=dict(event,event_id='new')
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):apply_event(self.state,new,expected_revision=old)
        self.order();self.event('FILL',order_id='one',quantity=1,price='100',fees='1')
        self.assertEqual(replay('real-strategy',[x['payload'] for x in self.state['events']]),self.state)
    def test_invalid_fill_and_state_tamper_rejected(self):
        self.cash();self.order(quantity=2)
        with self.assertRaisesRegex(ValueError,'INVALID_FILL_QUANTITY'):self.event('FILL',order_id='one',quantity=3,price='100',fees='0')
        bad=deepcopy(self.state);bad['shares']['SID-A']=100
        with self.assertRaisesRegex(ValueError,'STATE_INTEGRITY'):apply_event(bad,dict(event_id='bad',kind='CASH_CONFIRM',amount='1',cash_basis='TOTAL_UNINVESTED'),expected_revision=bad['revision'])


if __name__=='__main__':unittest.main()
