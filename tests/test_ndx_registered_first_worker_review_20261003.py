from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from scripts import ndx_registered_scoring_first_task_20261003 as worker


class Review(unittest.TestCase):
    def test_seed_environment_alone_cannot_override_process_hash_randomization(self):
        with patch.dict(worker.os.environ,{'PYTHONHASHSEED':'0'}),patch.object(worker.sys,'flags',SimpleNamespace(hash_randomization=1)):
            with self.assertRaises(ValueError):worker.worker_environment()
        with patch.dict(worker.os.environ,{'PYTHONHASHSEED':'1'}),patch.object(worker.sys,'flags',SimpleNamespace(hash_randomization=0)):
            with self.assertRaises(ValueError):worker.worker_environment()

    def test_return_survives_environment_or_runtime_failure_after_dispatch(self):
        for failed_probe in ('runtime','worker_environment'):
            changed=[False]
            def operation():changed[0]=True;return {'complete_return':list(range(13))}
            def metadata():
                if changed[0]:raise ValueError('changed during call')
                return {'initial':'captured'}
            with self.subTest(probe=failed_probe),TemporaryDirectory() as td,patch.object(worker,'OUTPUT',Path(td)),patch.object(worker,'space'),patch.object(worker,'runtime',return_value={}),patch.object(worker,'worker_environment',return_value={}),patch.object(worker,failed_probe,side_effect=metadata):
                written=[]
                try:worker.call_and_preserve('fit',operation,{}, {'path':'inputs','sha256':'a'*64},{'sources':{}},written)
                except ValueError:pass
                self.assertTrue((Path(td)/'raw_fit.json').exists(),'Returned result must be durable before post-call checks')
                raw=worker.loads((Path(td)/'raw_fit.json').read_bytes())
                self.assertTrue(raw['returned']);self.assertEqual(raw['returned_call_count'],1)
                self.assertEqual(raw['result'],{'complete_return':list(range(13))})

    def test_function_exception_is_not_a_returned_result(self):
        def operation():raise ArithmeticError('original compute failure')
        with TemporaryDirectory() as td,patch.object(worker,'OUTPUT',Path(td)),patch.object(worker,'space'),patch.object(worker,'runtime',return_value={}),patch.object(worker,'worker_environment',return_value={}):
            raw,ref=worker.call_and_preserve('fit',operation,{}, {'path':'inputs','sha256':'a'*64},{'sources':{}},[])
            self.assertFalse(raw['returned']);self.assertEqual(raw['returned_call_count'],0)
            self.assertIsNone(raw['result']);self.assertIsNone(raw['internal_optimizer_call_count'])
            self.assertEqual(raw['error']['type'],'ArithmeticError')
            self.assertEqual(worker.file_hash(ref['path']),ref['sha256'])


if __name__=='__main__':unittest.main()
