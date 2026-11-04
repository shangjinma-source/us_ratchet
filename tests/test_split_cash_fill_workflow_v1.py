"""Whole candidate flow with synthetic fills in disposable SQLite only."""
from copy import deepcopy
from fractions import Fraction
import unittest
from data.strategy_split_account_preview_v1 import preview_split_account
import test_split_account_preview_v1 as preview_fixture
import test_split_account_cost_projection as cost_fixture


class SplitCashFillWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=preview_fixture.SplitPreviewTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.arguments=deepcopy(self.fixture.arguments)
        self.store=self.fixture.fixture.store
        self.store.clock=self.fixture.fixture.base.clock
        self.service=cost_fixture.candidate.StrategyAccountService(
            database_path=self.store.path,account_id=self.arguments['state']['account_id'],
            resolver=lambda ticker:None)

    def preview(self):
        self.arguments['state']=self.store.read()
        return preview_split_account(**self.arguments)

    def fill_and_confirm(self,order):
        before=self.store.read()
        event=dict(event_id='synthetic-fill',kind='DIRECT_FILL',security_id=order['security_id'],
            side=order['side'],quantity=order['quantity'],price=order['limit_price'],fees='0',
            executed_at=self.arguments['now'])
        state,_=self.store.append(event,expected_revision=before['revision'])
        self.assertFalse(state['cash_confirmation_valid'])
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):self.preview()
        # A network retry carries the same event identity and must not double count.
        retried,_=self.store.append(event,expected_revision=before['revision'])
        self.assertEqual(retried,state)
        count=len(state['events'])
        confirmation=dict(event_id='synthetic-cash-after-fill',kind='CASH_CONFIRM',
            amount=str(Fraction(before['total_uninvested_cash'])+Fraction(order['estimated_cash_change'])),
            cash_basis='TOTAL_UNINVESTED')
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            self.store.append(confirmation,expected_revision=before['revision'])
        self.assertEqual(len(self.store.read()['events']),count)
        state,_=self.store.append(confirmation,expected_revision=state['revision'])
        return before,state

    def test_buy_fill_cash_refresh_and_costs_use_post_split_quantity(self):
        initial=self.preview()
        order=next(row for row in initial['candidate_difference']['new_orders'] if row['security_id']=='A')
        self.assertEqual(order['side'],'BUY')
        before,after=self.fill_and_confirm(order)
        self.assertEqual(after['shares']['A'],112+order['quantity'])
        costs=self.service.project(after)['account']['holding_costs']
        cost=next(row for row in costs if row['security_id']=='A')
        self.assertEqual(Fraction(cost['total_cost']),1400+order['quantity']*Fraction(order['limit_price']))
        subsequent=self.preview()
        self.assertEqual(subsequent['candidate_difference']['account_revision'],after['revision'])
        self.assertLessEqual(Fraction(subsequent['candidate_difference']['new_buy_cash_required']),
                            Fraction(after['total_uninvested_cash']))
        self.assertEqual(self.preview(),subsequent)
        self.assertEqual(self.store.read(),after)

    def test_exit_fill_then_cash_confirmation_does_not_buy_back_or_repeat_sell(self):
        self.arguments['observations'][-1]['closes']['A']='10'
        initial=self.preview()
        order=next(row for row in initial['candidate_difference']['new_orders'] if row['security_id']=='A')
        self.assertEqual((order['side'],order['quantity']),('SELL',112))
        _,after=self.fill_and_confirm(order)
        self.assertEqual(after['shares']['A'],0)
        self.assertFalse(any(row['security_id']=='A' for row in self.service.project(after)['account']['holding_costs']))
        subsequent=self.preview()
        self.assertEqual(subsequent['risk_result']['effective_target_quantities']['A'],0)
        self.assertFalse(any(row['security_id']=='A' for row in subsequent['candidate_difference']['new_orders']))
        self.assertEqual(self.store.read(),after)
