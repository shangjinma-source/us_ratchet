"""Small synthetic tests only: no market sources or strategy books."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities


def inputs():
    return dict(prices={'A': 10, 'B': 20, 'C': 30},
                metadata={sid: dict(ticker=sid, issuer_id=sid) for sid in 'ABC'},
                entered_cash=100, fee_bps=0, minimum_cash_buffer=0,
                training_scenarios=[{'A': '1.01', 'B': '1.2', 'C': '.9'}],
                scenario_dates=['2026-01-01'], decision_date='2026-01-02',
                max_objective_evaluations=150, fixed_seed='synthetic')


class FreshCashQuantityTests(unittest.TestCase):
    def test_all_k_quantity_composition_and_single_stock_full_allocation(self):
        args = inputs(); before = deepcopy(args)
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(args, before)
        self.assertEqual(result, search_fresh_cash_quantities(**args))
        self.assertEqual(result['selected']['quantities'], {'B': 5})
        self.assertEqual(result['selected']['residual_cash'], '0')
        self.assertEqual(result['selected']['actual_weights'], {'B': '1'})
        self.assertTrue(all(row['initialized'] for row in result['per_k']))
        self.assertGreater(result['per_k'][0]['visited_supports'], 1)
        self.assertLessEqual(result['objective_evaluations'], 150)
        self.assertFalse(result['global_optimum_established'])

    def test_non_equal_weights_are_optimized(self):
        args = inputs()
        args['prices'] = {'A': 10, 'B': 20}
        args['metadata'].pop('C')
        args['training_scenarios'] = [{'A': 2, 'B': '.5'}, {'A': '.5', 'B': 2}]
        args['scenario_dates'] = ['2026-01-01', '2026-01-02']
        result = search_fresh_cash_quantities(**args)
        weights = result['selected']['actual_weights']
        self.assertEqual(set(weights), {'A', 'B'})
        self.assertNotEqual(weights['A'], weights['B'])
        self.assertGreater(Fraction(result['selected']['training_gross_growth_product']), 1)

    def test_class_swap_unique_issuer_and_fee_cash_identity(self):
        args = inputs()
        args['metadata']['B']['issuer_id'] = 'A'
        args.update(fee_bps=10, minimum_cash_buffer=5)
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(len(result['per_k']), 2)
        self.assertIn('B', result['selected']['quantities'])
        for row in result['best_by_k'].values():
            self.assertFalse({'A', 'B'} <= set(row['quantities']))
            self.assertEqual(sum(Fraction(row[key]) for key in ('notional', 'fees', 'residual_cash')), 100)
            self.assertGreaterEqual(Fraction(row['residual_cash']), 5)

    def test_budget_coverage_and_structural_unaffordability(self):
        args = inputs(); args['max_objective_evaluations'] = 4
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['objective_evaluations'], 4)
        self.assertEqual(result['status'], 'BUDGET_STOPPED')
        self.assertTrue(result['all_affordable_k_initialized'])
        args['max_objective_evaluations'] = 3
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['status'], 'INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION')
        self.assertIsNone(result['selected'])
        args.update(entered_cash=15, max_objective_evaluations=20)
        result = search_fresh_cash_quantities(**args)
        self.assertEqual([row['structural_status'] for row in result['per_k']],
                         ['AFFORDABLE', 'UNAFFORDABLE_CHEAPEST_ISSUER_BOUND', 'UNAFFORDABLE_CHEAPEST_ISSUER_BOUND'])
        args['minimum_cash_buffer'] = 100
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['selected']['quantities'], {})
        self.assertEqual(result['selected']['residual_cash'], '15')

    def test_maturity_missing_data_and_invalid_inputs_fail_closed(self):
        for change in ({'scenario_dates': ['2026-01-03']},
                       {'training_scenarios': [{'A': 1, 'B': 1}]},
                       {'training_scenarios': [{'A': 1, 'B': 0, 'C': 1}]},
                       {'entered_cash': True}, {'fee_bps': float('nan')}):
            args = inputs(); args.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                search_fresh_cash_quantities(**args)


if __name__ == '__main__':
    unittest.main()
