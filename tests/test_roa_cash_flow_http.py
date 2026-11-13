from datetime import datetime,timezone
from hashlib import sha256
import json
import sqlite3
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
                before_records=addon.records()
                payload=json.dumps(dict(expected_revision=saved['revision'],document=doc))
                duplicated=payload.replace('"net_change": "60"','"net_change": "999", "net_change": "60"')
                for malformed in [duplicated,'[]','null','{"document": NaN}', ' '*16385]:
                    rejected=client.post('/api/strategy-account/cash-classification',content=malformed)
                    self.assertEqual(rejected.status_code,422,rejected.text)
                    self.assertEqual(addon.records(),before_records)
                    self.assertEqual(account.store.read(),saved)
                self.assertEqual(client.post('/api/strategy-account/cash-classification?unexpected=1',content=payload).status_code,422)
                for _ in range(2):self.assertEqual(client.post('/api/strategy-account/cash-classification',json=dict(expected_revision=saved['revision'],document=doc)).status_code,200)
                self.assertEqual(client.get('/api/strategy-account/cash-classification/profit').json()['profit']['profit_amount'],'10');self.assertEqual(account.store.read(),saved)
                # GET must not use write transaction/save validation.
                addon.store.save=lambda **_: (_ for _ in ()).throw(AssertionError('GET called save'))
                self.assertEqual(client.get('/api/strategy-account/cash-classification').status_code,200)
                original=account.valuation
                def concurrent_value():
                    value=original();errors=[]
                    def writer():
                        try:confirm('concurrent','160')
                        except BaseException as error:errors.append(error)
                    thread=Thread(target=writer);thread.start();thread.join(2)
                    self.assertFalse(thread.is_alive(),'valuation held account read lock');self.assertEqual(errors,[])
                    return value
                account.valuation=concurrent_value
                self.assertEqual(client.get('/api/strategy-account/cash-classification/profit').status_code,409)
                connection=sqlite3.connect(account.store.path);connection.execute('PRAGMA journal_mode=WAL');connection.close()
                with self.assertRaisesRegex(ValueError,'JOURNAL_MODE'):addon.current()
                paths=[r.path for r in app.routes];self.assertNotIn('/stage/cash-save',paths)
if __name__=='__main__':unittest.main()
