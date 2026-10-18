"""Saved completion metadata only; no fitted value re-evaluation or publication."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_completed_task_index_20260924 as module


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents={role:json.loads(Path(module.ref(role)['path']).read_bytes()) for role in module.BOUND}
        cls.evidence={task:{key:json.loads((module.TASK_ROOT/task/(name+'.json')).read_bytes())
            for key,name in [('audit','independent_readback'),('started','started'),('raw','raw'),('postcheck','postcheck')]}
            for task in module.AUDITS}

    def test_three_external_completions_and_full_denominator(self):
        value=module.assemble(self.documents,self.evidence)
        self.assertEqual(value['completed_task_count'],3)
        self.assertEqual(value['remaining_plan_task_count'],2355297)
        self.assertEqual(value['observed_completed_operation_counts'],dict(wrapper_call_attempt_count=3,deterministic_generation_request_count=1,numerical_fit_request_count=2,import_count=0))
        self.assertTrue(all(value[key] is False for key in module.FALSE))

    def test_omitted_duplicate_or_changed_task_id_rejected(self):
        evidence=deepcopy(self.evidence);evidence.pop(next(iter(evidence)))
        with self.assertRaises(ValueError):module.assemble(self.documents,evidence)
        documents=deepcopy(self.documents);documents['materialized']['materialization']['combinations'][0]['tasks'][1]=deepcopy(documents['materialized']['materialization']['combinations'][0]['tasks'][0])
        with self.assertRaises(ValueError):module.assemble(documents,self.evidence)

    def test_partial_or_boolean_return_is_not_completion(self):
        for attack in ('status','returned_bool','readback_bool','counts_bool'):
            evidence=deepcopy(self.evidence);item=evidence[next(iter(evidence))]
            if attack=='status':item['audit']['status']='PARTIAL'
            elif attack=='returned_bool':item['raw']['returned_fit_count']=True
            elif attack=='readback_bool':item['audit']['completed_saved_task_readbacks']=True
            else:item['raw']['operation_counts']['wrapper_call_attempt_count']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.assemble(self.documents,evidence)

    def test_source_lineage_or_postcheck_failure_rejected(self):
        for attack in ('raw_parent','postcheck','authority'):
            evidence=deepcopy(self.evidence);item=evidence[next(iter(evidence))]
            if attack=='raw_parent':item['raw']['started_reference']['sha256']='0'*64
            elif attack=='postcheck':item['postcheck']['error']={'type':'ValueError','message':'drift'}
            else:item['audit']['promotion_allowed']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.assemble(self.documents,evidence)

    def test_preserves_full_original_task_and_external_references(self):
        value=module.assemble(self.documents,self.evidence)
        for row,task in zip(value['completed_tasks'],self.documents['materialized']['materialization']['combinations'][0]['tasks']):
            self.assertEqual(row['full_task'],task)
            self.assertEqual(row['independent_readback_reference'],module.audit_ref(task['numerical_task_id']))

    def test_existing_namespace_and_source_conflict_reject_before_work(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT',Path(directory)/'index.json'),patch.object(module,'build') as build:
            with self.assertRaises(ValueError):module.publish()
            build.assert_not_called()
        with self.assertRaises(ValueError):module.guard({str(module.SOURCE):'0'*64})


if __name__=='__main__':unittest.main()
