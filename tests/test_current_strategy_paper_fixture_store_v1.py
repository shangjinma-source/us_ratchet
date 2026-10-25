import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from backtest.current_strategy_paper_fixture_store_v1 import PaperFixtureStore
from test_current_strategy_paper_slice_v1 import book, proposal, bar


class PaperFixtureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ratchet-paper-fixture-')
        self.application = book()['application']
        self.store = PaperFixtureStore(directory=self.temp.name, application=self.application)
        self.initial = self.store.initialize()
        p = proposal(self.initial)
        self.request = dict(kind='ACCEPT', operation_id='accept', expected_revision=self.initial['revision'],
                            proposal=p, accepted_at=p['inputs']['now'])

    def tearDown(self):
        self.temp.cleanup()

    def fresh(self, **kwargs):
        return PaperFixtureStore(directory=self.temp.name, application=self.application, **kwargs)

    def test_oversized_request_rejected_before_database_lock(self):
        original = self.store.path.read_bytes()
        request = dict(self.request, oversized='x' * (16 * 1024 * 1024))
        with patch.object(self.store, '_write', side_effect=AssertionError('MUST_NOT_LOCK')):
            with self.assertRaisesRegex(ValueError, 'PAPER_REQUEST_BYTE_BUDGET'):
                self.store.apply(request)
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(self.store.read(), self.initial)

    def test_restart_duplicate_and_settlement_replay(self):
        accepted = self.store.apply(self.request)
        self.assertEqual(self.fresh().read(), accepted)
        self.assertEqual(self.fresh().apply(self.request), accepted)
        oid = next(iter(accepted['orders']))
        request = dict(kind='SETTLE', operation_id='fill', expected_revision=accepted['revision'],
            minutes={oid:[bar()]}, observed_through='2026-02-02T10:02:00-05:00',
            evaluated_at='2026-02-02T10:02:01-05:00')
        filled = self.store.apply(request)
        self.assertEqual(filled['cash'], '19000')
        self.assertEqual(self.fresh().read(), filled)
        self.assertEqual(self.fresh().initialize(), filled)

    def test_failure_before_commit_rolls_back_whole_request(self):
        for target in ('after_begin', 'after_insert', 'before_commit'):
            def fail(phase):
                if phase == target: raise RuntimeError('injected')
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.fresh(fault=fail).apply(self.request)
            self.assertEqual(self.fresh().read(), self.initial)

    def test_process_death_before_and_after_commit(self):
        # Kill the actual child interpreter: no Python finally/rollback runs.
        # SQLite recovery and committed-request idempotence are tested on reopen.
        payload = Path(self.temp.name)/'request.json'
        payload.write_text(json.dumps(dict(application=self.application, request=self.request)))
        source = (
            'import json,os,sys; from pathlib import Path; '
            'from backtest.current_strategy_paper_fixture_store_v1 import PaperFixtureStore; '
            'p=json.loads(Path(sys.argv[1]).read_text()); '
            's=PaperFixtureStore(directory=str(Path(sys.argv[1]).parent),application=p["application"],'
            'fault=lambda phase: os._exit(77) if phase==sys.argv[2] else None); '
            's.apply(p["request"])')
        root = Path(__file__).resolve().parents[1]
        for phase in ('after_insert', 'before_commit'):
            result = subprocess.run([sys.executable, '-B', '-c', source, str(payload), phase], cwd=root,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 77, result.stderr)
            self.assertEqual(self.fresh().read(), self.initial)
        result = subprocess.run([sys.executable, '-B', '-c', source, str(payload), 'after_commit'],
                                cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 77, result.stderr)
        committed = self.fresh().read()
        self.assertEqual(len(committed['operations']), 1)
        self.assertEqual(self.fresh().apply(self.request), committed)

    def test_two_concurrent_identical_requests_commit_once(self):
        barrier = threading.Barrier(2)
        def run():
            barrier.wait(timeout=3)
            return self.fresh().apply(self.request)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            results = [f.result(timeout=5) for f in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.read()['operations']), 1)

    def test_competing_revisions_and_read_lock_timeout(self):
        barrier = threading.Barrier(2)
        def run(oid):
            request = dict(self.request, operation_id=oid)
            barrier.wait(timeout=3)
            try: return ('ok', self.fresh().apply(request))
            except ValueError as error: return ('error', str(error))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, oid) for oid in ['first','second']]
            results = [f.result(timeout=5) for f in futures]
        self.assertEqual(sorted(x[0] for x in results), ['error','ok'])
        self.assertEqual([x[1] for x in results if x[0]=='error'], ['PAPER_STALE_REVISION'])
        current = self.store.read()
        with sqlite3.connect(self.store.path) as blocker:
            blocker.execute('BEGIN')
            blocker.execute('SELECT * FROM paper_fixture_header').fetchall()
            with self.assertRaises(sqlite3.OperationalError):
                self.fresh(timeout_seconds=0.05).apply(current['operations'][0]['request'])
            blocker.rollback()
        blocker.close()
        self.assertEqual(self.store.read(), current)

    def test_corrupt_event_or_missing_row_never_reinitialized(self):
        self.store.apply(self.request)
        with sqlite3.connect(self.store.path) as connection:
            connection.execute("UPDATE paper_fixture_events SET request='{}'")
        connection.close()
        with self.assertRaises((ValueError, KeyError)):
            self.store.read()
        with self.assertRaises((ValueError, KeyError)):
            self.store.initialize()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute('DELETE FROM paper_fixture_events')
        connection.close()
        with self.assertRaisesRegex(ValueError, 'RECORD_COUNT_MISMATCH'):
            self.store.read()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute('DELETE FROM paper_fixture_header')
        connection.close()
        with self.assertRaisesRegex(ValueError, 'EXISTING_HEADER_MISSING'):
            self.store.initialize()

    def test_mismatched_application_and_non_temp_path_rejected(self):
        different = dict(self.application, account_id='paper-fixture:another')
        with self.assertRaisesRegex(ValueError, 'APPLICATION_CHANGED'):
            PaperFixtureStore(directory=self.temp.name, application=different).read()
        with self.assertRaisesRegex(ValueError, 'TEMP_DIRECTORY_REQUIRED'):
            PaperFixtureStore(directory=Path(__file__).resolve().parents[1], application=self.application)

    def test_real_database_hardlink_rejected_on_both_paths(self):
        with tempfile.TemporaryDirectory(prefix='ratchet-paper-fixture-linked-') as other:
            linked = PaperFixtureStore(directory=other,application=self.application)
            os.link(self.store.path,linked.path)
            self.assertEqual(self.store.path.stat().st_nlink,2)
            for candidate in (self.store,linked):
                with self.assertRaisesRegex(ValueError,'PAPER_HARDLINK_REJECTED'): candidate.read()
                with self.assertRaisesRegex(ValueError,'PAPER_HARDLINK_REJECTED'): candidate.apply(self.request)
            linked.path.unlink()
        self.assertEqual(self.store.read(),self.initial)

    def test_hardlinked_sidecars_rejected_before_sqlite_access(self):
        original = Path(self.temp.name)/'sidecar-original'
        original.write_bytes(b'fixture-only')
        for suffix in ('-journal','-wal','-shm'):
            with self.subTest(suffix=suffix):
                alias=Path(str(self.store.path)+suffix)
                os.link(original,alias)
                try:
                    with self.assertRaisesRegex(ValueError,'PAPER_HARDLINK_REJECTED'): self.store.read()
                    with self.assertRaisesRegex(ValueError,'PAPER_HARDLINK_REJECTED'): self.store.apply(self.request)
                    self.assertEqual(original.read_bytes(),b'fixture-only')
                finally: alias.unlink()

    def test_hardlink_added_during_transaction_rolls_back(self):
        alias=Path(self.temp.name)/'late-hardlink'
        def fault(phase):
            if phase=='before_commit':os.link(self.store.path,alias)
        try:
            with self.assertRaisesRegex(ValueError,'PAPER_HARDLINK_REJECTED'):
                self.fresh(fault=fault).apply(self.request)
        finally:
            if alias.exists():alias.unlink()
        self.assertEqual(self.store.read(),self.initial)

    def test_rehashed_false_outcome_still_fails_semantic_replay(self):
        from backtest.current_strategy_paper_fixture_store_v1 import canonical
        from backtest.current_strategy_paper_slice_v1 import digest
        self.store.apply(self.request)
        with sqlite3.connect(self.store.path) as connection:
            ordinal, request_raw, revision, previous = connection.execute(
                'SELECT ordinal,request,revision,previous_hash FROM paper_fixture_events').fetchone()
            outcome = {'status': 'FORGED_SUCCESS'}
            forged_hash = digest(dict(ordinal=ordinal, request=json.loads(request_raw),
                                     outcome=outcome, revision=revision, previous_hash=previous))
            connection.execute('UPDATE paper_fixture_events SET outcome=?,record_hash=?',
                               (canonical(outcome), forged_hash))
            connection.execute('UPDATE paper_fixture_header SET head_hash=?', (forged_hash,))
        connection.close()
        with self.assertRaisesRegex(ValueError, 'STORED_REPLAY_MISMATCH'):
            self.fresh().read()


if __name__ == '__main__':
    unittest.main()
