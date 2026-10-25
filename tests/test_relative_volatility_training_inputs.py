from datetime import date, timedelta
import unittest
from scripts.review_relative_volatility_training_inputs import check_series


class TrainingInputTests(unittest.TestCase):
    def test_constant_series_and_changed_units(self):
        days = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(253)]
        check_series(days, ['10'] * 253, days[-1], ['1'] * 12, '10')
        self.assertEqual(check_series(days, ['10'] * 253, days[-1], ['1'] * 12, '5'), 2)
        for values, gross, price in [(['10'] * 252, ['1'] * 12, '10'),
                                     (['10'] * 253, ['1'] * 12, '0'),
                                     (['10'] * 253, ['2'] * 12, '10'),
                                     (['0'] + ['10'] * 252, ['1'] * 12, '10')]:
            with self.assertRaises(ValueError):
                check_series(days, values, days[-1], gross, price)


if __name__ == '__main__':
    unittest.main()
