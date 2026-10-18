import math
import unittest

from scripts import ndx_evidenced_split_equal_delta_readback as review


class IndependentScalarReadbackTests(unittest.TestCase):
    def test_two_day_scalar_cost_and_drawdown_anchor(self):
        annual,drawdown=review.scalar_window([.1,-.2],.01)
        self.assertAlmostEqual(annual,(1.1*.99*.8)**126-1)
        self.assertAlmostEqual(drawdown,.2)
        _,first_loss=review.scalar_window([0.],.01)
        self.assertAlmostEqual(first_loss,.01)

    def test_linear_quantiles_have_no_dependency_on_numerical_library(self):
        self.assertEqual(review.quantile([9.,1.,5.],.5),5.)
        self.assertEqual(review.quantile([9.,1.,5.],.1),1.8)
        self.assertEqual(review.quantile([2.],.9),2.)

    def test_fixed_sample_rule_order_independent_and_all_k_covered(self):
        definitions=[['A'],['GOOG'],['FTNT'],['A','GOOG'],['A','FTNT'],['A','FTNT','GOOG']]
        samples=review.select_samples(definitions)
        self.assertEqual(samples,review.select_samples(list(reversed(definitions))))
        self.assertEqual({len(combo) for combo in samples},{1,2,3})
        self.assertIn(('GOOG',),samples)
        self.assertIn(('FTNT',),samples)

    def test_invalid_wealth_and_duplicate_source_json_rejected(self):
        with self.assertRaises(ValueError):review.scalar_window([-1.],0.)
        with self.assertRaises(ValueError):review.object_pairs([('a',1),('a',2)])

    def test_real_first_date_independent_all_record_and_sample_audit(self):
        report=review.verify_date('2023-04-03')
        self.assertEqual(report['record_count'],24575)
        self.assertEqual(report['scalar_sample_count'],36)
        self.assertLess(report['maximum_scalar_absolute_error'],1e-12)
        self.assertEqual(report['forward_affected_tickers'],['GOOG','GOOGL'])
        self.assertTrue(report['all_record_nondependent_fields_verified'])
        self.assertFalse(report['historical_evaluator_called'])


if __name__=='__main__':unittest.main()
