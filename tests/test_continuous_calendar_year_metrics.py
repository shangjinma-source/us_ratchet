import unittest

from backtest.continuous_calendar_year_metrics import calendar_year_metrics


class CalendarYearMetricsTests(unittest.TestCase):
    def report(self, **changes):
        args = dict(opening_date='2023-12-29', opening_equity='100',
                    expected_sessions=['2024-01-02', '2024-12-31', '2025-01-02'],
                    daily_ledger=[dict(date=d, equity=e, external_flow='0') for d,e in
                                  [('2024-01-02','80'), ('2024-12-31','120'), ('2025-01-02','90')]],
                    report_through='2025-01-02')
        args.update(changes)
        return calendar_year_metrics(**args)

    def test_continuous_basis_and_opening_loss(self):
        result = self.report()['years']
        self.assertEqual(result[0]['cumulative_return'], '1/5')
        self.assertEqual(result[0]['maximum_within_year_close_drawdown'], '1/5')
        self.assertEqual(result[1]['opening_equity'], '120')
        self.assertEqual(result[1]['cumulative_return'], '-1/4')
        self.assertEqual(result[1]['scope'], 'UNVERIFIED_CALENDAR_YEAR_SLICE')

    def test_missing_row_and_external_flow_rejected(self):
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE'):
            self.report(daily_ledger=[])
        rows = [dict(date=d, equity='100', external_flow='1') for d in
                ['2024-01-02','2024-12-31','2025-01-02']]
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_FLOW'):
            self.report(daily_ledger=rows)

    def test_midyear_start_cannot_claim_full_year(self):
        result = self.report(opening_date='2024-07-31',
                             expected_sessions=['2024-12-31'],
                             daily_ledger=[dict(date='2024-12-31', equity='120')],
                             report_through='2024-12-31')
        self.assertEqual(result['years'][0]['scope'], 'PARTIAL_YEAR_ON_SUPPLIED_CALENDAR')

    def test_later_report_cutoff_cannot_extend_observed_coverage(self):
        result = self.report(expected_sessions=['2024-01-02'],
                             daily_ledger=[dict(date='2024-01-02', equity='110')],
                             report_through='2024-12-31')
        self.assertEqual(result['last_observed_session'], '2024-01-02')
        self.assertEqual(result['requested_report_through'], '2024-12-31')
        self.assertFalse(result['years'][0]['full_year_coverage_verified'])
        self.assertFalse(result['years'][0]['year_to_date_coverage_verified'])
        self.assertEqual(result['years'][0]['scope'], 'UNVERIFIED_CALENDAR_YEAR_SLICE')

    def test_prior_year_midyear_basis_and_sparse_calendar_are_unverified(self):
        result = self.report(opening_date='2023-07-01',
                             expected_sessions=['2024-01-02', '2024-12-31'],
                             daily_ledger=[dict(date=d, equity='110') for d in
                                           ['2024-01-02', '2024-12-31']],
                             report_through='2024-12-31')
        self.assertEqual(result['years'][0]['scope'], 'UNVERIFIED_CALENDAR_YEAR_SLICE')
        self.assertFalse(result['years'][0]['full_year_coverage_verified'])


if __name__ == '__main__':
    unittest.main()
