import unittest,tempfile
from hashlib import sha256
from datetime import datetime,timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import StrategyAccountService,create_router as account_router
from api.roa_strategy import create_router
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_strategy_service import RoaStrategyService
class HttpTests(unittest.TestCase):
 def test_pending_cash_open_freeze_and_missed(self):
  with tempfile.TemporaryDirectory() as directory:
   now=[datetime.fromisoformat('2026-11-06T14:00:00+00:00')]
   account=StrategyAccountService(database_path=Path(directory)/'a.sqlite3',account_id='test',resolver=lambda _:None,clock=lambda:now[0])
   revision=account.initialize({'event_id':'init'})['account']['revision']
   life=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='test',strategy_epoch='e',contract_sha256='a'*64)
   signal=dict(signal_id='s',signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'A':'1/10'},execution_not_before_session='2026-11-06',securities=[dict(security_id='A',ticker='A')])
   def session(day):return dict(open_at=day+'T14:30:00+00:00',close_at=day+'T21:00:00+00:00')
   calls=[]
   def quotes(state,sids,day,phase,clock):
    calls.append(day)
    return dict(opening_session=day,opening_prices={'A':'10'},quote_valid_until=(clock+timedelta(seconds=120)).isoformat(),marks={'A':dict(security_id='A',currency='USD',price_basis='current',price='10',observed_at=clock.isoformat())},limits={'A':dict(security_id='A',price_basis='current',buy='10',sell='10',observed_at=clock.isoformat())})
   service=RoaStrategyService(account_service=account,lifecycle=life,signal_provider=lambda:signal,session_provider=session,quote_provider=quotes,clock=lambda:now[0],execution_admission=dict(enabled=True,strategy_epoch='e',contract_sha256='a'*64,open_window_seconds=300,close_window_seconds=300))
   app=FastAPI();app.include_router(create_router(coordinator=service))
   app.include_router(account_router(database_path=Path(directory)/'a.sqlite3',account_id='test',clock=lambda:now[0],
    resolver=lambda ticker:dict(ticker=ticker,security_id='A',source_references=['synthetic'],source_hashes={'synthetic':'b'*64})))
   with TestClient(app) as client:
    for asset in ('strategy_roa_controller.js','strategy_roa_mount.js'):
     web=Path(__file__).resolve().parents[1]/'web'
     page=(web/'index.html').read_text(encoding='utf-8')
     version=sha256((web/asset).read_bytes()).hexdigest()[:12]
     self.assertIn('/static/'+asset+'?v='+version,page)
     script=client.get('/static/'+asset+'?v='+version)
     self.assertEqual(script.status_code,200)
     self.assertIn('application/javascript',script.headers['content-type'])
     self.assertEqual(script.headers['cache-control'],'no-cache')
     self.assertEqual(script.content,(Path(__file__).resolve().parents[1]/'web'/asset).read_bytes())
    config=client.get('/api/strategy-roa/config').json();self.assertEqual(config['strategy_epoch'],'e')
    plan=client.get('/api/strategy-roa/snapshot').json();self.assertEqual(plan['status'],'PENDING_OPEN');self.assertTrue(plan['advice_ready']);self.assertFalse(plan['executable']);self.assertIsNone(plan['rows'][0]['quantity']);self.assertEqual(calls,[])
    body=dict(expected_revision=revision,event=dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED'))
    saved=client.post('/api/strategy-roa/cash-save-and-preview',json=body).json();self.assertTrue(saved['cash_saved']);self.assertEqual(saved['status'],'PENDING_OPEN')
    ledger=account.store.read();now[0]=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
    ready=client.post('/api/strategy-roa/advice-retry',json={}).json();self.assertIsNone(ready['cash_saved']);self.assertEqual(ready['status'],'READY',ready);self.assertTrue(ready['executable']);self.assertEqual(ready['target_quantities'],{'A':9});self.assertEqual(ready['rows'][0]['quantity'],9);self.assertEqual(len(ready['proposal_id']),64)
    self.assertEqual(ready['rows'][0]['price_context']['latest_price'],'10')
    self.assertEqual(ready['rows'][0]['price_context']['latest_at'],now[0].isoformat())
    self.assertIsNone(ready['rows'][0]['price_context']['reference_price'])
    self.assertEqual(account.store.read(),ledger)
    self.assertTrue(client.post('/api/strategy-roa/cash-status',json=body).json()['cash_saved'])
    fill=dict(expected_revision=ledger['revision'],event=dict(event_id='actual-test-fill',kind='DIRECT_FILL',ticker='A',side='BUY',quantity=4,price='10',fees='0',executed_at=now[0].isoformat()))
    recorded=client.post('/api/strategy-account/events',json=fill)
    self.assertEqual(recorded.status_code,200,recorded.text)
    revision=recorded.json()['account']['revision']
    confirmed=client.post('/api/strategy-roa/cash-save-and-preview',json=dict(expected_revision=revision,event=dict(kind='CASH_CONFIRM',event_id='cash-after-fill',amount='960',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))).json()
    self.assertEqual(confirmed['target_quantities'],{'A':9})
    self.assertEqual(confirmed['rows'][0]['held'],4)
    self.assertEqual(confirmed['rows'][0]['quantity'],5)
    self.assertEqual(confirmed['account']['available_cash'],'960')
    ledger=account.store.read()
    retried=client.post('/api/strategy-roa/advice-retry',json={}).json()
    self.assertEqual(retried['rows'][0]['quantity'],5)
    self.assertEqual(account.store.read(),ledger)
    now[0]=datetime.fromisoformat('2026-11-06T15:00:00+00:00')
    missed=client.get('/api/strategy-roa/snapshot').json();self.assertEqual(missed['status'],'MISSED');self.assertFalse(missed['executable']);self.assertIsNone(missed['rows'][0]['quantity'])
    self.assertIsNone(missed['rows'][0]['price_context'])
    self.assertEqual(account.store.read(),ledger)
    life.close_observation(session='2026-11-06',shares={'A':4},closing_prices={'A':'10'})
    original_signal=dict(signal)
    signal.update(signal_id='next',signal_date='2026-11-06',execution_not_before_session='2026-11-09')
    now[0]=datetime.fromisoformat('2026-11-07T02:00:00+00:00')
    weekend=client.get('/api/strategy-roa/snapshot').json()
    self.assertEqual(weekend['status'],'MISSED')
    self.assertEqual(weekend['execution_session'],'2026-11-06')
    self.assertEqual(weekend['signal_date'],'2026-11-05')
    self.assertEqual(weekend['market_signal']['execution_session'],'2026-11-09')
    self.assertEqual(weekend['execution_event']['session'],'2026-11-06')
    self.assertEqual(weekend['standard_open_valid_until'],'2026-11-06T14:35:00+00:00')
    self.assertFalse(weekend['executable']);self.assertFalse(weekend['late_execution'])
    self.assertEqual(account.store.read(),ledger)
    signal.clear();signal.update(original_signal)
    now[0]=datetime.fromisoformat('2026-11-06T15:00:00+00:00')
    remainder=dict(expected_revision=ledger['revision'],event=dict(event_id='remaining-test-fill',kind='DIRECT_FILL',ticker='A',side='BUY',quantity=5,price='10',fees='0',executed_at='2026-11-06T14:32:00+00:00'))
    recorded=client.post('/api/strategy-account/events',json=remainder)
    self.assertEqual(recorded.status_code,200,recorded.text)
    revision=recorded.json()['account']['revision']
    complete=client.post('/api/strategy-roa/cash-save-and-preview',json=dict(expected_revision=revision,event=dict(kind='CASH_CONFIRM',event_id='cash-complete',amount='910',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))).json()
    self.assertEqual(complete['status'],'HOLD',complete)
    self.assertFalse(complete['executable'])
    self.assertEqual(complete['rows'][0]['held'],9)
    self.assertIsNone(complete['rows'][0]['quantity'])
if __name__=='__main__':unittest.main()
