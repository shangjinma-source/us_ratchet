import unittest
from copy import deepcopy
from scripts.run_old_continuous_probe_v3 import admit_period_absence

class PeriodAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id='sid',start_exclusive='2024-05-31',end_inclusive='2024-06-28',selected_price_sources=['price'])
        self.review = dict(rows=[self.row])
        self.gate = dict(decision_date='2024-05-31',exposure_end_by_security={'sid':'2024-06-28'},unmapped_events=[],missing_action_streams=[dict(security_id='sid',source='price',selected_source_segments=[dict(source_path='price')])])

    def test_exact_period_clears_only_missing(self):
        self.assertTrue(admit_period_absence(self.gate,self.review)['admitted'])

    def test_short_coverage_rejected(self):
        self.row['end_inclusive']='2024-06-27'
        self.assertFalse(admit_period_absence(self.gate,self.review)['admitted'])

    def test_different_start_rejected(self):
        self.row['start_exclusive']='2024-06-01'
        self.assertFalse(admit_period_absence(self.gate,self.review)['admitted'])

    def test_wrong_source_rejected(self):
        self.row['selected_price_sources']=['other']
        self.assertFalse(admit_period_absence(self.gate,self.review)['admitted'])

    def test_known_action_never_waived(self):
        self.gate['unmapped_events']=[dict(kind='KNOWN_BARRIER')]
        result=admit_period_absence(self.gate,self.review)
        self.assertFalse(result['admitted'])
        self.assertEqual(result['unmapped_events'],self.gate['unmapped_events'])

if __name__=='__main__':unittest.main()
