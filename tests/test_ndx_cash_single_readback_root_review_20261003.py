"""Independent counterexamples for saved cash-plan verification."""
from copy import deepcopy
from fractions import Fraction
import unittest
from scripts import ndx_cash_topup_neighbor_single_evaluation_independent_readback_20261003 as reader


class ReviewTests(unittest.TestCase):
    def test_risk_tolerance_and_stock_denominator(self):
        securities = {s: {'issuer_id': s, 'risk_chain': s} for s in 'ABCD'}
        parameters = dict(zip(reader.RISK_KEYS, map(Fraction, ('.25', '.25', '.75', '1', '.25'))))
        result = reader.risk(dict.fromkeys('ABCD', 1), dict.fromkeys('ABCD', 10), securities, parameters)
        self.assertTrue(result['all_passed'])
        self.assertEqual(result['effective_n'], '4')
        self.assertEqual(result['weights'], dict.fromkeys('ABCD', '1/4'))
        securities['B']['risk_chain'] = 'A'
        result = reader.risk(dict.fromkeys('ABCD', 1), dict.fromkeys('ABCD', 10), securities, parameters)
        self.assertFalse(result['checks']['RISK_CHAIN_TOP1_WEIGHT'])
        self.assertTrue(all(v for k, v in result['checks'].items() if k != 'RISK_CHAIN_TOP1_WEIGHT'))

    def test_all_cash_is_not_risk_pass_and_zero_slot_not_issuer_conflict(self):
        securities = {s: {'issuer_id': 'same', 'risk_chain': 'same'} for s in 'AB'}
        parameters = dict(zip(reader.RISK_KEYS, map(Fraction, ('.45', '.05', '.8', '.7', '.55'))))
        result = reader.risk({'A': 0, 'B': 0}, {'A': 1, 'B': 2}, securities, parameters)
        self.assertEqual(result['reason'], 'ALL_CASH')
        self.assertIsNone(result['effective_n'])
        self.assertFalse(result['all_passed'])
        self.assertEqual(reader.conflicts({'A': 1, 'B': 0}, securities), {})
        self.assertEqual(reader.conflicts({'A': 1, 'B': 1}, securities), {'same': ['A', 'B']})

    def test_exact_fee_buffer_boundary_and_cash_flow_adjustment(self):
        a = dict(cash_event=dict(decision_date='2023-03-31', execution_date='2023-04-03', amount_usd='1'),
                 starting_cash_usd='100', holdings=dict.fromkeys('ABCD', 1),
                 execution_prices=dict.fromkeys('ABCD', '1'),
                 securities={s: dict(issuer_id=s, risk_chain=s) for s in 'ABCD'},
                 risk_parameters=dict(zip(reader.RISK_KEYS, ('.6', '.05', '.9', '.7', '.6'))),
                 transaction_cost_bps='10', minimum_cash_buffer_usd='99.999',
                 branches=[dict(branch_id='review', buy_limits=dict.fromkeys('ABCD', 1))], max_evaluations=1)
        args = dict(evaluation_inputs=a, plans_by_branch={'review': [dict(A=1, B=0, C=0, D=0)]})
        p = reader.independent_result(args)['branches'][0]['evaluated_plans'][0]
        self.assertEqual(p['cash_after_usd'], '99.999')
        self.assertEqual(p['cash_flow_adjusted_pnl_usd'], '-0.001')
        self.assertTrue(p['feasible'])
        changed = deepcopy(args)
        changed['evaluation_inputs']['minimum_cash_buffer_usd'] = '99.99900000000000000001'
        p = reader.independent_result(changed)['branches'][0]['evaluated_plans'][0]
        self.assertFalse(p['feasible'])
        self.assertFalse(p['financial_checks']['CASH_BUFFER'])
        self.assertTrue(p['financial_checks']['NONNEGATIVE_CASH'])


if __name__ == '__main__':
    unittest.main()
