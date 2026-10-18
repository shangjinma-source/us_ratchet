import unittest
from scripts.ndx_dynamic_training_date import prepare_date


class TrainingDateTests(unittest.TestCase):
    def test_real_cross_k_cohort_does_not_invent_technology_eligibility(self):
        result=prepare_date(source_batch='ndx_cardinality_real_runner_p2_exact_v2',
                            universe_track='strict_technology',selection_date='2024-02-01')
        self.assertEqual(len(result['context_sha256s']),11)
        self.assertEqual(len(result['records']),884)
        self.assertEqual(sorted({r['task']['holding_count'] for r in result['records']}),list(range(2,13)))
        self.assertEqual(sum(r['eligibility']['fractional_risk_passed'] and r['eligibility']['liquidity_passed']
                             for r in result['records']),810)
        self.assertEqual(result['selection']['rows'][0]['status'],'NO_ELIGIBLE_CANDIDATE')
        self.assertIsNone(result['selection']['rows'][0]['selected'])
        self.assertFalse(result['promotion_allowed'])

    def test_absent_coordinate_rejected(self):
        with self.assertRaisesRegex(ValueError,'absent'):
            prepare_date(source_batch='missing',universe_track='strict_technology',selection_date='2024-02-01')


if __name__=='__main__':
    unittest.main()
