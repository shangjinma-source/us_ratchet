import unittest
from unittest.mock import patch
from scripts import ndx_equal_base_coverage as coverage


class CoverageTests(unittest.TestCase):
    def test_empty_does_not_claim_completion(self):
        result = coverage.inspect_coverage([])
        self.assertEqual(result['expected_dates'], 15)
        self.assertEqual(result['completed_dates'], 0)
        self.assertEqual(len(result['missing_dates']), 15)
        self.assertFalse(result['all_equal_dates_verified'])

    def test_explicit_digest_and_duplicate_date(self):
        report = dict(coordinate=dict(source_batch='ndx_cardinality_real_runner_p2_exact_v2',
            universe_track='strict_technology', selection_date='2024-02-01'),
            evaluation=dict(count=24575), input_summary=dict(cardinalities=list(range(1, 15))))
        descriptor = dict(path='explicit.json', sha256='a' * 64)
        with patch.object(coverage, 'load_report', return_value=report) as loader:
            result = coverage.inspect_coverage([descriptor])
            loader.assert_called_once_with('explicit.json', expected_sha256='a' * 64)
            self.assertEqual(result['equal_weight_records'], 24575)
            self.assertFalse(result['all_equal_dates_verified'])
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                coverage.inspect_coverage([descriptor, descriptor])


if __name__ == '__main__':
    unittest.main()
