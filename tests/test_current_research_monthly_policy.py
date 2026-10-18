import unittest

from data.current_research_monthly_policy import route_monthly_research_policy


class MonthlyPolicyTests(unittest.TestCase):
    def route(self, decision, active, month, calendar=None):
        return route_monthly_research_policy(decision_date=decision, active_date=active,
            current_target_month=month, calendar=calendar if calendar is not None else [decision,active])

    def test_cross_year_reselect_and_already_selected_no_repeat(self):
        result=self.route('2026-12-31','2027-01-04','2026-12')
        self.assertEqual((result['action'],result['target_month'],result['reason']),
                         ('RESELECT','2027-01','MONTH_BOUNDARY_RESELECT'))
        self.assertEqual(self.route('2026-12-31','2027-01-04','2027-01')['action'],'ROLL')

    def test_monthly_catchup_once_after_successful_month_commit(self):
        result=self.route('2026-11-04','2026-11-05','2026-10')
        self.assertEqual(result['reason'],'MISSED_MONTH_BOUNDARY_CATCH_UP')
        self.assertEqual(result['action'],'RESELECT')
        self.assertEqual(self.route('2026-11-05','2026-11-06',result['target_month'])['action'],'ROLL')
        # Failed selection must not advance the month: retry stays explicit.
        self.assertEqual(self.route('2026-11-05','2026-11-06','2026-10')['action'],'RESELECT')

    def test_monthly_roll_does_not_assert_complete_exchange_calendar(self):
        result=self.route('2026-10-13','2026-10-14','2026-10')
        self.assertEqual(result['action'],'ROLL')
        self.assertFalse(result['calendar_completeness_verified'])
        self.assertEqual(result['search_calls'],0)
        self.assertFalse(result['state_changed'])

    def test_bad_dates_months_and_nonadjacent_calendar_rejected(self):
        for month in (None,'2026-1','2026-13','0000-01','2026-11'):
            with self.subTest(month=month),self.assertRaises(ValueError):
                self.route('2026-10-13','2026-10-14',month)
        for calendar in ([],['2026-10-14','2026-10-13'],['2026-10-13','2026-10-13','2026-10-14'],
                         ['2026-10-12','2026-10-14'],['2026-10-13','2026-10-14','2026-10-15']):
            with self.subTest(calendar=calendar),self.assertRaises(ValueError):
                self.route('2026-10-13','2026-10-15','2026-10',calendar)
        with self.assertRaises(ValueError):self.route('2026-02-30','2026-03-02','2026-02')


if __name__=='__main__':unittest.main()
