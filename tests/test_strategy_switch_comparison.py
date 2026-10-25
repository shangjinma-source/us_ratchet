import unittest
from core.strategy_switch_comparison import compare_switch


class SwitchComparisonTests(unittest.TestCase):
    def compare(self, **changes):
        arguments = dict(cash='100', holdings={'A': 10}, candidate={'B': 10}, prices={'A': '10', 'B': '10'},
                         scenarios=[{'A': '1', 'B': '2'}], scenario_dates=['2026-10-01'],
                         decision_date='2026-10-23', slippage_bps='0')
        arguments.update(changes)
        return compare_switch(**arguments)

    def test_shared_capital_and_turnover(self):
        result = self.compare(slippage_bps='100')
        self.assertEqual(result['equity'], '200')
        self.assertEqual(result['candidate_cash'], '98')
        self.assertEqual(result['slippage_cost'], '2')
        self.assertEqual(result['ranking'], 'CANDIDATE_HIGHER')

    def test_identical_portfolio_has_no_cost_and_ties(self):
        result = self.compare(candidate={'A': 10}, slippage_bps='100')
        self.assertEqual(result['slippage_cost'], '0')
        self.assertEqual(result['ranking'], 'TIE')

    def test_slippage_can_reverse_preference(self):
        result = self.compare(scenarios=[{'A': '1', 'B': '1.01'}], slippage_bps='100')
        self.assertEqual(result['ranking'], 'HOLD_HIGHER')

    def test_overspending_is_not_scored(self):
        result = self.compare(candidate={'B': 21})
        self.assertEqual(result['ranking'], 'UNAFFORDABLE')
        self.assertIsNone(result['candidate'])

    def test_invalid_evidence_rejected(self):
        for changes in [dict(scenario_dates=['2026-10-24']), dict(scenarios=[{'B': '2'}]),
                        dict(candidate={'B': True}), dict(slippage_bps='10000')]:
            with self.assertRaises(ValueError):
                self.compare(**changes)


if __name__ == '__main__':
    unittest.main()
