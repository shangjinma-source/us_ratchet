from copy import deepcopy
import unittest

from core.strategy_account_ledger import create_account, apply_event
from data.strategy_account_preview import preview_scoped_account


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.state=create_account('strategy')
        self.now='2026-10-16T14:05:00+00:00'
        self.arguments=dict(legacy_shares={'SNDK':50},
            marks={'SNDK':dict(security_id='SNDK',currency='USD',price_basis='TEST',price='100',observed_at=self.now)},
            limits={'SNDK':dict(security_id='SNDK',price_basis='TEST',buy='99',sell='101',observed_at=self.now)},
            target_quantities={'SNDK':10},now=self.now,maximum_mark_age_seconds=120,fee_bps='0')

    def event(self, **event):
        self.state,_=apply_event(self.state,event,expected_revision=self.state['revision'])

    def test_buy_then_manual_cash_and_existing_holdings(self):
        self.event(event_id='cash1',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
        self.event(event_id='fill',kind='DIRECT_FILL',security_id='SNDK',side='BUY',quantity=4,
                   price='100',fees='0',executed_at=self.now)
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):
            preview_scoped_account(state=self.state,**self.arguments)
        self.event(event_id='cash2',kind='CASH_CONFIRM',amount='600',cash_basis='TOTAL_UNINVESTED')
        result=preview_scoped_account(state=self.state,**self.arguments)
        self.assertEqual(result['strategy_equity'],'1000')
        self.assertEqual(result['new_orders'][0]['quantity'],6)
        self.assertEqual(result['legacy_shares_excluded'],{'SNDK':50})
        corrupt=deepcopy(self.state);corrupt['shares']['SNDK']=5
        with self.assertRaisesRegex(ValueError,'ACCOUNT_REPLAY_MISMATCH'):
            preview_scoped_account(state=corrupt,**self.arguments)

    def test_available_cash_cancellation_uses_ledger_total(self):
        self.event(event_id='cash1',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
        self.event(event_id='order',kind='ORDER_OPEN',order_id='one',security_id='SNDK',side='BUY',
                   quantity=4,limit_price='100',fee_per_share='0')
        self.event(event_id='cash2',kind='CASH_CONFIRM',amount='600',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        self.event(event_id='cancel',kind='CANCEL',order_id='one')
        result=preview_scoped_account(state=self.state,**self.arguments)
        self.assertEqual(self.state['cash'],'600')
        self.assertEqual(result['strategy_equity'],'1000')
        self.assertEqual(result['spendable_cash'],'1000')
        self.assertEqual(result['new_orders'][0]['quantity'],10)


if __name__=='__main__':unittest.main()
