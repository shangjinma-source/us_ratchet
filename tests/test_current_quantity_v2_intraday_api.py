from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.current_quantity_v2_intraday import create_router
from data.current_quantity_v2_intraday_factory import create_reference_service, MANIFEST
from test_current_quantity_v2_intraday_reference import fixture, NOW


class IntradayApiTests(unittest.TestCase):
    def test_http_real_adapter_budget_and_source_drift(self):
        original, snapshot, _, quotes, packet = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / MANIFEST).parent.mkdir(parents=True)
            (root / MANIFEST).write_bytes(packet['files']['manifest.json'])
            (root / 'identity.json').write_bytes(packet['files']['identity.json'])
            (root / 'input.json').write_bytes(original.input_reader(snapshot))
            snapshot['sources'][MANIFEST] = snapshot['sources'].pop('manifest.json')
            snapshots = SimpleNamespace(
                snapshot=lambda rid: deepcopy(snapshot),
                loader=lambda: dict(input_path='input.json', source_hashes={'input.json': snapshot['input_sha256']}))
            calls = []
            def fetch(ticker):
                calls.append(ticker)
                return quotes[ticker]
            service = create_reference_service(root=root, snapshot_service=snapshots, fetch=fetch, clock=lambda: NOW)
            app = FastAPI(); app.include_router(create_router(service=service))
            with TestClient(app) as client:
                url = '/api/current_portfolio_research/intraday'
                response = client.post(url, json={'research_id': 'a' * 24})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['indicative_notional'], '70')
                self.assertEqual(response.json()['remaining_cash'], '30')
                self.assertEqual(calls, ['AAA', 'BBB'])
                for body in ('{"research_id":"'+'a'*24+'","cash":20000}',
                             '{"research_id":"a","research_id":"b"}'):
                    self.assertEqual(client.post(url, content=body).status_code, 400)
                self.assertEqual(calls, ['AAA', 'BBB'])
                (root / 'identity.json').write_bytes(b'changed')
                response = client.post(url, json={'research_id': 'a' * 24})
                self.assertEqual(response.status_code, 503)
                self.assertTrue(all(s['limit_price'] is None and s['quantity'] == 0 for s in response.json()['stocks']))
                self.assertEqual(calls, ['AAA', 'BBB'])

    def test_route_rejects_cross_snapshot_result(self):
        service = SimpleNamespace(preview=lambda rid: dict(research_id='b'*24, research_only=True,
                                  execution_blocked=True, orders_created=False))
        app = FastAPI(); app.include_router(create_router(service=service))
        with TestClient(app) as client:
            response = client.post('/api/current_portfolio_research/intraday', json={'research_id':'a'*24})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['stocks'], [])


if __name__ == '__main__':
    unittest.main()
