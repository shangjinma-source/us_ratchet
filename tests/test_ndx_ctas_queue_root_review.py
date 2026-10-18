"""Independent small-set and fail-closed checks; no saved task materialization."""
from itertools import combinations, product
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_ctas_combination_materialize_20260925 as m


class Tests(unittest.TestCase):
    def test_every_forced_share_class_matches_sorted_small_oracle(self):
        groups = [('A', ['a0', 'a1']), ('B', ['b']), ('C', ['c0', 'c1']), ('D', ['d'])]
        lookup = {sid: (i, j) for i, (_, members) in enumerate(groups) for j, sid in enumerate(members)}
        for k in range(1, 5):
            full = []
            for chosen in combinations(groups, k):
                full.extend(list(row) for row in product(*(members for _, members in chosen)))
            full.sort(key=lambda row: [lookup[sid] for sid in row])
            for target in lookup:
                expected = [row for row in full if target in row]
                limit = min(2, len(expected))
                count, selected = m.forced_prefixes(groups, target, k, limit)
                self.assertEqual(count, len(expected))
                self.assertEqual([r['prefix_security_ids'] for r in selected], expected[:limit])
                self.assertEqual([r['full_rank'] for r in selected], [full.index(row) for row in expected[:limit]])

    def test_duplicate_issuer_or_security_cannot_define_pool(self):
        for groups in ([('A', ['a']), ('A', ['b'])], [('A', ['a']), ('B', ['a'])]):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                m.forced_prefixes(groups, 'a', 1, 1)

    def test_old402_scope_and_conflicting_loaded_source_fail_before_work(self):
        with patch.object(m.materializer, 'materialize_slice') as calculate:
            with self.assertRaises(ValueError):
                m.materialize_new([{}] * 34, [{}] * 34, [str(i) for i in range(401)])
            calculate.assert_not_called()
        key = next(iter(m.LOADED))
        with self.assertRaises(ValueError):
            m.guard({key: '0' * 64})


if __name__ == '__main__':
    unittest.main()
