import unittest
from copy import deepcopy
from fractions import Fraction

from backtest import ndx_saved_holdings_risk_diagnostic_research as module


def value(item):
    return Fraction(int(item['numerator']), int(item['denominator']))


class Tests(unittest.TestCase):
    def test_known_concentration_chain_sum_and_no_mutation(self):
        labels = {sid: dict(label=chain, observation_session='2026-04-01')
                  for sid, chain in [('a', 'X'), ('b', 'X'), ('c', 'Y')]}
        arguments = dict(session='2026-04-02', shares={'a': 0.1, 'b': 0.2, 'c': 0.1},
                         close_prices={'a': 10, 'b': 10, 'c': 10}, labels=labels)
        before = deepcopy(arguments)
        result = module.derive_daily_diagnostic(**arguments)
        self.assertEqual(arguments, before)
        self.assertEqual(value(result['invested_value']), 4)
        self.assertEqual(value(result['metrics']['hhi']), Fraction(3, 8))
        self.assertEqual(value(result['metrics']['effective_n']), Fraction(8, 3))
        self.assertEqual(value(result['chain_weights']['X']), Fraction(3, 4))
        self.assertEqual(sum(map(value, result['security_weights'].values())), 1)
        self.assertFalse(result['order_gate_evaluated'])

    def test_empty_holdings_are_undefined_not_zero_risk(self):
        result = module.derive_daily_diagnostic(session='2026-04-01', shares={}, close_prices={}, labels={})
        self.assertIsNone(result['metrics'])
        self.assertEqual(result['status'], 'ALL_CASH_CONCENTRATION_UNDEFINED')

    def test_asof_is_per_security_and_future_never_backfills(self):
        observations = {'2026-04-01': {'a': 'X', 'b': 'Y'},
                        '2026-04-03': {'a': 'Z'}, '2026-04-04': {'c': 'W'}}
        labels = module.latest_labels(session='2026-04-03', security_ids=['a', 'b'], observations=observations)
        self.assertEqual(labels['a']['label'], 'Z')
        self.assertEqual(labels['b']['observation_session'], '2026-04-01')
        with self.assertRaises(ValueError):
            module.latest_labels(session='2026-04-03', security_ids=['c'], observations=observations)

    def test_invalid_values_and_future_label_rejected(self):
        for bad in (True, 0, -1, float('nan'), float('inf'), '1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.derive_daily_diagnostic(session='2026-04-01', shares={'a': bad}, close_prices={'a': 1},
                    labels={'a': dict(label='X', observation_session='2026-04-01')})
        with self.assertRaises(ValueError):
            module.derive_daily_diagnostic(session='2026-04-01', shares={'a': 1}, close_prices={'a': 1},
                labels={'a': dict(label='X', observation_session='2026-04-02')})


if __name__ == '__main__':
    unittest.main()
