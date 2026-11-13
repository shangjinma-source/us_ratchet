import unittest
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.roa_strategy import create_router


class FundingHttpTests(unittest.TestCase):
    def setUp(self):
        self.reads = 0
        def read():
            self.reads += 1
            return {'status': 'READY', 'account': {'revision': 'a'}}
        self.coordinator = SimpleNamespace(
            account_service=SimpleNamespace(read=read, account_id='a'),
            lifecycle=SimpleNamespace(epoch='e'), snapshot=lambda: {'status': 'WAIT'})
        app = FastAPI()
        app.include_router(create_router(coordinator=self.coordinator))
        self.client = TestClient(app)
        self.body = dict(hsbc_cash='1000', usmart_cash='0', other_fee_reserve='25',
                         transfer_fee_reserve='0', hsbc_waiver_exhausted=True,
                         quota_month=datetime.now(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m'))

    def test_invalid_amount_never_reads_or_writes_account(self):
        for value in ['NaN', '-1', '1/2', 1000, '0.001']:
            body = dict(self.body, hsbc_cash=value)
            response = self.client.post('/api/strategy-roa/funding-preview', json=body)
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.reads, 0)

    def test_quota_month_cannot_carry_into_next_month(self):
        response = self.client.post('/api/strategy-roa/funding-preview', json=dict(self.body, quota_month='2000-01'))
        self.assertEqual(response.json()['status'], 'QUOTA_MONTH_MISMATCH')
        self.assertEqual(self.reads, 0)

    def test_failed_advice_never_becomes_funding_plan(self):
        response = self.client.post('/api/strategy-roa/funding-preview', json=self.body)
        self.assertEqual(response.json()['status'], 'WAIT_VERIFIED_ADVICE')
        self.assertFalse(response.json()['account_written'])
        self.assertEqual(self.reads, 2)

    def test_validated_preview_orchestration(self):
        with patch('scripts.verify_roa_live_advice.review', return_value={'api_advice_passed': True}) as review, patch('scripts.preview_broker_transfer.build_preview', return_value={'status':'FUNDING_PLAN_ONLY','executable':False}) as build:
            result = self.client.post('/api/strategy-roa/funding-preview', json=self.body)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.reads, 2)
        self.assertFalse(result.json()['orders_created'])
        self.assertEqual(build.call_args.kwargs['usmart_cash'], '0')
        review.assert_called_once()

    def test_holdings_mapping_forwarded_without_account_write(self):
        mapping = dict(account_revision='a', positions=[
            dict(broker='HSBC', security_id='security:a', quantity=12)])
        with patch('scripts.verify_roa_live_advice.review', return_value={'api_advice_passed': True}), patch('scripts.preview_broker_transfer.build_preview', return_value={'status':'FUNDING_PLAN_ONLY','executable':False}) as build:
            response = self.client.post('/api/strategy-roa/funding-preview', json=dict(self.body, broker_holdings=mapping))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(build.call_args.kwargs['broker_holdings'], mapping)
        self.assertFalse(response.json()['account_written'])

    def test_invalid_mapping_rejected_before_account_read(self):
        for quantity in [True, 0, -1, 1.5, '12']:
            mapping = dict(account_revision='a', positions=[
                dict(broker='HSBC', security_id='security:a', quantity=quantity)])
            response = self.client.post('/api/strategy-roa/funding-preview', json=dict(self.body, broker_holdings=mapping))
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.reads, 0)


if __name__ == '__main__':
    unittest.main()
