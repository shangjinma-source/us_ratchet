"""Independent mocked dispatch and durability checks, never actual engines."""
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
import test_ndx_dated_account_execution_20261003 as owner
m=owner.core


class Review(unittest.TestCase):
    def invoke(self,s,root):
        with patch.object(m,'prepare',return_value=s),patch.object(m,'OUTPUT',root/'out'):
            r=m.run(s['track'],dict(path=str(root/s['numerical_task_id']/'inputs.json'),sha256='a'*64),owner.REF,execute=True)
        post=m.loads(Path(r['path']).read_bytes());raw=m.loads(Path(post['raw_reference']['path']).read_bytes())
        return post,raw

    def test_none_return_is_durable_validation_failure_not_success(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'execute_engine',return_value=None) as engine,patch.object(m,'guard'):
            post,raw=self.invoke(owner.state(),Path(tmp))
            self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED')
            self.assertIsNone(raw['account']);self.assertEqual(raw['returned_account_count'],0)
            self.assertEqual(raw['engine_call_attempt_count'],1);engine.assert_called_once()

    def test_postguard_drift_preserves_exact_return_before_validation(self):
        marker={'synthetic_return':list(range(7))};calls=[]
        def guard(s):
            calls.append(1)
            if len(calls)>1:raise ValueError('drift after raw')
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'execute_engine',return_value=marker) as engine,patch.object(m,'guard',side_effect=guard),patch.object(m,'validate_returned') as validate:
            post,raw=self.invoke(owner.state(),Path(tmp))
            self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED')
            self.assertEqual(raw['account'],marker);self.assertEqual(raw['returned_account_count'],1)
            engine.assert_called_once();validate.assert_not_called()

    def test_exception_distinct_from_blocked_and_global_incumbent_single_attempt(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'execute_engine',side_effect=RuntimeError('original exception')) as engine,patch.object(m,'guard'):
            root=Path(tmp);s=owner.state('incumbent')
            post,raw=self.invoke(s,root)
            self.assertEqual(post['status'],'ACCOUNT_EXCEPTION_NO_RETURNED_RESULT')
            self.assertEqual(raw['error']['message'],'original exception');self.assertEqual(raw['returned_account_count'],0)
            s['numerical_task_id']='f'*64
            with self.assertRaises(ValueError):self.invoke(s,root)
            engine.assert_called_once()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'execute_engine') as engine,patch.object(m,'guard'):
            post,raw=self.invoke(owner.state(blocked=True),Path(tmp))
            self.assertEqual(post['status'],'NOT_EXECUTED_NONPOSITIVE_TARGET')
            self.assertEqual(raw['engine_call_attempt_count'],0);engine.assert_not_called()


if __name__=='__main__':unittest.main()
