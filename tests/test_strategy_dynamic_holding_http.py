"""Holding-chart HTTP contract: real ledger and chart data, injected source gate."""
from types import SimpleNamespace
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_dynamic_monthly_target import create_dynamic_holding_charts_router
import test_strategy_account_monthly_router as fixtures


class DynamicHoldingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.MonthlyRouterTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.row=self.f.fixture.identity['candidates'][0]
        identity=self.f.router.resolve_identity(self.row['ticker'])
        self.f.append(dict(event_id='held',kind='DIRECT_FILL',security_id=self.row['security_id'],
            identity_evidence=identity,quantity=1,side='BUY',price='100',fees='0',executed_at=self.f.now.isoformat()))
        self.calls=0;self.reject=False
        def gate():
            self.calls+=1
            if self.reject:raise ValueError('RUNTIME_SOURCE_CHANGED')
        self.gate=gate
        app=FastAPI();app.include_router(create_dynamic_holding_charts_router(service=self.f.router,
            validate_runtime=gate,bootstrap_configuration=self.f.configuration))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.query=dict(account_revision=self.f.router.accounts.read()['revision'],security_id=self.row['security_id'])

    def test_no_target_three_periods_source_gate_and_no_account_write(self):
        before=self.f.router.accounts.path.read_bytes()
        for interval in ('day','week','month'):
            response=self.client.get('/api/strategy-account/holding-bars',params=dict(self.query,interval=interval))
            self.assertEqual(response.status_code,200,response.text)
            self.assertTrue(response.json()['bars'])
            self.assertIsNone(response.json()['source_target_id'])
            self.assertTrue(response.json()['historical_only'])
        self.assertEqual(self.calls,6)
        self.assertEqual(self.f.router.accounts.path.read_bytes(),before)
        self.assertIsNone(self.f.router.current())
        self.assertEqual(self.f.selection_calls,0)
        self.reject=True
        rejected=self.client.get('/api/strategy-account/holding-bars',params=self.query)
        self.assertEqual(rejected.status_code,422)
        self.assertEqual(rejected.json()['reason'],'RUNTIME_SOURCE_CHANGED')

    def test_revision_unknown_sid_and_missing_gate_rejected(self):
        with self.assertRaisesRegex(ValueError,'HOLDING_CHART_SOURCE_GATE_REQUIRED'):
            create_dynamic_holding_charts_router(service=self.f.router,validate_runtime=None)
        stale=self.client.get('/api/strategy-account/holding-bars',params=dict(self.query,account_revision='0'*64))
        self.assertEqual(stale.status_code,409)
        missing=self.client.get('/api/strategy-account/holding-bars',params=dict(self.query,security_id='absent'))
        self.assertEqual(missing.status_code,422)
        self.assertEqual(missing.json()['reason'],'CHART_NOT_HELD')


if __name__=='__main__':unittest.main()
