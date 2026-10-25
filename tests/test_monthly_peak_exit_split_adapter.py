import sys
from pathlib import Path
import unittest
from fractions import Fraction as F
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tmp'))
from monthly_close_exit20_20261024_v1 import MonthlyCloseExit
from backtest.monthly_peak_exit_split_adapter import SplitAwareMonthlyPeak

class SplitPeakTests(unittest.TestCase):
 def setup_risk(self,old=1,new=10):
  event=dict(date='2024-08-08',security_id='S',type='split',old_shares=old,new_shares=new,source_references=['sealed-action'])
  risk=SplitAwareMonthlyPeak(MonthlyCloseExit(),[event])
  risk.apply(day='2024-07-31',month='2024-07-31',target={'S':9},closes={'S':'1000'})
  return risk,dict(date='2024-08-08',security_id='S',new_security_id='S',target_after=90)
 def step(self,risk,change,close):
  return risk.apply(day='2024-08-08',month='2024-07-31',target={'S':90},closes={'S':close},adjustments=[change])
 def test_split_no_false_exit_and_exact_threshold(self):
  risk,c=self.setup_risk();result,_=self.step(risk,c,'100');self.assertEqual(result,{'S':90});self.assertEqual(risk.risk.peaks['S'],F(100))
  result,_=risk.apply(day='2024-08-09',month='2024-07-31',target={'S':90},closes={'S':'80'});self.assertEqual(result,{'S':0})
 def test_latch_preserved(self):
  risk,c=self.setup_risk();risk.apply(day='2024-08-07',month='2024-07-31',target={'S':9},closes={'S':'700'})
  self.assertEqual(self.step(risk,c,'110')[0],{'S':0})
 def test_reverse_split(self):
  risk,c=self.setup_risk(10,1);self.assertEqual(self.step(risk,c,'10000')[0],{'S':90})
 def test_duplicate_rejected_without_mutation(self):
  risk,c=self.setup_risk();self.step(risk,c,'100')
  with self.assertRaises(ValueError):self.step(risk,c,'100')
  self.assertEqual(risk.risk.peaks['S'],F(100))
 def test_missing_and_unsupported_evidence_fail_atomically(self):
  for mode in ('missing','identity','refs','ratio'):
   risk,c=self.setup_risk()
   if mode=='missing':risk.actions=[]
   if mode=='identity':c['new_security_id']='T'
   if mode=='refs':risk.actions[0]['source_references']=[]
   if mode=='ratio':risk.actions[0]['new_shares']=0
   with self.assertRaises(ValueError):self.step(risk,c,'100')
   self.assertEqual(risk.risk.peaks['S'],F(1000));self.assertEqual(risk.last_day,'2024-07-31')
