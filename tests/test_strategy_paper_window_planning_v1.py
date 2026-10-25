from datetime import datetime
import unittest
from data.strategy_paper_window_planning_v1 import planning_state

class WindowPlanTests(unittest.TestCase):
    def run_at(self,at,initialized=False,start='2026-10-23'):
        dates=['2026-10-23','2026-10-26','2026-11-02']
        calendar=dict(calendar=dates,sessions=[dict(date=d,open_at=d+'T09:30:00'+('-05:00' if d=='2026-11-02' else '-04:00'),close_at=d+'T16:00:00'+('-05:00' if d=='2026-11-02' else '-04:00')) for d in dates])
        return planning_state(now=datetime.fromisoformat(at),calendar=calendar,start_session=start,end_session=dates[-1],account_initialized=initialized)
    def test_prewake_does_not_dispatch(self):self.assertEqual(self.run_at('2026-10-23T09:58:00-04:00')['wait_seconds'],120)
    def test_exact_window(self):
        for at in ['10:00:00','10:00:59.999999']:self.assertTrue(self.run_at('2026-10-23T'+at+'-04:00')['dispatch'])
        self.assertFalse(self.run_at('2026-10-23T10:01:00-04:00')['dispatch'])
    def test_sleep_resumption_cannot_backfill(self):
        self.assertEqual(self.run_at('2026-10-23T10:02:37-04:00')['status'],'MISSED_FIRST_WINDOW_REVIEW_REQUIRED')
        self.assertEqual(self.run_at('2026-10-26T10:00:00-04:00')['status'],'MISSED_REGISTERED_START_REVIEW_REQUIRED')
    def test_initialized_daily_miss_distinct(self):self.assertEqual(self.run_at('2026-10-26T11:00:00-04:00',True)['status'],'MISSED_DAILY_WINDOW_NO_NEW_DECISION')
    def test_dst_uses_ny_not_fixed_beijing_hour(self):
        self.assertTrue(self.run_at('2026-11-02T23:00:00+08:00',True)['dispatch'])
        self.assertFalse(self.run_at('2026-11-02T22:00:00+08:00',True)['dispatch'])
    def test_weekend_wait(self):self.assertEqual(self.run_at('2026-10-24T10:00:00-04:00',True)['status'],'WAITING_SESSION')

if __name__=='__main__':unittest.main()
