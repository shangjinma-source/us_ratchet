"""HTTP regression for dynamic dispatch; synthetic selection/quotes, real stores."""
from datetime import datetime
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_monthly_target import create_router
import test_strategy_account_monthly_router as router_fixture


class MonthlyDispatchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = router_fixture.MonthlyRouterTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        app = FastAPI()
        app.include_router(create_router(service=self.fixture.router))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.base = '/api/strategy-account/target'

    def test_stale_revision_rejected_without_selection_or_target(self):
        f = self.fixture
        before = f.router.accounts.path.read_bytes()
        request = dict(f.request(), expected_revision='0'*64)
        response = self.client.post(self.base+'/generate', json=request)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['reason'], 'STALE_REVISION')
        self.assertEqual(f.selection_calls, 0)
        self.assertIsNone(f.router.current())
        self.assertEqual(f.router.accounts.path.read_bytes(), before)

    def test_real_http_generation_preview_and_new_month_failure_preserve_target(self):
        f, client, base = self.fixture, self.client, self.base
        before = f.router.accounts.path.read_bytes()
        self.assertEqual(client.get(base).json()['status'], 'NOT_INITIALIZED')
        request = f.request()
        response = client.post(base+'/generate', json=request)
        self.assertEqual(response.status_code, 200, response.text)
        target = response.json()
        self.assertEqual(target['configuration_reason'], 'EXPLICIT_RECONFIGURE')
        self.assertEqual(len(target['targets']), 1)
        preview = client.post(base+'/preview', json=dict(
            expected_revision=request['expected_revision'], target_id=target['target_id']))
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()['difference']['new_orders'][0]['side'], 'BUY')
        self.assertEqual(preview.json()['core_calls'], 0)
        self.assertEqual(f.selection_calls, 1)
        f.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        current = client.get(base).json()
        self.assertEqual(current['target_id'], target['target_id'])
        self.assertEqual(current['configuration_reason'], 'MONTHLY_SELECTION')
        replay = client.post(base+'/generate', json=request)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()['target_id'], target['target_id'])
        missing = client.post(base+'/generate', json=f.request('january', 'MONTHLY_SELECTION'))
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(missing.json()['reason'], 'CURRENT_MONTH_RELEASE_REQUIRED')
        stale = client.post(base+'/preview', json=dict(
            expected_revision=request['expected_revision'], target_id=target['target_id']))
        self.assertEqual(stale.status_code, 422)
        self.assertEqual(stale.json()['reason'], 'MONTHLY_TARGET_REQUIRED')
        self.assertEqual(f.selection_calls, 1)
        self.assertEqual(len(f.router.targets.history()), 1)
        self.assertEqual(f.router.accounts.path.read_bytes(), before)
        self.assertNotIn('source_hashes', str(current))
        self.assertNotIn('runtime_pins', str(current))


if __name__ == '__main__':
    unittest.main()
