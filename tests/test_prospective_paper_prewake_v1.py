from datetime import datetime,timedelta
import unittest
from scripts.run_prospective_paper_prewake_v1 import wait_for_window
class PrewakeTests(unittest.TestCase):
 def run_case(self,start,jump=None):
  now=[datetime.fromisoformat(start)];called=[]
  calendar=dict(calendar=['2026-10-23'],sessions=[dict(date='2026-10-23',open_at='2026-10-23T09:30:00-04:00',close_at='2026-10-23T16:00:00-04:00')])
  def sleep(seconds):now[0]+=timedelta(seconds=jump if jump is not None else seconds)
  def dispatch():called.append(now[0]);return dict(status='TEST_DISPATCH')
  result=wait_for_window(calendar=calendar,start_session='2026-10-23',end_session='2026-10-23',account_initialized=False,clock=lambda:now[0],sleep=sleep,dispatch=dispatch)
  return result,called
 def test_prepares_then_dispatches_at_exact_window(self):
  result,calls=self.run_case('2026-10-23T09:58:00-04:00');self.assertEqual(len(calls),1);self.assertEqual(calls[0].strftime('%H:%M:%S'),'10:00:00')
 def test_sleep_jump_does_not_backfill(self):
  result,calls=self.run_case('2026-10-23T09:59:59-04:00',180);self.assertFalse(calls);self.assertEqual(result['status'],'MISSED_FIRST_WINDOW_REVIEW_REQUIRED')
 def test_too_early_does_not_hold_forever(self):self.assertEqual(self.run_case('2026-10-23T09:00:00-04:00')[0]['status'],'NOT_YET_PREWAKE')
 def test_clock_rollback_rejected(self):
  with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):self.run_case('2026-10-23T09:59:59-04:00',-1)
if __name__=='__main__':unittest.main()
