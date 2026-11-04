import os
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from data.strategy_release_replay_cache_v1 import VerifiedReplayCache


class ReplayCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.file = self.root / 'source.json'
        self.file.write_bytes(b'{"value":1}')
        self.digest = sha256(self.file.read_bytes()).hexdigest()
        self.cache = VerifiedReplayCache()
        self.calls = 0

    def compute(self, dependencies):
        self.calls += 1
        dependencies.read(self.root, 'source.json', self.digest)
        return {'rows': [1]}

    def test_hit_reuses_calculation_and_detaches_result(self):
        result = self.cache.resolve('a', self.compute)
        result['rows'].append(9)
        self.assertEqual(self.cache.resolve('a', self.compute), {'rows': [1]})
        self.assertEqual(self.calls, 1)

    def test_same_size_same_mtime_mutation_is_rejected_and_evicted(self):
        self.cache.resolve('a', self.compute)
        stamp = self.file.stat()
        self.file.write_bytes(b'{"value":2}')
        os.utime(self.file, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
            self.cache.resolve('a', self.compute)
        self.assertNotIn('a', self.cache.entries)

    def test_missing_dependency_cannot_reuse_result(self):
        self.cache.resolve('a', self.compute)
        self.file.unlink()
        with self.assertRaises(ValueError):
            self.cache.resolve('a', self.compute)

    def test_change_during_computation_cannot_publish_cache(self):
        def racing(dependencies):
            result = self.compute(dependencies)
            self.file.write_bytes(b'{"value":2}')
            return result
        with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
            self.cache.resolve('a', racing)
        self.assertFalse(self.cache.entries)

    def test_changed_input_recomputes_and_capacity_is_bounded(self):
        for key in ('account1-time1', 'account2-time1', 'account2-time2'):
            self.cache.resolve(key, self.compute)
        self.assertEqual(self.calls, 3)
        self.assertEqual(len(self.cache.entries), 2)

    def test_symlink_replacement_rejected_even_with_same_bytes(self):
        self.cache.resolve('a', self.compute)
        other = self.root / 'other.json'
        other.write_bytes(self.file.read_bytes())
        self.file.unlink()
        try:
            self.file.symlink_to(other)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, 'REPLAY_DEPENDENCY_LINK_REFUSED'):
            self.cache.resolve('a', self.compute)

    def test_resolver_binds_full_account_and_exact_time(self):
        from data import strategy_account_monthly_release_replayed_v1 as module
        now = datetime(2026, 11, 3, tzinfo=timezone.utc)
        def compute(**arguments):
            arguments['dependencies'].read(self.root, 'source.json', self.digest)
            return {'state': arguments['account_state']}
        with patch.object(module, '_REPLAY_CACHE', self.cache), patch.object(module, '_resolve', side_effect=compute) as resolve:
            arguments = dict(root=self.root, registry_path='source.json', registry_sha256=self.digest,
                clock=lambda: now, account_state={'revision': 'a', 'cash': '1'})
            module.resolve_monthly_runtime(**arguments)
            module.resolve_monthly_runtime(**arguments)
            self.assertEqual(resolve.call_count, 1)
            arguments['account_state']['cash'] = '2'
            module.resolve_monthly_runtime(**arguments)
            arguments['clock'] = lambda: now + timedelta(seconds=1)
            module.resolve_monthly_runtime(**arguments)
            self.assertEqual(resolve.call_count, 3)

    def test_concurrent_same_key_computes_once(self):
        entered, release = Event(), Event()
        def slow(dependencies):
            entered.set()
            if not release.wait(5):
                raise AssertionError('test release missing')
            return self.compute(dependencies)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.cache.resolve, 'a', slow)
            self.assertTrue(entered.wait(5))
            second = pool.submit(self.cache.resolve, 'a', slow)
            release.set()
            self.assertEqual(first.result(timeout=5), second.result(timeout=5))
        self.assertEqual(self.calls, 1)


if __name__ == '__main__':
    unittest.main()
