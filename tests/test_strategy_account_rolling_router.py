from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest

from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter, RollingArchivedHoldingCharts
import test_strategy_account_monthly_router as router_fixture
import test_strategy_account_archived_holding_charts as charts_fixture


class RollingRouterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = router_fixture.MonthlyRouterTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        old = self.fixture.router
        self.snapshot = dict(registry_path=old.registry_path, registry_sha256=old.registry_sha256,
            archive_path=old.archive_path, archive_sha256=old.archive_sha256, revision=0)
        self.calls = 0
        def provider():
            self.calls += 1
            return self.snapshot
        self.router = RollingMonthlyRuntimeRouter(root=self.fixture.root,
            initial_snapshot=self.snapshot, snapshot_provider=provider,
            clock=lambda: self.fixture.now, runtime_builder=self.fixture.build)
        self.fixture.router = self.router

    def test_new_snapshot_preserves_saved_target_and_shared_runtime(self):
        target = self.router.generate(**self.fixture.request())
        old_runtime = self.fixture.built[0]
        self.snapshot = dict(self.snapshot, revision=1, archive_path='archive2.json',
            archive_sha256=self.fixture.fixture.put('archive2.json', self.fixture.archive),
            registry_path='unavailable.json', registry_sha256='0'*64)
        self.assertEqual(self.router.preview()['target_id'], target['target_id'])
        self.assertIs(self.fixture.built[0], old_runtime)
        self.assertIs(old_runtime.lock, self.router.lock)
        self.assertIs(old_runtime.accounts, self.router.accounts)
        self.assertEqual(self.fixture.executed_configurations[-1], self.fixture.configuration)

    def test_reentrant_generation_reads_once_and_does_not_mix_archive(self):
        original = self.router._builder
        def builder(**kwargs):
            # Simulate activation during an operation; nested methods must stay
            # on the already acquired release even when provider state changes.
            self.snapshot = dict(self.snapshot, revision=2, archive_sha256='0'*64)
            self.assertIsNone(self.router.current())
            return original(**kwargs)
        self.router._builder = builder
        request = self.fixture.request()
        before = self.calls
        target = self.router.generate(**request)
        self.assertEqual(self.calls, before + 1)
        self.assertIsNotNone(target)
        with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
            self.router.preview()
        self.assertIsNone(self.router._active_snapshot)

    def test_provider_failure_never_falls_back_or_writes(self):
        state = self.router.accounts.read()
        self.snapshot = dict(self.snapshot, archive_sha256='invalid')
        with self.assertRaisesRegex(ValueError, 'ROLLING_SNAPSHOT_HASH_INVALID'):
            self.router.generate(event_id='bad', reason='INITIAL',
                expected_revision=state['revision'], previous_target_id=None)
        self.assertEqual(self.router.accounts.read(), state)
        self.assertIsNone(self.router.targets.current())
        self.assertEqual(self.fixture.built, [])
        self.assertIsNone(self.router._active_snapshot)
        self.snapshot['archive_sha256'] = self.router.archive_sha256
        self.assertIsNone(self.router.current())

    def test_invalid_path_and_revision_rejected_even_for_current(self):
        good = deepcopy(self.snapshot)
        for field, value in [('registry_path', '../escape.json'),
                             ('archive_path', 'C:/absolute.json'),
                             ('revision', True), ('revision', -1), ('revision', '1')]:
            with self.subTest(field=field, value=value):
                self.snapshot = dict(good, **{field: value})
                with self.assertRaises(ValueError):
                    self.router.current()
                self.assertIsNone(self.router._active_snapshot)
        self.snapshot = good
        self.assertIsNone(self.router.current())

    def test_explicit_compound_scope_is_immutable_and_detached(self):
        before = self.calls
        with self.router.snapshot_operation() as snapshot:
            self.snapshot['revision'] = 3
            self.assertEqual(snapshot['revision'], 0)
            with self.assertRaises(TypeError):
                snapshot['revision'] = 5
            self.router.current()
            with self.router.snapshot_operation() as nested:
                self.assertIs(nested, snapshot)
        self.assertEqual(self.calls, before + 1)
        with self.router.snapshot_operation() as snapshot:
            self.assertEqual(snapshot['revision'], 3)

    def test_other_thread_cannot_replace_inflight_snapshot(self):
        started, acquired = Event(), Event()
        def concurrent():
            started.set()
            with self.router.snapshot_operation() as snapshot:
                acquired.set()
                return snapshot['revision']
        with ThreadPoolExecutor(max_workers=1) as executor:
            with self.router.snapshot_operation() as snapshot:
                future = executor.submit(concurrent)
                self.assertTrue(started.wait(2))
                self.snapshot['revision'] = 4
                self.assertFalse(acquired.is_set())
                self.assertEqual(snapshot['revision'], 0)
                self.assertEqual(self.calls, 1)
            self.assertEqual(future.result(timeout=2), 4)
        self.assertEqual(self.calls, 2)

    def test_provider_exception_and_reentry_leave_scope_reusable(self):
        original = self.router._snapshot_provider
        def broken():
            raise OSError('snapshot storage unavailable')
        self.router._snapshot_provider = broken
        with self.assertRaisesRegex(OSError, 'snapshot storage unavailable'):
            self.router.current()
        self.router._snapshot_provider = lambda: self.router.current()
        with self.assertRaisesRegex(ValueError, 'ROLLING_PROVIDER_REENTRY'):
            self.router.current()
        self.router._snapshot_provider = original
        self.assertIsNone(self.router.current())

    def test_charts_follow_same_snapshot_and_failed_read_recovers(self):
        fixture = charts_fixture.ArchivedHoldingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        snapshot = dict(registry_path='unused.json', registry_sha256='0'*64,
            archive_path='first.json', archive_sha256=fixture.put('first.json', fixture.archive),
            revision=0)
        calls = []
        service = RollingMonthlyRuntimeRouter(root=fixture.root, initial_snapshot=snapshot,
            snapshot_provider=lambda: calls.append(1) or snapshot)
        # Use the genuine chart fixture's SQLite journals and real chart reader.
        service.accounts, service.targets = fixture.accounts, fixture.targets
        charts = RollingArchivedHoldingCharts(service=service, account_id='real',
            bootstrap_configuration=fixture.configuration)
        self.assertIs(charts.lock, service.lock)
        self.assertEqual(fixture.bars(charts)['source_kind'], 'BOOTSTRAP')
        old = fixture.target(fixture.configuration, 'old')
        empty = dict(decision_date='2026-11-02', candidates=[], source_hashes={})
        newer = dict(fixture.configuration, target_month='2026-11',
            training_manifest='empty.json', training_sha256=fixture.put('empty.json', empty))
        fixture.add('new.json', newer)
        fixture.target(newer, 'new')
        snapshot = dict(snapshot, revision=1, archive_path='second.json',
            archive_sha256=fixture.put('second.json', fixture.archive))
        before = len(calls)
        with service.snapshot_operation():
            result = fixture.bars(charts)
            service.current()
        self.assertEqual(len(calls), before + 1)
        self.assertEqual(result['source_target_id'], old['target_id'])
        self.assertTrue(result['historical_target_fallback'])
        good = deepcopy(snapshot)
        snapshot['archive_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
            fixture.bars(charts)
        self.assertIsNone(service._active_snapshot)
        snapshot = good
        self.assertEqual(fixture.bars(charts)['source_target_id'], old['target_id'])


if __name__ == '__main__':
    unittest.main()
