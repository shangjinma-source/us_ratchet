from copy import deepcopy
import unittest

from backtest.current_quantity_v2_annual_clock import build_observation_clock


def session(day, offset='-04:00', close='16:00:00', opened='09:30:00'):
    return dict(date=day, timezone='America/New_York',
                open_at=f'{day}T{opened}{offset}', close_at=f'{day}T{close}{offset}')


class AnnualClockTests(unittest.TestCase):
    def test_both_dst_transitions_and_one_observation_per_supplied_day(self):
        entries = [session('2026-03-06', '-05:00'), session('2026-03-09'),
                   session('2026-10-30'), session('2026-11-02', '-05:00')]
        before = deepcopy(entries)
        result = build_observation_clock(entries)
        self.assertEqual([row['observation_at'] for row in result], [
            '2026-03-06T15:00:00+00:00', '2026-03-09T14:00:00+00:00',
            '2026-10-30T14:00:00+00:00', '2026-11-02T15:00:00+00:00'])
        self.assertEqual(entries, before)
        self.assertEqual(len(result), len(entries))

    def test_early_close_and_explicit_utc_boundaries(self):
        entry = session('2026-11-27', '-05:00', '13:00:00')
        result = build_observation_clock([entry])[0]
        self.assertEqual(result['session_close'], '2026-11-27T18:00:00+00:00')
        self.assertEqual(result['order_time_in_force'], 'DAY')
        entry.update(open_at='2026-11-27T14:30:00Z', close_at='2026-11-27T18:00:00Z')
        self.assertEqual(build_observation_clock([entry])[0], result)

    def test_observation_requires_open_session_and_close_is_exclusive(self):
        for entry in [session('2026-10-15', opened='10:01:00'),
                      session('2026-10-15', close='10:00:00')]:
            with self.assertRaisesRegex(ValueError, 'OBSERVATION_OUTSIDE_SESSION'):
                build_observation_clock([entry])
        self.assertEqual(len(build_observation_clock([session('2026-10-15', opened='10:00:00')])), 1)

    def test_invalid_calendar_order_and_boundaries(self):
        first, second = session('2026-10-14'), session('2026-10-15')
        for entries in [[second, first], [first, first]]:
            with self.assertRaisesRegex(ValueError, 'ORDERED_UNIQUE_SESSIONS_REQUIRED'):
                build_observation_clock(entries)
        for changes in [dict(open_at='2026-10-14T09:30:00'),
                        dict(close_at='2026-10-15T16:00:00-04:00'),
                        dict(close_at='2026-10-14T08:00:00-04:00'),
                        dict(timezone='UTC'), dict(date='20261014')]:
            with self.assertRaises(ValueError):
                build_observation_clock([{**first, **changes}])
        for entries in [[], (), [{}], [None]]:
            with self.assertRaises(ValueError):
                build_observation_clock(entries)


if __name__ == '__main__':
    unittest.main()
