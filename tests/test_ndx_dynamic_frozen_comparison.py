import unittest
from unittest.mock import patch
from scripts import ndx_dynamic_frozen_comparison as comparison


class ComparisonTests(unittest.TestCase):
    def test_real_coordinates_and_preference_preserved(self):
        result = comparison.compare()
        self.assertEqual(len(result['rows']), 4)
        self.assertEqual(result['rows'][1]['role'], 'USER_PREFERENCE')
        self.assertEqual(result['rows'][1]['target_cardinalities'], [4])
        self.assertEqual(result['rows'][0]['target_cardinalities'], [4,5,6,8])
        self.assertFalse(result['winner_selected'])
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['candidate_search_exhaustive'])

    def test_changed_report_identity_rejected(self):
        name, _ = comparison.REPORTS['RETURN']
        with patch.dict(comparison.REPORTS, {'RETURN': (name, '0'*64)}):
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                comparison.compare()


if __name__ == '__main__':
    unittest.main()
