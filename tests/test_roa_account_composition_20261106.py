from datetime import datetime
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from docs.candidates.roa_account_composition_20261106 import build_isolated_composition
from docs.candidates.frozen_target_provider_20261106 import digest


class CompositionTests(unittest.TestCase):
    def test_one_cash_button_failure_recovery_partial_fill_and_repeat(self):
        with TemporaryDirectory() as directory:
            now=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            policy=dict(strategy_epoch='synthetic-roa',weights={'A':'1/10'},target_quantities={'A':9},
                signal_at='2026-11-05T21:00:00Z',valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T21:00:00Z')
            unavailable=[True]
            def quotes(account):
                if unavailable[0]:raise ValueError('QUOTE_UNAVAILABLE')
                return dict(marks={'A':dict(security_id='A',currency='USD',price_basis='current',price='100',observed_at=now.isoformat())},
                    limits={'A':dict(security_id='A',price_basis='current',buy='100',sell='100',observed_at=now.isoformat())})
            prepared=build_isolated_composition(directory=directory,account_id='test',
                resolver=lambda ticker:dict(ticker=ticker,security_id='A',source_references=['synthetic'],source_hashes={'synthetic':'a'*64}),
                policy=policy,contract_sha256=digest(policy),expected_epoch='synthetic-roa',quote_provider=quotes,clock=lambda:now)
            app=FastAPI();app.include_router(prepared['router'])
            with TestClient(app) as client:
                state=client.post('/api/strategy-account/initialize',json={'event_id':'init'}).json()['account']
                save_url='/api/research-candidate/cash-save-and-preview'
                body=dict(expected_revision=state['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                failed=client.post(save_url,json=body).json()
                self.assertTrue(failed['cash_saved']);self.assertFalse(failed['advice_ready'])
                state=prepared['account_service'].store.read()
                unavailable[0]=False
                recovered=client.post('/api/research-candidate/advice-retry',json={}).json()
                self.assertTrue(recovered['advice_ready'])
                self.assertEqual(recovered['account']['revision'],recovered['account_revision'])
                self.assertEqual(recovered['advice']['account_revision'],recovered['account_revision'])
                self.assertEqual(recovered['advice']['quote_valid_until'],'2026-11-06T14:33:00+00:00')
                self.assertEqual(recovered['advice']['execution_quotes']['A']['buy'],'100')
                self.assertEqual(recovered['account']['available_cash'],'1000')
                self.assertEqual(recovered['advice']['target_quantities'],{'A':9})
                self.assertEqual(prepared['account_service'].store.read(),state)
                filled=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=dict(
                    event_id='fill',kind='DIRECT_FILL',ticker='A',side='BUY',quantity=4,price='100',fees='0',executed_at=now.isoformat())))
                self.assertEqual(filled.status_code,200,filled.text)
                state=filled.json()['account']
                body=dict(expected_revision=state['revision'],event=dict(event_id='cash-after-fill',kind='CASH_CONFIRM',amount='600',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                result=client.post(save_url,json=body).json()
                self.assertEqual(result['advice']['difference']['new_orders'][0]['quantity'],5)
                self.assertEqual(result['account']['holdings'][0]['quantity'],4)
                self.assertEqual(result['account']['available_cash'],'600')
                before=prepared['account_service'].store.read()
                repeated=client.post(save_url,json=body).json()
                self.assertTrue(repeated['advice_ready'])
                self.assertEqual(prepared['account_service'].store.read(),before)
                self.assertFalse(result['advice']['executable'])
                self.assertFalse(before['orders'])
                original_project=prepared['account_service'].project
                def concurrent_cash_change(snapshot):
                    projected=original_project(snapshot)
                    prepared['account_service'].store.append(expected_revision=snapshot['revision'],event={
                        'event_id':'concurrent-cash','kind':'CASH_CONFIRM','amount':'550',
                        'cash_basis':'AVAILABLE_AFTER_RESERVATIONS'})
                    return projected
                with patch.object(prepared['account_service'],'project',side_effect=concurrent_cash_change):
                    stale=client.post('/api/research-candidate/advice-retry',json={}).json()
                self.assertFalse(stale['advice_ready'])
                self.assertNotIn('advice',stale)
                self.assertEqual(prepared['account_service'].store.read()['available_cash'],'550')
                self.assertNotEqual(stale['account_revision'],result['account_revision'])


if __name__=='__main__':unittest.main()
