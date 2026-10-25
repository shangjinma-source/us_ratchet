import unittest

from data.strategy_prospective_paper_cap_daily_v2 import account_targets


class AccountDomainTests(unittest.TestCase):
    def test_rotation_keeps_old_holding_as_zero_target(self):
        self.assertEqual(account_targets({'NEW': 10}, {'OLD': 0, 'NEW': 20}),
                         {'OLD': 0, 'NEW': 10})

    def test_exited_history_does_not_reintroduce_closed_position(self):
        risk = {'OLD': 0, 'NEW': 10}
        self.assertEqual(account_targets(risk, {'NEW': 20}), {'NEW': 10})
        self.assertEqual(risk, {'OLD': 0, 'NEW': 10})

    def test_all_cash_retains_held_and_pending_names(self):
        self.assertEqual(account_targets({}, {'HELD': 0, 'PENDING': 0}),
                         {'HELD': 0, 'PENDING': 0})

    def test_unknown_nonzero_risk_target_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, 'PAPER_CAP_ACCOUNT_DOMAIN'):
            account_targets({'UNKNOWN': 1}, {})


if __name__ == '__main__':
    unittest.main()
