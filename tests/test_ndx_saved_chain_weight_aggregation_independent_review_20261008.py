"""Independent exact-decimal and missing-evidence boundary checks."""
import unittest
from backtest import ndx_saved_chain_weight_aggregation_research as module


class ReviewTests(unittest.TestCase):
    def test_saved_total_is_not_renormalized_and_zero_sid_is_preserved(self):
        result = module.aggregate_saved_weights(session='2026-04-02',
            weights={'a': .7, 'b': .3000000000000001, 'zero': 0},
            chains={'a': 'X', 'b': 'X', 'zero': 'Z'},
            observation_dates={'a': '2026-04-02', 'b': '2026-03-01', 'zero': '2026-04-01'})
        self.assertEqual(result['total_saved_weight'], {'numerator': '10000000000000001', 'denominator': '10000000000000000'})
        self.assertEqual(result['maximum_chain_weight'], result['total_saved_weight'])
        self.assertEqual(result['chain_weights']['Z'], {'numerator': '0', 'denominator': '1'})
        for name in ('normalization_performed', 'original_saved_chain_aggregate',
                     'order_gate_evaluated', 'account_executed', 'promotion_allowed'):
            self.assertIs(result[name], False)

    def test_missing_weights_or_sid_labels_cannot_become_empty(self):
        base = dict(session='2026-04-02', weights={'sid': 1}, chains={'sid': 'X'},
                    observation_dates={'sid': '2026-04-01'})
        for name in ('weights', 'chains', 'observation_dates'):
            for value in (None, {}, {'other': 1}):
                with self.subTest(name=name, value=value), self.assertRaises((ValueError, TypeError)):
                    module.aggregate_saved_weights(**{**base, name: value})
        with self.assertRaises(TypeError):
            module.aggregate_saved_weights(session='2026-04-02', chains={}, observation_dates={})


if __name__ == '__main__': unittest.main()
