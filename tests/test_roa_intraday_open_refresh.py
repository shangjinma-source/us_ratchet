import importlib.util,unittest,tempfile
from datetime import datetime,timedelta
from pathlib import Path
from api.strategy_account import StrategyAccountService
from data.roa_execution_lifecycle import RoaExecutionLifecycle
import data.roa_strategy_service as m
class IntradayTests(unittest.TestCase):
 def test_intraday_fixed_targets_and_close_cutoff(self):
  with tempfile.TemporaryDirectory() as directory:
   now=[datetime.fromisoformat('2026-11-06T16:00:00+00:00')]
   account=StrategyAccountService(database_path=Path(directory)/'a.db',account_id='A',resolver=lambda _:None,clock=lambda:now[0]);account.initialize({'event_id':'init'})
   account.append(dict(expected_revision=account.store.read()['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')))
   before=account.store.read();life=RoaExecutionLifecycle(path=Path(directory)/'life.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
   signal=dict(signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'A':'1/10'},signal_id='s',execution_not_before_session='2026-11-06',securities=[dict(security_id='A',ticker='A')])
   def session(day):return dict(open_at=day+'T14:30:00+00:00',close_at=day+'T21:00:00+00:00')
   def quotes(state,sids,day,phase,clock):return dict(opening_session=day,opening_prices={'A':'10'},quote_valid_until=(clock+timedelta(seconds=60)).isoformat(),marks={'A':dict(security_id='A',currency='USD',price_basis='current',price='11',observed_at=clock.isoformat())},limits={'A':dict(security_id='A',price_basis='current',buy='11',sell='11',observed_at=clock.isoformat())})
   admission=dict(enabled=True,strategy_epoch='E',contract_sha256='a'*64,open_window_seconds=900,close_window_seconds=300)
   service=m.RoaStrategyService(account_service=account,lifecycle=life,signal_provider=lambda:signal,session_provider=session,quote_provider=quotes,clock=lambda:now[0],execution_admission=admission)
   self.assertEqual(service.snapshot()['status'],'MISSED')
   service.admission['intraday_open_refresh']=True
   ready=service.snapshot();self.assertEqual(ready['status'],'READY');self.assertTrue(ready['late_execution']);self.assertEqual(ready['target_quantities'],{'A':9});self.assertEqual(ready['rows'][0]['limit_price'],'11');self.assertEqual(account.store.read(),before)
   self.assertEqual(service.snapshot()['target_id'],ready['target_id']);self.assertEqual(sum(bool(e['materialized_revision']) for e in life.read()['events']),1)
   now[0]=datetime.fromisoformat('2026-11-06T20:30:00+00:00')
   later=service.snapshot();self.assertTrue(later['executable']);self.assertEqual(later['target_id'],ready['target_id']);self.assertEqual(later['target_quantities'],ready['target_quantities'])
   # The real cash HTTP route must update affordability in both directions,
   # while preserving the already materialized strategy targets.
   from fastapi import FastAPI
   from fastapi.testclient import TestClient
   from api.roa_strategy import create_router
   from fractions import Fraction
   app=FastAPI();app.include_router(create_router(coordinator=service))
   with TestClient(app) as client:
    for event_id,amount in [('cash-decrease','30'),('cash-increase','2000')]:
     body=dict(expected_revision=account.store.read()['revision'],event=dict(event_id=event_id,kind='CASH_CONFIRM',amount=amount,cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
     response=client.post('/api/strategy-roa/cash-save-and-preview',json=body)
     self.assertEqual(response.status_code,200,response.text)
     value=response.json();self.assertTrue(value['cash_saved']);self.assertEqual(value['status'],'READY')
     self.assertEqual(value['target_quantities'],ready['target_quantities'])
     self.assertEqual(value['account_revision'],account.store.read()['revision'])
     self.assertNotEqual(value['proposal_id'],later['proposal_id'])
     buys=[row for row in value['difference']['new_orders'] if row['side']=='BUY']
     self.assertLessEqual(sum(row['quantity']*Fraction(row['limit_price']) for row in buys),Fraction(amount))
     if amount=='2000':self.assertEqual(sum(row['quantity'] for row in buys),9)
     else:self.assertTrue(value['difference']['waiting_cash'])
     recorded=account.store.read()
     self.assertEqual(client.post('/api/strategy-roa/cash-save-and-preview',json=body).status_code,200)
     self.assertEqual(account.store.read(),recorded)
   before=account.store.read()
   now[0]=datetime.fromisoformat('2026-11-06T20:55:00+00:00');self.assertFalse(service.snapshot()['executable'])
   self.assertEqual(account.store.read(),before)
if __name__=='__main__':unittest.main()
