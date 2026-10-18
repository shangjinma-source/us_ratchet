import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import patch
from scripts import ndx_registered_forward_capture_runtime_20261009_v1 as module


class RegisteredCaptureRuntimeTests(unittest.TestCase):
    def test_pending_or_unapproved_execution_precedes_all_source_io(self):
        for execute in (False,True):
            with patch.object(module,'REGISTRATION_CORE',(module.REGISTRATION_CORE[0],None)),patch.object(module,'consume',side_effect=AssertionError('IO')):
                with self.assertRaises(ValueError):module.run(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,execute=execute)

    def test_private_five_module_closure_ignores_sysmodules_substitutions(self):
        sources={};refs=module.configured(module.DEPENDENCIES)
        raw={key:module.consume(item,sources)for key,item in refs.items()}
        fake=ModuleType('fake');fake.inspect_parent_history_v4=lambda x:(_ for _ in()).throw(AssertionError('hostile'))
        with patch.dict(sys.modules,{'backtest.ndx_prospective_observation_parent_history_research_v4':fake}):
            core=module.private_core(raw)
        self.assertIsNot(core.parent_view,fake)
        self.assertEqual(core.PARENT_VIEW_SHA256,module.DEPENDENCIES['parent_view'][1])
        raw['capture_core']+=b'\n'
        with self.assertRaisesRegex(ValueError,'Private dependency SHA'):module.private_core(raw)

    def test_current_cache_requires_nonempty_bounded_bytes(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'current.csv';path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'nonempty'):module.read_current(path)
            path.write_bytes(b'bytes');self.assertEqual(module.read_current(path),b'bytes')
            with self.assertRaises(ValueError):module.read_current(path.parent)

    def test_live_guard_detects_drift_without_permanent_mutable_claim(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'current.csv';path.write_bytes(b'first')
            item=module.reference(str(path),hashlib.sha256(b'first').hexdigest())
            with patch.object(module,'parent_namespaces'),patch.object(module,'CURRENT',{'QQQ':path,'SPY':path}):
                module.guard_current({}, {}, {'QQQ':item})
                with self.assertRaisesRegex(ValueError,'persistent mutable'):module.guard({str(path):item['sha256']},{})
                path.write_bytes(b'second')
                with self.assertRaisesRegex(ValueError,'Source SHA'):module.guard_current({}, {}, {'QQQ':item})

    def test_create_only_failure_preservation_and_resource_gate(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'started.json';module.save(path,dict(ok=True))
            with self.assertRaises(FileExistsError):module.save(path,{})
            class Disk:free=0
            with patch.object(module.shutil,'disk_usage',return_value=Disk()):
                with self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):module.save(path.parent/'QQQ.csv',{})
                module.save(path.parent/'failure.json',dict(status='FAILED_DO_NOT_CONSUME'))
            self.assertTrue(path.exists());self.assertTrue((path.parent/'failure.json').exists())
            self.assertFalse((path.parent/'QQQ.csv').exists())

    def test_duplicate_registration_or_nonfinite_json_reject(self):
        for raw in (b'{"schema":1,"schema":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):module.decode(raw)


if __name__=='__main__':unittest.main()
