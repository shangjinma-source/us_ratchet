"""New V5 publisher boundaries; temporary fixtures, never actual capture."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as module


def bound_dependencies():
    result = deepcopy(module.DEPENDENCIES)
    for key, (path, _) in result.items():
        result[key] = (path, hashlib.sha256((module.ROOT / path).read_bytes()).hexdigest())
    return result


class RegisteredCaptureV5RuntimeTests(unittest.TestCase):
    def test_pending_or_unapproved_execution_is_rejected_before_io(self):
        for execute in (False, True):
            with patch.object(module, 'REGISTRATION_CORE', (module.REGISTRATION_CORE[0], None)), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('Unapproved IO')):
                with self.assertRaises(ValueError):
                    module.run(registration_path='E:/synthetic/registration.json', registration_sha256='a' * 64, execute=execute)

    def test_private_six_module_closure_ignores_hostile_cached_imports(self):
        dependencies = bound_dependencies()
        with patch.object(module, 'DEPENDENCIES', dependencies):
            raw = {key: module.consume(item, {}) for key, item in module.configured(dependencies).items()}
            hostile = ModuleType('hostile')
            hostile.inspect_parent_history_v5 = lambda value: (_ for _ in ()).throw(AssertionError('Cached import'))
            with patch.dict(sys.modules, {
                'backtest.ndx_prospective_history_parent_view_research_v5': hostile,
                'backtest.ndx_prospective_observation_parent_history_research_v4': hostile,
            }):
                core = module.private_core(raw)
            self.assertIsNot(core.parent_view, hostile)
            self.assertIsNot(core.parent_view.legacy, hostile)
            self.assertEqual(core.LEGACY_VIEW_SHA256, dependencies['legacy_view'][1])
            self.assertEqual(Path(core.parent_view.legacy.__file__), module.ROOT / dependencies['legacy_view'][0])
            raw['legacy_view'] += b'\n'
            with self.assertRaisesRegex(ValueError, 'Private dependency SHA'):
                module.private_core(raw)

    def test_permanent_current_claim_is_rejected_before_read_and_live_guard_is_explicit(self):
        with TemporaryDirectory() as folder:
            current = Path(folder) / 'current.csv'
            current.write_bytes(b'original')
            reference = module.reference(str(current), module.digest(b'original'))
            with patch.object(module, 'CURRENT', {'QQQ': current, 'SPY': current}), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('Mutable read')):
                with self.assertRaisesRegex(ValueError, 'before immutable source read'):
                    module.consume(reference, {})
            with patch.object(module, 'CURRENT', {'QQQ': current, 'SPY': current}), \
                    patch.object(module, 'parent_namespaces'):
                module.guard_current({}, {}, {'QQQ': reference})
                current.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'Source SHA'):
                    module.guard_current({}, {}, {'QQQ': reference})

    def test_create_only_resource_and_failure_evidence_preserved(self):
        with TemporaryDirectory() as folder:
            started = Path(folder) / 'started.json'
            module.save(started, dict(ok=True))
            with self.assertRaises(FileExistsError):
                module.save(started, dict(ok=False))
            with patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError, 'RESOURCE_STOP'):
                    module.save(Path(folder) / 'capture.json', {})
                module.save(Path(folder) / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME'))
            self.assertTrue(started.exists())
            self.assertTrue((Path(folder) / 'failure.json').exists())
            self.assertFalse((Path(folder) / 'capture.json').exists())

    def test_duplicate_or_nonfinite_registration_json_rejected(self):
        for raw in (b'{"schema":1,"schema":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError):
                module.decode(raw)


if __name__ == '__main__':
    unittest.main()
