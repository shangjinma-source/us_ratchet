from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from data.news_event_calendar_v1 import window
from api.news_event_pipeline_v1 import create_event_router


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Thanksgiving deliberately absent: no weekday or next-calendar-day inference.
        self.document = dict(schema='FIXED_EXCHANGE_SESSIONS_V1', exchange='NASDAQ', sessions=[
            dict(date='2023-11-22', open='2023-11-22T14:30:00Z', close='2023-11-22T21:00:00Z'),
            dict(date='2023-11-24', open='2023-11-24T14:30:00Z', close='2023-11-24T18:00:00Z'),
            dict(date='2023-11-27', open='2023-11-27T14:30:00Z', close='2023-11-27T21:00:00Z')])
        self.path = self.root/'calendar.json'
        self.path.write_text(json.dumps(self.document), encoding='utf-8')
        self.reader = SimpleNamespace(validate=lambda: None, root=self.root,
                                      source=dict(calendar=dict(path='calendar.json', sha256=sha256(self.path.read_bytes()).hexdigest())))

    def test_overnight_uses_next_real_session(self):
        result = window(reader=self.reader, discovered_at='2023-11-22T22:00:00Z')
        self.assertEqual(result['not_before'], '2023-11-24T14:30:00+00:00')
        self.assertEqual(result['valid_until'], '2023-11-24T14:40:00+00:00')

    def test_intraday_and_early_close_bound(self):
        result = window(reader=self.reader, discovered_at='2023-11-24T17:58:00Z')
        self.assertEqual(result['valid_until'], '2023-11-24T18:00:00+00:00')

    def test_calendar_tamper_or_missing_coverage_rejects(self):
        with self.assertRaises(ValueError):
            window(reader=self.reader, discovered_at='2023-11-28T12:00:00Z')
        self.path.write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            window(reader=self.reader, discovered_at='2023-11-24T12:00:00Z')


class RouterTests(unittest.TestCase):
    def test_read_status_never_ticks_and_control_requires_exact_boolean(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        pipeline = SimpleNamespace(status=Mock(return_value=dict(status='DISABLED')),
                                   set_enabled=Mock(return_value=dict(status='WAITING')),
                                   tick=Mock(return_value=dict(status='NO_NEW_TIMELY_BODY')))
        app = FastAPI()
        app.include_router(create_event_router(pipeline=pipeline))
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/news/events/status').status_code, 200)
            pipeline.tick.assert_not_called()
            for payload in ('{"enabled":1}', '{"enabled":true,"enabled":false}', '{"enabled":true,"source":"untrusted"}'):
                self.assertEqual(client.post('/api/news/events/control', content=payload,
                                            headers={'Content-Type': 'application/json'}).status_code, 409)
            self.assertEqual(client.post('/api/news/events/control', json={'enabled': True}).status_code, 200)
            self.assertEqual(client.post('/api/news/events/tick', json={'source': 'x'}).status_code, 409)
            self.assertEqual(client.post('/api/news/events/tick', json={}).status_code, 200)
        pipeline.set_enabled.assert_called_once_with(True)
        pipeline.tick.assert_called_once()


if __name__ == '__main__':
    unittest.main()
