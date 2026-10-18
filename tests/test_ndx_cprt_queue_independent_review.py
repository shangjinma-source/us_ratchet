"""Independent synthetic review; no real queue materialization."""
import itertools
import math
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_cprt_combination_materialize_20260925 as m


class Review(unittest.TestCase):
    def test_all_forced_positions_and_classes_use_global_prefix_rank(self):
        groups = [('z', ['a']), ('a', ['z', 'y']), ('m', ['b']), ('c', ['x'])]
        ordered = sorted((issuer, sorted(sids)) for issuer, sids in groups)
        for k in range(1, 5):
            full = sorted(tuple(zip([i for i, _ in subset], choice))
                          for subset in itertools.combinations(ordered, k)
                          for choice in itertools.product(*(s for _, s in subset)))
            for forced in ('a', 'z', 'y', 'b', 'x'):
                expected = [row for row in full if forced in [s for _, s in row]]
                total, rows = m.forced_prefixes(groups, forced, k, min(2, len(expected)))
                self.assertEqual(total, len(expected))
                for position, row in enumerate(rows):
                    self.assertEqual(row['prefix_security_ids'], [s for _, s in expected[position]])
                    self.assertEqual(row['full_rank'], full.index(expected[position]))
                    self.assertEqual(row['forced_local_rank'], position)

    def test_denominator_closed_form_without_actual_ranking(self):
        choose = lambda n, k: math.comb(n, k) if 0 <= k <= n else 0
        self.assertEqual(sum(choose(18, k-1)+2*choose(18, k-2) for k in range(4, 21)), 786222)
        self.assertEqual(choose(18, 19)+2*choose(18, 18), 2)
        self.assertEqual(1571322-785100, 786222)

    def test_wrong_full_rank_and_boolean_completion_fail_closed(self):
        selection = dict(prefix_security_ids=[m.FORCED_SID], full_rank=9)
        base = dict(combination_count=1, materialized_task_count=3, completed_task_count=0,
                    combinations=[dict(prefix_security_ids=[m.FORCED_SID], rank=0, tasks=[])])
        for value in (base, dict(base, completed_task_count=False)):
            with patch.object(m.materializer, 'materialize_slice', return_value=value) as call:
                with self.assertRaises(ValueError):
                    m.materialize_new([{}]*34, [selection]*34, [str(i) for i in range(96)])
                self.assertEqual(call.call_count, 1)

    def test_loaded_source_conflict_rejected_before_file_reads(self):
        path, digest = next(iter(m.LOADED.items()))
        with patch.object(m.Path, 'read_bytes', side_effect=AssertionError('must reject conflict first')):
            with self.assertRaises(ValueError):
                m.guard({path: '0'*64 if digest != '0'*64 else '1'*64})


if __name__ == '__main__':
    unittest.main()
