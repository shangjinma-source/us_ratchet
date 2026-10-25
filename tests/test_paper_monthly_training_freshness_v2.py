from datetime import datetime
import unittest
from core.strategy_account_ledger import canonical
from scripts.run_prospective_paper_v2 import require_current_month_training, training_route


class MonthlyTrainingFreshnessTests(unittest.TestCase):
    def test_registered_first_month_seed_then_publication_only(self):
        config=dict(selection_training_manifest={'path':'seed'},selection_monthly_policy={'path':'policy'})
        app=dict(plan=dict(first_session=dict(date='2026-10-26')))
        self.assertEqual(training_route(config,app,'2026-10-26T14:00:00+00:00'),'seed')
        # UTC has crossed month end, but New York has not.
        self.assertEqual(training_route(config,app,'2026-11-01T01:00:00+00:00'),'seed')
        self.assertEqual(training_route(config,app,'2026-11-02T15:00:00+00:00'),'policy')
        self.assertEqual(training_route(config,app,'2027-01-04T15:00:00+00:00'),'policy')
        with self.assertRaisesRegex(ValueError,'BEFORE_INITIAL_MONTH'):
            training_route(config,app,'2026-09-30T14:00:00+00:00')
        with self.assertRaisesRegex(ValueError,'ROUTE_CONFLICT'):
            training_route(dict(config,selection_monthly_registry={'path':'registry'}),app,'2026-10-26T14:00:00+00:00')

    def setUp(self):
        self.calendar=canonical(dict(sessions=[
            dict(date='2026-10-30',close='2026-10-30T20:00:00+00:00'),
            dict(date='2026-11-02',close='2026-11-02T21:00:00+00:00'),
            dict(date='2026-11-30',close='2026-11-30T21:00:00+00:00'),
            dict(date='2026-12-01',close='2026-12-01T21:00:00+00:00')]))

    def check(self,date,close,now):
        require_current_month_training(historical={'decision_date':date},training_closed_at=close,
            calendar_bytes=self.calendar,now=now)

    def test_same_saved_training_cannot_be_reused_next_month(self):
        self.check('2026-10-30','2026-10-30T20:00:00+00:00','2026-11-02T15:00:00+00:00')
        with self.assertRaisesRegex(ValueError,'REFRESH_REQUIRED'):
            self.check('2026-10-30','2026-10-30T20:00:00+00:00','2026-12-01T15:00:00+00:00')
        self.check('2026-11-30','2026-11-30T21:00:00+00:00','2026-12-01T15:00:00+00:00')

    def test_future_missing_calendar_and_invented_close_rejected(self):
        with self.assertRaisesRegex(ValueError,'REFRESH_REQUIRED'):
            self.check('2026-12-01','2026-12-01T21:00:00+00:00','2026-12-01T15:00:00+00:00')
        with self.assertRaisesRegex(ValueError,'CLOSE_NOT_REGISTERED'):
            self.check('2026-11-30','2026-11-30T21:01:00+00:00','2026-12-01T15:00:00+00:00')
        with self.assertRaisesRegex(ValueError,'CALENDAR_COVERAGE'):
            self.check('2026-11-30','2026-11-30T21:00:00+00:00','2027-01-04T15:00:00+00:00')


if __name__=='__main__':unittest.main()
