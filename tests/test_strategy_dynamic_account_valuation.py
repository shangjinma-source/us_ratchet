"""Dynamic valuation HTTP: real account/version guards, synthetic market marks."""
from datetime import timedelta
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_dynamic_monthly_target import create_dynamic_account_router
import test_strategy_account_monthly_router as fixtures


class DynamicValuationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.MonthlyRouterTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        app = FastAPI()
        app.include_router(create_dynamic_account_router(service=self.f.router))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.candidate = self.f.fixture.identity['candidates'][0]
        result = self.client.post('/api/strategy-account/events', json=dict(
            expected_revision=self.f.router.accounts.read()['revision'],event=dict(
                event_id='fill',kind='DIRECT_FILL',ticker=self.candidate['ticker'],side='BUY',
                quantity=1,price='100',fees='0',executed_at=self.f.now.isoformat())))
        self.assertEqual(result.status_code,200,result.text)
        self.f.append(dict(event_id='confirmed',kind='CASH_CONFIRM',amount='1900',cash_basis='TOTAL_UNINVESTED'))
        self.f.router.generate(**self.f.request())

    def marks(self, provider, state):
        sid = self.candidate['security_id']
        return {sid:dict(security_id=sid,ticker=self.candidate['ticker'],currency='USD',
            price='120',observed_at=self.f.now.isoformat())}

    def test_valuation_combines_confirmed_cash_without_mutating_or_reselection(self):
        before = self.f.router.accounts.path.read_bytes()
        with patch('data.strategy_account_evidence_provider.StrategyAccountEvidenceProvider.valuation', lambda provider,state:self.marks(provider,state)):
            response = self.client.get('/api/strategy-account/valuation')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['market_value'],'120')
        self.assertEqual(response.json()['strategy_total'],'2020')
        self.assertEqual(self.f.selection_calls,1)
        self.assertEqual(self.f.router.accounts.path.read_bytes(),before)

    def test_account_change_during_capture_rejects_mixed_revision(self):
        def changing(provider,state):
            self.f.append(dict(event_id='concurrent',kind='CASH_CONFIRM',amount='1800',cash_basis='TOTAL_UNINVESTED'))
            return self.marks(provider,state)
        with patch('data.strategy_account_evidence_provider.StrategyAccountEvidenceProvider.valuation',changing):
            response = self.client.get('/api/strategy-account/valuation')
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['reason'],'STALE_REVISION')
        self.assertNotIn('market_value',response.json())

    def test_expired_marks_are_not_shown_as_current_valuation(self):
        def stale(provider,state):
            marks=self.marks(provider,state)
            for mark in marks.values():mark['observed_at']=(self.f.now-timedelta(seconds=121)).isoformat()
            return marks
        with patch('data.strategy_account_evidence_provider.StrategyAccountEvidenceProvider.valuation',stale):
            response=self.client.get('/api/strategy-account/valuation')
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(response.json()['reason'],'VALUATION_EXPIRED')


if __name__ == '__main__':unittest.main()
