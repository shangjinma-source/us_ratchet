"""Temporary attempts and mocked fitter only; never execute actual optimization."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_multik_single_task_20260924 as module


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={role:module.codec.loads(Path(module.ref(role)['path']).read_bytes()) for role in module.BOUND}
        cls.numerical=module.fitter._sources()
        cls.taskid=cls.docs['queue']['new_materializations'][0]['combinations'][0]['tasks'][0]['numerical_task_id']

    def state(self):
        state=module.validate_inputs(self.docs,self.taskid,self.numerical)
        state.update(source_hashes={},input_references={},runtime=module.runtime())
        return state

    def test_materialized_counts_reject_boolean(self):
        for key,value in [('completed_task_count',False),('materialized_task_count',True)]:
            documents=deepcopy(self.docs);documents['queue']['new_materializations'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                module.validate_inputs(documents,self.taskid,self.numerical)

    def test_old_ids_permanently_excluded_and_duplicate_new_ids_rejected(self):
        for row in self.docs['completed_index']['completed_tasks']:
            with self.assertRaises(ValueError):module.validate_inputs(self.docs,row['numerical_task_id'],self.numerical)
        bad=deepcopy(self.docs)
        combos=bad['queue']['new_materializations'][1]['combinations']
        combos[1]['tasks'][0]=deepcopy(combos[0]['tasks'][0])
        with self.assertRaises(ValueError):module.validate_inputs(bad,self.taskid,self.numerical)

    def test_old_root_residue_blocks_new_task_before_sources(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OLD_OUTPUT_ROOT',Path(directory)):
            (Path(directory)/self.taskid).mkdir()
            with patch.object(module.fitter,'_sources') as sources,self.assertRaises(ValueError):REAL_PREFLIGHT(self.taskid)
            sources.assert_not_called()

    def test_boolean_rank_and_resigned_location_rejected(self):
        for location_attack in (False,True):
            bad=deepcopy(self.docs);combo=bad['queue']['new_materializations'][1]['combinations'][0]
            if location_attack:
                task=combo['tasks'][0];task['location_identity']['rank']=False;task['location_id']=module.digest(task['location_identity'])
            else:combo['rank']=False
            with self.assertRaises(ValueError):module.validate_inputs(bad,self.taskid,self.numerical)

    def test_bound_metadata_and_three_explicit_ids(self):
        tasks=self.docs['queue']['new_materializations'][0]['combinations'][0]['tasks']
        with patch.object(module.fitter,'refit_dynamic_cutoff_weights') as fit:
            for task in tasks:
                state=module.validate_inputs(self.docs,task['numerical_task_id'],self.numerical)
                self.assertEqual(len(state['returns']),126)
                self.assertIsNone(state['task']['numerical_identity']['requested_previous_target_weights'])
            fit.assert_not_called()
        with self.assertRaises(ValueError):module.validate_inputs(self.docs,'0'*64,self.numerical)
        bad=deepcopy(self.docs);bad['audit']['actual_fitter_invocation_count']=True
        with self.assertRaises(ValueError):module.validate_inputs(bad,self.taskid,self.numerical)

    def attempt(self,directory,fit,guard=None):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(module,'OUTPUT_ROOT',Path(directory)/'fixed'))
        stack.enter_context(patch.object(module,'preflight',return_value=self.state()))
        stack.enter_context(patch.object(module,'guard',side_effect=guard))
        stack.enter_context(patch.object(module.fitter,'refit_dynamic_cutoff_weights',side_effect=fit))
        return Path(directory)/'fixed'/self.taskid

    def test_preflight_only_no_files_no_fit_and_boolean_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            def forbidden(**kwargs):raise AssertionError('fit forbidden')
            destination=self.attempt(directory,forbidden)
            self.assertEqual(module.run(self.taskid)['wrapper_call_attempt_count'],0)
            self.assertFalse(destination.exists())
            with self.assertRaises(ValueError):module.run(self.taskid,execute=1)

    def test_exception_raw_retained_and_actual_preflight_refuses_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            destination=self.attempt(directory,ValueError('synthetic numerical error'))
            original=module.preflight
            module.run(self.taskid,execute=True)
            raw=json.loads((destination/'raw.json').read_bytes())
            self.assertEqual(raw['status'],'FIT_EXCEPTION');self.assertIsNone(raw['fitted'])
            self.assertEqual(raw['operation_counts']['wrapper_call_attempt_count'],1)
            self.assertIn('planned_operation_counts',json.loads((destination/'started.json').read_bytes()))
            # Use the real preflight entry gate without reading production inputs.
            with self.assertRaises(ValueError):REAL_PREFLIGHT(self.taskid)

    def test_raw_survives_post_return_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            destination=self.attempt(directory,lambda **kwargs:dict(full_return='preserved'),[None,ValueError('source drift')])
            module.run(self.taskid,execute=True)
            self.assertEqual(json.loads((destination/'raw.json').read_bytes())['fitted'],{'full_return':'preserved'})
            post=json.loads((destination/'postcheck.json').read_bytes())
            self.assertEqual(post['status'],'NUMERICAL_OR_VALIDATION_FAILURE')
            self.assertFalse(post['independent_readback_performed'])

    def test_started_only_or_unknown_directory_blocks_before_inputs(self):
        for name in ('started.json','unknown.json'):
            with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT_ROOT',Path(directory)):
                target=Path(directory)/self.taskid;target.mkdir();(target/name).write_text('{}')
                with patch.object(module.fitter,'_sources') as source, self.assertRaises(ValueError):REAL_PREFLIGHT(self.taskid)
                source.assert_not_called()

    def test_complete_prior_passed_without_filtering_and_raw_before_postcheck(self):
        with tempfile.TemporaryDirectory() as directory:
            observed=[]
            def fake(**kwargs):observed.append(kwargs);return {'unvalidated':'full'}
            destination=self.attempt(directory,fake)
            state=self.state();state['task']['numerical_identity']['requested_previous_target_weights']={'EXITED':1.0}
            with patch.object(module,'preflight',return_value=state),patch.object(module,'postflight',return_value={'a':False}):
                module.run(self.taskid,execute=True)
            self.assertEqual(observed[0]['previous_target_weights'],{'EXITED':1.0})
            self.assertEqual(json.loads((destination/'postcheck.json').read_bytes())['status'],'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK')


REAL_PREFLIGHT=module.preflight
if __name__=='__main__':unittest.main()
