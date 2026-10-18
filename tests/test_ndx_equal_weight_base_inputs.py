"""Read-only integration checks of the sealed base-definition cohort."""
import unittest
from unittest.mock import patch
from scripts import ndx_equal_weight_base_inputs as inputs


class EqualBaseInputsTests(unittest.TestCase):
    def test_real_cohort_definitions_not_saved_scores(self):
        prepared = inputs.prepare_equal_base_date(
            source_batch='ndx_cardinality_real_runner_p2_exact_v2',
            universe_track='strict_technology', selection_date='2024-02-01')
        self.assertEqual(prepared['summary']['equal_weight_base_count'], 24575)
        self.assertEqual(prepared['summary']['all_base_count'], 25944)
        self.assertEqual(prepared['summary']['cardinalities'], list(range(1, 15)))
        self.assertIn(('AMAT', 'AVGO', 'CDNS', 'GOOG'), prepared['combinations'])
        self.assertEqual(len(set(prepared['combinations'])), 24575)
        self.assertFalse(prepared['summary']['saved_economic_metrics_used'])
        self.assertFalse(prepared['summary']['new_evaluation_performed'])
        self.assertEqual(prepared['training_semantics']['training_semantics_sha256'],
                         '0813a7c6d91fc35a21fcd4a4fb1612e2b741bb75c63b23933740504db27a11a0')

    def test_readiness_identity_mismatch_rejected(self):
        with patch.object(inputs, 'READINESS_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'Readiness identity'):
                inputs.prepare_equal_base_date(
                    source_batch='ndx_cardinality_real_runner_p2_exact_v2',
                    universe_track='strict_technology', selection_date='2024-02-01')


if __name__ == '__main__':
    unittest.main()
