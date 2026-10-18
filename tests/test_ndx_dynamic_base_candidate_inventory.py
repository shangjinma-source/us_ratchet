import unittest
from unittest.mock import patch
from scripts import ndx_dynamic_base_candidate_inventory as module


class BaseInventoryTests(unittest.TestCase):
    def test_real_base_delta_and_reference_retained(self):
        result=module.inventory_date(source_batch='ndx_cardinality_real_runner_p2_exact_v2',
            universe_track='strict_technology',selection_date='2024-02-01')
        self.assertEqual(result['base_count'],25944)
        self.assertEqual(result['delta_count'],884)
        self.assertEqual([row['holding_count'] for row in result['rows']],list(range(1,15)))
        self.assertEqual(sum(len(row['preference_reference']) for row in result['rows']),1)
        self.assertFalse(result['old_and_v3_economic_scores_merged'])
        self.assertFalse(result['full_current_pool_coverage_verified'])

    def test_index_identity_required(self):
        with patch.object(module,'INDEX_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'mismatch'):
                module.inventory_date(source_batch='x',universe_track='x',selection_date='2024-02-01')


if __name__=='__main__':
    unittest.main()
