"""HTTP-only synthetic split ledger flow; no production server or account."""
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_split_account_cost_projection as fixture


class SplitAccountHTTPTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.SplitAccountCostProjectionTests();self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.mark=dict(security_id='A',ticker='AAA',currency='USD',price='13',unit_id='new',
                       observed_at=self.base.base.clock().isoformat())
        app=FastAPI()
        app.include_router(fixture.candidate.create_router(database_path=self.base.store.path,
            account_id='synthetic-account', clock=self.base.base.clock,
            valuation_provider=lambda state:{'A':dict(self.mark)},
            resolver=lambda ticker:dict(ticker=ticker,security_id='A',source_references=['synthetic'],
                                       source_hashes={'synthetic':'f'*64})))
        self.client=TestClient(app);self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)

    def read(self):
        response=self.client.get('/api/strategy-account')
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['account']

    def test_split_read_cash_fill_retry_and_reconfirmation_via_http(self):
        account=self.read()
        self.assertEqual(account['holding_costs'][0]['quantity'],112)
        def write(event,revision=None):
            return self.client.post('/api/strategy-account/events',json=dict(
                expected_revision=revision or account['revision'],event=event))
        response=write(dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
        self.assertEqual(response.status_code,200,response.text);account=response.json()['account']
        revision=account['revision']
        fill=dict(event_id='fill-after-split',kind='DIRECT_FILL',ticker='AAA',side='SELL',quantity=14,
                  price='13',fees='0',executed_at=self.base.base.clock().isoformat())
        response=write(fill);self.assertEqual(response.status_code,200,response.text)
        account=response.json()['account'];cost=account['holding_costs'][0]
        self.assertEqual((cost['quantity'],cost['total_cost']),(98,'1225'))
        self.assertFalse(account['cash_confirmation_valid'])
        retried=write(fill,revision);self.assertEqual(retried.status_code,200,retried.text)
        self.assertEqual(retried.json()['account'],account)
        cash=dict(event_id='cash-after-sell',kind='CASH_CONFIRM',amount='1182',cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(write(cash,revision).status_code,409)
        response=write(cash);self.assertEqual(response.status_code,200,response.text)
        account=response.json()['account'];self.assertTrue(account['cash_confirmation_valid'])
        self.assertEqual(self.read(),account)

    def test_browser_cannot_insert_split_or_approve_its_own_action(self):
        before=self.base.store.read()
        action=dict(self.base.base.arguments['action'],event_id='forged-action')
        response=self.client.post('/api/strategy-account/events',json=dict(expected_revision=before['revision'],event=action))
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.base.store.read(),before)

    def test_valuation_requires_post_split_units(self):
        response=self.client.get('/api/strategy-account/valuation')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['market_value'],'1456')
        self.mark['unit_id']='old'
        response=self.client.get('/api/strategy-account/valuation')
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(response.json()['reason'],'VALUATION_SPLIT_UNIT_REQUIRES_REVIEW')
