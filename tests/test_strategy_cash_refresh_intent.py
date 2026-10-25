from copy import deepcopy
import unittest

from core.strategy_account_ledger import create_account,apply_event
from data.strategy_cash_refresh_intent import plan_cash_refresh


class CashRefreshIntentTests(unittest.TestCase):
    def setUp(self):
        self.state=create_account('a');self.counter=0
        self.target=dict(target_id='t',payload=dict(account_id='a',target_month='2026-10'))
        self.now='2026-10-20T14:00:00+00:00'
        self.event('CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')

    def event(self,kind,**fields):
        self.counter+=1
        self.state,_=apply_event(self.state,dict(event_id=str(self.counter),kind=kind,**fields),
                                 expected_revision=self.state['revision'])

    def plan(self,**kwargs):
        args=dict(state=self.state,target=self.target,now=self.now);args.update(kwargs)
        return plan_cash_refresh(**args)

    def capital(self):
        return dict(schema='SERVER_EXPLICIT_STRATEGY_CAPITAL_CHANGE_V1',event_id='deposit1',
            account_id='a',account_revision=self.state['revision'],
            cash_confirmation_event_id=self.state['last_cash_confirmation_event'],
            previous_target_id='t',direction='CONTRIBUTION',amount='500')

    def test_same_month_cash_increase_decrease_repeat_never_reselect(self):
        for amount in ('1500','0','1500','1500'):
            self.event('CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED')
            before=deepcopy(self.state)
            result=self.plan()
            self.assertIsNone(result['selection_reason'])
            self.assertEqual(result['next_action'],'REFRESH_DAILY_SIGNAL')
            self.assertEqual(self.state,before)

    def test_sale_proceeds_not_assumed_new_capital(self):
        self.event('DIRECT_FILL',security_id='S',side='BUY',quantity=2,
                   price='100',fees='0',executed_at=self.now)
        self.event('DIRECT_FILL',security_id='S',side='SELL',quantity=2,
                   price='150',fees='0',executed_at=self.now)
        self.event('CASH_CONFIRM',amount='1100',cash_basis='TOTAL_UNINVESTED')
        self.assertIsNone(self.plan()['selection_reason'])

    def test_initial_and_month_roll_keep_selection(self):
        self.assertEqual(self.plan(target=None)['selection_reason'],'INITIAL')
        old=deepcopy(self.target);old['payload']['target_month']='2026-09'
        self.assertEqual(self.plan(target=old)['selection_reason'],'MONTHLY_SELECTION')

    def test_explicit_new_capital_missing_event_does_not_guess(self):
        self.assertEqual(self.plan(intent='APPLY_CAPITAL_CHANGE')['status'],
                         'CAPITAL_CHANGE_EVENT_REQUIRED')
        result=self.plan(intent='APPLY_CAPITAL_CHANGE',capital_change=self.capital())
        self.assertEqual(result['selection_reason'],'EXPLICIT_RECONFIGURE')
        self.assertEqual(result['capital_event_consumption'],'ON_SUCCESSFUL_TARGET_PUBLICATION_ONLY')

    def test_duplicate_capital_event_and_stale_binding(self):
        capital=self.capital()
        result=self.plan(intent='APPLY_CAPITAL_CHANGE',capital_change=capital,
                         consumed_capital_event_ids=['deposit1'])
        self.assertIsNone(result['selection_reason'])
        self.event('CASH_CONFIRM',amount='1500',cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(self.plan(intent='APPLY_CAPITAL_CHANGE',capital_change=capital,
            consumed_capital_event_ids=['deposit1'])['status'],'CAPITAL_CHANGE_ALREADY_APPLIED')
        with self.assertRaises(ValueError):
            self.plan(intent='APPLY_CAPITAL_CHANGE',capital_change=capital)


if __name__=='__main__':
    unittest.main()
