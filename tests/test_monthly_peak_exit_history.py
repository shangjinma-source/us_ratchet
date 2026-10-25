from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.monthly_peak_exit_history import monthly_exit_observations
from data.monthly_peak_exit_store import MonthlyPeakExitStore


class MonthlyHistoryTests(unittest.TestCase):
    def inputs(self):
        dates = ['2026-10-01', '2026-10-02', '2026-10-05']
        times = {day: day + 'T20:00:00+00:00' for day in dates}
        return dict(base_target=dict(monthly_decision_date=dates[0],
            quantities={'A': 10}, price_units={'A': 'nominal'}, origin_reference='test'),
            signal_date=dates[-1], observed_at=dates[-1]+'T21:00:00+00:00',
            session_dates=dates, session_close_times=dict(closes=times, review_reference='test'),
            histories={'A': dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                unit_asof=dates[-1], currency='USD', basis_id='nominal', review_reference='test'),
                source_reference='test', closes=[dict(date=day, completed_at=times[day], close=price)
                    for day, price in zip(dates, ['100', '80', '110'])])})

    def test_full_window_catches_exit_before_rebound(self):
        observations = monthly_exit_observations(**self.inputs())
        with TemporaryDirectory() as directory:
            result = MonthlyPeakExitStore(Path(directory)/'risk.sqlite').advance(
                account_id='test', expected_previous_session=None,
                observations=observations, baseline_targets={'A': 10})
            self.assertEqual(result['effective_target_quantities'], {'A': 0})

    def test_next_morning_full_window_repeat_after_restart(self):
        inputs = self.inputs()
        inputs['observed_at'] = '2026-10-06T14:00:00+00:00'
        observations = monthly_exit_observations(**inputs)
        with TemporaryDirectory() as directory:
            path = Path(directory)/'risk.sqlite'
            for previous in (None, '2026-10-05'):
                result = MonthlyPeakExitStore(path).advance(account_id='test',
                    expected_previous_session=previous, observations=observations,
                    baseline_targets={'A': 10})
                self.assertEqual(result['effective_target_quantities'], {'A': 0})

    def test_missing_session_and_future_close_rejected(self):
        original = self.inputs()
        missing = deepcopy(original)
        del missing['histories']['A']['closes'][1]
        future = deepcopy(original)
        future['histories']['A']['closes'][-1]['completed_at'] = '2026-10-06T20:00:00+00:00'
        for inputs in [missing, future]:
            with self.assertRaises(ValueError):
                monthly_exit_observations(**inputs)

    def test_zero_target_keeps_exit_history_for_later_cash_update(self):
        inputs = self.inputs()
        inputs['base_target']['quantities']['A'] = 0
        observations = monthly_exit_observations(**inputs)
        with TemporaryDirectory() as directory:
            store = MonthlyPeakExitStore(Path(directory)/'risk.sqlite')
            result = store.advance(account_id='test', expected_previous_session=None,
                observations=observations, baseline_targets={'A': 0})
            self.assertEqual(result['state']['exited'], ['A'])
            result = store.advance(account_id='test', expected_previous_session='2026-10-05',
                observations=observations[-1:], baseline_targets={'A': 20})
            self.assertEqual(result['effective_target_quantities'], {'A': 0})


if __name__ == '__main__':
    unittest.main()
