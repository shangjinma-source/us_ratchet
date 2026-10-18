import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_joint_weight_runner as old
from backtest.ndx_joint_weight_evaluation_v2 import _bind
from test_ndx_joint_weight_runner import prepared

spec=importlib.util.spec_from_file_location('batch_v3',Path(__file__).resolve().parents[1]/'scripts/ndx_joint_weight_batch_v3.py')
batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)


class BatchV3Tests(unittest.TestCase):
    def fixture(self,root):
        tasks,inputs=prepared()
        plan=dict(experiment_sha256='e'*64,experiment=dict(evaluation_contract=inputs['contract'],
            training_lookback_days=504,minimum_price_rows_before_selection=252,allow_revised_return_data=True),
            plans=[dict(tasks=tasks,child_sha256='a'*64,child_path='unused',coordinate={})],planned=2)
        capture=dict(schema='ndx_joint_weight_batch_capture_v1',experiment_sha256='e'*64,cli_sha256='c'*64,
            tasks=tasks,prepared_inputs={k:old._panel_context(v) for k,v in inputs.items()},
            source_evidence=old._normalize(dict(experiment_sha256='e'*64,cli_sha256='c'*64,loader_provenance={})),
            numerical_sources=old._source_hashes(),runtime={},panel_metadata={})
        capture['capture_sha256']=old._sha(capture)
        path=root/'old_capture.json';path.write_bytes(old._json_bytes(capture))
        manifest=dict(schema='ndx_joint_weight_frozen_inputs_v1',original_experiment_sha256='e'*64,
            captures=[dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
        manifest_path=root/'manifest.json';manifest_path.write_text(json.dumps(manifest))
        return plan,inputs,capture,manifest_path

    def test_frozen_inputs_new_v3_evaluations_resume_without_live_reprepare(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan,inputs,capture,path=self.fixture(root)
            bundle=batch.load_frozen_inputs(path,plan)
            checkpoint_root=root/'v3_results';destination=root/'v3_capture';destination.mkdir()
            isolated=_bind(batch.runner._RUN,CHECKPOINT_ROOT=checkpoint_root)
            calls=[]
            def capture_before_evaluation(*args,**kwargs):
                self.assertTrue(list(destination.glob('*.json')),
                                'Captured immutable inputs must exist before evaluator invocation')
                calls.append(kwargs.get('max_tasks'))
                return isolated(*args,**kwargs)
            old_globals=dict(old.__dict__)
            old_raw=(root/'old_capture.json').read_bytes()
            with patch.object(batch,'prepare_joint_weight_history_inputs',side_effect=AssertionError('must use frozen')),patch.object(
                batch.runner,'run_joint_weight_tasks_v3',capture_before_evaluation):
                execute=batch.bound_executor(bundle,batch.dependency_hashes())
                first=execute(plan,max_new_evaluations=1,destination=destination,cli_hash='b'*64)
                second=execute(plan,max_new_evaluations=1,destination=destination,cli_hash='b'*64)
            self.assertEqual((first['planned'],first['attempted'],first['completed']),(2,1,1))
            self.assertEqual((second['planned'],second['attempted'],second['completed'],second['resumed']),(2,1,2,1))
            self.assertEqual(calls,[1,1])
            self.assertEqual(old_raw,(root/'old_capture.json').read_bytes())
            for key,value in old_globals.items():self.assertIs(old.__dict__[key],value)
            context=json.loads(next(checkpoint_root.rglob('context.json')).read_bytes())
            self.assertIn('backtest/ndx_projection_reconstruction_research.py',context['numerical_sources'])
            self.assertIn('backtest/ndx_joint_weight_runner_v3.py',context['numerical_sources'])
            self.assertIn('backtest/ndx_joint_weight_evaluation_v3.py',context['numerical_sources'])
            evidence=batch._restore(context['source_evidence'])
            self.assertFalse(evidence['loader_provenance']['old_results_reused'])
            self.assertEqual(evidence['loader_provenance']['frozen_capture']['path'],str(root/'old_capture.json'))

    def test_frozen_contract_changed_or_outer_digest_tampered_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan,_,_,path=self.fixture(root)
            changed=copy.deepcopy(plan);changed['experiment']['evaluation_contract']['portfolio_cash_usd']=25000.
            with self.assertRaisesRegex(ValueError,'evaluation contract differs'):
                batch.load_frozen_inputs(path,changed)
            (root/'old_capture.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Unrecoverable source'):
                batch.load_frozen_inputs(path,plan)

    def test_namespace_binds_helper_manifest_and_experiment(self):
        dependencies=batch.dependency_hashes()
        original=batch.namespace_hash('a'*64,'b'*64,dependencies)
        self.assertNotEqual(original,batch.namespace_hash('c'*64,'b'*64,dependencies))
        self.assertNotEqual(original,batch.namespace_hash('a'*64,'c'*64,dependencies))
        changed=dict(dependencies);changed['scripts/ndx_joint_weight_batch.py']='0'*64
        self.assertNotEqual(original,batch.namespace_hash('a'*64,'b'*64,changed))
        from scripts import ndx_joint_weight_batch_v2 as previous
        self.assertNotEqual(batch.BATCH_ROOT,previous.BATCH_ROOT)
        self.assertNotEqual(original,previous.namespace_hash('a'*64,'b'*64,previous.dependency_hashes()))

    def test_execute_requires_positive_global_budget_not_bool(self):
        for budget in (None,0,-1,True):
            with self.subTest(budget=budget),self.assertRaisesRegex(ValueError,'Positive global budget'):
                batch.run('unused','unused',execute=True,max_new_evaluations=budget)

    def test_budget_does_not_shrink_later_coordinate_denominator(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan,_,_,manifest=self.fixture(root)
            bundle=batch.load_frozen_inputs(manifest,plan)
            second=copy.deepcopy(plan['plans'][0]);second['child_sha256']='d'*64
            for task in second['tasks']:
                task['child_manifest_sha256']='d'*64
                task['job_id']=old._sha({k:v for k,v in task.items()
                                        if k not in ('job_id','second_stage_selection_tags')})
            plan['plans'].append(second);plan['planned']=4
            destination=root/'captures';destination.mkdir()
            isolated=_bind(batch.runner._RUN,CHECKPOINT_ROOT=root/'v3_runs')
            with patch.object(batch.runner,'run_joint_weight_tasks_v3',isolated),patch.object(
                    batch,'prepare_joint_weight_history_inputs',side_effect=AssertionError('later input must not load')):
                result=batch.bound_executor(bundle,batch.dependency_hashes())(
                    plan,max_new_evaluations=1,destination=destination,cli_hash='b'*64)
            self.assertEqual((result['planned'],result['attempted'],result['completed']),(4,1,1))
            self.assertEqual(len(list(destination.glob('*.json'))),1)


if __name__=='__main__':
    unittest.main()
