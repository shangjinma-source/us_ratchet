"""Independent HTTP acceptance and recovery of the current-quote cash scope."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_current_quantity_v2_current_cash_plan as fixtures
from test_current_quantity_v2_current_cash_ledger import frozen_fixture
from api.current_quantity_v2_paper import PREFIX, create_router
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore


class CurrentCashHttpTests(unittest.TestCase):
    def test_accept_fill_and_retry_without_sources(self):
        fixtures.CurrentCashTests.setUpClass()
        try:
            proposal, args = frozen_fixture(fixtures.CurrentCashTests.args)
            now = datetime.fromisoformat(args['now']) + timedelta(seconds=1)
            with TemporaryDirectory() as folder:
                service = QuantityV2PaperService(
                    store=QuantityV2PaperStore(Path(folder) / 'paper.sqlite3'),
                    initial_resolver=lambda aid, pid, at: dict(
                        proposal=deepcopy(proposal), account_state=deepcopy(args['account_state'])),
                    clock=lambda: now)
                app = FastAPI()
                app.include_router(create_router(service=service))
                with TestClient(app) as client:
                    request = dict(account_id=proposal['account_id'],
                                   proposal_id=proposal['proposal_id'], operation_id='current-cash-http')
                    response = client.post(PREFIX + '/accept', json=request)
                    self.assertEqual(response.status_code, 200, response.text)
                    account = response.json()
                    self.assertEqual(account['target_quantities'], {'A': 6, 'B': 4})
                    self.assertEqual(account['historical_target_quantities'], {'A': 1, 'B': 1})
                    self.assertEqual(account['execution_target_id'], proposal['execution_target_id'])
                    now += timedelta(seconds=1)
                    order = next(row for row in account['orders'] if row['security_id'] == 'A')
                    event = dict(event_id='fill-http', type='FILL', order_id=order['order_id'],
                                 expected_revision=account['revision'], quantity=1, price='9',
                                 fees='1/5', executed_at=now.isoformat())
                    response = client.post(PREFIX + '/event', json=dict(
                        account_id=account['account_id'], event=event))
                    self.assertEqual(response.status_code, 200, response.text)
                    latest = response.json()
                    self.assertEqual(latest['cash'], '504/5')
                    self.assertEqual(latest['shares'], {'A': 1})
                    service.initial_resolver = None
                    service.clock = lambda: (_ for _ in ()).throw(AssertionError('retry clock'))
                    retry = client.post(PREFIX + '/accept', json=request)
                    self.assertEqual(retry.status_code, 200, retry.text)
                    self.assertEqual(retry.json(), latest)
                    self.assertEqual(client.get(PREFIX + '/account', params={
                        'account_id': account['account_id']}).json(), latest)
        finally:
            fixtures.CurrentCashTests.tearDownClass()


if __name__ == '__main__':
    unittest.main()
