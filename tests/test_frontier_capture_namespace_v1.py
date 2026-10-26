from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from data.saved_frontier_live_reader_v1 import capture_namespace
from test_strategy_monthly_supplement_capture import SupplementTests


class NamespaceTests(unittest.TestCase):
    def setUp(self):
        self.case = SupplementTests()
        self.case.setUp()
        self.session = dict(date='2026-10-23', open='2026-10-23T13:30:00+00:00',
                            close='2026-10-23T20:00:00+00:00')

    def directory(self, root):
        return capture_namespace(root, started=self.case.now, session=self.session)

    def test_slots_reuse_id_preserve_original_and_fetch_new_timestamps(self):
        with TemporaryDirectory() as root:
            original = self.case.run_capture(root)
            before = {p.relative_to(root): p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            first = self.case.run_capture(self.directory(root))
            self.case.now += timedelta(minutes=14, seconds=59)
            again = self.case.run_capture(self.directory(root))
            self.assertTrue(again['reused'])
            self.assertEqual(self.case.calls, 4)
            self.case.now += timedelta(seconds=1)
            next_slot = self.case.run_capture(self.directory(root))
            self.assertFalse(next_slot['reused'])
            self.assertEqual(self.case.calls, 6)
            self.assertEqual({r['capture_id'] for r in (original, first, next_slot)}, {first['capture_id']})
            self.assertNotEqual(first['finished_at'], next_slot['finished_at'])
            for name, raw in before.items():
                self.assertEqual((Path(root)/name).read_bytes(), raw)

    def test_session_bounds_and_finite_slots(self):
        with TemporaryDirectory() as root:
            start = self.case.now.replace(hour=13, minute=30)
            slots = {capture_namespace(root, started=start+timedelta(minutes=i), session=self.session)
                     for i in range(390)}
            self.assertEqual(len(slots), 26)
            for now in (start-timedelta(microseconds=1), start+timedelta(minutes=390)):
                with self.assertRaisesRegex(ValueError, 'SLOT_SESSION'):
                    capture_namespace(root, started=now, session=self.session)

    def test_concurrent_capture_uses_single_owner_and_preserves_failed_slot(self):
        with TemporaryDirectory() as root:
            entered, release = Event(), Event()
            fetch = self.case.fetch
            def delayed(*args):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('TEST_WAIT_EXCEEDED')
                return fetch(*args)
            self.case.fetch = delayed
            directory = self.directory(root)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.case.run_capture, directory)
                try:
                    self.assertTrue(entered.wait(5))
                    second = pool.submit(self.case.run_capture, directory).result(timeout=5)
                    self.assertEqual(second['status'], 'NEEDS_RECOVERY')
                finally:
                    release.set()
                first.result(timeout=5)
            self.assertEqual(self.case.calls, 2)
            self.case.now += timedelta(minutes=15)
            directory = self.directory(root)
            def failed(*args):
                raise OSError('TEST_TRANSPORT_FAILED')
            self.case.fetch = failed
            with self.assertRaises(OSError):
                self.case.run_capture(directory)
            failed_bytes = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}
            self.case.fetch = lambda *args: self.fail('failed slot must not retry')
            self.assertEqual(self.case.run_capture(directory)['status'], 'NEEDS_RECOVERY')
            self.assertEqual(failed_bytes, {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
