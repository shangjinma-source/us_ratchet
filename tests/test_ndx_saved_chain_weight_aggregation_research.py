import unittest
from backtest import ndx_saved_chain_weight_aggregation_research as module


class Tests(unittest.TestCase):
    def test_decimal_roundoff_preserved_without_renormalization(self):
        result = module.aggregate_saved_weights(session='2026-04-02',
            weights={'a': 0.1, 'b': 0.2, 'c': 0.6999999999999998},
            chains={'a': 'X', 'b': 'X', 'c': 'Y'}, observation_dates=dict.fromkeys(('a','b','c'), '2026-04-01'))
        self.assertEqual(result['chain_weights']['X'], dict(numerator='3', denominator='10'))
        self.assertEqual(result['total_saved_weight'], dict(numerator='4999999999999999', denominator='5000000000000000'))
        self.assertFalse(result['normalization_performed'])

    def test_empty_is_undefined_and_invalid_original_evidence_rejected(self):
        empty = module.aggregate_saved_weights(session='2026-04-02', weights={}, chains={}, observation_dates={})
        self.assertIsNone(empty['maximum_chain_weight'])
        for bad in (True, -0.1, 1.1, float('nan'), '0.2', 0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.aggregate_saved_weights(session='2026-04-02', weights={'a':bad}, chains={'a':'X'}, observation_dates={'a':'2026-04-01'})
        with self.assertRaises(ValueError):
            module.aggregate_saved_weights(session='2026-04-02', weights={'a':1}, chains={'a':'X'}, observation_dates={'a':'2026-04-03'})


if __name__ == '__main__':
    unittest.main()
