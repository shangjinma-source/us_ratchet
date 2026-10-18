"""Producer boundaries while the final shared-reader pin remains pending."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as producer


def arguments():
    return dict(registration_path='E:/synthetic/capture_registration.json', registration_sha256='a' * 64,
        implementation_pair_binding_path='E:/synthetic/B.json', implementation_pair_binding_sha256='b' * 64,
        consumer_role_registry_path='E:/synthetic/C.json', consumer_role_registry_sha256='c' * 64, execute=True)


class ContinuationCaptureBoundaryTests(unittest.TestCase):
    def test_pending_shared_reader_and_every_pending_kernel_reject_before_io(self):
        constants = ('SHARED_ANCESTRY_VERIFIER', 'REGISTRATION_CORE', 'REFERENCE_CORE', 'PAIR_BINDING_CORE',
            'CONSUMER_REGISTRY_CORE', 'CONSUMER_METADATA_CORE', 'ANCESTRY_CONTRACT', 'LEGACY_ANCESTRY_CONTRACT',
            'PREFIX_CORE', 'GAP_CORE')
        for name in constants:
            with self.subTest(name=name), patch.object(producer, name, (getattr(producer, name)[0], None)), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('Pending source IO')), \
                    patch.object(producer, 'consume', side_effect=AssertionError('Pending consume')):
                with self.assertRaises(ValueError):
                    producer.run(**arguments())
        with patch.object(producer, 'consume', side_effect=AssertionError('Disabled IO')):
            values = arguments()
            values['execute'] = False
            with self.assertRaises(ValueError):
                producer.run(**values)

    def test_windows_reference_aliases_and_conflicts_reject(self):
        for invalid in ('relative/file', 'E:/x/../y', 'E:/x./y', 'E:/con/file', 'E:/x:stream', '//server/share/x'):
            with self.subTest(path=invalid), self.assertRaises(ValueError):
                producer.reference(invalid, 'a' * 64)
        sources = {}
        producer.merge(sources, producer.reference('E:/fixed/file.json', 'a' * 64))
        for path, digest in [('e:\\fixed\\FILE.json', 'a' * 64), ('E:/fixed/file.json', 'b' * 64)]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                producer.merge(sources, producer.reference(path, digest))

    def test_private_business_modules_use_original_verified_bytes(self):
        raw = {role: producer.consume(item, {}) for role, item in producer.configured(producer.DEPENDENCIES).items()}
        original = deepcopy(raw)
        hostile = ModuleType('hostile_cached_parent_view')
        hostile.inspect_parent_history_v5 = lambda value: (_ for _ in ()).throw(AssertionError('Cached code'))
        with patch.dict(sys.modules, {'backtest.ndx_prospective_history_parent_view_research_v5': hostile}):
            core = producer.private_core(raw)
        self.assertIsNot(core.parent_view, hostile)
        self.assertEqual(core.PARENT_VIEW_SHA256, producer.DEPENDENCIES['parent_view'][1])
        self.assertEqual(raw, original)
        raw['capture_core'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'Private dependency SHA'):
            producer.private_core(raw)

    def test_mutable_cache_never_enters_immutable_sources(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'current.csv'
            path.write_bytes(b'current')
            item = producer.reference(str(path), producer.digest(b'current'))
            with patch.object(producer, 'CURRENT', {'QQQ': path, 'SPY': path}), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('Mutable IO')):
                with self.assertRaisesRegex(ValueError, 'Mutable cache excluded'):
                    producer.consume(item, {})
            with patch.object(producer, 'CURRENT', {'QQQ': path, 'SPY': path}):
                self.assertEqual(producer.consume(item, {}, allow_current=True), b'current')

    def test_create_only_resource_stop_and_failure_evidence(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)
            producer.save(path / 'started.json', {'started': True})
            with self.assertRaises(FileExistsError):
                producer.save(path / 'started.json', {'started': False})
            with patch.object(producer.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError, 'RESOURCE_STOP'):
                    producer.save(path / 'capture.json', {})
                producer.save(path / 'failure.json', {'status': 'FAILED_DO_NOT_CONSUME'})
            self.assertEqual({item.name for item in path.iterdir()}, {'started.json', 'failure.json'})

    def test_json_duplicate_and_nonfinite_values_reject(self):
        for raw in (b'{"schema":1,"schema":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.assertRaises(ValueError):
                producer.decode(raw)


if __name__ == '__main__':
    unittest.main()
