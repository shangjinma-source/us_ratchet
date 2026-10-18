import unittest
from fractions import Fraction
from backtest import return_priority_paper_continuous_book_research as subject


class SignedFlow(unittest.TestCase):
    def test_withdrawal_changes_equity_not_strategy_return_or_cagr(self):
        day1,day2='2026-10-09','2026-10-12'
        inputs=dict(calendar=[day1,day2],open_prices={day1:{},day2:{}},close_prices={day1:{},day2:{}},
            metadata=dict(A=dict(ticker='A',issuer_id='IA',risk_chain='CA')),initial_shares={},initial_cash=1000,
            fee_bps=10,minimum_cash_buffer=100,decisions=[],cash_events=[dict(id='withdraw',session=day2,amount=-300)],
            risk_parameters=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),
            enforce_initial_target_risk=False,declared_price_basis='CONDITIONAL_PAPER')
        result=subject.simulate_paper_book(**inputs)
        self.assertEqual(Fraction(result['final_cash']),700)
        self.assertEqual(Fraction(result['daily_rows'][-1]['cumulative_time_weighted_return']),0)
        self.assertEqual(Fraction(result['daily_rows'][-1]['external_cash_flow']),-300)
        self.assertIsNone(result['cagr'])
        self.assertFalse(result['annualization_performed'])
        inputs['cash_events'][0]['amount']=-1300
        blocked=subject.simulate_paper_book(**inputs)
        self.assertEqual(blocked['reason'],'EXTERNAL_WITHDRAWAL_EXCEEDS_PRE_EXECUTION_CASH')
        self.assertEqual(Fraction(blocked['final_cash']),1000)
        self.assertEqual(blocked['consumed_cash_event_ids'],[])


if __name__=='__main__':unittest.main()
