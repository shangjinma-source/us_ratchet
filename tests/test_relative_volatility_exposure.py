import unittest
from scripts.diagnose_relative_volatility_exposure import multipliers


class ExposureTests(unittest.TestCase):
    def test_flat_and_high_recent_risk(self):
        self.assertEqual(multipliers([0.] * 252)['relative_multiplier'], 1)
        result = multipliers([0.] * 230 + [-.1, .1] * 11)
        self.assertGreater(result['relative_multiplier'], 0)
        self.assertLess(result['relative_multiplier'], 1)

    def test_no_leverage_or_incomplete_window(self):
        result = multipliers([-.1, .1] * 115 + [0.] * 22)
        self.assertEqual(result['relative_multiplier'], 1)
        with self.assertRaises(ValueError):
            multipliers([0.] * 251)


if __name__ == '__main__':
    unittest.main()
