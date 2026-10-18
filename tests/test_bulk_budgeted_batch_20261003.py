import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/ndx_bulk_budgeted_batch_20261003.py'
spec = importlib.util.spec_from_file_location('bulk_batch', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BatchTests(unittest.TestCase):
    def test_risk_failure_continues_but_numerical_exception_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            called = []
            def runner(task_id):
                called.append(task_id)
                return dict(path='synthetic', sha256='a'*64)
            def reader(task_id, reference):
                outcome = {'one':'RISK_FAILED', 'two':'NUMERICAL_EXCEPTION'}[task_id]
                return module.save(base / (task_id+'.json'), dict(numerical_task_id=task_id,
                    status='PASSED', attempt_outcome=outcome))
            result = module.execute_queue(['one', 'two', 'three'], run_task=runner, read_task=reader,
                verify_sources=lambda: None, output=base/'batch', initial_rows=[])
            document = module.reference_load(result)
            self.assertEqual(called, ['one','two'])
            self.assertEqual(document['undispatched_task_ids'], ['three'])
            self.assertEqual(document['new_outcome_counts']['RISK_FAILED'], 1)
            self.assertEqual(document['status'], 'STOPPED_WITH_EVIDENCE')
            with self.assertRaises(ValueError):
                module.execute_queue(['one'], run_task=runner, read_task=reader,
                    verify_sources=lambda: None, output=base/'batch', initial_rows=[])
            self.assertEqual(called, ['one','two'])

    def test_readback_failure_preserves_external_anchor_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            calls=[]
            def runner(task_id):
                calls.append(task_id)
                return dict(path='saved_postcheck', sha256='a'*64)
            def reader(task_id, reference):
                raise ValueError('independent source mismatch')
            result = module.execute_queue(['one', 'two'], run_task=runner, read_task=reader,
                verify_sources=lambda:None, output=base/'batch', initial_rows=[])
            document=module.reference_load(result)
            self.assertEqual(calls,['one'])
            self.assertEqual(document['new_readback_count'],0)
            self.assertEqual(document['failure']['postcheck_reference']['path'],'saved_postcheck')
            self.assertEqual(document['undispatched_task_ids'],['two'])

    def test_duplicates_rejected_before_any_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'batch'
            with self.assertRaises(ValueError):
                module.execute_queue(['one','one'],run_task=lambda x: self.fail('dispatch'),
                    read_task=lambda x,y:None,verify_sources=lambda:None,output=output,initial_rows=[])
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
