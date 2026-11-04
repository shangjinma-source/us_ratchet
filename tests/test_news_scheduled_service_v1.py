from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.news_scheduled_earnings_v1 import create_router
from data.news_scheduled_service_v1 import ScheduledEarningsService
import test_news_scheduled_earnings_v1 as fixtures


class ScheduledServiceTests(unittest.TestCase):
    def setup_service(self, root):
        calls = []
        current = [datetime.fromisoformat('2026-11-04T05:00:00+00:00')]
        def collector(cache, now):
            calls.append(now)
            snapshot = fixtures.ScheduledEarningsTests().fixture(cache)
            return dict(events=snapshot['events'], receipts=snapshot['source_receipts'],
                        errors=[], request_count=3)
        service = ScheduledEarningsService(root, collector=collector, clock=lambda: current[0])
        return service, calls, current

    def test_read_is_offline_and_expiry_is_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); service, calls, current = self.setup_service(root)
            self.assertEqual(service.read()['status'], 'NO_CAPTURE'); self.assertEqual(calls, [])
            self.assertTrue(service._collect()); self.assertEqual(len(calls), 1)
            before = (root/'snapshot.json').read_bytes()
            self.assertEqual(len(service.read()['events']), 1)
            with patch.object(service, 'progress', return_value={'status': 'FAILED'}):
                self.assertEqual(service.read()['status'], 'UNAVAILABLE')
            current[0] += timedelta(hours=25)
            self.assertFalse(service.read()['events'])
            self.assertEqual((root/'snapshot.json').read_bytes(), before)
            self.assertEqual(len(calls), 1)

    def test_source_change_and_partial_capture_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); service, _, _ = self.setup_service(root); service._collect()
            for path in (root/'raw').glob('*.json'): path.write_bytes(b'corrupt')
            self.assertFalse(service.read()['events'])
            snapshot = json.loads((root/'snapshot.json').read_text(encoding='utf-8'))
            snapshot['fetch_errors'] = [{'message': 'unavailable'}]
            (root/'snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
            self.assertEqual(service.read()['status'], 'UNAVAILABLE')

    def test_http_read_refresh_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); service, calls, _ = self.setup_service(root)
            app = FastAPI(); app.include_router(create_router(service=service))
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/news/scheduled-earnings').json()['status'], 'NO_CAPTURE')
                self.assertFalse((root/'refresh_requests_v2.sqlite3').exists())
                endpoint = '/api/news/scheduled-earnings/refresh'
                self.assertEqual(client.post(endpoint, json={}, headers={'Origin': 'https://untrusted.example'}).status_code, 403)
                self.assertEqual(client.post(endpoint, json={'url': 'https://example.com'}).status_code, 400)
                self.assertEqual(client.post(endpoint, json={}).status_code, 202)
                service.refresh.worker.join(timeout=10); self.assertFalse(service.refresh.worker.is_alive())
                result = client.get('/api/news/scheduled-earnings').json()
                self.assertEqual(result['refresh']['status'], 'SUCCEEDED')
                self.assertEqual(len(result['events']), 1)
                self.assertEqual(client.post(endpoint, json={}).status_code, 429)
                self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
