import unittest
from backtest.ndx_fractional_research_gates import fractional_research_gates


class FractionalGatesTests(unittest.TestCase):
    def fixture(self):
        return dict(metrics=dict(issuer_top1=.25, weight_top3_max=.75, risk_chain_top1=.25,
            effective_n_min=4., portfolio_min_median_dollar_volume_usd=1e8,
            declared_max_single_passed=True, declared_security_top3_weight_passed=True,
            declared_risk_chain_top1_weight_passed=True, declared_effective_n_passed=True,
            liquidity_constraint_passed=True), contract=dict(max_single_weight=.45, top_weight_cap=.8,
            risk_chain_top1_cap=.55, minimum_effective_n_ratio=.7, minimum_median_dollar_volume_usd=5e7),
            holding_count=4)

    def test_fractional_only_no_whole_lot_fabrication(self):
        result = fractional_research_gates(**self.fixture())
        self.assertTrue(result['fractional_risk_passed'])
        self.assertIsNone(result['technology_scope_passed'])
        self.assertNotIn('historical_whole_lot_passed', result)
        self.assertFalse(result['current_whole_lot_execution_verified'])

    def test_numerical_failure_is_retained(self):
        inputs = self.fixture()
        inputs['metrics']['risk_chain_top1'] = .75
        inputs['metrics']['declared_risk_chain_top1_weight_passed'] = False
        self.assertFalse(fractional_research_gates(**inputs)['fractional_risk_passed'])

    def test_boolean_and_false_saved_gate_rejected(self):
        for key, value in [('effective_n_min', True), ('declared_max_single_passed', 1),
                           ('declared_max_single_passed', False), ('issuer_top1', -1)]:
            inputs = self.fixture()
            inputs['metrics'][key] = value
            with self.assertRaises(ValueError):
                fractional_research_gates(**inputs)

    def test_stored_thresholds_bind_contract_even_when_gates_agree(self):
        inputs = self.fixture()
        inputs['metrics'].update(declared_max_single_weight=.45,
            declared_security_top3_weight_cap=.8, declared_risk_chain_top1_weight_cap=.55,
            declared_minimum_effective_n=2.8, minimum_median_dollar_volume_usd=5e7)
        self.assertTrue(fractional_research_gates(**inputs)['fractional_risk_passed'])
        inputs['metrics']['declared_max_single_weight'] = .5
        with self.assertRaisesRegex(ValueError, 'threshold differs'):
            fractional_research_gates(**inputs)
        inputs['metrics'].pop('declared_minimum_effective_n')
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            fractional_research_gates(**inputs)


if __name__ == '__main__':
    unittest.main()
