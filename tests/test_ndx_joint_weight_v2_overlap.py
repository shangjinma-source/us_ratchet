"""Independent overlap coverage, integrity, and no-write regression tests."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_joint_weight_runner as old
from backtest import ndx_joint_weight_evaluation_v2 as revised
from test_ndx_joint_weight_runner import prepared

spec=importlib.util.spec_from_file_location('overlap',Path(__file__).resolve().parents[1]/'scripts/ndx_joint_weight_v2_overlap.py')
overlap=importlib.util.module_from_spec(spec);spec.loader.exec_module(overlap)


class OverlapTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.root_patch=patch.object(old,'CHECKPOINT_ROOT',self.root)
        self.root_patch.start();self.addCleanup(self.root_patch.stop)

    def capture(self,*,mutate=None,checkpoint=True):
        tasks,inputs=prepared()
        context=dict(schema='ndx_joint_weight_checkpoint_v1',tasks=tasks,
            prepared_inputs={k:old._panel_context(v) for k,v in inputs.items()},
            source_evidence=old._normalize({'test':'overlap'}),numerical_sources=old._source_hashes(),
            runtime=dict(python=old.platform.python_version(),numpy=old.np.__version__,
                         pandas=old.pd.__version__,scipy=old.scipy.__version__))
        if mutate:
            mutate(context)
        digest=old._sha(context);directory=self.root/digest;directory.mkdir()
        old._publish(directory/'context.json',context)
        if checkpoint:
            prior=old.evaluate_joint_weight_task(tasks[0],**inputs)
            item=dict(context_sha256=digest,task=tasks[0],status='EVALUATED',result=old._normalize(prior))
            item['checkpoint_sha256']=old._sha(item)
            old._publish(directory/(tasks[0]['job_id']+'.json'),item)
        return digest,directory,tasks,inputs

    def test_actual_v2_evaluates_missing_old_tasks_without_writes(self):
        digest,directory,tasks,inputs=self.capture()
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=overlap.run([digest])
        self.assertEqual((result['planned'],result['evaluated']),(2,2))
        self.assertEqual([r['had_v1_checkpoint'] for r in result['rows']],[True,False])
        self.assertEqual(len(result['rows'][0]['fractional_metric_absolute_difference']),8)
        self.assertNotIn('fractional_metric_absolute_difference',result['rows'][1])
        self.assertFalse(result['prior_results_reused'])
        self.assertFalse(result['promotion_allowed'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_context_schema_empty_and_duplicate_tasks_rejected(self):
        mutations=[lambda c:c.update(schema='unknown'),lambda c:c.update(tasks=[]),
                   lambda c:c.update(tasks=c['tasks']+[copy.deepcopy(c['tasks'][0])])]
        for mutation in mutations:
            digest,_,_,_=self.capture(mutate=mutation,checkpoint=False)
            with self.subTest(digest=digest),self.assertRaises(ValueError):
                overlap.run([digest])

    def test_checkpoint_extra_fields_and_noncanonical_context_rejected(self):
        digest,directory,tasks,_=self.capture()
        path=directory/(tasks[0]['job_id']+'.json')
        import json
        item=json.loads(path.read_bytes());item.pop('checkpoint_sha256')
        item['unbound_extra']=True;item['checkpoint_sha256']=old._sha(item)
        path.write_bytes(old._json_bytes(item))
        with self.assertRaises(ValueError):
            overlap.run([digest])
        path=directory/'context.json';path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Noncanonical'):
            overlap.run([digest])

    def test_computation_exception_is_not_a_negative_result(self):
        digest,_,_,_=self.capture(checkpoint=False)
        actual=revised.evaluate_joint_weight_task_v2;calls=0
        def one_error(task,**inputs):
            nonlocal calls
            calls+=1
            if calls==1:
                raise ValueError('Numerical solver did not converge')
            return actual(task,**inputs)
        with patch.object(revised,'evaluate_joint_weight_task_v2',side_effect=one_error):
            result=overlap.run([digest])
        self.assertEqual((result['planned'],result['evaluated']),(2,1))
        self.assertEqual(result['rows'][0]['status'],'V2_COMPUTATION_ERROR')
        self.assertNotIn('declared_constraints_passed',result['rows'][0])
        self.assertEqual(result['rows'][1]['status'],'V2_EVALUATED')

    def test_resigned_baseline_identity_and_boolean_poison_rejected(self):
        import json
        digest, directory, tasks, _ = self.capture()
        path = directory / (tasks[0]['job_id'] + '.json')
        original = json.loads(path.read_bytes())
        for field, value in [('tickers', 'WRONG'), ('holding_count', True),
                             ('return_p50_vs_012922', True), ('declared_constraints_passed', 1)]:
            item = copy.deepcopy(original)
            item.pop('checkpoint_sha256')
            item['result']['mapping'][field] = value
            item['checkpoint_sha256'] = old._sha(item)
            path.write_bytes(old._json_bytes(item))
            with self.subTest(field=field), self.assertRaises(ValueError):
                overlap.run([digest])

    def test_old_dependency_source_drift_at_end_is_rejected(self):
        digest,_,_,_=self.capture(checkpoint=False)
        sources=old._source_hashes();changed=dict(sources)
        changed['backtest/ndx_joint_weight_delta.py']='0'*64
        calls=0
        def hashes():
            nonlocal calls
            calls+=1
            return sources if calls==1 else changed
        with patch.object(old,'_source_hashes',side_effect=hashes):
            with self.assertRaises(ValueError):
                overlap.run([digest])


if __name__=='__main__':
    unittest.main()
