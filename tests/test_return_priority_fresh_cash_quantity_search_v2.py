"""Synthetic coverage and independent exhaustive objective checks; no market runs."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import unittest

from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities


def inputs():
    return dict(prices={'A': 2, 'B': 3, 'C': 4},
                metadata={sid: dict(ticker=sid, issuer_id=sid) for sid in 'ABC'},
                entered_cash=12, fee_bps=0, minimum_cash_buffer=0,
                training_scenarios=[{'A': 2, 'B': '.5', 'C': '1.1'},
                                    {'A': '.5', 'B': 2, 'C': '1.1'}],
                scenario_dates=['2026-01-01', '2026-01-02'], decision_date='2026-01-02',
                max_objective_evaluations=400, fixed_seed='synthetic-v2')


def exhaustive_best(arguments):
    names = sorted(arguments['prices'])
    cash = F(arguments['entered_cash'])
    fee = F(arguments['fee_bps']) / 10000
    buffer = F(arguments['minimum_cash_buffer'])
    best = None
    for quantities in product(*(range(int(cash // F(arguments['prices'][sid])) + 1) for sid in names)):
        q = {sid: n for sid, n in zip(names, quantities) if n}
        if len({arguments['metadata'][sid]['issuer_id'] for sid in q}) != len(q):
            continue
        notional = sum((F(arguments['prices'][sid]) * n for sid, n in q.items()), F(0))
        residual = cash-notional*(1+fee)
        if residual < 0 or (q and residual < buffer):
            continue
        growth = F(1)
        for scenario in arguments['training_scenarios']:
            growth *= (residual+sum((F(arguments['prices'][sid])*n*F(str(scenario[sid]))
                                    for sid, n in q.items()), F(0)))/cash
        candidate = (growth, -notional, tuple(sorted(q.items())))
        if best is None or candidate > best:
            best = candidate
    return dict(best[2])


class CoverageV2Tests(unittest.TestCase):
    def test_support_enumeration_completion_is_not_quantity_completion(self):
        result = search_fresh_cash_quantities(**inputs())
        # All three pair supports and the triple are affordable in this fixture.
        self.assertEqual(result['local_search_budget_by_k']['2']['support_seeds_emitted'], 3)
        self.assertEqual(result['local_search_budget_by_k']['3']['support_seeds_emitted'], 1)
        for lane in result['local_search_budget_by_k'].values():
            self.assertTrue(lane['support_enumeration_complete'])
            self.assertFalse(lane['all_integer_quantities_enumerated'])
            self.assertLessEqual(lane['support_seed_objective_evaluations'], lane['used'])

    def test_exact_single_quantity_interior_optimum(self):
        args = inputs()
        args.update(prices={'A': 1}, metadata={'A': dict(ticker='A', issuer_id='A')},
                    entered_cash=100, training_scenarios=[{'A': 2}, {'A': '.5'}])
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['selected']['quantities'], {'A': 50})
        self.assertEqual(result['single_security_optima']['A']['quantity'], 50)
        self.assertTrue(result['single_security_quantity_optimum_established'])
        self.assertFalse(result['global_optimum_established'])

    def test_single_integer_search_matches_exhaustive_grid(self):
        cases = 0
        for cash in [3, 11, 24]:
            for price in [1, 2, 5]:
                for fee in [0, 125]:
                    for relatives in [('.2', '3'), ('1', '1'), ('1.1', '2'), ('.1', '.9')]:
                        args = inputs()
                        args.update(prices={'A': price}, metadata={'A': dict(ticker='A', issuer_id='A')},
                                    entered_cash=cash, fee_bps=fee,
                                    training_scenarios=[{'A': relatives[0]}, {'A': relatives[1]}])
                        result = search_fresh_cash_quantities(**args)
                        self.assertEqual(result['selected']['quantities'], exhaustive_best(args), args)
                        if 'A' in result['single_security_optima']:
                            maximum = result['single_security_optima']['A']['maximum_affordable']
                            def growth(q):
                                residual = F(cash)-q*F(price)*(1+F(fee)/10000)
                                return (residual+q*price*F(relatives[0]))*(residual+q*price*F(relatives[1]))
                            expected = max(range(1, maximum+1), key=lambda q: (growth(q), -q))
                            self.assertEqual(result['single_security_optima']['A']['quantity'], expected)
                        cases += 1
        self.assertEqual(cases, 72)

    def test_101_security_pool_has_no_single_support_starvation(self):
        args = inputs()
        names = ['S'+str(index) for index in range(101)]
        args.update(prices={sid: 10 for sid in names},
                    metadata={sid: dict(ticker=sid, issuer_id=sid) for sid in names},
                    training_scenarios=[{sid: '1.01' for sid in names}],
                    scenario_dates=['2026-01-01'], entered_cash=2000,
                    max_objective_evaluations=1)
        preflight = search_fresh_cash_quantities(**args)
        args['max_objective_evaluations'] = preflight['required_evaluation_budget']
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['per_k'][0]['visited_supports'], 101)
        self.assertEqual(len(result['per_k']), 101)
        self.assertTrue(all(row['initialized'] for row in result['per_k']))

    def test_all_single_supports_at_exact_mandatory_budget(self):
        args = inputs()
        first = search_fresh_cash_quantities(**args)
        args['max_objective_evaluations'] = first['required_evaluation_budget']
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['per_k'][0]['visited_supports'], 3)
        self.assertTrue(result['all_affordable_single_security_supports_initialized'])
        self.assertTrue(all(row['initialized'] for row in result['per_k']))
        self.assertLessEqual(result['objective_evaluations'], result['required_evaluation_budget'])
        args['max_objective_evaluations'] -= 1
        rejected = search_fresh_cash_quantities(**args)
        self.assertEqual(rejected['objective_evaluations'], 0)
        self.assertIsNone(rejected['selected'])

    def test_budget_lanes_determinism_and_no_mutation(self):
        args = inputs(); args['max_objective_evaluations'] = 40
        before = deepcopy(args)
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(args, before)
        self.assertEqual(result, search_fresh_cash_quantities(**args))
        lanes = result['local_search_budget_by_k'].values()
        allocations = [lane['allocated'] for lane in lanes]
        self.assertLessEqual(max(allocations)-min(allocations), 1)
        self.assertEqual(sum(allocations)+result['mandatory_evaluations']+result['single_security_optimization_evaluations'], 40)
        self.assertEqual(sum(lane['used'] for lane in lanes)+result['mandatory_evaluations']+result['single_security_optimization_evaluations'], result['objective_evaluations'])
        self.assertTrue(all(0 <= lane['used'] <= lane['allocated'] for lane in lanes))
        self.assertFalse(result['global_optimum_established'])

    def test_small_domain_matches_independent_exhaustive_enumeration(self):
        for fee, buffer, shared in [(0, 0, False), (100, 1, False), (0, 0, True)]:
            args = inputs(); args.update(fee_bps=fee, minimum_cash_buffer=buffer)
            if shared:
                args['metadata']['B']['issuer_id'] = 'A'
            with self.subTest(fee=fee, buffer=buffer, shared=shared):
                result = search_fresh_cash_quantities(**args)
                self.assertEqual(result['selected']['quantities'], exhaustive_best(args))
                self.assertEqual(result['per_k'][0]['visited_supports'], 3)

    def test_no_affordable_stocks_and_exact_one_share(self):
        args = inputs(); args.update(entered_cash=1, max_objective_evaluations=1)
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['selected']['quantities'], {})
        self.assertEqual(result['local_search_budget_by_k'], {})
        args['entered_cash'] = 2; args['max_objective_evaluations'] = 2
        result = search_fresh_cash_quantities(**args)
        self.assertEqual(result['single_security_seed_quantities'], {'A': [1]})
        self.assertEqual(result['mandatory_evaluations'], 2)


if __name__ == '__main__':
    unittest.main()
