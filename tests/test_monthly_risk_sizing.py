import unittest
from core.monthly_risk_sizing import capped_monthly_quantities


class MonthlyRiskSizingTests(unittest.TestCase):
    def test_cap_leaves_cash_instead_of_redistributing(self):
        result = capped_monthly_quantities(equity='20000',
            weights={'A': '9/10', 'B': '1/10'}, decision_prices={'A': '100', 'B': '300'})
        self.assertEqual(result['target_quantities'], {'A': 100, 'B': 6})
        self.assertEqual(result['unallocated_cash'], '8200')

    def test_actual_equity_and_whole_share_floor(self):
        result = capped_monthly_quantities(equity='19999', weights={'A': '1'},
                                            decision_prices={'A': '100'})
        self.assertEqual(result['target_quantities'], {'A': 99})
        with self.assertRaises(ValueError):
            capped_monthly_quantities(equity='20000', weights={'A': '2'},
                                      decision_prices={'A': '100'})


if __name__ == '__main__':
    unittest.main()
