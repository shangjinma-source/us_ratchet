from copy import deepcopy
import unittest
from test_ndx_first_period_incumbent_cash_flow_independent_readback_20261003 import documents
from scripts import ndx_first_period_incumbent_cash_flow_independent_readback_20261003 as reader


class ReviewTests(unittest.TestCase):
    def test_frozen_open_execution_not_replaced_by_a_cheaper_plan(self):
        args = documents()
        execution = args['account']['paths'][0]['account']['executions'][0]
        execution['frozen_delta']['A'] -= 1
        with self.assertRaises(AssertionError):
            reader.inspect_saved(**args)

    def test_terminal_cash_and_injection_are_independent_quantities(self):
        for field in ('terminal_equity_usd', 'total_cash_injection_usd', 'total_fees_usd'):
            args = documents()
            args['account']['paths'][0]['account'][field] = '0'
            with self.subTest(field=field), self.assertRaises(AssertionError):
                reader.inspect_saved(**args)

    def test_risk_observation_cannot_be_hidden_on_a_control(self):
        args = documents()
        risk = args['account']['paths'][0]['account']['daily'][0]['risk']
        risk['risk_chain_weights'] = {}
        with self.assertRaises(AssertionError):
            reader.inspect_saved(**args)
        args = documents()
        args['account']['paths'][0]['account']['risk_is_order_gate'] = True
        with self.assertRaises(AssertionError):
            reader.inspect_saved(**args)


if __name__ == '__main__':
    unittest.main()
