"""HTTP to real isolated V2 worker using a small synthetic admitted universe."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.current_quantity_research_v2 import create_router
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from test_current_quantity_portfolio_research_v2 import fixture


class IsolatedApiTests(unittest.TestCase):
    def test_cash_reselects_and_chart_remains_bound_to_original_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, descriptor = fixture(root)
            service = CurrentQuantityPortfolioResearchV2(
                root=root, source_loader=lambda: deepcopy(descriptor))
            app = FastAPI()
            app.include_router(create_router(service=service))
            base = '/api/current_portfolio_research'
            with TestClient(app) as client:
                first_response = client.post(base, json={'entered_cash': '60'})
                second_response = client.post(base, json={'entered_cash': '100'})
                self.assertEqual(first_response.status_code, 200)
                self.assertEqual(second_response.status_code, 200)
                first, second = first_response.json(), second_response.json()
                self.assertEqual(first['target_quantities'], {'B': 1})
                self.assertEqual(second['target_quantities'], {'A': 1, 'B': 1})
                self.assertNotEqual(first['research_id'], second['research_id'])
                self.assertEqual(second['implementation_mode'], 'ISOLATED_PINNED_SOURCE_BYTES')
                self.assertIsNone(second['executable_buy_quantities'])
                self.assertTrue(second['execution_blocked'])
                repeated = client.post(base, json={'entered_cash': '100.00'}).json()
                self.assertTrue(repeated['cache_hit'])
                self.assertEqual(repeated['research_id'], second['research_id'])
                query = dict(research_id=first['research_id'], ticker='BBB', interval='day', bars=90)
                bars = client.get(base + '/bars', params=query)
                self.assertEqual(bars.status_code, 200)
                self.assertEqual(bars.json()['research_id'], first['research_id'])
                self.assertTrue(all(row['date'] <= '2026-10-13' for row in bars.json()['bars']))
                self.assertEqual(client.get(base + '/bars', params=dict(query, ticker='AAA')).status_code, 503)
                (root / 'B.json').write_bytes(b'changed source')
                stale = client.get(base + '/snapshot', params={'research_id': first['research_id']})
                self.assertEqual(stale.status_code, 503)
                self.assertNotIn('target_quantities', stale.json())


if __name__ == '__main__':
    unittest.main()
