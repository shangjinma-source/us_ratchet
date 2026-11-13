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
        self.coordinator.broker_cash_service = SimpleNamespace(read=lambda: dict(
            status='CONFIRMED_BROKER_CASH_SPLIT', account_revision='a',
            document={'balances': {'HSBC': {'available_cash':'1000'}, 'USMART': {'available_cash':'0'}}}))
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

    def test_real_budget_calculator_uses_confirmed_split(self):
        self.body['hsbc_cash'] = '5000'
        self.coordinator.broker_cash_service = SimpleNamespace(read=lambda: dict(
            status='CONFIRMED_BROKER_CASH_SPLIT', account_revision='a',
            document={'balances': {'HSBC': {'available_cash':'5000'}, 'USMART': {'available_cash':'0'}}}))
        self.coordinator.snapshot = lambda: dict(account=dict(holdings=[], orders=[], available_cash='5000', revision='a'),
            difference=dict(new_orders=[dict(side='BUY',security_id='stock',quantity=20,limit_price='100')]),
            rows=[dict(security_id='stock',ticker='TEST')], proposal_id='p',target_id='t',
            quote_valid_until='future-fixture',execution_session='fixture')
        with patch('scripts.verify_roa_live_advice.review', return_value={'api_advice_passed':True}):
            response = self.client.post('/api/strategy-roa/funding-preview', json=self.body)
        from fractions import Fraction
        self.assertEqual(response.status_code, 200)
        result=response.json()
        self.assertEqual(result['planned_usmart_buys'][0]['quantity'],20)
        self.assertEqual(Fraction(result['proposed_transfer_credit_usd']),Fraction('2026.88'))
        self.assertEqual(Fraction(result['hsbc_remaining_if_funded_usd']),Fraction('2973.12'))
        self.assertFalse(result['orders_created'])

    def test_unconfirmed_split_does_not_reach_market_or_budget(self):
        self.coordinator.broker_cash_service = SimpleNamespace(read=lambda: {'status':'BROKER_CASH_CONFIRMATION_REQUIRED'})
        response=self.client.post('/api/strategy-roa/funding-preview',json=self.body)
        self.assertEqual(response.json()['status'],'BROKER_CASH_CONFIRMATION_REQUIRED')
        self.assertEqual(self.reads,0)

    def test_invalid_mapping_rejected_before_account_read(self):
        for quantity in [True, 0, -1, 1.5, '12']:
            mapping = dict(account_revision='a', positions=[
                dict(broker='HSBC', security_id='security:a', quantity=quantity)])
            response = self.client.post('/api/strategy-roa/funding-preview', json=dict(self.body, broker_holdings=mapping))
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.reads, 0)


if __name__ == '__main__':
    unittest.main()
