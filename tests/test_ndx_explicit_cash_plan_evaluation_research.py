from copy import deepcopy
from decimal import Inexact, localcontext
import unittest
from unittest.mock import patch
from backtest import ndx_explicit_cash_plan_evaluation_research as module


def fixture():
    return dict(cash_event=dict(decision_date='2023-04-28', execution_date='2023-05-01', amount_usd='100'),
                starting_cash_usd='100', holdings={sid: 10 for sid in 'ABCD'},
                securities={sid: dict(issuer_id=sid, risk_chain=sid) for sid in 'ABCD'}, execution_prices={sid: '10' for sid in 'ABCD'},
                branches=[dict(branch_id='first', buy_limits={'A': 2}), dict(branch_id='second', buy_limits={'B': 1})],
                risk_parameters=dict(zip(module.kernel.RISK_KEYS, ('.45', '.05', '.8', '.7', '.55'))),
                transaction_cost_bps='10', minimum_cash_buffer_usd='100', max_evaluations=10)


class ExplicitPlanTests(unittest.TestCase):
    def test_matches_existing_kernel_financial_risk_and_preserves_order(self):
        inputs = fixture()
        plans = {'first': [{'A': 2}, {'A': 0}], 'second': [{'B': 1}]}
        original = deepcopy((inputs, plans))
        reference = module.kernel.evaluate_branches(**inputs)
        result = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch=plans)
        self.assertEqual((inputs, plans), original)
        self.assertEqual(result['cartesian_candidate_count'], 5)
        self.assertEqual(result['supplied_plan_count'], 3)
        for i, branch in enumerate(result['branches']):
            for row in branch['evaluated_plans']:
                expected = reference['branches'][i]['candidates'][row['original_cartesian_rank']]
                self.assertEqual({k: v for k, v in row.items() if k not in ('supplied_plan_index', 'original_cartesian_rank')},
                                 {k: v for k, v in expected.items() if k != 'rank'})

    def test_validation_zero_once_global_budget_and_suffix_preserved(self):
        inputs = fixture()
        inputs['max_evaluations'] = 1
        plans = {'first': [{'A': 2}, {'A': 0}], 'second': [{'B': 1}]}
        original = module.kernel.evaluate_branches
        with patch.object(module.kernel, 'evaluate_branches', wraps=original) as called:
            result = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch=plans)
            self.assertEqual(called.call_count, 1)
            self.assertEqual(called.call_args.kwargs['max_evaluations'], 0)
        self.assertEqual(result['evaluated_count'], 1)
        self.assertEqual(result['unevaluated_supplied_plan_count'], 2)
        self.assertEqual(result['branches'][1]['supplied_plans'][0]['buy_shares'], {'B': 1})
        self.assertEqual(result['branches'][1]['evaluated_plans'], [])
        self.assertFalse(result['full_integer_space_infeasibility_claimed'])

    def test_duplicate_cap_bool_and_sid_mismatch_fail_even_outside_budget(self):
        for first in ([{'A': 0}, {'A': 0}], [{'A': 3}], [{'A': True}], [{'A': 1.0}], [{'B': 1}], [{}]):
            inputs = fixture()
            inputs['max_evaluations'] = 0
            with self.subTest(first=first), self.assertRaises(ValueError):
                module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch={'first': first, 'second': []})
        inputs = fixture()
        inputs['max_evaluations'] = True
        with self.assertRaises(ValueError):
            module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch={'first': [], 'second': []})

    def test_empty_supplied_set_and_cash_control(self):
        inputs = fixture()
        result = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch={'first': [], 'second': []})
        self.assertEqual(result['evaluated_count'], 0)
        self.assertEqual(result['cartesian_candidate_count'], 5)
        inputs.update(holdings={}, securities={}, execution_prices={}, branches=[dict(branch_id='cash', buy_limits={})])
        result = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch={'cash': [{}]})
        row = result['branches'][0]['evaluated_plans'][0]
        self.assertEqual(row['risk']['reason'], 'ALL_CASH')
        self.assertFalse(row['feasible'])

    def test_hostile_context_long_values(self):
        inputs = fixture()
        inputs['execution_prices']['A'] = '10.12345678901234567890123456789'
        inputs['starting_cash_usd'] = '1478.4820750045776'
        plans = {'first': [{'A': 2}], 'second': [{'B': 1}]}
        expected = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch=plans)
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = True
            self.assertEqual(module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch=plans), expected)

    def test_complete_old_holdings_issuer_conflict_and_fee_buffer(self):
        inputs = fixture()
        inputs['securities']['B']['issuer_id'] = 'A'
        result = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch={'first': [{'A': 0}], 'second': []})
        row = result['branches'][0]['evaluated_plans'][0]
        self.assertEqual(row['issuer_conflicts'], {'A': ['A', 'B']})
        self.assertFalse(row['feasible'])
        inputs = fixture()
        inputs['starting_cash_usd'] = '0'
        result = module.evaluate_explicit_plans(evaluation_inputs=inputs, plans_by_branch={'first': [{'A': 2}], 'second': []})
        row = result['branches'][0]['evaluated_plans'][0]
        self.assertFalse(row['financial_checks']['CASH_BUFFER'])
        self.assertEqual(row['fees_usd'], '0.02')


if __name__ == '__main__':
    unittest.main()
