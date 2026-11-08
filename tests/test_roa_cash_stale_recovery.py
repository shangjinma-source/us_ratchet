"""Real temporary SQLite/HTTP stale-write recovery; no live-account writes."""
import tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService
from api.roa_strategy import create_router
from data.roa_cash_advice_coordinator import CashAdviceCoordinator

class CashStaleRecoveryTests(unittest.TestCase):
    def test_absence_same_revision_remains_uncertain_but_stale_is_provably_unsaved(self):
        with tempfile.TemporaryDirectory() as folder:
            account=StrategyAccountService(database_path=Path(folder)/'test.sqlite',account_id='test',resolver=lambda _:None,clock=lambda:datetime(2026,11,9,tzinfo=timezone.utc))
            account.initialize({'event_id':'init'})
            service=CashAdviceCoordinator(account_service=account,builder=None)
            body=dict(expected_revision=account.store.read()['revision'],event=dict(kind='CASH_CONFIRM',event_id='delayed',amount='3000',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
            app=FastAPI();app.include_router(create_router(coordinator=service))
            with TestClient(app) as client:
                pending=client.post('/api/strategy-roa/cash-status',json=body)
                self.assertIsNone(pending.json()['cash_saved'])
                account.append(dict(expected_revision=body['expected_revision'],event=dict(body['event'],event_id='other',amount='500')))
                before=account.store.read()
                # A delayed old request cannot overwrite the newer confirmation.
                rejected=client.post('/api/strategy-roa/cash-save-and-preview',json=body)
                self.assertEqual(rejected.status_code,503)
                recovered=client.post('/api/strategy-roa/cash-status',json=body)
                self.assertEqual(recovered.status_code,200)
                self.assertIs(recovered.json()['cash_saved'],False)
                self.assertEqual(recovered.json()['reason'],'CASH_NOT_SAVED_ACCOUNT_CHANGED')
                self.assertEqual(account.store.read(),before)
                # Retry with a fresh event/revision; advice can fail without losing cash.
                fresh=dict(expected_revision=before['revision'],event=dict(body['event'],event_id='fresh'))
                saved=client.post('/api/strategy-roa/cash-save-and-preview',json=fresh)
                self.assertTrue(saved.json()['cash_saved'])
                latest=account.store.read()
                self.assertEqual(client.post('/api/strategy-roa/cash-save-and-preview',json=fresh).json()['cash_saved'],True)
                self.assertEqual(account.store.read(),latest)
                self.assertTrue(client.post('/api/strategy-roa/cash-status',json=fresh).json()['cash_saved'])
                conflict=dict(fresh,event=dict(fresh['event'],amount='1'))
                self.assertIsNone(client.post('/api/strategy-roa/cash-status',json=conflict).json()['cash_saved'])
                self.assertEqual(account.store.read(),latest)
if __name__=='__main__':unittest.main()
