import unittest,tempfile
from pathlib import Path
from data.roa_execution_lifecycle import RoaExecutionLifecycle
class LifecycleTests(unittest.TestCase):
 def test_open_once_and_missed_no_implicit_fill(self):
  with tempfile.TemporaryDirectory() as directory:
   life=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='a',strategy_epoch='e',contract_sha256='a'*64)
   signal=dict(signal_id='s',signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'A':'1/10'})
   args=dict(signal=signal,session='2026-11-06',open_at='2026-11-06T14:30:00+00:00',open_until='2026-11-06T14:31:00+00:00',close_at='2026-11-06T20:59:00+00:00',close_until='2026-11-06T21:00:00+00:00')
   state=life.plan(**args);self.assertEqual(len(state['events']),1)
   self.assertEqual(life.plan(**args),state)
   self.assertEqual(life.event_view(now='2026-11-06T14:00:00+00:00')['status'],'PENDING_OPEN')
   account=dict(account_id='a',cash_confirmation_valid=True,shares={'OLD':2},total_uninvested_cash='1000',revision='r')
   eid=state['events'][0]['event_id']
   with self.assertRaises(ValueError):life.materialize_open(event_id=eid,account=account,opening_prices={'A':'10','OLD':'50'},now='2026-11-06T14:00:00+00:00')
   event=life.materialize_open(event_id=eid,account=account,opening_prices={'A':'10','OLD':'50'},now='2026-11-06T14:30:00+00:00')
   self.assertEqual(event['targets'],{'A':10})
   account['total_uninvested_cash']='2000'
   again=life.materialize_open(event_id=eid,account=account,opening_prices={'A':'20','OLD':'50'},now='2026-11-06T14:30:30+00:00')
   self.assertEqual(again['targets'],{'A':10})
   self.assertEqual(life.event_view(now='2026-11-06T15:00:00+00:00')['status'],'MISSED')
   self.assertEqual(account['shares'],{'OLD':2})
 def test_close_uses_actual_shares_and_is_idempotent(self):
  with tempfile.TemporaryDirectory() as directory:
   life=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='a',strategy_epoch='e',contract_sha256='a'*64)
   life.close_observation(session='2026-11-05',shares={'A':5},closing_prices={'A':'100'})
   state=life.close_observation(session='2026-11-06',shares={'A':5},closing_prices={'A':'79'})
   self.assertEqual(state['pending'],['A']);self.assertEqual(state['peaks'],{'A':'100'})
   self.assertEqual(life.close_observation(session='2026-11-06',shares={'A':5},closing_prices={'A':'79'}),state)
   with self.assertRaises(ValueError):life.close_observation(session='2026-11-06',shares={},closing_prices={})
if __name__=='__main__':unittest.main()
