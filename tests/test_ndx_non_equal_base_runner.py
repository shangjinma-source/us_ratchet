from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_non_equal_base_runner as runner
from backtest.ndx_dynamic_training_semantics import training_semantics
from test_ndx_joint_weight_evaluation import fixture


class NonEqualBaseRunnerTests(unittest.TestCase):
    def setUp(self):
        task, inputs = fixture()
        self.prepared = dict(inputs=inputs, source_hashes={}, tasks=[],
            training_semantics=training_semantics(inputs=inputs,
                decision_data_end=task['decision_data_end'],source_batch='fixture',universe_track='research'))
        for spec in ('constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'):
            identity = dict(task,weight_spec=spec,schema_version=runner.preparation.SCHEMA,
                            source_batch='fixture',universe_track='research')
            self.prepared['tasks'].append(dict(identity,job_id=runner.preparation._sha(identity)))
        self.temp = tempfile.TemporaryDirectory(prefix='non_equal_runner_test_',dir=runner.ROOT/'data/cache/research')
        self.addCleanup(self.temp.cleanup)
        self.args = dict(source_batch='fixture',universe_track='research',selection_date=task['selection_date'],
                         output_root=str(Path(self.temp.name)/'out'))
        patcher = patch.object(runner.preparation,'prepare_non_equal_base_date',return_value=self.prepared)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_plan_then_partial_resume_exact_context(self):
        plan = runner.run(**self.args)
        self.assertEqual(plan['status'],'PLAN_ONLY')
        self.assertFalse(Path(plan['output_dir']).exists())
        partial = runner.run(**self.args,execute=True,max_new_tasks=1)
        self.assertEqual((partial['completed'],partial['status']),(1,'PARTIAL'))
        result = runner.run(**self.args,execute=True,resume=True)
        self.assertEqual((result['completed'],result['resumed'],result['attempted']),(2,1,1))
        with patch.object(runner.evaluator,'evaluate_non_equal_fractional',side_effect=AssertionError('Must resume')):
            resumed = runner.run(**self.args,execute=True,resume=True)
        self.assertEqual(resumed['resumed'],2)

    def test_evaluation_exception_not_completed_and_context_create_only(self):
        with patch.object(runner.evaluator,'evaluate_non_equal_fractional',side_effect=ValueError('synthetic evaluation failure')):
            with self.assertRaisesRegex(ValueError,'synthetic evaluation failure'):
                runner.run(**self.args,execute=True)
        directory = next(Path(self.args['output_root']).iterdir())
        self.assertEqual([p.name for p in directory.glob('*.json')],['context.json'])
        context = directory/'context.json'; context.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'Create-only artifact'):
            runner.run(**self.args,execute=True,resume=True)
        self.assertEqual(context.read_bytes(),b'{}')

    def test_corrupt_checkpoint_rejected_without_overwrite(self):
        completed = runner.run(**self.args,execute=True,max_new_tasks=1)
        path = Path(completed['output_dir'])/(self.prepared['tasks'][0]['job_id']+'.json')
        document = json.loads(path.read_bytes()); document['status']='FAILED'
        raw=runner._bytes(document);path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'Resume checkpoint binding'):
            runner.run(**self.args,execute=True,resume=True)
        self.assertEqual(path.read_bytes(),raw)

    def test_explicit_resume_and_output_scope(self):
        runner.run(**self.args,execute=True,max_new_tasks=1)
        with self.assertRaisesRegex(ValueError,'requires explicit'):
            runner.run(**self.args,execute=True)
        for path in (runner.ROOT,runner.ROOT/'data/cache/research',
                     runner.ROOT/'data/cache/research/ndx_joint_weight_runs_v3/other'):
            with self.assertRaises(ValueError): runner.run(**dict(self.args,output_root=str(path)))

    def test_rehashed_missing_economic_metric_rejected(self):
        completed = runner.run(**self.args,execute=True,max_new_tasks=1)
        path = Path(completed['output_dir'])/(self.prepared['tasks'][0]['job_id']+'.json')
        document = json.loads(path.read_bytes())
        result = runner._restore(document['result'])
        result['result'].pop('paired_return_p10_vs_incumbent')
        document['result'] = runner.encoding._normalize(result)
        document.pop('checkpoint_sha256')
        document['checkpoint_sha256'] = runner._sha(document)
        path.write_bytes(runner._bytes(document))
        with self.assertRaisesRegex(ValueError,'Missing/nonfinite fractional metric'):
            runner.run(**self.args,execute=True,resume=True)

    def test_rehashed_scope_or_empty_window_rejected(self):
        completed = runner.run(**self.args,execute=True,max_new_tasks=1)
        path = Path(completed['output_dir'])/(self.prepared['tasks'][0]['job_id']+'.json')
        saved = json.loads(path.read_bytes())
        for mutation in (lambda r:r.update(point_in_time_verified=True),
                         lambda r:r['historical_window_weights'][0].update(weights={}),
                         lambda r:r['historical_window_weights'][0].update(fit_end='2030-01-01')):
            document = deepcopy(saved)
            result = runner._restore(document['result']);mutation(result)
            document['result'] = runner.encoding._normalize(result)
            document.pop('checkpoint_sha256')
            document['checkpoint_sha256'] = runner._sha(document)
            path.write_bytes(runner._bytes(document))
            with self.assertRaises(ValueError):runner.run(**self.args,execute=True,resume=True)


if __name__ == '__main__': unittest.main()
