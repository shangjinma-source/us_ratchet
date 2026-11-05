"""Real HTTP/journal continuity on a temporary split account; no live writes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
import unittest

from data.strategy_split_bundle_v1 import prepare_split_bundle
from docs.candidates import strategy_account_split_cost_projection as candidate
import test_strategy_split_bundle_v1 as fixtures


class SplitAccountHttpContinuityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SplitBundleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        prepare_split_bundle(**self.fixture.arguments)
        identity = dict(security_id='A', ticker='A', source_references=['synthetic'],
                        source_hashes={'synthetic': 'a' * 64})
        app = FastAPI()
        app.include_router(candidate.create_router(
            database_path=self.fixture.directory / 'account.sqlite3',
            account_id='synthetic-account', resolver=lambda ticker: dict(
                identity, security_id=ticker, ticker=ticker),
            clock=self.fixture.clock))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def read(self):
        response = self.client.get('/api/strategy-account')
        self.assertEqual(response.status_code, 200)
        return response.json()['account']

    def append(self, event, revision=None):
        return self.client.post('/api/strategy-account/events', json=dict(
            expected_revision=revision or self.read()['revision'], event=event))

    def test_available_cash_with_open_buy_is_not_reserved_twice(self):
        source_before = self.fixture.source.read()
        cash = dict(event_id='http-cash', kind='CASH_CONFIRM', amount='5000',
                    cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(self.append(cash).status_code, 200)
        order = dict(event_id='http-buy-order', kind='ORDER_OPEN', order_id='buy-B',
                     ticker='B', side='BUY', quantity=10, limit_price='13', fee_per_share='0')
        self.assertEqual(self.append(order).status_code, 200)
        cash = dict(cash, event_id='http-available-cash', cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        self.assertEqual(self.append(cash).status_code, 200)
        self.assertEqual(self.read()['available_cash'], '5000')
        self.assertEqual(self.read()['reserved_cash'], '130')
        self.assertEqual(self.read()['total_uninvested_cash'], '5130')
        self.assertTrue(self.read()['cash_confirmation_valid'])
        revision = self.read()['revision']
        sale = dict(event_id='http-sale', kind='DIRECT_FILL', ticker='A', side='SELL',
                    quantity=20, price='13', fees='0',
                    executed_at=self.fixture.clock().isoformat())
        self.assertEqual(self.append(sale, revision).status_code, 200)
        after_sale = self.read()
        self.assertEqual(after_sale['holdings'][0]['quantity'], 92)
        self.assertFalse(after_sale['cash_confirmation_valid'])
        # Retry the original request after its revision has advanced.
        self.assertEqual(self.append(sale, revision).status_code, 200)
        self.assertEqual(self.read(), after_sale)
        self.assertEqual(self.append(dict(cash, event_id='http-cash-after',
                                         amount='5260')).status_code, 200)
        current = self.read()
        self.assertTrue(current['cash_confirmation_valid'])
        self.assertEqual(current['available_cash'], '5260')
        self.assertEqual(current['reserved_cash'], '130')
        self.assertEqual(current['total_uninvested_cash'], '5390')
        self.assertEqual(current['holding_costs'][0]['quantity'], 92)
        self.assertEqual(current['fills'][0]['quantity'], 14)
        self.assertEqual(self.fixture.source.read(), source_before)

    def test_committed_write_projection_failure_requires_readback(self):
        cash = dict(event_id='uncertain-http-cash', kind='CASH_CONFIRM', amount='6000',
                    cash_basis='TOTAL_UNINVESTED')
        revision = self.read()['revision']
        with patch.object(candidate.StrategyAccountService, 'project',
                          side_effect=RuntimeError('synthetic response failure')):
            response = self.append(cash, revision)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['reason'], 'RECONCILE_REQUIRED')
        reconciled = self.read()
        self.assertNotEqual(reconciled['revision'], revision)
        self.assertEqual(self.append(cash, revision).status_code, 200)
        self.assertEqual(self.read(), reconciled)


if __name__ == '__main__':
    unittest.main()
