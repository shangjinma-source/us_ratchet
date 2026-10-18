"""Independent synthetic metadata attacks, no actual batch or raw audit."""
from copy import deepcopy
import unittest
from scripts import ndx_dated_economic_batch_independent_readback_20261003 as m
from test_ndx_dated_economic_batch_independent_readback_20261003 import partition_fixture,task_fixture

class ReviewTests(unittest.TestCase):
    def test_context_external_roles_cannot_be_resigned_or_bool(self):
        for change in (lambda c:c.update(full_task_count=True),lambda c:c['input_references']['summary'].update(sha256='f'*64),lambda c:c['source_hashes'].pop(m.ref('driver')['path']),lambda c:c.update(comparison_stage_not_implemented=1)):
            summary,initial,batch=partition_fixture();change(batch['context'])
            with self.assertRaises(ValueError):m.partition(summary,initial,batch)
    def test_complete_cannot_skip_empty_or_absent_stage(self):
        for stage in m.STAGES:
            tid,refs,docs,row=task_fixture();docs[stage]={}
            with self.subTest(stage=stage):
                with self.assertRaises((ValueError,KeyError)):m.validate_task(tid,refs,docs,row)
        tid,refs,docs,row=task_fixture()
        with self.assertRaises((ValueError,KeyError)):m.validate_task(tid,refs,{},row)
    def test_returned_account_requires_exact_call_and_return_counts(self):
        for key,value in [('engine_call_attempt_count',False),('returned_account_count',0),('status','ACCOUNT_EXCEPTION')]:
            tid,refs,docs,row=task_fixture();docs['raw'][key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):m.validate_task(tid,refs,docs,row)
    def test_no_completed_missing_partition_or_authority_equivalence(self):
        for change in (lambda b:b['undispatched_task_ids'].pop(),lambda b:b['failure'].update(task_stage_invoked=True),lambda b:b.update(incumbent_executed=0),lambda b:b['new_completed_rows'][0]['stage_references'].pop('continuous_readback')):
            s,i,b=partition_fixture();change(b)
            with self.assertRaises(ValueError):m.partition(s,i,b)
    def test_references_reader_and_old_cutoff_stay_independent(self):
        for change in (lambda d:d['continuous_readback']['source_hashes'].clear(),lambda d:d['inputs']['inputs']['original_task']['numerical_identity'].update(cutoff='2026-09-21'),lambda d:d['account_readback'].update(point_in_time_verified=0),lambda d:d['continuous'].update(control_core_call_count=1)):
            tid,refs,docs,row=task_fixture();change(docs)
            with self.assertRaises(ValueError):m.validate_task(tid,refs,docs,row)

if __name__=='__main__':unittest.main()
