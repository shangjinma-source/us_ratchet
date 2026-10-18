"""Independent boundary checks without creating any actual materialization."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_bkng_combination_materialize_20260925 as module


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {key: module.codec.loads((module.BASE / path).read_bytes())
                         for key, (path, _) in module.BOUND.items()}

    def test_exact_v4_metadata_and_prior198(self):
        with patch.object(module.materializer, 'materialize_slice', side_effect=AssertionError('no actual materialization')):
            plan, panel, groups, ids = module.inputs(self.documents)
        self.assertEqual((len(panel['universe']), len(groups), len(ids)), (22, 21, 198))
        self.assertEqual(plan['cardinalities'][-1]['k'], 21)
        self.assertTrue(plan['cardinalities'][-1]['necessary_bound_certificates'])

    def test_reference_or_completed_set_changes_refuse(self):
        for attack in ('parent', 'old_id'):
            docs = deepcopy(self.documents)
            if attack == 'parent':
                docs['rebinding_audit']['candidate_reference']['sha256'] = '0' * 64
            else:
                docs['rebinding_audit']['verified_numerical_task_ids'][0] = '0' * 64
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                module.inputs(docs)

    def test_forced_first_and_last_issuer_do_not_alias_classes(self):
        groups = [('A', ['a1', 'a2']), ('B', ['b']), ('C', ['c1', 'c2'])]
        count, first = module.forced_prefixes(groups, 'a2', 2)
        self.assertEqual(count, 3)
        self.assertEqual([r['prefix_security_ids'] for r in first], [['a2', 'b'], ['a2', 'c1']])
        count, last = module.forced_prefixes(groups, 'c2', 2)
        self.assertEqual(count, 3)
        self.assertEqual([r['prefix_security_ids'] for r in last], [['a1', 'c2'], ['a2', 'c2']])


if __name__ == '__main__':
    unittest.main()
