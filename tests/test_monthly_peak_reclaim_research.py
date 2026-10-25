import unittest
from backtest.monthly_peak_reclaim_research import MonthlyPeakReclaim
from backtest.monthly_peak_exit_split_adapter import SplitAwareMonthlyPeak
class ReclaimTests(unittest.TestCase):
 def test_exact_threshold_reclaim_and_repeat_exit(self):
  r=MonthlyPeakReclaim()
  for day,price,expected in [('01','100',10),('02','80',0),('03','99.99',0),('04','100',10),('05','79',0)]:
   result,_=r.apply(day='2024-01-'+day,month='2024-01-01',target={'S':10},closes={'S':price});self.assertEqual(result['S'],expected)
 def test_month_reset(self):
  r=MonthlyPeakReclaim();r.apply(day='a',month='a',target={'S':10},closes={'S':100});r.apply(day='b',month='a',target={'S':10},closes={'S':70})
  self.assertEqual(r.apply(day='c',month='c',target={'S':10},closes={'S':70})[0]['S'],10)
 def test_split_does_not_reclaim(self):
  event=dict(date='2024-01-03',security_id='S',type='split',old_shares=1,new_shares=10,source_references=['sealed'])
  r=SplitAwareMonthlyPeak(MonthlyPeakReclaim(),[event]);r.apply(day='2024-01-01',month='2024-01-01',target={'S':10},closes={'S':100});r.apply(day='2024-01-02',month='2024-01-01',target={'S':10},closes={'S':70})
  result,d=r.apply(day='2024-01-03',month='2024-01-01',target={'S':100},closes={'S':9},adjustments=[dict(date='2024-01-03',security_id='S',new_security_id='S')]);self.assertEqual(result['S'],0);self.assertFalse(d['S']['reclaimed'])
