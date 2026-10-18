"""Independent synthetic task-reader attacks; no actual raw audit."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_multik_single_task_independent_readback_20260924 as f
from scripts import ndx_new_cutoff_multik_single_task_independent_readback_20260924 as m


class IndependentReview(unittest.TestCase):
    def test_full_universe_not_only_selected_coordinates(self):
        docs,panel,tid=f.authorized_fixture()
        docs['plan']['plan']['canonical_groups'].pop()
        with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.expected_state(docs,tid)

    def test_matching_self_signed_prior_does_not_override_hard_first_decision(self):
        docs,panel,tid=f.authorized_fixture()
        task=docs['queue']['new_materializations'][1]['combinations'][1]['tasks'][2]
        docs['plan']['plan']['context']['previous_target_weights']={'EXIT':1.}
        task['numerical_identity']['requested_previous_target_weights']={'EXIT':1.}
        task['numerical_task_id']=m.pure.digest(task['numerical_identity'])
        with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.expected_state(docs,task['numerical_task_id'])

    def test_old_schema_and_wrong_pointer_cannot_authorize_saved_raw(self):
        for attack in ('schema','pointer','queue'):
            case=f.case()
            if attack=='schema':case['raw']['schema']='NEW_CUTOFF_SINGLE_TASK_RAW_V1'
            elif attack=='pointer':case['started']['task_reference']['json_pointer']='/new_materializations/15/combinations/1/tasks/2'
            else:case['started']['queue_reference']['sha256']='0'*64
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_envelopes(**case)

    def test_unselected_fullpanel_bad_cell_is_rejected(self):
        docs,panel,tid=f.authorized_fixture()
        panel['returns']=panel['returns'].astype(object)
        panel['returns'].iloc[0,-1]=True
        with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.expected_state(docs,tid)


if __name__=='__main__':unittest.main()
