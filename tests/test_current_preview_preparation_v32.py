from contextlib import asynccontextmanager
import unittest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from api.strategy_frontier_daily_preview_v1 import create_router
from data.strategy_unified_server_preparation_v32 import attach_current_preview
import test_bound_preview_snapshot_v1 as fixtures


class CompositionTests(unittest.TestCase):
    def test_preserves_existing_preview_and_lifecycle_and_binds_new_gate(self):
        fixture = fixtures.BoundSnapshotTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        lifecycle = []
        @asynccontextmanager
        async def lifespan(app):
            lifecycle.append('start')
            yield
            lifecycle.append('stop')
        router = APIRouter(lifespan=lifespan)
        router.include_router(create_router(service=fixture.service))
        previous_gate = fixture.service.validate_sources
        state = {'fail': False}
        def gate():
            if state['fail']: raise ValueError('V32_SOURCE_CHANGED')
        prepared = dict(router=router, bound_snapshot_daily=fixture.service,
                        observed_daily=fixture.service.observed)
        result = attach_current_preview(prepared=prepared, validate_sources=gate)
        self.assertIs(result['router'], router)
        self.assertIs(result['bound_snapshot_daily'], fixture.service)
        self.assertIs(fixture.service.validate_sources, previous_gate)
        self.assertIs(result['current_advice'].bound.validate_sources, gate)
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            self.assertEqual(lifecycle, ['start'])
            response = client.get('/api/strategy-daily-v3/current')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['daily']['status'], 'WAIT')
            self.assertEqual(client.post('/api/strategy-daily-v3/preview',json=fixture.binding).status_code, 200)
            fixture.hook = lambda: state.update(fail=True)
            response = client.get('/api/strategy-daily-v3/current')
            self.assertEqual(response.status_code, 409)
            self.assertNotIn('daily', response.json())
        self.assertEqual(lifecycle, ['start', 'stop'])
        with self.assertRaisesRegex(ValueError, 'V32_DUPLICATE_CURRENT_ROUTE'):
            attach_current_preview(prepared=prepared, validate_sources=gate)

    def test_unbound_or_wrong_preview_rejected(self):
        with self.assertRaisesRegex(ValueError, 'V32_BOUND_PREVIEW_REQUIRED'):
            attach_current_preview(prepared={'router': APIRouter()}, validate_sources=lambda: None)


if __name__ == '__main__':
    unittest.main()
