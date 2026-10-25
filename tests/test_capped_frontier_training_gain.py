from fractions import Fraction as F
import unittest

from scripts.explain_capped_frontier_training_gain import decompose, growth_factors


class TrainingGainTests(unittest.TestCase):
    def test_one_favorable_scenario_can_determine_the_positive_gap(self):
        result = decompose([F(1), F(1)], [F(2), F(3, 4)])
        self.assertEqual(result['exact_full_product_ratio'], '3/2')
        self.assertTrue(result['full_strict_improvement'])
        self.assertEqual(result['omission_cases_still_strictly_ahead'], 1)
        self.assertFalse(result['rows'][0]['chosen_strictly_ahead_without_this_scenario'])
        self.assertTrue(result['rows'][1]['chosen_strictly_ahead_without_this_scenario'])

    def test_all_positive_gains_and_exact_ties(self):
        self.assertEqual(decompose([F(1)] * 3, [F(11, 10)] * 3)['omission_cases_still_strictly_ahead'], 3)
        equal = decompose([F(1)] * 3, [F(1)] * 3)
        self.assertFalse(equal['full_strict_improvement'])
        self.assertEqual(equal['omission_cases_still_strictly_ahead'], 0)

    def test_residual_cash_and_initial_fee(self):
        arguments = dict(entered_cash='100', fee_bps='100', prices={'a': '10'},
                         training_scenarios=[{'a': '2'}, {'a': '1/2'}])
        self.assertEqual(growth_factors({'a': 5}, arguments), [F(299, 200), F(149, 200)])
        self.assertEqual(growth_factors({}, arguments), [F(1), F(1)])
        with self.assertRaises(ValueError):
            growth_factors({'a': 10}, arguments)
        with self.assertRaises(ValueError):
            growth_factors({'a': True}, arguments)


if __name__ == '__main__':
    unittest.main()
