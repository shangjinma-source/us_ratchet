from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from data.strategy_account_action_capture_v3 import (
    FramedActionJournalV3, StrategyAccountActionCaptureV3)


class JournalTests(unittest.TestCase):
    def test_durable_disk_replay_duplicate_budget_and_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = FramedActionJournalV3(folder, maximum_bytes=4)
            with ThreadPoolExecutor(max_workers=4) as pool:
                paths = list(pool.map(lambda _: journal.put(b'\x00a\nb', '.raw'), range(8)))
            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(journal.files, {})
            with self.assertRaisesRegex(ValueError, 'TOO_LARGE'):
                journal.put(b'x', '.raw')
            receipt = journal.finish()
            self.assertEqual(receipt['unique_entries'], 1)
            self.assertFalse(receipt['projections_individually_fsynced'])
            self.assertEqual(journal.files[paths[0]], b'\x00a\nb')
            self.assertEqual((Path(folder)/Path(paths[0]).name).read_bytes(), b'\x00a\nb')
            with self.assertRaisesRegex(ValueError, 'CLOSED'):
                journal.put(b'new', '.raw')

    def test_truncated_tampered_or_extra_frames_rejected(self):
        for mode in ('truncate', 'tamper', 'append'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                journal = FramedActionJournalV3(folder)
                journal.put(b'original', '.raw')
                journal.finish()
                path = Path(folder)/'capture.journal'
                raw = path.read_bytes()
                path.write_bytes(raw[:-1] if mode == 'truncate' else
                                 raw[:-1]+b'!' if mode == 'tamper' else raw+raw)
                with self.assertRaises(ValueError):
                    FramedActionJournalV3.replay(path, journal.entries)

    def test_fsync_failure_does_not_return_memory_success(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = FramedActionJournalV3(folder)
            journal.put(b'original', '.raw')
            with patch('data.strategy_account_action_capture_v3.os.fsync',
                       side_effect=OSError(5, 'secret')):
                with self.assertRaises(OSError):
                    journal.finish()
            journal.close()
            self.assertEqual(journal.files, {})
            self.assertFalse((Path(folder)/'capture.index.json').exists())
            self.assertTrue((Path(folder)/'capture.journal').exists())

    def capture_fixture(self, folder, *, fetch=None, rss=None):
        point = [datetime(2026, 10, 20, 14, tzinfo=timezone.utc)]
        capture = StrategyAccountActionCaptureV3(
            fetch=fetch or (lambda ticker, *args: {'status': 200, 'body': b'{"chart":{}}'}),
            rss_fetch=rss or (lambda: {'status': 200, 'body': b'<rss/>'}),
            clock=lambda: point[0])
        request = dict(account_id='fixture', state_revision='revision',
                       window_start=(point[0]-timedelta(days=1)).isoformat(),
                       observed_floor=point[0].isoformat(),
                       securities={str(i): {'ticker': 'A'+str(i)} for i in range(8)},
                       current_target_quantities={})
        return capture, request, Path(folder)/'capture', point

    def test_full_capture_original_bytes_and_consumer_compatible_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            capture, request, path, _ = self.capture_fixture(folder)
            result = capture.capture(request, path)
            self.assertEqual(len(result['documents']['action_receipts']), 8)
            for logical, raw in result['files'].items():
                self.assertEqual((path/Path(logical).name).read_bytes(), raw)
                self.assertEqual(result['source_hashes'][logical], sha256(raw).hexdigest())
            complete = json.loads((path/'complete.json').read_bytes())
            self.assertEqual(complete['storage']['protocol'], 'FSYNCED_FRAMED_JOURNAL_V3')
            self.assertEqual(complete['source_hashes'], result['source_hashes'])
            self.assertFalse((path/'failed.json').exists())
            with self.assertRaises(FileExistsError):
                capture.capture(request, path)

    def test_fetch_error_diagnostics_redacted_and_no_complete(self):
        def fetch(*args):
            raise TimeoutError(110, 'SECRET_TOKEN_DO_NOT_SAVE')
        with tempfile.TemporaryDirectory() as folder:
            capture, request, path, _ = self.capture_fixture(folder, fetch=fetch)
            with self.assertRaisesRegex(ValueError, 'INCOMPLETE_ACTION_DOMAIN'):
                capture.capture(request, path)
            raw = (path/'diagnostics.json').read_bytes()
            self.assertNotIn(b'SECRET_TOKEN', raw)
            error = json.loads(raw)['0']
            self.assertEqual(error['stage'], 'fetch')
            self.assertEqual(error['exception_category'], 'TimeoutError')
            self.assertEqual(error['errno'], 110)
            self.assertFalse((path/'complete.json').exists())

    def test_slow_journal_or_marker_fsync_crosses_window(self):
        import os
        original = os.fsync
        for barrier in (2, 4):
            with self.subTest(barrier=barrier), tempfile.TemporaryDirectory() as folder:
                capture, request, path, point = self.capture_fixture(folder)
                calls = [0]
                def fsync(descriptor):
                    calls[0] += 1
                    original(descriptor)
                    if calls[0] == barrier:
                        point[0] += timedelta(seconds=120)
                with patch('data.strategy_account_action_capture_v3.os.fsync', side_effect=fsync):
                    with self.assertRaisesRegex(ValueError, 'WINDOW_EXPIRED'):
                        capture.capture(request, path)
                self.assertFalse((path/'complete.json').exists())
                self.assertTrue((path/'failed.json').exists())

    def test_projection_write_failure_and_rss_bound_fail_closed(self):
        original = Path.open
        with tempfile.TemporaryDirectory() as folder:
            capture, request, path, _ = self.capture_fixture(folder)
            def broken(target, *args, **kwargs):
                if target.suffix == '.raw' and args and args[0] == 'xb':
                    raise OSError(28, 'disk full')
                return original(target, *args, **kwargs)
            with patch.object(Path, 'open', broken):
                with self.assertRaises(OSError):
                    capture.capture(request, path)
            self.assertFalse((path/'complete.json').exists())
            self.assertTrue((path/'capture.index.json').exists())
            error = json.loads((path/'diagnostics.json').read_bytes())['_capture']
            self.assertEqual(error['stage'], 'journal_fsync_replay_projection')
            self.assertEqual(error['errno'], 28)
        with tempfile.TemporaryDirectory() as folder:
            capture, request, path, _ = self.capture_fixture(
                folder, rss=lambda: {'status': 200, 'body': b'x'*(2*1024*1024+1)})
            with self.assertRaisesRegex(ValueError, 'RSS_RAW_BYTES_INVALID'):
                capture.capture(request, path)
            self.assertFalse((path/'complete.json').exists())

    def test_metadata_barrier_clock_rollback_is_rejected(self):
        import os
        original = os.fsync
        with tempfile.TemporaryDirectory() as folder:
            capture, request, path, point = self.capture_fixture(folder)
            calls = [0]
            def fsync(descriptor):
                calls[0] += 1
                original(descriptor)
                if calls[0] == 2:
                    point[0] += timedelta(seconds=10)
                if calls[0] == 4:
                    point[0] -= timedelta(seconds=1)
            with patch('data.strategy_account_action_capture_v3.os.fsync', side_effect=fsync):
                with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK'):
                    capture.capture(request, path)
            self.assertTrue((path/'failed.json').exists())
            self.assertFalse((path/'complete.json').exists())

    def test_actual_provider_original_review_accepts_disk_replayed_package(self):
        from test_strategy_account_evidence_provider import ProviderTests
        from data.strategy_account_target_inputs import build_target_inputs
        with tempfile.TemporaryDirectory() as folder:
            provider, state, now, _ = ProviderTests().fixture(folder)
            old = provider.actions
            provider.actions = StrategyAccountActionCaptureV3(
                fetch=old.fetch, rss_fetch=old.rss_fetch, clock=old.clock)
            result = provider(state)
            inputs = build_target_inputs(
                state=state, now=now[0].isoformat(), maximum_mark_age_seconds=120,
                **{key: value for key, value in result.items() if key != 'limits'})
            self.assertEqual(inputs['status'], 'INPUTS_READY_NOT_EXECUTED')
            self.assertEqual(set(inputs['binding']['marks']), {'A', 'B'})
            complete_paths = list((Path(folder)/'capture').glob('*/actions/complete.json'))
            self.assertEqual(len(complete_paths), 1)
            complete = json.loads(complete_paths[0].read_bytes())
            self.assertEqual(complete['storage']['protocol'], 'FSYNCED_FRAMED_JOURNAL_V3')


if __name__ == '__main__':
    unittest.main()
