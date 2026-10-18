import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_joint_weight_runner as original
from backtest import ndx_joint_weight_runner_v2 as previous
from backtest import ndx_joint_weight_runner_v3 as runner
from backtest import ndx_joint_weight_evaluation_v2 as binding
from backtest import ndx_joint_weight_evaluation_v3 as evaluation
from test_ndx_joint_weight_runner import prepared


class RunnerV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = binding._bind(runner._RUN, CHECKPOINT_ROOT=self.root)

    def test_real_budget_resume_and_frozen_v2_isolation(self):
        tasks, inputs = prepared()
        before_globals = dict(previous.__dict__)
        before_binding = dict(binding.__dict__)
        old_files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in previous.CHECKPOINT_ROOT.rglob('*.json')}
        evidence = {'kind': 'V3_REAL_SYNTHETIC_TEST'}
        first = self.run(tasks, prepared_inputs=inputs, source_evidence=evidence, max_tasks=1)
        self.assertEqual((first['planned'], first['completed'], first['attempted']), (2, 1, 1))
        second = self.run(tasks, prepared_inputs=inputs, source_evidence=evidence, max_tasks=1)
        self.assertEqual((second['completed'], second['attempted'], second['resumed']), (2, 1, 1))

        def forbidden(*args, **kwargs):
            raise AssertionError('Resume must not reevaluate')

        resume = binding._bind(self.run, evaluate_joint_weight_task=forbidden)
        third = resume(tasks, prepared_inputs=inputs, source_evidence=evidence, max_tasks=1)
        self.assertEqual((third['completed'], third['attempted'], third['resumed']), (2, 0, 2))
        self.assertEqual(first['context_sha256'], second['context_sha256'])
        directory = Path(first['output_dir'])
        self.assertTrue(directory.is_relative_to(self.root))
        context = json.loads((directory/'context.json').read_bytes())
        self.assertEqual(context['numerical_sources'], runner.source_hashes())
        self.assertTrue(set(previous.NUMERICAL_SOURCES) <= set(context['numerical_sources']))
        self.assertIn('scripts/ndx_projection_reconstruction_probe.py', context['numerical_sources'])
        for task in tasks:
            checkpoint = json.loads((directory/(task['job_id']+'.json')).read_bytes())
            result = evaluation.evaluate_joint_weight_task_v3(task, **inputs)
            self.assertEqual(checkpoint['result'], original._normalize(result))
            self.assertEqual(result['projection_reconstruction_audit']['attempt_count'], 0)
        self.assertEqual(old_files, {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in previous.CHECKPOINT_ROOT.rglob('*.json')})
        for name, value in before_globals.items():
            self.assertIs(previous.__dict__[name], value)
        for name, value in before_binding.items():
            self.assertIs(binding.__dict__[name], value)

    def test_runner_source_drift_before_and_during_cannot_publish(self):
        tasks, inputs = prepared()
        hashes = runner.source_hashes()
        drifted = dict(hashes, **{'backtest/ndx_joint_weight_evaluation_v3.py': '0'*64})
        before = binding._bind(self.run, _source_hashes=lambda: drifted)
        with self.assertRaisesRegex(ValueError, 'since import'):
            before(tasks, prepared_inputs=inputs, source_evidence={'test': True}, max_tasks=1)
        self.assertEqual(list(self.root.iterdir()), [])
        calls = []

        def changing():
            calls.append(True)
            return hashes if len(calls) == 1 else drifted

        during = binding._bind(self.run, _source_hashes=changing)
        with self.assertRaisesRegex(ValueError, 'during evaluation'):
            during(tasks, prepared_inputs=inputs, source_evidence={'test': True}, max_tasks=1)
        self.assertEqual([p.name for p in self.root.rglob('*.json')], ['context.json'])

    def test_evaluator_source_drift_before_and_after(self):
        tasks, inputs = prepared()
        with patch.object(evaluation, 'source_hashes', return_value={}):
            with self.assertRaisesRegex(ValueError, 'since import'):
                evaluation.evaluate_joint_weight_task_v3(tasks[0], **inputs)
        with patch.object(evaluation, 'source_hashes', side_effect=[evaluation._LOADED_SOURCES, {}]):
            with self.assertRaisesRegex(ValueError, 'during evaluation'):
                evaluation.evaluate_joint_weight_task_v3(tasks[0], **inputs)

    def test_unmodified_numerical_path_equals_v2_except_audit(self):
        tasks, inputs = prepared()
        actual = evaluation.evaluate_joint_weight_task_v3(tasks[0], **inputs)
        audit = actual.pop('projection_reconstruction_audit')
        self.assertEqual(audit['attempts'], [])
        self.assertEqual(actual, binding.evaluate_joint_weight_task_v2(tasks[0], **inputs))


if __name__ == '__main__':
    unittest.main()
