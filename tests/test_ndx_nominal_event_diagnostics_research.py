import unittest

import pandas as pd

from backtest.ndx_nominal_event_diagnostics_research import diagnose_nominal_events as diagnose


class NominalEventDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.DatetimeIndex(['2022-07-15', '2022-07-18', '2022-07-19'])
        self.prices = pd.DataFrame({'GOOG': [2200., 110., 111.], 'X': [100., 30., 31.]}, index=self.dates)
        self.event = dict(ticker='GOOG', session='2022-07-18', new_shares=20, old_shares=1,
                          source_url='https://example.org/evidence', evidence_sha256='a'*64)

    def call(self, **overrides):
        arguments = dict(prices=self.prices, execution_calendar=self.dates,
                         split_events=[self.event], jump_ratio_threshold=.5)
        return diagnose(**{**arguments, **overrides})

    def test_declared_twenty_and_twenty_one_are_not_silently_corrected(self):
        twenty = self.call()
        twenty_one = self.call(split_events=[{**self.event, 'new_shares': 21}])
        self.assertEqual(len(twenty['jumps']), 2)
        self.assertAlmostEqual(twenty['declared_event_diagnostics'][0]['declared_ratio_adjusted_return'], 0.)
        self.assertAlmostEqual(twenty_one['declared_event_diagnostics'][0]['declared_ratio_adjusted_return'], .05)
        self.assertEqual(twenty_one['declared_event_diagnostics'][0]['declared_event']['new_shares'], 21)
        self.assertFalse(twenty_one['corporate_action_coverage_verified'])
        self.assertFalse(twenty_one['inferred_events_used_for_accounting'])

    def test_unmatched_ordinary_jump_does_not_generate_events(self):
        result = self.call()
        self.assertEqual([r['ticker'] for r in result['unmatched_jumps']], ['X'])
        self.assertIsNone(result['unmatched_jumps'][0]['declared_ratio_adjusted_return'])
        self.assertEqual(result['generated_events'], [])

    def test_no_event_no_jump_does_not_imply_coverage(self):
        result = self.call(split_events=[], jump_ratio_threshold=.01)
        self.assertEqual(result['jumps'], [])
        self.assertEqual(result['declared_event_diagnostics'], [])
        self.assertFalse(result['corporate_action_coverage_verified'])
        result = self.call(jump_ratio_threshold=.01)
        self.assertEqual(len(result['declared_event_diagnostics']), 1)

    def test_invalid_event_identity_dates_duplicates(self):
        for events in ([{**self.event, 'session': '2022-07-15'}],
                       [{**self.event, 'session': '2022-07-16'}],
                       [{**self.event, 'ticker': 'NO'}], [self.event, self.event]):
            with self.assertRaises(ValueError):
                self.call(split_events=events)

    def test_missing_calendar_duplicate_dates_and_nonfinite(self):
        for calendar in (self.dates.delete(1), self.dates[[0, 0, 2]], self.dates[::-1]):
            with self.assertRaises(ValueError):
                self.call(execution_calendar=calendar)
        prices = self.prices.copy()
        prices.iloc[0, 0] = float('nan')
        with self.assertRaises(ValueError):
            self.call(prices=prices)
        for threshold in (True, 0., 1., float('nan')):
            with self.assertRaises(ValueError):
                self.call(jump_ratio_threshold=threshold)


if __name__ == '__main__':
    unittest.main()
