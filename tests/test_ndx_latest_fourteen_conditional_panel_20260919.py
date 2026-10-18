import copy
import json
import unittest
from unittest.mock import patch
from scripts import ndx_latest_fourteen_conditional_panel_20260919 as m


class FourteenTests(unittest.TestCase):
    def test_actual_five_coordinates_and_lrcx_floor(self):
        facts=json.loads(m.Path(m.FIVE['path']).read_bytes())
        for fact in facts['rows']:
            coordinate=m.coordinate(fact,['2026-03-18','2026-09-17'])
            self.assertEqual(coordinate['dated_fact']['dated_as_of'][:4],'2025')
            self.assertFalse(coordinate['latest_interval_verified'])
        lrcx=next(r for r in facts['rows'] if r['ticker']=='LRCX')
        with self.assertRaises(ValueError):m.coordinate(lrcx,['2024-10-02','2026-09-17'])
        bad=copy.deepcopy(lrcx);bad['cusip']='512807108'
        with self.assertRaises(ValueError):m.coordinate(bad,['2026-03-18','2026-09-17'])

    def test_original_nine_exact_and_relabel_rejected(self):
        original=json.loads(m.Path(m.PANEL['path']).read_bytes())
        panel=m.old.typed_decode(original['panel'])
        m.prove_old_subset(panel,copy.deepcopy(panel))
        changed=copy.deepcopy(panel);changed['returns'].iloc[0,0]+=1e-10
        with self.assertRaises(ValueError):m.prove_old_subset(panel,changed)
        changed=copy.deepcopy(panel)
        row=next(r for r in changed['observed_provenance_and_missing'] if r['ticker']=='GOOG')
        row['coordinate_assumption']['latest_interval_verified']=True
        with self.assertRaises(ValueError):m.prove_old_subset(panel,changed)

    def test_resigned_anchor_and_output_flags_rejected(self):
        with patch.dict(m.PANEL,sha256='0'*64):
            with self.assertRaises(ValueError):m.build()
        with patch.object(m,'build',return_value={'fit_performed':False}):
            with self.assertRaises(ValueError):m.verify({'fit_performed':0})

    def test_complete_original_supplemental_is_immutable(self):
        original=json.loads(m.Path(m.PANEL['path']).read_bytes())['supplemental_dated_and_risk_provenance']
        after=copy.deepcopy(original)
        m.prove_old_supplemental(original,after)
        after['GOOG']['joint_historical_availability_inferred']=True
        with self.assertRaises(ValueError):m.prove_old_supplemental(original,after)


if __name__=='__main__':unittest.main()
