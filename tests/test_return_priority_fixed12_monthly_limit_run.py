import unittest
from fractions import Fraction
from scripts.return_priority_fixed12_monthly_limit_run import summarize


class ContinuousMetricsTests(unittest.TestCase):
    def fixture(self):
        outcome=dict(status='COMPLETE',cash='100',shares={'x':2},receivable='0',
            daily_ledger=[dict(date='2025-01-02',equity='18000'),dict(date='2025-07-30',equity='22000')],
            order_log=[dict(event='ASSUMED_FILLED',side='BUY',quantity=10,price='100'),
                       dict(event='ASSUMED_FILLED',side='SELL',quantity=4,price='125'),
                       dict(event='EXPIRED_UNFILLED',quantity=3)])
        audit=[dict(response=dict(status='READY',target_shares={'x':3},wait_cash=[{'security_id':'x'}],investable_equity_at_reset='20000')),
               dict(response=dict(status='READY',target_shares={'x':3},wait_cash=[],investable_equity_at_reset=None))]
        return outcome,audit

    def test_true_continuous_return_drawdown_and_calendar_year(self):
        o,a=self.fixture();m=summarize(o,a,'20000',['2024-07-31','2025-07-30'])
        self.assertEqual(Fraction(m['total_return']),Fraction(1,10))
        self.assertEqual(Fraction(m['daily_close_maximum_drawdown']),Fraction(1,10))
        self.assertEqual(m['annualization_basis']['calendar_days'],364)
        self.assertAlmostEqual(m['annualized_return'],1.1**(365/364)-1)

    def test_turnover_denominators_wait_and_unfinished(self):
        o,a=self.fixture();m=summarize(o,a,'20000',['2024-07-31','2025-07-30'])
        self.assertEqual(m['turnover']['gross_traded_notional'],'1500')
        self.assertEqual(m['turnover']['gross_notional_over_initial_equity'],'3/40')
        self.assertEqual(m['turnover']['mean_observed_close_equity_including_initial'],'20000')
        self.assertEqual(m['filled_orders'],2);self.assertEqual(m['expired_orders'],1)
        self.assertEqual(m['cash_wait_days'],1);self.assertEqual(m['terminal_target_difference'],{'x':1})

    def test_blocked_partial_cannot_report_completed_return(self):
        o,a=self.fixture();o['status']='BLOCKED';o['daily_ledger']=o['daily_ledger'][:1]
        m=summarize(o,a,'20000',['2024-07-31','2025-07-30'])
        self.assertIsNone(m['total_return']);self.assertIsNone(m['annualized_return'])
        self.assertIsNone(m['daily_close_maximum_drawdown']);self.assertEqual(m['partial_observed_drawdown'],'1/10')


if __name__=='__main__':unittest.main()
