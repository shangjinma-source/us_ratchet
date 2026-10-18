"""IO boundary tests with temporary files; pure semantic tests live separately."""
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_forward_gap_parent_source_capture_20261009_v3 as producer


class CaptureIOTests(unittest.TestCase):
    def test_pending_anchor_rejects_before_io(self):
        with patch.object(producer, 'PURE_SHA', None), patch.object(Path, 'read_bytes', side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError, 'Pending'):
                producer.run(execute=True)

    def test_exclusive_namespace_checked_before_source_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(producer, 'OUTPUT', Path(folder)), patch.object(producer, 'PURE_SHA', 'a'*64),
                  patch.object(Path, 'read_bytes', side_effect=AssertionError('IO'))):
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    producer.run(execute=True)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"k":1,"k":2}', b'{"k":NaN}', b'{"k":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                producer.decode(raw)

    def test_mutable_cache_cannot_be_persistent_source(self):
        with patch.object(producer, 'parent_namespaces'), patch.object(producer, 'consume', side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError, 'persistent mutable'):
                producer.guard({str(producer.CURRENT['QQQ']): 'a'*64}, {})

    def fixture(self, root):
        def write(relative, raw):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return producer.reference(str(path), producer.digest(raw))
        accounted = {t: write('baseline/'+t+'.csv', b'accounted\n') for t in ('QQQ', 'SPY')}
        actual = {t: write('actual/'+t+'.csv', b'actual\n') for t in ('QQQ', 'SPY')}
        tzif = write('baseline/New_York.tzif', b'tzif')
        history = {'history': {'captured_source_references': accounted, 'baseline_references': actual,
                              'tzif_reference': tzif}, 'source_hashes': {}}
        entries = {'reference': write('parent/history.json', producer.encode(history)),
                   'publication_reference': write('parent/publication.json', b'{"source_hashes":{}}'),
                   'readback_reference': write('reader/independent_readback.json', b'{"source_hashes":{}}'),
                   'reader_reference': write('scripts/reader.py', b'reader')}
        write('parent/started.json', b'{}'); write('reader/started.json', b'{}')
        pure = write('backtest/pure.py', b'pure')
        dependencies = {key: write('backtest/'+key+'.py', key.encode()) for key in ('base', 'scoped')}
        current = {t: Path(write('data/cache/'+t+'.csv', b'current-'+t.encode())['path']) for t in ('QQQ', 'SPY')}
        core = SimpleNamespace()
        def plan(**arguments):
            core.arguments = arguments
            return dict(schema='FORWARD_GAP_PARENT_CAPTURE_PLAN_V3', status='NO_NEW_SESSION',
                        source_reference_claims={item['path']: item['sha256'] for item in
                            (*arguments['source_references'].values(), arguments['tzif_reference'])},
                        **{key: False for key in producer.FLAGS if key != 'network_quote_refresh_performed'})
        core.plan_gap_parent_capture = plan
        stack = ExitStack()
        values = dict(ROOT=root, OUTPUT=root/'output', PURE=Path(pure['path']), PURE_SHA=pure['sha256'], CURRENT=current,
                      PARENT_BOUND={k:(str(Path(v['path']).relative_to(root)),v['sha256']) for k,v in entries.items()},
                      DEPENDENCIES={k:(str(Path(v['path']).relative_to(root)),v['sha256']) for k,v in dependencies.items()})
        stack.enter_context(patch.multiple(producer, **values))
        stack.enter_context(patch.object(producer, 'private_core', return_value=core))
        stack.enter_context(patch.object(producer.shutil, 'disk_usage', return_value=SimpleNamespace(free=10**12)))
        return stack, core

    def test_capture_preserves_raw_bytes_and_baseline_roles(self):
        with tempfile.TemporaryDirectory() as folder:
            stack, core = self.fixture(Path(folder))
            with stack:
                result = producer.run(execute=True)
                output = producer.OUTPUT
                self.assertEqual({p.name for p in output.iterdir()},
                                 {'started.json', 'capture.json', 'publication.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif'})
                capture = producer.decode(Path(result['capture_reference']['path']).read_bytes())
                for ticker in ('QQQ', 'SPY'):
                    self.assertEqual((output/(ticker+'.csv')).read_bytes(), b'current-'+ticker.encode())
                    self.assertEqual(core.arguments['accounted_baseline_bytes'][ticker], b'accounted\n')
                    self.assertEqual(core.arguments['actual_baseline_bytes'][ticker], b'actual\n')
                    self.assertNotIn(str(producer.CURRENT[ticker]), capture['source_hashes'])
                self.assertFalse(capture['observation_created'])
                self.assertFalse(capture['future_independent_oos'])
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    producer.run(execute=True)

    def test_failed_plan_preserved_and_never_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            stack, core = self.fixture(Path(folder))
            with stack:
                core.plan_gap_parent_capture = lambda **arguments: (_ for _ in ()).throw(ValueError('semantic reject'))
                with self.assertRaisesRegex(ValueError, 'semantic reject'):
                    producer.run(execute=True)
                self.assertTrue((producer.OUTPUT/'started.json').is_file())
                self.assertTrue((producer.OUTPUT/'QQQ.csv').is_file())
                self.assertFalse((producer.OUTPUT/'publication.json').exists())
                failure = producer.decode((producer.OUTPUT/'failure.json').read_bytes())
                self.assertEqual(failure['status'], 'FAILED_DO_NOT_CONSUME')
                self.assertIs(failure['retry_allowed'], False)
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    producer.run(execute=True)

    def test_resource_stop_does_not_create_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            stack, core = self.fixture(Path(folder))
            with stack, patch.object(producer.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError, 'RESOURCE_STOP'):
                    producer.run(execute=True)
                self.assertFalse(producer.OUTPUT.exists())

    def test_save_is_durable_and_createonly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'saved.json'
            with (patch.object(producer, 'OUTPUT', Path(folder)),
                  patch.object(producer.shutil, 'disk_usage', return_value=SimpleNamespace(free=10**12))):
                item = producer.save(path, {'strict': False})
                self.assertEqual(producer.digest(path.read_bytes()), item['sha256'])
                with self.assertRaises(FileExistsError):
                    producer.save(path, {'strict': True})


if __name__ == '__main__':
    unittest.main()
