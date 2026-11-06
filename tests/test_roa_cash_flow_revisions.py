from datetime import datetime,timezone
from hashlib import sha256
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import Thread
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService
from api.roa_strategy import create_router
from data.roa_strategy_service import RoaStrategyService
from data.roa_cash_flow.composition import attach_flow

class ActualRoaTests(unittest.TestCase):
    def test_existing_cash_endpoint_and_stale_valuation(self):
        with TemporaryDirectory() as d:
            root=Path(d);directory=root/'data/strategy_account';directory.mkdir(parents=True);now=[datetime(2026,11,6,10,tzinfo=timezone.utc)]
            account=StrategyAccountService(database_path=directory/'account.sqlite',account_id='test',resolver=lambda _:None,clock=lambda:now[0],valuation_provider=lambda _: {})
            account.initialize({'event_id':'init'})
            def confirm(event,amount):return account.append(dict(expected_revision=account.store.read()['revision'],event=dict(event_id=event,kind='CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED')))
            confirm('start','100');old=account.store.read();value=account.valuation()
            baseline=dict(initial_equity='100',cash='100',effective_at=value['valued_at'],account_revision=old['revision'],holdings=[],valuation_evidence=value)
            def pin(name,doc):
                path=directory/name;raw=json.dumps(doc).encode();path.write_bytes(raw);return dict(path=path.relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
            config=dict(schema='ROA_FLOW_CLASSIFICATION_CONFIG_V1',baseline=pin('baseline.json',baseline),ledger=pin('ledger.json',old),sidecar_path='data/strategy_account/flows.sqlite')
            def no_signal():raise ValueError('WAIT_DAILY_MARKET_SIGNAL')
            roa=RoaStrategyService(account_service=account,lifecycle=SimpleNamespace(epoch='test',contract='a'*64),signal_provider=no_signal,session_provider=None,quote_provider=None,clock=lambda:now[0])
            prepared=attach_flow(prepared=dict(roa_service=roa,router=create_router(coordinator=roa)),root=root,configuration=config,clock=lambda:now[0],validate_sources=lambda:None);addon=prepared['cash_classification']
            with self.assertRaises(sqlite3.OperationalError):addon.current()
            self.assertFalse(addon.store.path.exists());addon.store.initialize()
            app=FastAPI();app.include_router(prepared['router'])
            with TestClient(app) as client:
                now[0]=datetime(2026,11,6,10,2,tzinfo=timezone.utc)
                response=client.post('/api/strategy-roa/cash-save-and-preview',json=dict(expected_revision=old['revision'],event=dict(event_id='new',kind='CASH_CONFIRM',amount='160',cash_basis='TOTAL_UNINVESTED')))
                self.assertTrue(response.json()['cash_saved']);self.assertFalse(response.json()['advice_ready'])
                saved=account.store.read();result=client.get('/api/strategy-account/cash-classification').json();row=result['unresolved'][0]
                doc=dict(schema='CASH_CHANGE_CLASSIFICATION_V1',account_id='test',cash_event_id='new',before_revision=row['before_revision'],after_revision=row['after_revision'],net_change='60',items=[dict(item_id='d',kind='DEPOSIT',amount='50',effective_at='2026-11-06T10:01:00Z'),dict(item_id='i',kind='INCOME',amount='10',effective_at='2026-11-06T10:01:00Z')])
                for _ in range(2):self.assertEqual(client.post('/api/strategy-account/cash-classification',json=dict(expected_revision=saved['revision'],document=doc)).status_code,200)
                self.assertEqual(client.get('/api/strategy-account/cash-classification').json()['profit']['profit_amount'],'10');self.assertEqual(account.store.read(),saved)
                import copy
                original_account=account.store.read();original_db=sha256(account.store.path.read_bytes()).hexdigest()
                original_hash=client.get('/api/strategy-account/cash-classification').json()['classified'][0]['document_sha256']
                corrected=copy.deepcopy(doc);corrected['items']=[dict(item_id='d',kind='DEPOSIT',amount='60',effective_at='2026-11-06T10:01:00Z')]
                def post(document,expected_hash,revision=None):
                    response=client.post('/api/strategy-account/cash-classification',json=dict(expected_revision=revision or original_account['revision'],document=document,expected_document_sha256=expected_hash))
                    return response
                def history():
                    with closing(sqlite3.connect(addon.store.path)) as connection:
                        return connection.execute('SELECT payload,document_sha256 FROM classification_history ORDER BY sequence').fetchall()
                self.assertEqual(len(history()),1)
                # Same prior hash cannot overwrite another successful revision.
                first=post(corrected,original_hash);self.assertEqual(first.status_code,200,first.text)
                new_hash=first.json()['document_sha256'];self.assertNotEqual(original_hash,new_hash)
                self.assertEqual(len(history()),2)
                competitor=copy.deepcopy(doc);competitor['items']=[dict(item_id='i',kind='INCOME',amount='60',effective_at='2026-11-06T10:01:00Z')]
                self.assertEqual(post(competitor,original_hash).status_code,409)
                self.assertEqual(len(history()),2)
                # Lost-response retry of the exact previous correction is idempotent.
                for _ in range(2):self.assertEqual(post(corrected,original_hash).status_code,200)
                self.assertEqual(len(history()),2)
                self.assertEqual(json.loads(history()[0][0]),doc);self.assertEqual(json.loads(history()[1][0]),corrected)
                current=client.get('/api/strategy-account/cash-classification').json()
                self.assertEqual(current['profit']['profit_amount'],'0');self.assertEqual(current['profit']['net_external_flow'],'60')
                # Deliberate unrecorded-trade flag blocks performance but remains visible and repairable.
                blocked=copy.deepcopy(corrected);blocked['items'][0]['kind']='UNRECORDED_TRADE'
                response=post(blocked,new_hash);self.assertEqual(response.status_code,200,response.text);blocked_hash=response.json()['document_sha256']
                state=client.get('/api/strategy-account/cash-classification').json()
                self.assertIsNone(state['profit']);self.assertEqual(state['classified'][0]['classification_state'],'REPAIR_REQUIRED')
                self.assertEqual(post(corrected,blocked_hash).status_code,200)
                self.assertEqual(len(history()),4)
                self.assertEqual(client.get('/api/strategy-account/cash-classification').json()['profit']['profit_amount'],'0')
                self.assertEqual(account.store.read(),original_account)
                self.assertEqual(sha256(account.store.path.read_bytes()).hexdigest(),original_db)
                # A real later account revision invalidates a pending sidecar correction.
                confirm('next-confirm','160');latest=account.store.read();latest_db=sha256(account.store.path.read_bytes()).hexdigest()
                self.assertEqual(post(competitor,new_hash).status_code,409)
                self.assertEqual(len(history()),4);self.assertEqual(account.store.read(),latest)
                self.assertEqual(sha256(account.store.path.read_bytes()).hexdigest(),latest_db)
                print('PASS: stale hash, retry idempotence, history, account revision, corrected profit, blocked repair, untouched account bytes')
if __name__=='__main__':unittest.main()
