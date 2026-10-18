from copy import deepcopy
from decimal import localcontext, Inexact, ROUND_DOWN
from fractions import Fraction
import unittest
from unittest.mock import patch
from backtest import ndx_new_cash_target_selection_research as module


def fixture():
    inputs = dict(cash_event=dict(decision_date='2023-04-28', execution_date='2023-05-01', amount_usd='100'),
                  starting_cash_usd='100', holdings={sid: 10 for sid in 'ABCD'},
                  securities={sid: dict(issuer_id=sid, risk_chain=sid) for sid in 'ABCD'},
                  execution_prices={sid: '10' for sid in 'ABCD'}, branches=[dict(branch_id='lane', buy_limits={'A': 2})],
                  risk_parameters=dict(zip(module.kernel.RISK_KEYS, ('.45', '.05', '.8', '.7', '.55'))),
                  transaction_cost_bps='10', minimum_cash_buffer_usd='100', max_evaluations=10)
    return inputs, {'lane': dict(A='4', B='2', C='2', D='2')}


def fraction(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


class TargetSelectionTests(unittest.TestCase):
    def test_exact_normalization_and_internal_full_evaluation_retained(self):
        inputs, targets = fixture()
        original = deepcopy((inputs, targets))
        result = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
        self.assertEqual((inputs, targets), original)
        selection = result['selections'][0]
        self.assertEqual(fraction(selection['original_target_sum']), 10)
        self.assertEqual(selection['selected']['buy_shares'], {'A': 2})
        self.assertEqual(selection['selected']['positive_holding_count'], 4)
        self.assertEqual(len(result['evaluation']['branches'][0]['candidates']), 3)
        self.assertEqual(fraction(selection['selected']['target_l1_distance']), Fraction(8, 35))

    def test_old_out_of_target_stock_counts_cash_does_not(self):
        inputs, _ = fixture()
        targets = {'lane': {'A': '1'}}
        first = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
        inputs['starting_cash_usd'] = '1000000'
        second = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
        self.assertEqual(first['selections'][0]['feasible_candidate_scores'], second['selections'][0]['feasible_candidate_scores'])
        self.assertEqual(first['selections'][0]['selected']['buy_shares'], second['selections'][0]['selected']['buy_shares'])
        self.assertEqual(first['selections'][0]['absent_target_sids_assigned_zero'], ['B', 'C', 'D'])
        self.assertEqual(fraction(first['selections'][0]['selected']['target_l1_distance']), Fraction(10, 7))

    def test_exact_tie_uses_fee_then_original_rank(self):
        inputs, _ = fixture()
        inputs['branches'][0]['buy_limits'] = {'A': 1}
        targets = {'lane': dict(A='85', B='81', C='81', D='81')}
        for fee in ('10', '0'):
            inputs['transaction_cost_bps'] = fee
            result = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
            selection = result['selections'][0]
            self.assertEqual(selection['feasible_candidate_scores'][0]['target_l1_distance'], selection['feasible_candidate_scores'][1]['target_l1_distance'])
            self.assertEqual(selection['selected']['original_rank'], 0)

    def test_source_weight_sum_slightly_off_one_is_preserved_and_normalized(self):
        inputs, _ = fixture()
        target = {'lane': dict(A='0.25000000000000002', B='0.25', C='0.25', D='0.25')}
        selected = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=target)['selections'][0]
        self.assertEqual(selected['original_target_literals'], target['lane'])
        self.assertEqual(fraction(selected['original_target_sum']), Fraction('1.00000000000000002'))
        self.assertEqual(sum(fraction(value) for value in selected['normalized_target_weights'].values()), 1)

    def test_risk_issuer_and_budget_cannot_be_bypassed(self):
        inputs, targets = fixture()
        inputs['holdings'] = dict(A=100, B=1, C=1, D=1)
        result = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
        self.assertIsNone(result['selections'][0]['selected'])
        self.assertFalse(result['full_integer_space_infeasibility_claimed'])
        inputs, targets = fixture()
        inputs['max_evaluations'] = 0
        result = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
        self.assertEqual(result['selections'][0]['domain_status'], 'BUDGET_LIMITED')
        self.assertEqual(result['selections'][0]['unevaluated_count'], 3)
        self.assertIsNone(result['selections'][0]['selected'])

    def test_bad_target_maps_fail_before_kernel(self):
        inputs, targets = fixture()
        invalid = [{}, {'other': {'A': '1'}}, {'lane': {}}, {'lane': {'A': '0'}}, {'lane': {'UNKNOWN': '1'}},
                   {'lane': {'A': True}}, {'lane': {'A': 0.5}}, {'lane': {'A': '-1'}}, {'lane': {'A': 'NaN'}}]
        with patch.object(module.kernel, 'evaluate_branches', side_effect=AssertionError('must not evaluate')):
            for target in invalid:
                with self.subTest(target=target), self.assertRaises(ValueError):
                    module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=target)

    def test_inconsistent_feasible_flag_fails_closed(self):
        inputs, targets = fixture()
        result = module.kernel.evaluate_branches(**inputs)
        result['branches'][0]['candidates'][0]['financial_checks']['CASH_BUFFER'] = False
        with patch.object(module.kernel, 'evaluate_branches', return_value=result):
            with self.assertRaises(ValueError):
                module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)

    def test_hostile_decimal_context_does_not_change_result(self):
        inputs, targets = fixture()
        inputs['execution_prices']['A'] = '10.12345678901234567890123456789012345678'
        targets['lane']['A'] = '0.25000000000000002'
        expected = module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets)
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            self.assertEqual(module.select_target_plans(evaluation_inputs=inputs, target_weights_by_branch=targets), expected)


if __name__ == '__main__':
    unittest.main()
