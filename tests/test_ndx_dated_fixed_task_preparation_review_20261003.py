"""Independent synthetic new-cutoff contract checks, no actual materialization."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_dated_fixed_task_preparation_research import fixture
from test_ndx_dated_fixed_task_preparation_20261003 import fixture as documents
from backtest import ndx_dated_fixed_task_preparation_research as core
from scripts import ndx_dated_fixed_task_preparation_20261003 as wrapper

class IndependentReview(unittest.TestCase):
    def test_all_cells_and_old_new_contract_are_separate(self):
        args=fixture();out=core.prepare_dated_tasks(**args)
        old=args['prior_preparation']['materialized']['combinations']
        expected=float(Fraction(1,100))
        self.assertEqual(len(out['combinations']),544)
        for c,previous in zip(out['combinations'],old):
            self.assertTrue(all(v==expected for row in c['fit_matrix']['returns'] for v in row))
            self.assertEqual(c['fit_matrix']['dates'][-1],'2026-03-20')
            self.assertEqual(c['selection_position'],previous['selection_position'])
            for task,prior in zip(c['tasks'],previous['tasks']):
                self.assertEqual(task['complete_prior_different_cutoff_task'],prior)
                self.assertNotEqual(task['location_id'],prior['location_id'])
                self.assertNotEqual(task['numerical_task_id'],prior['numerical_task_id'])
                self.assertIsNone(task['numerical_identity']['requested_previous_target_weights'])
                self.assertEqual(task['expected_fitter_previous_target_weights'],{})
        self.assertEqual(out['new_fit_count'],0)
        self.assertEqual(out['remaining_new_cutoff_uncompleted_task_count'],core.FULL_TASK_COUNT)

    def test_last_task_resigned_contract_and_location_rejected(self):
        for mode in ('parameter','prior','rankbool','fingerprint'):
            args=fixture();t=args['prior_preparation']['materialized']['combinations'][-1]['tasks'][-1]
            if mode=='parameter':t['numerical_identity']['parameters']['fit_days']=125
            elif mode=='prior':t['numerical_identity']['requested_previous_target_weights']={}
            elif mode=='rankbool':t['location_identity']['rank']=True
            else:t['numerical_identity']['fitter_source_fingerprint']='f'*64
            t['numerical_task_id']=core.digest(t['numerical_identity']);t['location_id']=core.digest(t['location_identity'])
            with self.subTest(mode=mode),self.assertRaises(ValueError):core.prepare_dated_tasks(**args)

    def test_resigned_frame_does_not_replace_exact_training_evidence(self):
        args=fixture();p=args['training_panel'];p['fit_payload']['returns']['data'][-1][-1]=.02
        p['training_frame_sha256']=core.digest(p['fit_payload']['returns']);p['fit_payload_sha256']=core.digest(p['fit_payload']);p['content_sha256']=core.digest({k:v for k,v in p.items() if k!='content_sha256'})
        with self.assertRaises(ValueError):core.prepare_dated_tasks(**args)

    def test_wrapper_publication_and_immutable_failure_guards(self):
        for role in ('training_publication','prior_publication'):
            docs,refs=documents();docs[role]['source_hashes']={'forged':'f'*64}
            with self.assertRaises(ValueError):wrapper.project_inputs(docs,refs)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';path.write_bytes(b'a');runtime=wrapper.runtime();path.write_bytes(b'b')
            with self.assertRaises(ValueError):wrapper.guard({str(path):wrapper.sha(b'a')},runtime)
            with patch.object(wrapper,'runtime',return_value={}):
                with self.assertRaises(ValueError):wrapper.guard({},runtime)
            output=Path(folder)/'failed';output.mkdir();(output/'failure.json').write_text('{}')
            with patch.object(wrapper,'OUTPUT',output),patch.object(wrapper,'load_inputs',side_effect=AssertionError('no retry')):
                with self.assertRaises(ValueError):wrapper.run(execute=True)

if __name__=='__main__':unittest.main()
