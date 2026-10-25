from copy import deepcopy
import unittest

from backtest import quantity_anchor_coupled_completion as completion
from backtest.quantity_coupled_frontier_partition import verify
from test_quantity_anchor_coupled_completion import fixture


class FrontierPartitionTests(unittest.TestCase):
    def test_every_budget_boundary_preserves_all_suffixes(self):
        sources, _ = fixture(seed={'B': 2})
        full = completion.build(**sources)['coupled']
        for budget in range(full['visited_nodes'] + 2):
            certificate = completion.build(**sources, node_budget=budget)['coupled']
            before = deepcopy(certificate)
            result = verify(certificate)
            self.assertEqual(result['closed_patterns'] + result['pending_patterns'], result['total_patterns'])
            self.assertEqual(result['pending_patterns'] == 0, certificate['domain_complete'])
            self.assertFalse(result['numerical_proofs_verified'])
            self.assertEqual(certificate, before)

    def test_missing_duplicate_reordered_and_boolean_frontier_rejected(self):
        sources, _ = fixture()
        certificate = completion.build(**sources, node_budget=1)['coupled']
        self.assertGreater(len(certificate['unsearched_frontier']), 1)
        frontier = certificate['unsearched_frontier']
        variants = [frontier[:-1], frontier + [frontier[-1]], list(reversed(frontier)), [[True]]]
        for bad in variants:
            changed = deepcopy(certificate)
            changed['unsearched_frontier'] = bad
            with self.assertRaises(ValueError):
                verify(changed)

    def test_false_completion_and_missing_or_repeated_ledger_rejected(self):
        sources, _ = fixture()
        certificate = completion.build(**sources)['coupled']
        changes = [('ledger', certificate['ledger'][1:]),
                   ('ledger', certificate['ledger'] + certificate['ledger'][-1:]),
                   ('domain_complete', False), ('visited_nodes', True), ('checked_points', -1)]
        for key, bad in changes:
            changed = deepcopy(certificate)
            changed[key] = bad
            with self.assertRaises(ValueError):
                verify(changed)


if __name__ == '__main__':
    unittest.main()
