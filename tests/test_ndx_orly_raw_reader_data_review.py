"""Independent synthetic raw recovery boundary tests; never actual raw readback."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_orly_single_task_independent_readback_20260925 as owner
from scripts import ndx_new_cutoff_orly_single_task_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    def test_late_unselected_task_boolean_location_and_fifth_sidecar(self):
        for attack in ('location','sidecar','old300'):
            docs,panel,tid=owner.authorized_fixture()
            if attack=='location':
                t=docs['queue']['new_materializations'][-1]['combinations'][0]['tasks'][-1]
                t['location_identity']['spec_index']=True;t['location_id']=m.pure.digest(t['location_identity'])
            elif attack=='sidecar':docs['queue']['preserved_sidecar_references'][4]={}
            else:tid=docs['rebinding']['rows'][-1]['numerical_task_id']
            with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.expected_state(docs,tid)

    def test_raw_external_link_pointer_runtime_and_permissions(self):
        for attack in ('pointer','startedref','runtime','permission'):
            c=owner.case()
            if attack=='pointer':c['started']['task_reference']['json_pointer']='/new_materializations/33/combinations/0/tasks/2'
            elif attack=='startedref':c['raw']['started_reference']['sha256']='b'*64;c['started_reference']=dict(c['started_reference'],sha256='a'*64)
            elif attack=='runtime':c['raw']['runtime']={'version':'different'}
            else:c['raw']['promotion_allowed']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_envelopes(**c)

    def test_saved_numerical_exception_is_distinct_from_validation_drift(self):
        c=owner.case();c['raw'].update(status='FIT_EXCEPTION',fitted=None,error=dict(type='ValueError',message='inner source finally failed'),returned_fit_count=0)
        detail=m.inspect_envelopes(**c)
        self.assertEqual(m.summary_status(detail,{'error':deepcopy(detail['error'])}),'NUMERICAL_EXCEPTION_NO_RETURNED_FIT')
        self.assertEqual(m.summary_status(detail,{'error':dict(type='ValueError',message='later runtime changed')}),'VALIDATION_FAILURE_RECORDED')
        self.assertFalse(detail['numerical_failure_is_economic_infeasibility'])
        c['raw']['internal_optimizer_call_count']=0
        with self.assertRaises(ValueError):m.inspect_envelopes(**c)

    def test_sources_conflict_and_no_runner_fitter_import(self):
        with patch.object(m,'RUNNER_SHA','f'*64):
            first=next(iter(m.LOADED))
            with self.assertRaises(ValueError):m.guard({first:'0'*64})
        text=m.SOURCE.read_text()
        self.assertNotIn('import ndx_new_cutoff_orly_single_task_20260925',text)
        self.assertNotIn('import ndx_dynamic_cutoff_refit',text)

if __name__=='__main__':unittest.main()
