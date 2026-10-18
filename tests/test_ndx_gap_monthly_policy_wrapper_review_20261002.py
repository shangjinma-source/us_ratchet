from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_gap_monthly_policy_20261002 as m
from test_ndx_gap_monthly_policy_20261002 import fixture,monthly_observation_coordinates

class MonthlyWrapperReview(unittest.TestCase):
    def test_full_mapping_unknown_and_no_new_observation(self):
        f,refs=fixture();saved=deepcopy(f);r=m.assemble(f,refs,monthly_observation_coordinates)
        self.assertEqual(f,saved);self.assertEqual(r['saved_frontier_rows'],f['known_accounted_rows'])
        self.assertEqual(r['projection_inputs']['new_prospective_observations'],[])
        for i,row in enumerate(r['projection_inputs']['known_rows']):
            self.assertEqual(row['evidence_reference'],dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'))
            self.assertEqual(row['seal_status'],'UNKNOWN' if i<60 else 'NOT_ATTEMPTED')
        self.assertEqual(r['projection']['months'][-1],dict(month='2026-10',first_observed_session=None,observed_count=0,missed_count=1))
        self.assertEqual(r['prospective_monthly_coordinate_count'],0)
        for flag in m.FLAGS:self.assertIs(r[flag],False)
        self.assertFalse(r['cryptographic_user_signature_claimed'])

    def test_corrupt_counts_and_coordinate_types_rejected(self):
        for kind in ('countbool','coordinateint','completeclaim'):
            f,refs=fixture()
            def corrupt(**kwargs):
                r=monthly_observation_coordinates(**kwargs)
                if kind=='countbool':r['new_prospective_observation_count']=False
                elif kind=='coordinateint':r['rows'][-1]['monthly_coordinate_eligible']=0
                else:r['complete_sequence_independently_verified']=True
                return r
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.assemble(f,refs,corrupt)

    def test_namespace_refusal_and_input_mutations(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)),patch.object(m,'prepare') as prepare:
            with self.assertRaisesRegex(ValueError,'no retry'):m.run()
            prepare.assert_not_called()
        for kind in ('gap_to_parent','date_duplicate','gap_permission'):
            f,refs=fixture()
            if kind=='gap_to_parent':f['known_accounted_rows'][-1]['kind']='SEALED_PARENT_OBSERVED_SESSION'
            elif kind=='date_duplicate':f['known_accounted_rows'][-1]['session']=f['known_accounted_rows'][-2]['session']
            else:f['known_accounted_rows'][-1]['counts_as_observed_session']=0
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.assemble(f,refs,monthly_observation_coordinates)

if __name__=='__main__':unittest.main()
