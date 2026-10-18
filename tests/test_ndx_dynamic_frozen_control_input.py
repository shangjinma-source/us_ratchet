import unittest
from scripts.ndx_dynamic_frozen_control_input import prepare_control


class FrozenControlInputTests(unittest.TestCase):
    def test_real_frozen_weights_and_calendar(self):
        result = prepare_control('ndx_cardinality_real_runner_p2_exact_v3/strict_technology/RETURN')
        self.assertEqual(result['opens'].shape, (294, 8))
        self.assertTrue(result['opens'].index.equals(result['closes'].index))
        self.assertEqual(len(result['schedule']), 14)
        self.assertLess(result['original_weights']['MU'], .05)
        self.assertLess(result['original_weights']['TSM'], .05)
        self.assertAlmostEqual(sum(result['original_weights'].values()), 1)
        first = result['schedule'][0]['targets']
        for row in result['schedule']:
            self.assertEqual(row['targets'], first)
            self.assertEqual(set(result['risk_chains'][row['decision_date']]), set(first))
        self.assertEqual(result['capital_usd'], 25000)
        self.assertFalse(result['risk_provenance']['promotion_allowed'])


if __name__ == '__main__':
    unittest.main()
