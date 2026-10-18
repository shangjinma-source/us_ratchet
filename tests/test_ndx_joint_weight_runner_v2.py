"""Independent real-evaluator tests for isolated v2 checkpoint execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backtest import ndx_joint_weight_runner as v1
from backtest import ndx_joint_weight_runner_v2 as v2
from backtest import ndx_joint_weight_evaluation_v2 as evaluation
from backtest import ndx_joint_weight_evaluation as old_evaluation
from backtest import ndx_cardinality_discovery as discovery
from test_ndx_joint_weight_runner import prepared


class RunnerV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.run=evaluation._bind(v2._RUN,CHECKPOINT_ROOT=self.root)

    def test_real_budget_resume_source_binding_and_v1_untouched(self):
        tasks,inputs=prepared()
        evidence={'kind':'V2_INDEPENDENT_SYNTHETIC_TEST'}
        globals_before={name:value for name,value in v1.__dict__.items()}
        dependency_before=(old_evaluation.evaluate_joint_weight_task.__globals__['evaluate_synthetic_portfolio'],
            discovery.evaluate_synthetic_portfolio.__globals__['constrained_fixed_shrinkage_weights'],
            discovery.constrained_fixed_shrinkage_weights.__globals__['project_concentration_envelope_weights'])
        old_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in v1.CHECKPOINT_ROOT.rglob('*.json')}
        first=self.run(tasks,prepared_inputs=inputs,source_evidence=evidence,max_tasks=1)
        self.assertEqual((first['planned'],first['completed'],first['attempted']),(2,1,1))
        self.assertEqual(first['status'],'PARTIAL')
        second=self.run(tasks,prepared_inputs=inputs,source_evidence=evidence,max_tasks=1)
        self.assertEqual((second['planned'],second['completed'],second['attempted'],second['resumed']),(2,2,1,1))
        self.assertEqual(first['context_sha256'],second['context_sha256'])
        def must_not_evaluate(*args,**kwargs):
            raise AssertionError('Completed checkpoint must resume')
        resume=evaluation._bind(self.run,evaluate_joint_weight_task=must_not_evaluate)
        third=resume(tasks,prepared_inputs=inputs,source_evidence=evidence,max_tasks=1)
        self.assertEqual((third['completed'],third['attempted'],third['resumed']),(2,0,2))
        directory=Path(first['output_dir'])
        self.assertTrue(directory.is_relative_to(self.root))
        context=json.loads((directory/'context.json').read_bytes())
        expected=set(v1.NUMERICAL_SOURCES)|set(evaluation.SOURCE_PATHS)|{'backtest/ndx_joint_weight_runner_v2.py'}
        self.assertEqual(set(context['numerical_sources']),expected)
        self.assertEqual(context['numerical_sources'],v2.source_hashes())
        for task in tasks:
            checkpoint=json.loads((directory/(task['job_id']+'.json')).read_bytes())
            actual=evaluation.evaluate_joint_weight_task_v2(task,**inputs)
            self.assertEqual(checkpoint['result'],v1._normalize(actual))
            self.assertEqual(checkpoint['status'],'EVALUATED')
        self.assertEqual(old_files,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in v1.CHECKPOINT_ROOT.rglob('*.json')})
        self.assertEqual(set(globals_before),set(v1.__dict__))
        for name,value in globals_before.items():
            self.assertIs(v1.__dict__[name],value,name)
        self.assertEqual(dependency_before,(
            old_evaluation.evaluate_joint_weight_task.__globals__['evaluate_synthetic_portfolio'],
            discovery.evaluate_synthetic_portfolio.__globals__['constrained_fixed_shrinkage_weights'],
            discovery.constrained_fixed_shrinkage_weights.__globals__['project_concentration_envelope_weights']))

    def test_source_drift_before_evaluation_rejected_without_output(self):
        tasks,inputs=prepared()
        drifted=v2.source_hashes();drifted['backtest/ndx_concentration_projection_v2.py']='0'*64
        changed=evaluation._bind(self.run,_source_hashes=lambda:drifted)
        with self.assertRaisesRegex(ValueError,'since import'):
            changed(tasks,prepared_inputs=inputs,source_evidence={'test':True},max_tasks=1)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_source_drift_during_real_evaluation_cannot_publish_checkpoint(self):
        tasks,inputs=prepared()
        original=v2.source_hashes();calls=0
        def changing_hashes():
            nonlocal calls
            calls+=1
            if calls==1:
                return original
            return dict(original,**{'backtest/ndx_joint_weight_evaluation_v2.py':'0'*64})
        changed=evaluation._bind(self.run,_source_hashes=changing_hashes)
        with self.assertRaisesRegex(ValueError,'during evaluation'):
            changed(tasks,prepared_inputs=inputs,source_evidence={'test':True},max_tasks=1)
        self.assertEqual([p.name for p in self.root.rglob('*.json')],['context.json'])


if __name__=='__main__':
    unittest.main()
