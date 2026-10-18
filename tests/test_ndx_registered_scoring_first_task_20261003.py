from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from copy import deepcopy
import unittest
from scripts import ndx_registered_scoring_first_task_20261003 as m
from backtest import ndx_registered_scoring_job_inputs_research as assembly
from test_ndx_registered_scoring_job_inputs_research import fixture as assembly_fixture


def fixture():
    args=assembly_fixture();assembled=assembly.assemble_registered_scoring_job_inputs(**args)
    context=dict(args=args,refs={'budget':args['budget_reference']},sources={},manifest=dict(runtime_versions=m.runtime(),source_hashes={}),assembler=SimpleNamespace(assemble_registered_scoring_job_inputs=lambda **kw:deepcopy(assembled)))
    fit=dict(schema='MULTIDECISION_CAUSAL_ROLLING_FITS_V1',cutoff=assembled['cutoff'],weight_spec='equal_weight',securities=assembled['rolling_inputs']['securities'],windows=[dict(window_index=i,weights=[.25]*4) for i in range(13)],source_hashes={},**dict.fromkeys(('source_bytes_authenticated','outer_lane_prior_applied','score_computed','point_in_time_verified','account_executed','promotion_allowed'),False))
    score=dict(schema='synthetic_score',value=1.)
    def reduce(**kw):
        assert (m.OUTPUT/'raw_fit.json').is_file()
        return deepcopy(score)
    def inspect(**kw):
        assert (m.OUTPUT/'raw_score.json').is_file()
        return dict(status='PASS',window_count=13)
    modules={'rolling':SimpleNamespace(source_hashes=lambda:{},fit_causal_scoring_windows=lambda **kw:deepcopy(fit)), 'reducer':SimpleNamespace(reduce_fitted_scoring_windows=reduce), 'inspector':SimpleNamespace(inspect_fitted_scoring_windows=inspect)}
    return context,assembled,modules


class Tests(unittest.TestCase):
    def run_mock(self,context,assembled,modules):
        return m.run(execute=True)
    def test_fresh_environment_before_load(self):
        with patch.object(m,'FRESH_CLI',False),patch.object(m,'load_inputs',side_effect=AssertionError('load')):
            with self.assertRaises(ValueError):m.run(execute=True)
        with patch.dict(m.os.environ,{'PYTHONHASHSEED':'invalid'}):
            with self.assertRaises(ValueError):m.worker_environment()
    def test_success_and_raw_first(self):
        context,a,modules=fixture()
        with TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'out'),patch.object(m,'TASK_ID',a['job_id']),patch.object(m,'FRESH_CLI',True),patch.object(m,'worker_environment',return_value={'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0}),patch.object(m,'load_inputs',return_value=context),patch.object(m,'private',side_effect=lambda role,s:modules[role]),patch.object(m,'space'),patch.object(m,'guard'):
            r=m.run(execute=True);p=m.loads(Path(r['path']).read_bytes())
            self.assertEqual(p['outcome'],'SCORED_PENDING_INDEPENDENT_READBACK');self.assertFalse(p['whole_queue_completed'])
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','inputs.json','raw_fit.json','raw_score.json','score_inspection.json','postcheck.json'})
            with self.assertRaises(ValueError):m.run(execute=True)
    def test_none_exception_and_unserializable_results(self):
        for mode in ('none','exception','unserializable','score_exception'):
            context,a,modules=fixture()
            def raising(**kw):raise RuntimeError('original exception')
            if mode=='none':modules['rolling'].fit_causal_scoring_windows=lambda **kw:None
            if mode=='exception':modules['rolling'].fit_causal_scoring_windows=raising
            if mode=='unserializable':modules['rolling'].fit_causal_scoring_windows=lambda **kw:object()
            if mode=='score_exception':modules['reducer'].reduce_fitted_scoring_windows=raising
            with self.subTest(mode=mode),TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'out'),patch.object(m,'TASK_ID',a['job_id']),patch.object(m,'FRESH_CLI',True),patch.object(m,'worker_environment',return_value={'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0}),patch.object(m,'load_inputs',return_value=context),patch.object(m,'private',side_effect=lambda role,s:modules[role]),patch.object(m,'space'),patch.object(m,'guard'):
                with self.assertRaises((ValueError,RuntimeError)):m.run(execute=True)
                stage='score' if mode=='score_exception' else 'fit';raw=m.loads((m.OUTPUT/f'raw_{stage}.json').read_bytes());failure=m.loads((m.OUTPUT/'failure.json').read_bytes())
                self.assertEqual(raw['returned'],mode in ('none','unserializable'));self.assertTrue(raw['call_invoked']);self.assertIsNone(raw['internal_optimizer_call_count'])
                self.assertEqual(failure['outcome'],'NUMERICAL_EXCEPTION' if mode in ('exception','score_exception') else 'VALIDATION_FAILURE')
                if mode=='unserializable':self.assertFalse(raw['result_preserved_as_json']);self.assertTrue((m.OUTPUT/'raw_fit_representation.bin').exists())
    def test_environment_failure_after_return_keeps_raw(self):
        context,a,modules=fixture();state={'changed':False}
        original=modules['rolling'].fit_causal_scoring_windows
        def returning(**kw):
            result=original(**kw);state['changed']=True;return result
        modules['rolling'].fit_causal_scoring_windows=returning
        def env():
            if state['changed']:raise ValueError('changed worker environment')
            return {'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0}
        with TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'out'),patch.object(m,'TASK_ID',a['job_id']),patch.object(m,'FRESH_CLI',True),patch.object(m,'worker_environment',side_effect=env),patch.object(m,'load_inputs',return_value=context),patch.object(m,'private',side_effect=lambda role,s:modules[role]),patch.object(m,'space'),patch.object(m,'guard'):
            with self.assertRaisesRegex(ValueError,'changed worker'):m.run(execute=True)
            raw=m.loads((m.OUTPUT/'raw_fit.json').read_bytes());self.assertTrue(raw['returned']);self.assertEqual(len(raw['result']['windows']),13)
            self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'raw_score.json').exists())

    def test_post_fit_drift_keeps_return(self):
        context,a,modules=fixture();calls=[]
        def guard(s):
            calls.append(True)
            if len(calls)==3:raise ValueError('post-fit source drift')
        with TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'out'),patch.object(m,'TASK_ID',a['job_id']),patch.object(m,'FRESH_CLI',True),patch.object(m,'worker_environment',return_value={'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0}),patch.object(m,'load_inputs',return_value=context),patch.object(m,'private',side_effect=lambda role,s:modules[role]),patch.object(m,'space'),patch.object(m,'guard',side_effect=guard):
            with self.assertRaisesRegex(ValueError,'post-fit'):m.run(execute=True)
            self.assertTrue(m.loads((m.OUTPUT/'raw_fit.json').read_bytes())['returned'])
            self.assertFalse((m.OUTPUT/'raw_score.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())

if __name__=='__main__':unittest.main()
