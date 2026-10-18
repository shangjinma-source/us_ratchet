"""Prove small support enumeration against independent combinations."""
from fractions import Fraction as F
from itertools import combinations
import unittest

from backtest.affordable_support_seeds import affordable_support_seeds


class SupportSeedTests(unittest.TestCase):
    def test_complete_unique_affordable_issuer_supports_and_cash(self):
        names = ['D', 'B', 'A', 'E', 'C']
        metadata = {sid: {'issuer_id': 'AB' if sid in 'AB' else sid} for sid in names}
        costs = dict(zip(names, map(F, [7, 3, 2, 13, 5])))
        for cash in map(F, [1, 5, 12, 30]):
            for k in range(1, 6):
                expected = {tuple(sorted(group)) for group in combinations(names, k)
                            if len({metadata[sid]['issuer_id'] for sid in group}) == k
                            and sum(costs[sid] for sid in group) <= cash}
                rows = list(affordable_support_seeds(ordered_sids=names, metadata=metadata,
                                                     unit_costs=costs, spendable=cash, k=k))
                actual = [tuple(sorted(row)) for row in rows]
                self.assertEqual(set(actual), expected)
                self.assertEqual(len(actual), len(set(actual)))
                for row in rows:
                    self.assertTrue(all(type(q) is int and q > 0 for q in row.values()))
                    self.assertLessEqual(sum(costs[sid]*q for sid, q in row.items()), cash)

    def test_fractional_cost_boundary_and_empty_domain(self):
        args = dict(ordered_sids=['A', 'B'], metadata={sid: {'issuer_id': sid} for sid in 'AB'},
                    unit_costs={'A': F(101, 100), 'B': F(202, 100)}, k=2)
        self.assertEqual(list(affordable_support_seeds(**args, spendable=F(303, 100))), [{'A': 1, 'B': 1}])
        self.assertEqual(list(affordable_support_seeds(**args, spendable=F(302, 100))), [])
        self.assertEqual(list(affordable_support_seeds(ordered_sids=[], metadata={}, unit_costs={}, spendable=F(10), k=1)), [])


if __name__ == '__main__':
    unittest.main()
