"""Independent mocked queue checks, never actual queue audit."""
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_cprt_combination_independent_readback_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    def test_k20_shareclass_collapse_and_location_alias_rejected(self):
        for attack in ('class', 'location', 'order', 'boolean'):
            a = owner.batch()
            if attack == 'class':
                a['materializations'][-1]['combinations'][0]['prefix_security_ids'] = a['materializations'][-2]['combinations'][0]['prefix_security_ids'][:]
            elif attack == 'location':
                a['materializations'][-1]['combinations'][0]['tasks'][0]['location_id'] = a['materializations'][0]['combinations'][0]['tasks'][0]['location_id']
            elif attack == 'order':
                a['materializations'][0]['combinations'][0]['prefix_security_ids'].reverse()
            else:
                a['selections'][0]['forced_local_rank'] = False
            with self.subTest(attack=attack), patch.object(m.pure, 'verify_materialized', return_value={}):
                with self.assertRaises(ValueError):
                    m.validate_materializations(**a)

    def test_bad_fullrank_rejected_before_pure_numeric_check(self):
        a = owner.batch()
        a['materializations'][0]['start'] = 0
        a['materializations'][0]['stop'] = 1
        with patch.object(m.pure, 'verify_materialized') as verify:
            with self.assertRaises(ValueError):
                m.validate_materializations(**a)
            verify.assert_not_called()

    def test_issuer_order_is_not_security_lex_order(self):
        groups = [dict(issuer_id='A', security_ids=['z']),
                  dict(issuer_id='B', security_ids=['a', 'b']),
                  dict(issuer_id='C', security_ids=['c'])]
        self.assertEqual(m.forced_rank(groups, ['z', 'c'], 'c'), 0)
        self.assertEqual(m.forced_rank(groups, ['a', 'c'], 'c'), 1)
        self.assertEqual(m.forced_rank(groups, ['b', 'c'], 'c'), 2)
        with self.assertRaises(ValueError):
            m.forced_rank(groups, ['c', 'z'], 'c')

    def test_source_conflict_precedes_disk_read(self):
        path, digest = next(iter(m.LOADED.items()))
        with patch.object(m.Path, 'read_bytes', side_effect=AssertionError('no disk reads')):
            with self.assertRaises(ValueError):
                m.guard({path: '0'*64 if digest != '0'*64 else '1'*64})


if __name__ == '__main__':
    unittest.main()
