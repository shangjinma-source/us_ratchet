import unittest
from scripts import ndx_non_equal_fast_independent_readback as review


class IndependentNoFitReadbackTests(unittest.TestCase):
    def test_twenty_metric_aggregation_and_initial_cost(self):
        rows=[dict(candidate_return=.2,candidate_drawdown=.1,incumbent_return=.1,incumbent_drawdown=.2,
            target_return=.05,target_drawdown=.15,turnover=.4,cost=.0004),
            dict(candidate_return=.4,candidate_drawdown=.2,incumbent_return=.2,incumbent_drawdown=.1,
            target_return=.1,target_drawdown=.05,turnover=.2,cost=.0002)]
        metrics=review.aggregate(rows)
        self.assertEqual(len(metrics),20)
        self.assertAlmostEqual(metrics['return_p50'],.3)
        self.assertAlmostEqual(metrics['paired_return_p10_vs_incumbent'],.11)
        self.assertEqual(metrics['initial_turnover'],.4)
        self.assertEqual(metrics['initial_transaction_cost'],.0004)
        self.assertEqual(metrics['ongoing_rebalance_turnover_p50'],.2)
        self.assertEqual(review.compare_metrics(metrics,metrics),0.)
        changed=dict(metrics,return_p50=.4)
        with self.assertRaises(ValueError):review.compare_metrics(metrics,changed)

    def test_fixed_sample_selection_by_k_and_weight_spec(self):
        rows=[dict(task=dict(job_id=str(i),holding_count=k,weight_spec=spec,tickers=ticker))
            for i,(k,spec,ticker) in enumerate([(1,'a','A'),(1,'a','B'),(1,'a','C'),(1,'b','B'),(2,'a','A;B')])]
        self.assertEqual(review.sample_jobs(rows),{'0','2','3','4'})
        self.assertEqual(review.sample_jobs(rows),review.sample_jobs(list(reversed(rows))))

    def test_actual_first_date_readonly_observed_fixture(self):
        report=review.verify_date('2023-04-03','8c6a8a79abd4fb7835bd0935b1689e12d2e622cec6aaca5576c0f03a1ef0a39e')
        self.assertEqual(report['count'],269)
        self.assertEqual(report['sample_count'],38)
        self.assertLess(report['maximum_absolute_error'],1e-12)
        self.assertFalse(report['fit_or_projection_called'])


if __name__=='__main__':unittest.main()
