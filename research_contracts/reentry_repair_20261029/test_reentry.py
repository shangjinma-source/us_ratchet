import unittest
from reentry_repair import ReentryRepair

def result(day,epoch='2024-01-01',exited=False,buy=False,sid='S'):
 return dict(status='READY',risk_overlay={'state':{'decision_date':epoch,'session_date':day,'exited':[sid] if exited else []}},orders=[dict(security_id=sid,side='BUY' if buy else 'SELL',quantity=4)])
class Tests(unittest.TestCase):
 def setup_engine(self,closes):
  def coverage(lock,end,buys):
   if 'S' not in buys:return {'status':'NOT_CURRENT_BUY'}
   return dict(status='VERIFIED',current_security_id='S',completed_rows=[dict(date=d,security_id='S',close=p) for d,p in sorted(closes.items()) if lock['exit_date']<d<=end])
  return ReentryRepair(close_prices={'S':closes},verify_interval=coverage)
 def call(self,e,r,day,h=0):return e.adjust(r,state={'shares':{'S':h}},decision_date=day,active_date='2099-01-01')
 def test_below_blocks_and_equality_repairs(self):
  e=self.setup_engine({'2024-01-30':'10','2024-02-01':'9','2024-02-02':'10'})
  self.call(e,result('2024-01-30',exited=True),'2024-01-30',4)
  self.assertEqual(self.call(e,result('2024-02-01',buy=True),'2024-02-01')['orders'],[])
  self.assertEqual(len(self.call(e,result('2024-02-02',buy=True),'2024-02-02')['orders']),1)
 def test_intermediate_recovery_then_fall_still_released(self):
  e=self.setup_engine({'2024-01-30':'10','2024-01-31':'11','2024-02-01':'8'})
  self.call(e,result('2024-01-30',exited=True),'2024-01-30',4)
  self.assertEqual(len(self.call(e,result('2024-02-01',buy=True),'2024-02-01')['orders']),1)
  self.assertFalse(e.locks)
 def test_zero_position_exit_does_not_reset_existing_reference(self):
  e=self.setup_engine({'2024-01-30':'10','2024-02-01':'8'})
  self.call(e,result('2024-01-30',exited=True),'2024-01-30',4)
  self.call(e,result('2024-02-01',epoch='2024-02-01',exited=True),'2024-02-01',0)
  self.assertEqual(e.locks['S']['reference_price'],'10')
 def test_exit_intent_locks_without_fill_and_same_day_not_repair(self):
  e=self.setup_engine({'2024-01-30':'10'})
  out=self.call(e,result('2024-01-30',exited=True),'2024-01-30',4)
  self.assertEqual(out['orders'][0]['quantity'],4);self.assertIn('S',e.locks)
 def test_coverage_missing_fails_not_abstain(self):
  e=ReentryRepair(close_prices={'S':{'2024-01-30':'10'}},verify_interval=lambda *a:{'status':'BLOCKED'})
  self.call(e,result('2024-01-30',exited=True),'2024-01-30',4)
  with self.assertRaisesRegex(ValueError,'COVERAGE'):self.call(e,result('2024-02-01',buy=True),'2024-02-01')
 def test_split_before_compare(self):
  def coverage(*a):return dict(status='VERIFIED',current_security_id='N',completed_rows=[dict(date='2024-10-01',security_id='N',close='10',conversion={'old_sid':'S','new_sid':'N','ratio':'10','kind':'REVIEWED_INTEGER_SPLIT'})])
  e=ReentryRepair(close_prices={'S':{'2024-09-30':'100'}},verify_interval=coverage)
  self.call(e,result('2024-09-30',exited=True),'2024-09-30',4)
  r=result('2024-10-01',buy=True,sid='N');self.assertEqual(len(self.call(e,r,'2024-10-01')['orders']),1);self.assertFalse(e.locks)
if __name__=='__main__':unittest.main()
