import unittest
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from api.strategy_frontier_latest_display_charts_v1 import create_router
from data.strategy_frontier_latest_display_charts_v1 import FrontierLatestDisplayChartsV1
from data.strategy_unified_server_preparation_v31 import attach_display_batch


class CompositionTests(unittest.TestCase):
    def test_original_service_and_lifecycle_preserved_once(self):
        calls = []
        @asynccontextmanager
        async def lifecycle(app):
            calls.append('start')
            yield
            calls.append('stop')
        router = APIRouter(lifespan=lifecycle)
        existing = FrontierLatestDisplayChartsV1(view=object(), validate_sources=lambda: None,
                                               output_root='unused')
        router.include_router(create_router(service=existing))
        prepared = dict(router=router, observed_daily=object())
        gate = lambda: None
        result = attach_display_batch(prepared=prepared, validate_sources=gate)
        self.assertIs(result['router'], router)
        self.assertIs(result['observed_daily'], prepared['observed_daily'])
        self.assertIs(result['display_batch'].view, existing.view)
        self.assertIs(result['display_batch'].display_options['validate_sources'], gate)
        self.assertEqual(len(router.routes), 3)
        result['display_batch'].bars = lambda **kwargs: {'status': 'DISPLAY_ONLY', 'charts': []}
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            self.assertEqual(calls, ['start'])
            response = client.get('/api/strategy-display/latest-batch?security_id=A&expected_proposal_id=p')
            self.assertEqual(response.status_code, 200)
            asset = client.get('/static/strategy_display_batch_fetch.js')
            self.assertEqual(asset.status_code, 200)
            self.assertEqual(asset.content, (Path(__file__).resolve().parents[1]/'web/strategy_display_batch_fetch.js').read_bytes())
            self.assertEqual(asset.headers['cache-control'], 'no-store')
        self.assertEqual(calls, ['start', 'stop'])
        with self.assertRaisesRegex(ValueError, 'V31_DUPLICATE_BATCH_ROUTE'):
            attach_display_batch(prepared=prepared, validate_sources=gate)

    def test_missing_original_route_rejected(self):
        with self.assertRaisesRegex(ValueError, 'V31_DISPLAY_ROUTE_REQUIRED'):
            attach_display_batch(prepared={'router': APIRouter()}, validate_sources=lambda: None)


if __name__ == '__main__':
    unittest.main()
