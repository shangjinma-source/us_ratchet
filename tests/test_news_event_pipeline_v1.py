from contextlib import closing
import importlib.util
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data.news_event_pipeline_v1 import EventNewsPipeline
from data.news_model_coordinator_v1 import ModelCoordinator
from data.news_event_model_v1 import analyze_event, project_event


class EventPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.now = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
        self.binding = dict(expected_revision='a', target_id='b', expected_proposal_id='c')
        self.model_calls = self.finalize_calls = 0
        self.fail_list = False
        self.old = False
        self.body = 'body-hash'
        def context():
            return dict(revision=self.binding['expected_revision'], shares={'sid': 2}), dict(
                target_id='b', proposal_id='c', payload=dict(target_quantities={'sid': 3})), {'sid': 'MRNA'}
        def bound(binding):
            if binding != self.binding:
                raise ValueError('STALE_ACCOUNT_OR_TARGET')
            return context()
        def finalize(binding, pending):
            bound(binding)
            self.finalize_calls += 1
            return 202, dict(job_id='j')
        self.service = SimpleNamespace(cache=self.cache, validate=lambda: None, context=context,
                                       bound_context=bound, start_event=finalize,
                                       status=lambda identifier: dict(status='COMPLETE'))
        owner = self
        class Sources:
            supported = {'MRNA', 'SNDK'}
            def __init__(self, *args, **kwargs):
                self.receipts = []
                self.request_count = 0
            def discover(self, ticker):
                self.request_count += 1
                if owner.fail_list:
                    raise ValueError('FAILED')
                return [dict(ticker=ticker, url='https://issuer/story', title='Title',
                             published_at=(datetime(2026, 10, 28, 10, 59, tzinfo=timezone.utc)-timedelta(days=int(owner.old))).isoformat(),
                             discovered_at=owner.now.isoformat(), original={})]
            def hydrate(self, row):
                self.request_count += 1
                return dict(id='e', title=row['title'], url=row['url'], tickers=['MRNA'],
                            published_at=row['published_at'], collected_at=owner.now.isoformat(),
                            discovered_at=row['discovered_at'], content_sha256=owner.body)
        self.factory = Sources
        def build(snapshot, cache, positions, **kwargs):
            return dict(sources={'e': dict(id='e')}, fingerprint='f')
        def analyze(*args, **kwargs):
            self.model_calls += 1
            return dict(schema='SOURCE_ONLY_EVENT_OPINION_V1', status='SUCCEEDED', rows=[],
                        receipt=dict(finished_at=self.now.isoformat()))
        self.analyzer = analyze
        self.pipeline = EventNewsPipeline(self.service, sources_factory=Sources, analyzer=analyze,
                                         source_builder=build, clock=lambda: self.now,
                                         calendar_window=lambda stamp: dict(not_before='2026-10-28T13:30:00+00:00',
                                                                            valid_until='2026-10-28T13:40:00+00:00'))

    def test_disabled_has_no_collection_or_inference(self):
        self.assertEqual(self.pipeline.tick()['status'], 'DISABLED')
        self.assertEqual(self.model_calls, 0)

    def test_fresh_first_start_preopen_then_open_no_second_inference(self):
        self.pipeline.set_enabled(True)
        self.assertEqual(self.pipeline.tick()['status'], 'SOURCE_OPINION_READY')
        self.assertEqual(self.model_calls, 1)
        self.assertEqual(self.finalize_calls, 0)
        self.now += timedelta(hours=2, minutes=30)
        self.pipeline.tick()
        self.assertEqual((self.model_calls, self.finalize_calls), (1, 1))
        self.assertFalse(self.pipeline.status()['orders_created'])

    def test_first_start_old_article_is_baseline_only(self):
        self.old = True
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 0)

    def test_failed_list_does_not_advance_seen_or_finalize(self):
        self.pipeline.set_enabled(True)
        self.fail_list = True
        self.pipeline.tick()
        self.assertEqual(self.pipeline.load()['seen'], {})
        self.assertEqual(self.model_calls, 0)
        self.fail_list = False
        self.now += timedelta(minutes=1)
        self.pipeline.tick()
        self.fail_list = True
        self.now += timedelta(hours=2, minutes=29)
        self.pipeline.tick()
        self.assertEqual(self.finalize_calls, 0)

    def test_account_revision_change_discards_pending_without_repeating_body(self):
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        self.binding['expected_revision'] = 'new'
        self.now += timedelta(hours=2, minutes=30)
        self.pipeline.tick()
        self.assertEqual((self.model_calls, self.finalize_calls), (1, 0))

    def test_open_window_expiry_and_disable(self):
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        self.now += timedelta(hours=3)
        self.pipeline.tick()
        self.assertEqual(self.finalize_calls, 0)
        self.pipeline.set_enabled(False)
        self.assertEqual(self.pipeline.status()['status'], 'DISABLED')

    def test_deferred_model_is_retryable_not_false_attempt(self):
        self.pipeline.analyzer = lambda *args, **kwargs: dict(status='DEFERRED', attempts=0)
        self.pipeline.set_enabled(True)
        self.assertEqual(self.pipeline.tick()['status'], 'WAIT_SHARED_MODEL_BUDGET')
        self.assertEqual(self.pipeline.load()['consumed'], [])
        self.pipeline.analyzer = self.analyzer
        self.now += timedelta(minutes=1)
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 1)

    def test_storage_failure_releases_local_and_database_lease(self):
        self.pipeline.set_enabled(True)
        with patch.object(self.pipeline, 'load', side_effect=OSError('storage')):
            with self.assertRaises(OSError):
                self.pipeline.tick()
        self.assertFalse(self.pipeline.lock.locked())
        with patch.object(self.pipeline, 'save', side_effect=OSError('storage')):
            with self.assertRaises(OSError):
                self.pipeline.tick()
        self.assertFalse(self.pipeline.lock.locked())
        with closing(self.pipeline.connection()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM lease').fetchone()[0], 0)

    def test_other_instance_lease_blocks_tick_and_preserves_state(self):
        from data.news_refresh_service import process_identity
        self.pipeline.set_enabled(True)
        with closing(self.pipeline.connection()) as connection, connection:
            connection.execute('INSERT INTO lease VALUES (1,?,?)', process_identity())
        self.assertEqual(self.pipeline.tick()['status'], 'BUSY')
        self.assertEqual(self.model_calls, 0)
        with closing(self.pipeline.connection()) as connection, connection:
            connection.execute('DELETE FROM lease')
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 1)

    def test_source_failure_invalidates_running_finalizer(self):
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        pending = self.pipeline.load()['pending']
        self.assertTrue(self.pipeline.valid_event(pending))
        self.fail_list = True
        self.now += timedelta(minutes=1)
        self.pipeline.tick()
        self.assertFalse(self.pipeline.valid_event(pending))

    def test_disable_reenable_cannot_resurrect_old_pending(self):
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        pending = self.pipeline.load()['pending']
        self.pipeline.set_enabled(False)
        self.pipeline.set_enabled(True)
        self.assertFalse(self.pipeline.valid_event(pending))

    def test_worker_recovers_after_unexpected_tick_failure_without_browser(self):
        waits = iter((False, False, True))
        with patch.object(self.pipeline.stop_event, 'wait', side_effect=lambda timeout: next(waits)), patch.object(
                self.pipeline, 'tick', side_effect=[OSError('fixture'), dict(status='DISABLED')]) as tick:
            self.pipeline.start_worker()
            self.pipeline.worker.join(timeout=2)
        self.assertEqual(tick.call_count, 2)
        result = self.pipeline.status()
        self.assertFalse(result['worker_alive'])
        self.assertFalse(result['continuous_monitoring'])
        self.assertEqual(result['last_worker_error']['code'], 'EVENT_WORKER_TICK_FAILED')
        self.assertEqual(self.model_calls, 0)


class ModelBudgetTests(unittest.TestCase):
    def test_live_owner_is_not_replaced_after_ttl_and_failure_consumes(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime.now(timezone.utc)]
            coordinator = ModelCoordinator(directory, clock=lambda: now[0])
            with coordinator.reserve('event'):
                now[0] += timedelta(hours=2)
                with self.assertRaisesRegex(ValueError, 'ALREADY_RUNNING'):
                    with coordinator.reserve('investment'):
                        self.fail()
            with coordinator.reserve('refresh', units=4):
                pass
            with closing(coordinator.connection()) as connection:
                self.assertEqual(connection.execute('SELECT SUM(units) FROM reservations').fetchone()[0], 5)

    def test_source_projection_never_transmits_quantity(self):
        payload, _ = project_event([], [dict(security_id='s', ticker='T', original_qty=999, target_qty=999)])
        self.assertEqual(payload['positions'], [dict(security_id='s', ticker='T')])

    def test_deferred_no_receipt_then_one_model_and_cached(self):
        from hashlib import sha256
        source = dict(id='x', title='t', url='https://issuer', published_at='2026-10-28T10:00:00+00:00',
                      observed_at='2026-10-28T10:01:00+00:00', security_ids=['s'], tickers=['T'],
                      content_kind='FULL_TEXT', text='Evidence.', text_sha256=sha256(b'Evidence.').hexdigest())
        positions = [dict(security_id='s', ticker='T')]
        answer = dict(rows=[dict(security_id='s', ticker='T', action='ABSTAIN', reason='不足',
                                buy_fraction='1/1', holding_fraction='1/1', counterevidence=[], uncertainty=[], evidence=[])])
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)/'event_analysis'
            with ModelCoordinator(directory).reserve('investment'):
                result = analyze_event([source], positions, cache)
                self.assertEqual((result['status'], result['attempts']), ('DEFERRED', 0))
                self.assertFalse(list(cache.glob('*/receipt.json')))
            # Isolated fixture advances reservation timestamps; no production state.
            with closing(ModelCoordinator(directory).connection()) as connection:
                connection.execute('UPDATE reservations SET started=started-61')
                connection.commit()
            with patch('data.news_event_model_v1._invoke', return_value=(answer, {})) as invoke:
                first = analyze_event([source], positions, cache)
                second = analyze_event([source], positions, cache)
                self.assertEqual((first['status'], second['status']), ('SUCCEEDED', 'CACHED'))
                self.assertEqual(invoke.call_count, 1)
                self.assertEqual(first['schema'], 'SOURCE_ONLY_EVENT_OPINION_V1')


if __name__ == '__main__':
    unittest.main()
