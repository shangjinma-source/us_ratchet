from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.quantity_integer_box_certificate_prototype import solve, verify
from backtest.quantity_integer_box_resume import resume
from test_quantity_integer_box_certificate_prototype import fixture, oracle


class ResumeTests(unittest.TestCase):
    def test_partitioned_search_matches_uninterrupted_and_oracle(self):
        initial = solve(**fixture(), node_budget=2)
        saved = deepcopy(initial)
        current = initial
        for budget in (3, 4, 1000):
            current = resume(current, expected_input_sha256=initial['input_sha256'],
                             additional_nodes=budget)
        self.assertEqual(initial, saved)
        self.assertEqual(current['coverage_ledger'][:2], saved['coverage_ledger'])
        self.assertEqual(current, solve(**fixture(), node_budget=1009))
        self.assertEqual(Fraction(current['lower_product']), max(v for v, _ in oracle(fixture())))
        self.assertTrue(verify(current, expected_input_sha256=initial['input_sha256'])['complete'])

    def test_zero_budget_preserves_frontier_and_rejects_invalid_budget(self):
        initial = solve(**fixture(), node_budget=1)
        self.assertEqual(initial, resume(initial, expected_input_sha256=initial['input_sha256'], additional_nodes=0))
        for budget in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                resume(initial, expected_input_sha256=initial['input_sha256'], additional_nodes=budget)

    def test_untrusted_input_and_missing_frontier_rejected(self):
        initial = solve(**fixture(), node_budget=1)
        with self.assertRaises(ValueError):
            resume(initial, expected_input_sha256='wrong', additional_nodes=1)
        damaged = deepcopy(initial)
        damaged['unsearched_frontier'].pop()
        with self.assertRaises(ValueError):
            resume(damaged, expected_input_sha256=initial['input_sha256'], additional_nodes=1)

    def test_impact_order_keeps_full_domain_and_matches_oracle(self):
        initial = solve(**fixture(), node_budget=2)
        result = resume(initial, expected_input_sha256=initial['input_sha256'],
                        additional_nodes=1000, split_policy='anchor_impact')
        self.assertTrue(verify(result, expected_input_sha256=initial['input_sha256'])['complete'])
        self.assertEqual(Fraction(result['lower_product']), max(v for v, _ in oracle(fixture())))
        self.assertEqual(result['coverage_ledger'][:2], initial['coverage_ledger'])
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_SPLIT_POLICY'):
            resume(initial, expected_input_sha256=initial['input_sha256'],
                   additional_nodes=1, split_policy='unknown')


if __name__ == '__main__':
    unittest.main()
