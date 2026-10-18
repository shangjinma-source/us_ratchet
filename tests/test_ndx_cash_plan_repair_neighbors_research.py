from copy import deepcopy
from itertools import product
import unittest
from backtest import ndx_cash_plan_repair_neighbors_research as module


class RepairNeighborTests(unittest.TestCase):
    def test_small_full_grid_independent_neighbor_definition(self):
        caps = {'C': 2, 'A': 2, 'B': 2}
        seed = {'A': 1, 'B': 1, 'C': 1}
        result = module.generate_repair_neighbors(buy_limits=caps, seed_plans=[seed], excluded_plans=[], max_generated_plans=100)
        actual = {tuple(row['buy_shares'][sid] for sid in 'ABC') for row in result['generated_plans']}
        expected = {coordinate for coordinate in product(range(3), repeat=3)
                    if 1 <= sum(value != 1 for value in coordinate) <= 2}
        self.assertEqual(actual, expected)
        self.assertEqual(result['total_move_attempts'], 18)
        self.assertEqual(len(actual), 18)
        self.assertNotIn((0, 0, 0), actual)

    def test_stable_order_provenance_and_budget_full_count(self):
        inputs = dict(buy_limits={'B': 2, 'A': 2}, seed_plans=[{'B': 1, 'A': 1}], excluded_plans=[], max_generated_plans=100)
        original = deepcopy(inputs)
        result = module.generate_repair_neighbors(**inputs)
        self.assertEqual(inputs, original)
        expected = [(0, 1), (2, 1), (1, 0), (1, 2), (0, 0), (0, 2), (2, 0), (2, 2)]
        self.assertEqual([tuple(row['buy_shares'][sid] for sid in 'AB') for row in result['generated_plans']], expected)
        inputs['max_generated_plans'] = 3
        prefix = module.generate_repair_neighbors(**inputs)
        self.assertEqual(prefix['generated_plans'], result['generated_plans'][:3])
        self.assertEqual(prefix['distinct_remaining_plan_count'], 8)
        self.assertEqual(prefix['ungenerated_plan_count'], 5)
        self.assertEqual(prefix['generated_plans'][0]['first_move_deltas'], {'A': -1})

    def test_overlap_exclusion_and_first_seed_provenance(self):
        result = module.generate_repair_neighbors(buy_limits={'A': 2}, seed_plans=[{'A': 0}, {'A': 2}], excluded_plans=[{'A': 1}], max_generated_plans=10)
        self.assertEqual(result['total_move_attempts'], 4)
        self.assertEqual(result['out_of_bounds_attempt_count'], 2)
        self.assertEqual(result['unique_excluded_coordinate_count'], 1)
        self.assertEqual(result['duplicate_valid_coordinate_attempt_count'], 1)
        self.assertEqual(result['generated_plans'], [])
        result = module.generate_repair_neighbors(buy_limits={'A': 2}, seed_plans=[{'A': 0}, {'A': 2}], excluded_plans=[], max_generated_plans=10)
        self.assertEqual(result['generated_plans'][0]['first_seed_index'], 0)
        self.assertEqual(result['generated_plans'][0]['first_move_deltas'], {'A': 1})

    def test_zero_caps_zero_budget_and_empty_domain(self):
        result = module.generate_repair_neighbors(buy_limits={'A': 0}, seed_plans=[{'A': 0}], excluded_plans=[], max_generated_plans=0)
        self.assertEqual(result['out_of_bounds_attempt_count'], 2)
        self.assertEqual(result['distinct_remaining_plan_count'], 0)
        result = module.generate_repair_neighbors(buy_limits={'A': 2}, seed_plans=[{'A': 1}], excluded_plans=[], max_generated_plans=0)
        self.assertEqual(result['distinct_remaining_plan_count'], 2)
        self.assertEqual(result['ungenerated_plan_count'], 2)
        self.assertFalse(result['full_integer_space_infeasibility_claimed'])
        result = module.generate_repair_neighbors(buy_limits={}, seed_plans=[{}], excluded_plans=[], max_generated_plans=0)
        self.assertEqual(result['total_move_attempts'], 0)

    def test_invalid_plan_and_resource_bounds(self):
        base = dict(buy_limits={'A': 2}, seed_plans=[{'A': 1}], excluded_plans=[], max_generated_plans=10)
        for key, value in [('seed_plans', [{'A': 1}, {'A': 1}]), ('seed_plans', [{'A': True}]),
                           ('seed_plans', [{'A': 1.0}]), ('seed_plans', [{'A': 3}]), ('seed_plans', [{}]),
                           ('excluded_plans', [{'A': -1}]), ('max_generated_plans', True), ('buy_limits', {'A': False})]:
            inputs = deepcopy(base)
            inputs[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                module.generate_repair_neighbors(**inputs)
        with self.assertRaises(ValueError):
            module.generate_repair_neighbors(buy_limits={str(i): 1 for i in range(71)},
                                             seed_plans=[{str(i): 0 for i in range(71)}], excluded_plans=[], max_generated_plans=1)


if __name__ == '__main__':
    unittest.main()
