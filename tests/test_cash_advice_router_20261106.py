from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService, WriteOutcomeUncertain
from docs.candidates.cash_advice_coordinator_20261106 import CashAdviceCoordinator
from docs.candidates.cash_advice_router_20261106 import create_router
from docs.candidates.frozen_target_builder_20261106 import FrozenTargetBuilder
from docs.candidates.frozen_target_provider_20261106 import digest


class RouterTests(unittest.TestCase):
    def test_cash_http_failure_retry_unknown_and_strict_input(self):
        with TemporaryDirectory() as directory:
            now=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            account=StrategyAccountService(database_path=Path(directory)/'account.sqlite3',account_id='test',resolver=lambda _:None,clock=lambda:now)
            initial=account.initialize({'event_id':'init'})['account']
            policy=dict(strategy_epoch='test',weights={'NEW':'1'},signal_at='2026-11-05T21:00:00Z',valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T14:32:00Z')
            unavailable=[True]
            def quotes(state):
                if unavailable[0]:raise ValueError('QUOTE_UNAVAILABLE')
                return dict(marks={'NEW':dict(security_id='NEW',currency='USD',price_basis='current',price='100',observed_at=now.isoformat())},limits={'NEW':dict(security_id='NEW',price_basis='current',buy='100',sell='100',observed_at=now.isoformat())})
            builder=FrozenTargetBuilder(directory=Path(directory)/'targets',policy=policy,contract_sha256=digest(policy),expected_epoch='test',account_id='test',store=account.store,quote_provider=quotes,clock=lambda:now)
            coordinator=CashAdviceCoordinator(account_service=account,builder=builder)
            app=FastAPI();app.include_router(create_router(coordinator=coordinator))
            with TestClient(app) as client:
                url='/api/research-candidate/cash-save-and-preview'
                body=dict(expected_revision=initial['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
                failed=client.post(url,json=body)
                self.assertEqual(failed.status_code,200)
                self.assertEqual(failed.json()['cash_saved'],True)
                self.assertFalse(failed.json()['advice_ready'])
                saved=account.store.read()
                unavailable[0]=False
                retry=client.post('/api/research-candidate/advice-retry',json={})
                self.assertEqual(retry.status_code,200)
                self.assertTrue(retry.json()['advice_ready'])
                self.assertEqual(retry.json()['advice']['target_id'],builder.versions[-1]['target_id'])
                self.assertEqual(retry.json()['advice']['difference']['new_orders'][0]['quantity'],10)
                self.assertFalse(retry.json()['advice']['executable'])
                self.assertEqual(account.store.read(),saved)
                self.assertTrue(client.post(url,json=body).json()['advice_ready'])
                self.assertEqual(account.store.read(),saved)
                for invalid in [dict(body,weights={}),dict(body,event=dict(body['event'],kind='DIRECT_FILL'))]:
                    self.assertEqual(client.post(url,json=invalid).status_code,422)
                self.assertEqual(client.post('/api/research-candidate/advice-retry',json={'weights':{}}).status_code,422)
                self.assertEqual(client.post(url,content='{"event":{},"event":{}}').status_code,422)
                account.append=Mock(side_effect=WriteOutcomeUncertain())
                unknown=client.post(url,json=dict(body,event=dict(body['event'],event_id='not-saved')))
                self.assertEqual(unknown.status_code,503)
                self.assertIsNone(unknown.json()['cash_saved'])
                self.assertFalse(unknown.json()['advice_ready'])

    def test_durable_cash_then_read_value_error_never_reports_unsaved(self):
        with TemporaryDirectory() as directory:
            now=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            account=StrategyAccountService(database_path=Path(directory)/'account.sqlite3',account_id='test',resolver=lambda _:None,clock=lambda:now)
            initial=account.initialize({'event_id':'init'})['account']
            real_append=account.append
            real_read=account.store.read
            def append_then_break_read(body):
                response=real_append(body)
                account.store.read=Mock(side_effect=ValueError('READ_UNAVAILABLE'))
                return response
            account.append=Mock(side_effect=append_then_break_read)
            builder=Mock()
            coordinator=CashAdviceCoordinator(account_service=account,builder=builder)
            app=FastAPI();app.include_router(create_router(coordinator=coordinator))
            with TestClient(app) as client:
                response=client.post('/api/research-candidate/cash-save-and-preview',json=dict(expected_revision=initial['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')))
                self.assertEqual(response.status_code,200,response.text)
                self.assertTrue(response.json()['cash_saved'])
                self.assertFalse(response.json()['advice_ready'])
                self.assertIsNone(response.json()['account_revision'])
                account.append.assert_called_once()
                builder.rebuild.assert_not_called()
                account.store.read=real_read
                self.assertEqual(real_read()['available_cash'],'1000')
                self.assertEqual(len(real_read()['events']),1)


if __name__=='__main__':unittest.main()
