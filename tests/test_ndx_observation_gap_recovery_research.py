import unittest
from backtest.ndx_observation_gap_recovery_research import classify_gap_recovery


class GapRecoveryTests(unittest.TestCase):
    def run_case(self,clock,dates=None):
        return classify_gap_recovery(last_sealed_session='2026-09-24',
            common_source_sessions=dates if dates is not None else ['2026-09-25','2026-09-28','2026-09-29','2026-09-30','2026-10-01'],
            observed_at_utc=clock,prospective_start_date='2026-10-01')

    def test_missed_deadline_never_backfills_five_rows(self):
        result=self.run_case('2026-10-02T14:00:00+00:00')
        self.assertEqual(result['missed_or_ineligible_row_count'],5)
        self.assertIsNone(result['timeliness_candidate'])
        self.assertTrue(all(not r['decision_eligible'] for r in result['pending_classifications']))

    def test_only_latest_completed_can_be_timing_candidate(self):
        result=self.run_case('2026-10-02T20:01:00+00:00',['2026-09-25','2026-10-01','2026-10-02'])
        self.assertEqual(result['timeliness_candidate']['session'],'2026-10-02')
        self.assertEqual(result['missed_or_ineligible_row_count'],2)
        self.assertEqual(result['timeliness_candidate']['conservative_seal_deadline_utc'],'2026-10-05T13:30:00+00:00')
        self.assertFalse(result['candidate_seal_allowed'])
        self.assertFalse(result['system_clock_verified'])

    def test_in_progress_excluded_and_deadline_is_strict(self):
        dates=['2026-10-01','2026-10-02']
        before=self.run_case('2026-10-02T13:29:59+00:00',dates)
        self.assertEqual(before['timeliness_candidate']['session'],'2026-10-01')
        after=self.run_case('2026-10-02T13:30:00+00:00',dates)
        self.assertIsNone(after['timeliness_candidate'])
        self.assertEqual(after['excluded_not_completed_sessions'],['2026-10-02'])

    def test_reject_naive_clock_duplicates_and_old_prefix(self):
        for clock,dates in [('2026-10-02T14:00:00',[]),('2026-10-02T14:00:00+00:00',['2026-10-01']*2),
                            ('2026-10-02T14:00:00+00:00',['2026-09-24'])]:
            with self.subTest(clock=clock,dates=dates),self.assertRaises(ValueError):
                self.run_case(clock,dates)


if __name__=='__main__':
    unittest.main()
