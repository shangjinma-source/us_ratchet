import importlib.util,unittest,tempfile
from datetime import datetime,timedelta
from pathlib import Path
from api.strategy_account import StrategyAccountService
from data.roa_execution_lifecycle import RoaExecutionLifecycle
import data.roa_strategy_service as m
class LateTests(unittest.TestCase):
 def test_late_once_cash_and_expiry(self):
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
   service.admission['late_open_session']='2026-11-06'
   ready=service.snapshot();self.assertEqual(ready['status'],'READY');self.assertTrue(ready['late_execution']);self.assertEqual(ready['target_quantities'],{'A':9});self.assertEqual(ready['rows'][0]['limit_price'],'11');self.assertEqual(account.store.read(),before)
   self.assertEqual(service.snapshot()['target_id'],ready['target_id']);self.assertEqual(sum(bool(e['materialized_revision']) for e in life.read()['events']),1)
   now[0]=datetime.fromisoformat('2026-11-06T20:55:00+00:00');self.assertFalse(service.snapshot()['executable'])
   service.admission['late_open_session']='2026-11-07';self.assertFalse(service.snapshot()['executable'])
if __name__=='__main__':unittest.main()
