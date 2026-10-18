import unittest
from unittest.mock import patch
from scripts import ndx_double_replacement_compressed_worker_20261008 as worker


class WorkerInterfaceTests(unittest.TestCase):
    def test_pending_anchors_stop_before_registration_read(self):
        with patch.object(worker,'read',side_effect=AssertionError('IO forbidden')):
            with self.assertRaisesRegex(ValueError,'Pending immutable SHA'):
                worker.execute(registration_path='not-existing.json',registration_sha256='1'*64,execute=True)

    def test_resource_proof_cannot_be_supplied_as_caller_cap(self):
        with patch.multiple(worker,LIFECYCLE_SHA='2'*64,RESOURCE_PROOF_SHA='3'*64),patch.object(worker,'read',side_effect=AssertionError('IO forbidden')):
            with self.assertRaisesRegex(ValueError,'Pending worst-case'):
                worker.execute(registration_path='not-existing.json',registration_sha256='1'*64,execute=True)

    def test_private_dependency_injection_without_global_module_replacement(self):
        import sys
        before=dict(sys.modules)
        marker=object()
        module=worker.private_module('synthetic',b'from backtest import fixed\nvalue=fixed','synthetic.py',{'fixed':marker})
        self.assertIs(module.value,marker)
        self.assertEqual(set(sys.modules),set(before))
        self.assertTrue(all(sys.modules[k] is v for k,v in before.items()))
        with self.assertRaisesRegex(ValueError,'Exact private'):
            worker.private_module('reject',b'from backtest import another','synthetic.py',{'fixed':marker})


if __name__=='__main__': unittest.main()
