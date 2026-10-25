from copy import deepcopy
from fractions import Fraction as F
import unittest
from scripts.summarize_relative_variance_result import summarize


class SummaryTests(unittest.TestCase):
    def fixture(self, recover=True):
        rows=[dict(date=d,equity=str(v),cash=str(v//2),external_flow='0')
              for d,v in [('2025-01-16',24000),('2025-01-31',18000),
                          ('2025-02-03',24000 if recover else 20000)]]
        book=dict(status='COMPLETE', daily_ledger=rows,
            selection_account_states=[{'decision_date':'2025-01-15'}],
            order_log=[dict(event='ASSUMED_NEXT_OPEN_FILLED',date=d) for d in
                       ['2025-01-16','2025-01-16','2025-02-03']],
            fees='3',total_return=str(F(rows[-1]['equity'])/20000-1))
        review=dict(status='INDEPENDENT_FRONTIER_ACCOUNT_RISK_REVIEW_PASS',
            final_equity=rows[-1]['equity'],interval_return=book['total_return'],
            fills=3,close_observations=3,fees='3',max_close_drawdown='1/4')
        return book,review

    def test_recovery_month_boundaries_cash_and_counts(self):
        book,review=self.fixture()
        r=summarize(book,review)
        self.assertEqual(r['drawdown_peak_date'],'2025-01-16')
        self.assertEqual(r['drawdown_trough_date'],'2025-01-31')
        self.assertEqual(r['recovery_date'],'2025-02-03')
        self.assertFalse(r['unrecovered'])
        self.assertEqual(r['maximum_monthly_fills'],2)
        self.assertEqual(r['mean_daily_cash_equity_ratio'],0.5)
        self.assertEqual(r['worst_day']['return_fraction'],'-1/4')
        self.assertEqual(r['worst_month']['return_fraction'],'-1/10')
        self.assertTrue(all(m['boundary_calendar_month_truncated'] for m in r['monthly_returns']))
        self.assertEqual(r['elapsed_calendar_days'],19)
        self.assertAlmostEqual(r['annualized_return_36525'],1.2**(365.25/19)-1)
        self.assertEqual(r['gap_loss']['status'],'NOT_CALCULATED')

    def test_unrecovered_and_review_fail_closed(self):
        book,review=self.fixture(False)
        self.assertTrue(summarize(book,review)['unrecovered'])
        self.assertIsNone(summarize(book,review)['recovery_date'])
        for key,value in [('status','RUNNING'),('total_return','9')]:
            bad=deepcopy(book);bad[key]=value
            with self.assertRaises(ValueError):summarize(bad,review)
        for key,value in [('status','PENDING'),('fills',0),('max_close_drawdown','0')]:
            bad=deepcopy(review);bad[key]=value
            with self.assertRaises(ValueError):summarize(book,bad)


if __name__=='__main__':
    unittest.main()
