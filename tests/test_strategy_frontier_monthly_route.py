from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_frontier_monthly_target_v1 import create_router
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from test_saved_monthly_frontier_proposal import native_fixture, sign
from hashlib import sha256
from datetime import datetime
from core.strategy_account_ledger import canonical
from data.strategy_frontier_target_charts_v1 import StrategyFrontierTargetChartsV1


class FrontierMonthlyRouteTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.target = native_fixture()
        root = Path(directory.name)
        raw = canonical({'chart': {'error': None, 'result': [{
            'meta': dict(symbol='B', currency='USD', instrumentType='EQUITY',
                         exchangeTimezoneName='America/New_York', dataGranularity='1d'),
            'timestamp': [int(datetime.fromisoformat('2026-10-14T20:00:00+00:00').timestamp())],
            'indicators': {'quote': [dict(open=[100], high=[102], low=[98], close=[101], volume=[200])]},
        }]}})
        (root/'B.json').write_bytes(raw)
        digest = sha256(raw).hexdigest()
        manifest = canonical(dict(decision_date='2026-10-14', source_hashes={'B.json': digest},
            candidates=[dict(security_id='B', ticker='B', status='READY_CONDITIONAL', training_source='B.json')]))
        (root/'synthetic-training.json').write_bytes(manifest)
        binding = self.target['payload']['decision']['payload']['input_binding']
        binding['source_hashes'].update({'B.json': digest, 'synthetic-training.json': sha256(manifest).hexdigest()})
        sign(self.target)
        case = self

        class Monthly:
            def validate_current_target_pins(self):
                return None

            def snapshot_operation(self):
                return nullcontext()

            def current(self):
                return deepcopy(case.target)

            def _month(self):
                return '2026-10'

        store = SavedFrontierProposalStore(Path(directory.name)/'proposal.sqlite3')
        self.proposal = store.bind(self.target)
        view = SavedFrontierMonthlyView(monthly=Monthly(), proposals=store,
                                       validate_sources=lambda: None)
        app = FastAPI()
        app.include_router(create_router(service=view, charts=StrategyFrontierTargetChartsV1(root=root, target_service=view)))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_get_preserves_original_and_exposes_new_security_separately(self):
        response = self.client.get('/api/strategy-account/target')
        self.assertEqual(response.status_code, 200)
        value = response.json()
        self.assertEqual(value['target_id'], self.target['target_id'])
        self.assertEqual(value['proposal_id'], self.proposal['proposal_id'])
        self.assertEqual({row['security_id'] for row in value['targets']}, {'A'})
        self.assertEqual({row['security_id'] for row in value['proposal_targets']}, {'A', 'B'})
        self.assertEqual(value['risk_monthly_targets'],
                         self.proposal['payload']['proposed_target_quantities'])
        self.assertNotIn('frontier_proposal', value)
        self.assertNotIn('payload', value)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_http_new_saved_proposal_stock_candles_and_stale_binding(self):
        query = dict(target_id=self.target['target_id'], security_id='B', interval='day',
                     expected_proposal_id=self.proposal['proposal_id'])
        response = self.client.get('/api/strategy-account/target/bars', params=query)
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual(value['bars'][0]['close'], 101)
        self.assertEqual(value['proposal_id'], self.proposal['proposal_id'])
        self.assertNotIn('payload', value)
        self.assertNotIn('frontier_proposal', value)
        query['expected_proposal_id'] = '0'*64
        response = self.client.get('/api/strategy-account/target/bars', params=query)
        self.assertIn(response.status_code, (409, 422))
        self.assertEqual(response.json()['reason'], 'STALE_FRONTIER_PROPOSAL')

    def test_legacy_preview_cannot_bypass_proposal_admission(self):
        response = self.client.post('/api/strategy-account/target/preview', json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['reason'], 'FRONTIER_DAILY_PREVIEW_REQUIRED')


if __name__ == '__main__':
    unittest.main()
