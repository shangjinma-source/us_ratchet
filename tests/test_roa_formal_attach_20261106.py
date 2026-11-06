"""Real attach/router/lifespan, isolated temporary account; no production files."""
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router
from data.roa_account_composition import attach_roa


class Signal:
    def __init__(self,**kwargs):self.refreshes=0
    def frozen_roster(self):return [dict(security_id='A',ticker='A')]
    def __call__(self):raise ValueError('WAIT_DAILY_MARKET_SIGNAL')
    def refresh_completed(self):self.refreshes+=1;return dict(status='UPDATED')


class Calendar:
    def __init__(self,root):pass
    def __call__(self,day):
        if day=='2026-11-07':raise ValueError('SESSION_NOT_IN_CALENDAR')
        return dict(open_at=day+'T14:30:00+00:00',close_at=day+'T21:00:00+00:00',previous_session='2026-11-05')


class AttachTests(unittest.TestCase):
    def test_actual_attach_missing_signal_lifespan_and_close(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);now=[datetime.fromisoformat('2026-11-07T16:00:00+00:00')]
            router=create_router(database_path=root/'account.sqlite3',account_id='isolated',resolver=lambda _:None,clock=lambda:now[0])
            events=[]
            @asynccontextmanager
            async def original_lifespan(app):
                events.append('start')
                try:yield
                finally:events.append('stop')
            router.lifespan_context=original_lifespan
            config=dict(account_id='isolated',strategy_epoch='test',contract_sha256='a'*64,contract_hashes={'contract':'a'*64},
                daily_signal_path='data/strategy_account/test/daily.json',lifecycle_path='data/strategy_account/test/life.json',close_evidence_path='data/strategy_account/test/close')
            with patch('data.roa_account_composition.RoaDailySignalProvider',Signal),patch('data.roa_account_composition.RoaSessionReader',Calendar), \
                 patch('data.roa_account_composition.load_completed_close_prices',return_value=dict(prices={},evidence={})) as close:
                prepared=attach_roa(prepared={'router':router},root=root,configuration=config,validate_sources=lambda:None,clock=lambda:now[0])
                account=prepared['roa_service'].account_service
                account.initialize({'event_id':'init'})
                state=account.store.read()
                account.append(dict(expected_revision=state['revision'],event=dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED')))
                baseline=account.store.read()
                app=FastAPI();app.include_router(prepared['router'])
                with TestClient(app) as client:
                    self.assertEqual(client.get('/api/strategy-roa/config').status_code,200)
                    self.assertEqual(account.account_id,'isolated')
                    self.assertEqual(client.get('/api/strategy-account').json()['account']['revision'],baseline['revision'])
                    self.assertEqual(client.get('/api/strategy-roa/snapshot').status_code,503)
                    self.assertFalse(client.post('/api/strategy-roa/advice-retry',json={}).json()['advice_ready'])
                    prepared['roa_maintain_completed_session']()
                    self.assertEqual(prepared['roa_maintenance_status']['status'],'WAIT')
                    now[0]=datetime.fromisoformat('2026-11-06T21:05:00+00:00')
                    prepared['roa_maintain_completed_session']()
                    self.assertEqual(prepared['roa_maintenance_status']['status'],'COMPLETE')
                    self.assertEqual(close.call_count,1)
                    prepared['roa_maintain_completed_session']()
                    self.assertEqual(close.call_count,1)
                self.assertEqual(events,['start','stop'])
                self.assertEqual(account.store.read(),baseline)


if __name__=='__main__':unittest.main()
