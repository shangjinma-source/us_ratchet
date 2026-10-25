import json
import unittest

from core.monthly_peak_exit import advance_monthly_exit


class MonthlyPeakExitTests(unittest.TestCase):
    def step(self, state=None, day='2026-10-01', close='100', quantity=13,
             decision='2026-10-01', units='nominal-v1'):
        return advance_monthly_exit(state=state, account_id='isolated-test',
            decision_date=decision, session_date=day, closes={'SNDK': close},
            unit_ids={'SNDK': units}, baseline_targets={'SNDK': quantity})

    def test_exit_survives_restart_refresh_and_new_capital(self):
        start = self.step()['state']
        above = self.step(start, '2026-10-02', '80.01')['state']
        self.assertEqual(above['exited'], [])
        hit = self.step(above, '2026-10-05', '80')
        self.assertEqual(hit['effective_target_quantities']['SNDK'], 0)
        restored = json.loads(json.dumps(hit['state']))
        rebound = self.step(restored, '2026-10-06', '120', quantity=30)
        self.assertEqual(rebound['effective_target_quantities']['SNDK'], 0)
        refreshed = self.step(rebound['state'], '2026-10-06', '120', quantity=40)
        self.assertEqual(refreshed['state'], rebound['state'])
        reset = self.step(refreshed['state'], '2026-11-02', '120', decision='2026-11-02')
        self.assertEqual(reset['effective_target_quantities']['SNDK'], 13)

    def test_changed_units_backwards_and_incomplete_start_rejected(self):
        start = self.step()['state']
        for kwargs in [dict(day='2026-10-02', units='split'),
                       dict(day='2026-09-30'), dict(close='101')]:
            with self.assertRaises(ValueError):
                self.step(start, **kwargs)
        with self.assertRaises(ValueError):
            self.step(day='2026-10-05')

    def test_existing_reduction_is_not_applied_twice(self):
        result = self.step(quantity=6)
        self.assertEqual(result['effective_target_quantities']['SNDK'], 6)


if __name__ == '__main__':
    unittest.main()
