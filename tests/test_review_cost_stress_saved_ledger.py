from copy import deepcopy
import unittest
import test_continuous_guided_cost_stress as fixtures
from backtest.continuous_guided_cost_stress import run_cost_stress_arm
from scripts.review_cost_stress_saved_ledger import review


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.assembled,self.ohlc,resolver=fixtures.CostStressTests().data()
        self.outcome=run_cost_stress_arm(arm='continuous32_half',scenario='fee1_slippage10',
            assembled=self.assembled,ohlc=self.ohlc,initial_cash='1000',history_resolver=resolver)
    def check(self):
        return review(outcome=self.outcome,session_dates=self.assembled['session_dates'],ohlc=self.ohlc,
            initial_cash='1000',fee_bps='1',slippage_bps='10')
    def test_replays_cost_cash_and_positions(self):
        self.assertEqual(self.check()['status'],'SUPPORTED_SAVED_LEDGER_REPLAY_VERIFIED')
    def test_tampered_holdings_and_fill(self):
        original=deepcopy(self.outcome)
        self.outcome['daily_ledger'][0]['shares']['A']=999
        with self.assertRaisesRegex(ValueError,'DAILY_STATE'):self.check()
        self.outcome=original
        next(r for r in self.outcome['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED')['fee']='123'
        with self.assertRaisesRegex(ValueError,'FILL_PRICE_FEE'):self.check()
    def test_missing_fill_and_exposed_rights_do_not_pass(self):
        original=deepcopy(self.outcome)
        self.outcome['order_log']=[r for r in self.outcome['order_log'] if r['event']!='ASSUMED_NEXT_OPEN_FILLED']
        with self.assertRaises(ValueError):self.check()
        self.outcome=original
        self.outcome['order_log'].insert(0,dict(date=self.assembled['session_dates'][0],event='CONDITIONAL_DTC_CONVERSION'))
        self.assertEqual(self.check()['status'],'UNSUPPORTED_EVENT_REQUIRES_REVIEW')


if __name__=='__main__':unittest.main()
