from fractions import Fraction as F
import unittest
from scripts.diagnose_frontier_scenario_stability import omission_ranks, validate_dates


class StabilityTests(unittest.TestCase):
    def test_scenario_count_and_decision_date_binding(self):
        arguments = dict(scenario_dates=[f'2025-{month:02d}-01' for month in range(1, 13)],
                         training_scenarios=[{}] * 12, decision_date='2026-01-01')
        result = dict(decision_date='2026-01-01')
        validate_dates(arguments, result, '2026-01-01')
        for field, value in [('training_scenarios', [{}] * 13), ('decision_date', '2026-02-01')]:
            with self.assertRaises(ValueError):
                validate_dates(dict(arguments, **{field: value}), result, '2026-01-01')
        with self.assertRaises(ValueError):
            validate_dates(arguments, dict(decision_date='2026-02-01'), '2026-01-01')

    def test_one_extreme_scenario_drives_winner(self):
        self.assertEqual(omission_ranks({'winner': [F(4), F(1)],
            'alternative': [F(3, 2), F(3, 2)]}, 'winner'), [2, 1])

    def test_ties_do_not_displace_incumbent(self):
        self.assertEqual(omission_ranks({'a': [F(2), F(2)], 'b': [F(2), F(2)]}, 'a'), [1, 1])

    def test_invalid_or_nonwinning_input_rejected(self):
        for values in ({'a': [F(0), F(2)]}, {'a': [F(1)]},
                       {'a': [F(1), F(1)], 'b': [F(2), F(2)]}):
            with self.assertRaises(ValueError):
                omission_ranks(values, 'a')


if __name__ == '__main__':
    unittest.main()
