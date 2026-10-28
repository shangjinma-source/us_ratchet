"""Publication-anchored admission; mocked discovery/inference, real pinned calendar."""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest

from data.news_event_calendar_v1 import window

candidate = os.environ.get('NEWS_EVENT_PIPELINE_CANDIDATE')
if candidate:
    specification = importlib.util.spec_from_file_location('publication_pipeline_candidate', candidate)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
else:
    from data import news_event_pipeline_v1 as module


@unittest.skipUnless(hasattr(module.EventNewsPipeline, 'publication_window'), 'Publication-window candidate not released')
class PublicationWindowTests(unittest.TestCase):
    def setUp(self):
        fixture = runpy.run_path(str(Path(__file__).with_name('test_news_event_pipeline_v1.py')))['EventPipelineTests']
        fixture.setUp(self)
        self.pipeline.__class__ = module.EventNewsPipeline
        dates = ['2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02']
        sessions = [dict(date=day, open=day+('T14:30:00Z' if day == '2026-11-02' else 'T13:30:00Z'),
                         close=day+('T21:00:00Z' if day == '2026-11-02' else 'T20:00:00Z')) for day in dates]
        path = self.cache/'calendar.json'
        path.write_text(json.dumps(dict(schema='FIXED_EXCHANGE_SESSIONS_V1', exchange='NASDAQ', sessions=sessions)), encoding='utf-8')
        reader = SimpleNamespace(root=self.cache, validate=lambda: None,
                                 source=dict(calendar=dict(path='calendar.json', sha256=sha256(path.read_bytes()).hexdigest())))
        self.pipeline.calendar_window = lambda stamp: window(reader=reader, discovered_at=stamp)
        original = self.factory
        owner = self
        self.publication = '2026-10-28T10:59:00+00:00'
        class Sources(original):
            def discover(self, ticker):
                rows = super().discover(ticker)
                for row in rows:
                    row['published_at'] = owner.publication
                return rows
        self.pipeline.sources_factory = Sources

    def test_preopen_discovered_two_hours_later_keeps_first_open(self):
        self.now = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
        self.assertEqual(self.pipeline.set_enabled(True)['status'], 'WAITING')
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 1)
        pending = self.pipeline.load()['pending']
        self.assertEqual(pending['execution_window']['not_before'], '2026-10-28T13:30:00+00:00')
        self.assertEqual(pending['opinion_valid_until'], '2026-10-28T13:40:00+00:00')
        self.assertEqual(pending['snapshot']['events'][0]['discovery_delay_seconds'], 7260)

    def test_intraday_more_than_ten_minutes_is_not_admitted(self):
        self.publication = '2026-10-28T14:00:00Z'
        self.now = datetime(2026, 10, 28, 14, 11, tzinfo=timezone.utc)
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 0)
        self.assertIsNone(self.pipeline.load()['pending'])

    def test_after_close_waits_next_true_session_including_dst_weekend(self):
        self.publication = '2026-10-30T21:00:00Z'
        self.now = datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc)
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        pending = self.pipeline.load()['pending']
        self.assertEqual(pending['execution_window']['not_before'], '2026-11-02T14:30:00+00:00')
        self.assertEqual(pending['opinion_valid_until'], '2026-11-02T14:40:00+00:00')

    def test_discovery_does_not_extend_intraday_expiry(self):
        self.publication = '2026-10-28T14:00:00Z'
        self.now = datetime(2026, 10, 28, 14, 9, tzinfo=timezone.utc)
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        self.assertEqual(self.pipeline.load()['pending']['opinion_valid_until'], '2026-10-28T14:10:00+00:00')
        self.now = datetime(2026, 10, 28, 14, 10, tzinfo=timezone.utc)
        self.pipeline.tick()
        self.assertEqual(self.finalize_calls, 0)

    def test_multiple_sources_intersect_not_refresh_window(self):
        result = self.pipeline.publication_window([dict(published_at='2026-10-28T14:00:00Z'),
                                                   dict(published_at='2026-10-28T14:02:00Z')])
        self.assertEqual(result['not_before'], '2026-10-28T14:02:00+00:00')
        self.assertEqual(result['valid_until'], '2026-10-28T14:10:00+00:00')

    def test_missing_calendar_rejects_before_model(self):
        self.pipeline.calendar_window = None
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 0)
        self.assertIsNone(self.pipeline.load()['pending'])

    def test_old_pending_job_rejected_before_first_tick_and_generation_revoked(self):
        self.now = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        state = self.pipeline.load()
        pending = state['pending']
        pending['job_id'] = 'already-started-r27-job'
        # R27's discovered-at-derived envelope lacks publication binding.
        pending['execution_window'].pop('window_anchor')
        pending['execution_window'].pop('source_windows')
        previous_generation = state['source_generation']
        self.pipeline.save(state)
        self.now = datetime(2026, 10, 28, 13, 31, tzinfo=timezone.utc)
        self.assertFalse(self.pipeline.valid_event(pending), 'status/finalization guard rejects before a worker tick')
        self.pipeline.tick()
        updated = self.pipeline.load()
        self.assertIsNone(updated['pending'])
        self.assertGreater(updated['source_generation'], previous_generation)

    def test_valid_event_cannot_be_read_after_publication_window(self):
        self.now = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
        self.pipeline.set_enabled(True)
        self.pipeline.tick()
        pending = self.pipeline.load()['pending']
        self.now = datetime(2026, 10, 28, 13, 31, tzinfo=timezone.utc)
        self.assertTrue(self.pipeline.valid_event(pending))
        self.now = datetime(2026, 10, 28, 13, 40, tzinfo=timezone.utc)
        self.assertFalse(self.pipeline.valid_event(pending))

    def seed_old_baseline(self):
        self.pipeline.set_enabled(True)
        row = self.pipeline.sources_factory(self.cache).discover('MRNA')[0]
        key = module.digest({name: row[name] for name in ('ticker', 'url', 'title', 'published_at')})
        state = self.pipeline.load()
        state['seen'][key] = dict(status='BASELINE_NOT_TIMELY', attempts=0)
        self.pipeline.save(state)
        return key

    def test_old_baseline_before_first_open_is_reevaluated_once(self):
        self.now = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
        key = self.seed_old_baseline()
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 1)
        state = self.pipeline.load()
        self.assertEqual(state['seen'][key], dict(status='BODY_READY', attempts=1))
        self.assertEqual(state['pending']['opinion_valid_until'], '2026-10-28T13:40:00+00:00')
        consumed = list(state['consumed'])
        self.now = datetime(2026, 10, 28, 13, 1, tzinfo=timezone.utc)
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 1)
        self.assertEqual(self.pipeline.load()['consumed'], consumed)

    def test_old_baseline_after_first_window_remains_unanalysed(self):
        self.now = datetime(2026, 10, 28, 13, 41, tzinfo=timezone.utc)
        key = self.seed_old_baseline()
        self.pipeline.tick()
        self.assertEqual(self.model_calls, 0)
        self.assertEqual(self.pipeline.load()['seen'][key], dict(status='BASELINE_WINDOW_EXPIRED', attempts=0))


if __name__ == '__main__':
    unittest.main()
