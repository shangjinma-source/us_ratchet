import copy
import json
import unittest
from unittest.mock import patch
from scripts import ndx_latest_fourteen_conditional_panel_20260919 as m


class FourteenIndependentTests(unittest.TestCase):
    def test_all_four_original_frames_and_security_class_preserved(self):
        original=json.loads(m.Path(m.PANEL['path']).read_bytes());before=m.old.typed_decode(original['panel'])
        for frame in ('returns','nominal_close','raw_volume','dollar_volume'):
            bad=copy.deepcopy(before);bad[frame].iloc[-1,-1]+=1
            with self.subTest(frame=frame),self.assertRaises(ValueError):m.prove_old_subset(before,bad)
        bad=copy.deepcopy(before);bad['universe'].iloc[0,bad['universe'].columns.get_loc('security_id')]='forged'
        with self.assertRaises(ValueError):m.prove_old_subset(before,bad)

    def test_five_facts_never_claim_latest_continuity(self):
        facts=json.loads(m.Path(m.FIVE['path']).read_bytes())
        for fact in facts['rows']:
            value=m.coordinate(fact,['2026-03-18','2026-09-17'])
            self.assertFalse(value['latest_interval_verified']);self.assertFalse(value['provider_binding_verified'])
            for flag in m.five.FALSE:
                bad=copy.deepcopy(fact);bad[flag]=True
                with self.subTest(ticker=fact['ticker'],flag=flag),self.assertRaises(ValueError):m.coordinate(bad,['2026-03-18','2026-09-17'])

    def test_reverification_rejects_metadata_permission_change(self):
        expected=dict(schema='SOURCE_BOUND_LATEST_FOURTEEN_CONDITIONAL_PANEL_V1',execution_authorized=False,previous_fit_results_reused=False)
        with patch.object(m,'build',return_value=expected):
            for field in ('execution_authorized','previous_fit_results_reused'):
                value=dict(expected);value[field]=True
                with self.subTest(field=field),self.assertRaises(ValueError):m.verify(value)


if __name__=='__main__':unittest.main()
