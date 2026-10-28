import unittest
from copy import deepcopy
from backtest.two_stage_execution_research_v1 import run_staged
from backtest.two_stage_execution_independent_review_v1 import review
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from test_capped_frontier_independent_review import inputs,raw_fixture

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.domain,self.bars=inputs()
        self.book=run_staged(mode='BUY_TWO_OPENS',assembled=self.domain,ohlc=self.bars,initial_cash='20000',fee_bps='1',slippage_bps='10',max_new_searches=1,risk=MonthlyExitCoreResearchAdapter([]),selector=lambda **args:raw_fixture(args))
    def check(self,book):
        return review(book,self.domain,self.bars,initial_cash='20000',dividend_events=[],expected_fee_bps='1',expected_slippage_bps='10')
    def test_real_kernel_independent(self):
        self.assertTrue(self.check(self.book)['risk_provider_certified'])
    def test_fill_log_not_trusted(self):
        b=deepcopy(self.book)
        next(r for r in b['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED')['quantity']=1
        with self.assertRaisesRegex(ValueError,'STAGE_FILL_LOG'):self.check(b)
    def test_phase_audit_not_trusted(self):
        b=deepcopy(self.book);b['execution_stage_audit'][1]['decisions'][0]['phase']=1
        with self.assertRaisesRegex(ValueError,'STAGE_PHASE_AUDIT'):self.check(b)
    def test_second_phase_cannot_half_again(self):
        b=deepcopy(self.book);b['execution_stage_audit'][1]['adjusted']['orders'][0]['quantity']=25
        with self.assertRaisesRegex(ValueError,'STAGE_ORDER_ARITHMETIC'):self.check(b)
    def test_exit_not_delayed(self):
        b=deepcopy(self.book)
        for stage in b['execution_stage_audit']:
            for order in stage['adjusted']['orders']:
                if order['side']=='SELL':order['quantity']=1
        with self.assertRaisesRegex(ValueError,'STAGE_ORDER_ARITHMETIC'):self.check(b)

if __name__=='__main__':unittest.main()
