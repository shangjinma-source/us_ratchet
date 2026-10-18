"""Independent mocked single-attempt durability checks; no real fit/preflight."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_orly_single_task_independent_readback_20260925 as fixture
from scripts import ndx_new_cutoff_orly_single_task_20260925 as m

class Tests(unittest.TestCase):
    def test_returned_raw_survives_postflight_drift_and_never_retries(self):
        c=fixture.case();state=deepcopy(c['state']);state.update(returns=None,runtime=m.runtime())
        task=state['task']['numerical_task_id'];calls=0
        def guard(sources):
            nonlocal calls
            calls+=1
            if calls==2:raise ValueError('source changed after fit')
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT_ROOT',Path(directory)),patch.object(m,'preflight',return_value=state),patch.object(m,'guard',side_effect=guard),patch.object(m.fitter,'refit_dynamic_cutoff_weights',return_value=c['raw']['fitted']) as fit:
            m.run(task,execute=True)
            folder=Path(directory)/task
            raw=json.loads((folder/'raw.json').read_text());post=json.loads((folder/'postcheck.json').read_text())
            self.assertEqual(raw['status'],'FIT_RETURNED');self.assertEqual(raw['returned_fit_count'],1)
            self.assertEqual(post['status'],'NUMERICAL_OR_VALIDATION_FAILURE');self.assertIn('source changed',post['error']['message'])
            with self.assertRaises(FileExistsError):m.run(task,execute=True)
            self.assertEqual(fit.call_count,1)
            self.assertIsNone(fit.call_args.kwargs['previous_target_weights'])

    def test_wrapper_exception_records_unknown_optimizer_count(self):
        c=fixture.case();state=deepcopy(c['state']);state.update(returns=None,runtime=m.runtime());task=state['task']['numerical_task_id']
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT_ROOT',Path(directory)),patch.object(m,'preflight',return_value=state),patch.object(m,'guard'),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=ValueError('synthetic failed internal call')) as fit:
            m.run(task,execute=True);raw=json.loads((Path(directory)/task/'raw.json').read_text())
            self.assertEqual(raw['status'],'FIT_EXCEPTION');self.assertEqual(raw['returned_fit_count'],0)
            self.assertIsNone(raw['internal_optimizer_call_count']);self.assertEqual(fit.call_count,1)
            self.assertFalse(raw['retry_allowed'])

    def test_every_prior_namespace_blocks_before_sources_or_fit(self):
        for key in ('OUTPUT_ROOT','OLD_OUTPUT_ROOT','MULTIK_OUTPUT_ROOT','CPRT_OUTPUT_ROOT','BKNG_OUTPUT_ROOT'):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
                task='f'*64;(Path(directory)/task).mkdir()
                with patch.object(m,key,Path(directory)),patch.object(m,'guard') as guard,patch.object(m.fitter,'refit_dynamic_cutoff_weights') as fit:
                    with self.assertRaises(ValueError):m.preflight(task)
                    guard.assert_not_called();fit.assert_not_called()

    def test_explicit_execute_bool_and_source_conflict(self):
        with patch.object(m,'preflight') as preflight:
            with self.assertRaises(ValueError):m.run('a'*64,execute=1)
            preflight.assert_not_called()
        p=next(iter(m.LOADED))
        with self.assertRaises(ValueError):m.guard({p:'f'*64})

if __name__=='__main__':unittest.main()
