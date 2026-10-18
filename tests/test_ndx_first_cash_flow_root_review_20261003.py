from copy import deepcopy
import unittest
from test_ndx_first_period_incumbent_cash_flow_paths_20261003 import fixture
from scripts import ndx_first_period_incumbent_cash_flow_paths_20261003 as wrapper
from backtest.ndx_incumbent_cash_flow_research import simulate_incumbent_cash_flow


class IndependentReview(unittest.TestCase):
    def test_risk_failure_is_observed_without_changing_control_orders(self):
        inputs, nominal, candidates, refs = fixture()
        nominal['original_risk_parameters']['max_single_weight'] = .1
        for row, candidate in zip(inputs['rows'], candidates['rows']):
            row['risk_parameters']['max_single_weight'] = '0.1'
            candidate['input_row'] = deepcopy(row)
        result = wrapper.assemble(inputs, nominal, candidates, refs, simulate_incumbent_cash_flow)
        for path in result['paths']:
            first = path['account']['executions'][0]
            self.assertEqual(first['status'], 'FILLED')
            self.assertFalse(first['actual_risk']['checks']['MAX_SINGLE_WEIGHT'])
            self.assertFalse(first['risk_is_order_gate'])

    def test_original_nonunit_weight_sum_is_preserved_in_preparation(self):
        inputs, nominal, _, refs = fixture()
        for decision in nominal['original_fixed_schedule']['schedule']:
            decision['targets']['A']['target_weight'] = .12
        prepared = wrapper.prepare_path(inputs['rows'][0], nominal, refs['nominal'])
        self.assertEqual(prepared['core_inputs']['fixed_weights']['A'], '0.12')
        self.assertEqual(prepared['core_inputs']['fixed_weights']['B'], '0.125')
        self.assertEqual(prepared['core_inputs']['initial']['holdings'], {})

    def test_candidate_flow_and_identity_cannot_be_silently_remapped(self):
        for attack in ('duplicate', 'pointer', 'fee'):
            inputs, nominal, candidates, refs = fixture()
            if attack == 'duplicate':
                candidates['rows'][1] = deepcopy(candidates['rows'][0])
            elif attack == 'pointer':
                candidates['rows'][0]['input_reference']['json_pointer'] = '/rows/1'
            else:
                candidates['rows'][0]['accounting_inputs']['transaction_cost_bps'] = '0'
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                wrapper.validate_candidates(inputs, candidates, nominal, refs)


if __name__ == '__main__':
    unittest.main()
