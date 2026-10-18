"""Publisher boundary tests; no production run or successful report publication."""
import hashlib
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import backtest
from scripts import ndx_prospective_gap_history_20261009_v3 as publisher


def fixture_namespaces(root):
    for name, files in publisher.SOURCE_NAMESPACES.items():
        folder = root / 'data/cache/research' / name
        folder.mkdir(parents=True)
        for name in files:
            (folder / name).write_bytes(b'{}')


class PublisherIndependentTests(unittest.TestCase):
    def test_pending_pure_sha_refuses_before_any_source_io_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'not-created'
            with patch.object(publisher, 'PURE_SHA', None), patch.object(publisher, 'OUTPUT', out):
                with patch.object(Path, 'read_bytes', side_effect=AssertionError('Forbidden pending source IO')):
                    with self.assertRaisesRegex(ValueError, 'Pending immutable source SHA'):
                        publisher.run(execute=True)
            self.assertFalse(out.exists())

    def test_existing_output_refuses_before_source_io(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'existing'
            out.mkdir()
            with patch.object(publisher, 'PURE_SHA', 'a' * 64), patch.object(publisher, 'OUTPUT', out):
                with patch.object(Path, 'read_bytes', side_effect=AssertionError('Forbidden existing namespace IO')):
                    with self.assertRaisesRegex(ValueError, 'Create-only namespace'):
                        publisher.run(execute=True)
            self.assertEqual(list(out.iterdir()), [])

    def test_namespace_extra_file_or_directory_and_replaced_directory_rejected(self):
        for attack in ('file', 'directory', 'replaced'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture_namespaces(root)
                folder = root / 'data/cache/research' / next(iter(publisher.SOURCE_NAMESPACES))
                if attack == 'file':
                    (folder / 'extra.json').write_bytes(b'{}')
                elif attack == 'directory':
                    (folder / 'extra').mkdir()
                else:
                    (folder / 'history.json').unlink()
                    (folder / 'history.json').mkdir()
                with patch.object(publisher, 'ROOT', root):
                    with self.assertRaises(ValueError):
                        publisher.guard_namespaces()

    def test_real_symlink_file_is_rejected_even_when_name_matches_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_namespaces(root)
            folder = root / 'data/cache/research' / next(iter(publisher.SOURCE_NAMESPACES))
            target = root / 'outside-source.json'
            target.write_bytes(b'{}')
            link = folder / 'history.json'
            link.unlink()
            link.symlink_to(target)
            with patch.object(publisher, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'No linked source or output'):
                    publisher.guard_namespaces()

    def test_private_dependency_graph_ignores_sys_modules_and_package_attribute_substitutes(self):
        blob = publisher.PURE.read_bytes()
        fake = types.ModuleType('backtest.ndx_variable_prefix_capture_research')
        fake.POLICY = 'FORGED_POLICY'
        fake.plan_history_capture = lambda **kwargs: (_ for _ in ()).throw(AssertionError('Substitute invoked'))
        with patch.dict('sys.modules', {'backtest.ndx_variable_prefix_capture_research': fake}):
            with patch.object(backtest, 'ndx_variable_prefix_capture_research', fake, create=True):
                sources = {}
                private = publisher.private_pure(blob, sources)
        self.assertIsNot(private.capture_core, fake)
        self.assertEqual(private.POLICY, 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH')
        self.assertEqual(private.DEPENDENCY_SHA256, {key: value[1] for key, value in publisher.DEPENDENCIES.items()})
        self.assertEqual(len(sources), 3)
        for path, digest in sources.items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), digest)

    def test_consumed_bytes_and_later_source_drift_are_both_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_namespaces(root)
            source = root / 'input.json'
            source.write_bytes(b'original')
            reference = publisher.reference(source, hashlib.sha256(b'original').hexdigest())
            sources = {}
            self.assertEqual(publisher.consume(reference, sources), b'original')
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Source bytes changed'):
                publisher.consume(reference, {})
            with patch.object(publisher, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Source drift'):
                    publisher.guard(sources)

    def test_persistent_live_cache_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_namespaces(root)
            path = root / 'data/cache/QQQ.csv'
            path.write_bytes(b'x')
            with patch.object(publisher, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'No permanent mutable cache claim'):
                    publisher.guard({str(path): hashlib.sha256(b'x').hexdigest()})


if __name__ == '__main__':
    unittest.main()
