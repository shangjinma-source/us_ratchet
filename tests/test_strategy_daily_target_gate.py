import unittest
from copy import deepcopy

from data.strategy_daily_target_gate import resolve_daily_target


class DailyTargetGateTests(unittest.TestCase):
    def setUp(self):
        self.args = dict(account_id='a', account_revision=2, target_id='t',
                         target_month='2026-10', monthly_quantities={'s': 21},
                         strategy_shares={'s': 14}, available_cash='10000',
                         pending_orders=[], now='2026-10-20T14:00:00+00:00',
                         expected_policy_id='explicit-test-policy')
        self.signal = dict(account_id='a', account_revision=2, target_id='t',
                           policy_id='explicit-test-policy', evidence_id='server-evidence',
                           observed_at='2026-10-19T20:00:00+00:00',
                           available_at='2026-10-19T20:01:00+00:00',
                           valid_from='2026-10-20T13:30:00+00:00',
                           valid_until='2026-10-20T20:00:00+00:00',
                           effective_target_quantities={'s': 14})

    def test_cash_and_monthly_gap_are_not_a_buy_signal(self):
        result = resolve_daily_target(**self.args)
        self.assertEqual(result['status'], 'WAIT_SIGNAL')
        self.assertIsNone(result['effective_target_quantities'])

    def test_hold_buy_sell_have_one_shared_effective_target(self):
        for quantity, action in ((14, 'HOLD'), (21, 'BUY'), (7, 'SELL'), (0, 'SELL')):
            signal = deepcopy(self.signal)
            signal['effective_target_quantities']['s'] = quantity
            result = resolve_daily_target(**self.args, signal=signal)
            self.assertEqual(result['rows'][0]['action'], action)
            self.assertEqual(result['effective_target_quantities']['s'], quantity)
            self.assertFalse(result['execution_allowed'])

    def test_empty_cash_blocks_buy_not_sell(self):
        self.args['available_cash'] = '0'
        for quantity, action in ((21, 'WAIT'), (7, 'SELL')):
            self.signal['effective_target_quantities']['s'] = quantity
            self.assertEqual(resolve_daily_target(**self.args, signal=self.signal)['rows'][0]['action'], action)

    def test_pending_orders_are_not_fills_or_automatically_cancelled(self):
        self.args['pending_orders'] = [dict(account_id='a', scope='STRATEGY',
            security_id='s', side='BUY', remaining_quantity=7)]
        before = deepcopy(self.args)
        self.signal['effective_target_quantities']['s'] = 0
        result = resolve_daily_target(**self.args, signal=self.signal)
        self.assertEqual(result['rows'][0]['action'], 'WAIT')
        self.assertEqual(self.args, before)

    def test_stale_month_or_stale_signal_never_exposes_target(self):
        self.args['target_month'] = '2026-09'
        self.assertEqual(resolve_daily_target(**self.args, signal=self.signal)['status'], 'WAIT_MONTHLY_TARGET')
        self.args['target_month'] = '2026-10'
        self.args['now'] = self.signal['valid_until']
        self.assertIsNone(resolve_daily_target(**self.args, signal=self.signal)['effective_target_quantities'])

    def test_false_revision_future_data_and_missing_security_rejected(self):
        for key, value in [('account_revision', True), ('target_id', 'other'),
                           ('observed_at', '2026-10-21T20:00:00+00:00'),
                           ('effective_target_quantities', {})]:
            signal = deepcopy(self.signal)
            signal[key] = value
            with self.assertRaises(ValueError):
                resolve_daily_target(**self.args, signal=signal)

    def test_ledger_string_revision_and_strict_type_binding(self):
        self.args['account_revision'] = 'fa4a7d' + '0' * 58
        self.signal['account_revision'] = self.args['account_revision']
        self.assertEqual(resolve_daily_target(**self.args, signal=self.signal)['status'], 'DAILY_TARGET_READY')
        self.signal['account_revision'] = 2
        with self.assertRaises(ValueError):
            resolve_daily_target(**self.args, signal=self.signal)
        for invalid in (True, '', '  ', -1):
            self.args['account_revision'] = invalid
            self.signal['account_revision'] = invalid
            with self.assertRaises(ValueError):
                resolve_daily_target(**self.args, signal=self.signal)

    def test_policy_is_explicit_nonempty_string(self):
        for invalid in (True, {}, ['policy'], '   '):
            self.args['expected_policy_id'] = invalid
            with self.assertRaises(ValueError):
                resolve_daily_target(**self.args, signal=self.signal)
        self.args['expected_policy_id'] = None
        self.assertEqual(resolve_daily_target(**self.args, signal=self.signal)['status'],
                         'WAIT_POLICY_RELEASE')


if __name__ == '__main__':
    unittest.main()
