import unittest
from copy import deepcopy
from scripts.research.rsi2_complete_window_metrics_20261106 import summarize
class MetricsTests(unittest.TestCase):
 def fixture(self):return dict(status='COMPLETE',reason=None,initial_cash='100',daily_ledger=[dict(date='2024-01-02',equity='80'),dict(date='2024-01-03',equity='100'),dict(date='2024-01-04',equity='90')],order_log=[])
 def run_book(self,b):return summarize(b,anchor='2023-12-29',expected_sessions=['2024-01-02','2024-01-03','2024-01-04'])
 def test_close_drawdown_and_censored_recovery(self):
  r=self.run_book(self.fixture());self.assertEqual(r['daily_close_maximum_drawdown'],'1/5');self.assertEqual(r['longest_completed_recovery']['end_date'],'2024-01-03');self.assertTrue(r['longest_completed_recovery']['recovered'])
 def test_reject_blocked_short_duplicate_flow(self):
  for mode in ['blocked','short','duplicate','flow']:
   with self.subTest(mode=mode):
    b=self.fixture()
    if mode=='blocked':b['status']='BLOCKED'
    if mode=='short':b['daily_ledger'].pop()
    if mode=='duplicate':b['daily_ledger'][1]['date']='2024-01-02'
    if mode=='flow':b['daily_ledger'][0]['external_flow']='10'
    with self.assertRaises(ValueError):self.run_book(b)
if __name__=='__main__':unittest.main()
