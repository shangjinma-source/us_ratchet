import unittest
from backtest import ndx_observation_gap_recovery_research as m

class GapReview(unittest.TestCase):
    def classify(self,last,days,clock,start):
        return m.classify_gap_recovery(last_sealed_session=last,common_source_sessions=days,observed_at_utc=clock,prospective_start_date=start)
    def test_weekend_dst_deadline_and_exact_boundary(self):
        a=self.classify('2026-03-05',['2026-03-06'],'2026-03-09T13:29:59+00:00','2026-03-06')
        self.assertEqual(a['timeliness_candidate']['conservative_close_utc'],'2026-03-06T21:00:00+00:00')
        self.assertEqual(a['timeliness_candidate']['conservative_seal_deadline_utc'],'2026-03-09T13:30:00+00:00')
        b=self.classify('2026-03-05',['2026-03-06'],'2026-03-09T13:30:00+00:00','2026-03-06');self.assertIsNone(b['timeliness_candidate'])
        c=self.classify('2026-10-29',['2026-10-30'],'2026-11-02T14:29:59+00:00','2026-10-30')
        self.assertEqual(c['timeliness_candidate']['conservative_seal_deadline_utc'],'2026-11-02T14:30:00+00:00')
    def test_old_gap_never_reclassified_timely_and_future_excluded(self):
        a=self.classify('2026-09-29',['2026-09-30','2026-10-01','2026-10-02'],'2026-10-02T12:00:00+00:00','2026-10-01')
        self.assertEqual(a['pending_classifications'][0]['classification'],'EARLIER_PENDING_ROW_NOT_TIMELY_EVIDENCE')
        self.assertEqual(a['timeliness_candidate']['session'],'2026-10-01')
        self.assertEqual(a['excluded_not_completed_sessions'],['2026-10-02'])
        self.assertTrue(all(not a[k] for k in ('candidate_seal_allowed','canonical_calendar_append_allowed','system_clock_verified','point_in_time_verified')))
    def test_empty_and_invalid_clock_and_weekend(self):
        a=self.classify('2026-10-01',[],'2026-10-02T12:00:00+00:00','2026-10-01');self.assertEqual(a['missed_or_ineligible_row_count'],0);self.assertIsNone(a['timeliness_candidate'])
        for days,clock in [(['2026-10-03'],'2026-10-02T12:00:00+00:00'),([], '2026-10-01T19:59:59+00:00'),([], '2026-10-02T12:00:00')]:
            with self.subTest(days=days,clock=clock),self.assertRaises(ValueError):self.classify('2026-10-01',days,clock,'2026-10-01')

if __name__=='__main__':unittest.main()
