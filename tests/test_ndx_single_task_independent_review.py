"""Independent temporary-evidence tests; no actual fitter or saved audit run."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_single_task_20260924 as m


class IndependentReview(unittest.TestCase):
    def exercise(self, effect, *, runtime_values=None, post=None):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        directory=Path(temporary.name);taskid='a'*64
        identity=dict(cutoff='2026-09-21',selected={},weight_spec='equal_weight',
                      requested_previous_target_weights=None,parameters={})
        state=dict(task=dict(numerical_identity=identity),returns=None,
                   source_hashes={},runtime={'v':1})
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(m,'OUTPUT_ROOT',directory))
        stack.enter_context(patch.object(m,'preflight',return_value=state))
        stack.enter_context(patch.object(m,'guard'))
        stack.enter_context(patch.object(m,'runtime',side_effect=runtime_values or [{'v':1}]*4))
        fitter=stack.enter_context(patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=effect))
        stack.enter_context(patch.object(m,'postflight',side_effect=post or (lambda *a: {'check':True})))
        result=m.run(taskid,execute=True)
        target=directory/taskid
        return target,fitter,json.loads(Path(result['path']).read_bytes())

    def test_runtime_drift_preserves_raw_and_calls_once(self):
        folder,fit,result=self.exercise(lambda **kw: {'returned':True},runtime_values=[{'v':1},{'v':2}])
        fit.assert_called_once()
        raw=json.loads((folder/'raw.json').read_bytes())
        self.assertEqual(raw['fitted'],{'returned':True})
        self.assertEqual(raw['returned_fit_count'],1)
        self.assertEqual(result['status'],'NUMERICAL_OR_VALIDATION_FAILURE')
        self.assertFalse(result['independent_readback_performed'])

    def test_finally_exception_does_not_invent_partial_return_or_optimizer_count(self):
        def finally_error(**kw):
            try:return {'computed':'but never returned'}
            finally:raise ValueError('source guard in fitter finally')
        folder,fit,result=self.exercise(finally_error)
        fit.assert_called_once()
        raw=json.loads((folder/'raw.json').read_bytes())
        self.assertIsNone(raw['fitted']);self.assertEqual(raw['returned_fit_count'],0)
        self.assertIsNone(raw['internal_optimizer_call_count'])
        self.assertEqual(raw['operation_counts']['deterministic_generation_request_count'],1)
        self.assertEqual(result['status'],'NUMERICAL_OR_VALIDATION_FAILURE')

    def test_orphan_during_postflight_fails_closed_without_second_call(self):
        def post(*args):
            (m.OUTPUT_ROOT/('a'*64)/'foreign.json').write_text('{}')
            return {'check':True}
        folder,fit,result=self.exercise(lambda **kw:{'retained':1},post=post)
        fit.assert_called_once()
        self.assertTrue((folder/'raw.json').exists())
        self.assertEqual(result['status'],'NUMERICAL_OR_VALIDATION_FAILURE')
        self.assertIn('Unexpected',result['error']['message'])

    def test_request_spec_counts_do_not_claim_internal_optimization(self):
        for spec,equal in [('equal_weight',1),('shrinkage',0),('turnover_anchor',0)]:
            value=m.counts({'numerical_identity':{'weight_spec':spec}})
            self.assertEqual(value,dict(wrapper_call_attempt_count=1,
                deterministic_generation_request_count=equal,numerical_fit_request_count=1-equal,import_count=0))


if __name__=='__main__':unittest.main()
