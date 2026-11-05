import json, unittest
from copy import deepcopy
from docs.candidates import momentum_absence_20261105 as module

class AbsenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=json.loads((module.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
        cls.proof=module.normalize(cls.document)

    def test_five_real_captures_without_receipt_fabrication(self):
        self.assertEqual([x['capture_checks']['verified_sessions'] for x in self.proof['rows']],[85,442,62,22,22])
        self.assertEqual(self.proof['rows'][0]['receipt_fields_not_present'],['body_truncated'])
        self.assertEqual(self.proof['rows'][-1]['receipt_fields_not_present'],['rows','returned_events'])

    def test_identity_and_source_binding(self):
        row=self.proof['rows'][0]
        bad=deepcopy(self.document);bad['prepared_input_candidate']['metadata'][row['security_id']]['ticker']='OTHER'
        with self.assertRaisesRegex(ValueError,'SID_IDENTITY'):module.normalize(bad)
        bad=deepcopy(self.document);bad['source_hashes'][row['selected_price_sources'][0]]='bad'
        with self.assertRaisesRegex(ValueError,'EXECUTION_SOURCE'):module.normalize(bad)

    def test_scope_source_and_explicit_actions_stay_blocked(self):
        row=self.proof['rows'][0];sid=row['security_id'];source=row['selected_price_sources'][0]
        gate=dict(decision_date=row['start_exclusive'],exposure_end_by_security={sid:row['end_inclusive']},missing_action_streams=[dict(security_id=sid,source=source,selected_source_segments=[dict(source_path=source)])],unmapped_events=[])
        self.assertTrue(module.admit_period_absence(gate,self.proof)['admitted'])
        for field in ['date','source','action']:
            bad=deepcopy(gate)
            if field=='date':bad['exposure_end_by_security'][sid]='2026-07-30'
            if field=='source':bad['missing_action_streams'][0]['source']='other'
            if field=='action':bad['unmapped_events']=[dict(kind='splits')]
            self.assertFalse(module.admit_period_absence(bad,self.proof)['admitted'])

if __name__=='__main__':unittest.main()
