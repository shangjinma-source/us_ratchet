import unittest

from core.strategy_account_ledger import apply_event, create_account, replay


class DirectFillTests(unittest.TestCase):
    def setUp(self):
        self.state = create_account('new-strategy')
        self.fill = dict(event_id='broker-fill-1', kind='DIRECT_FILL',
            security_id='SNDK-SID', side='BUY', quantity=3, price='100', fees='1',
            executed_at='2026-10-16T10:05:00-04:00')

    def apply(self, event):
        self.state, effect = apply_event(self.state, event, expected_revision=self.state['revision'])
        return effect

    def test_fill_without_fake_order_and_manual_cash_reconfirmation(self):
        self.apply(dict(event_id='cash-1',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
        effect = self.apply(self.fill)
        self.assertEqual(self.state['shares'], {'SNDK-SID':3})
        self.assertEqual(self.state['orders'], {})
        self.assertEqual(self.state['cash'], '1000')
        self.assertEqual(effect['cash_delta'], '-301')
        self.assertFalse(self.state['execution_ready'])
        self.apply(dict(event_id='cash-2',kind='CASH_CONFIRM',amount='699',cash_basis='TOTAL_UNINVESTED'))
        self.assertTrue(self.state['execution_ready'])
        self.assertEqual(self.state, replay('new-strategy', [x['payload'] for x in self.state['events']]))
        state, original = apply_event(self.state, self.fill, expected_revision='old')
        self.assertEqual(state, self.state)
        self.assertEqual(original, effect)

    def test_open_order_must_be_linked_instead_of_double_counted(self):
        self.apply(dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
        self.apply(dict(event_id='order',kind='ORDER_OPEN',order_id='o',security_id='SNDK-SID',
            side='BUY',quantity=5,limit_price='100',fee_per_share='0'))
        with self.assertRaisesRegex(ValueError, 'LINK_FILL_TO_EXISTING_ORDER'):
            self.apply(self.fill)

    def test_cannot_sell_legacy_or_accept_ambiguous_time(self):
        with self.assertRaisesRegex(ValueError, 'INSUFFICIENT_STRATEGY_SHARES'):
            self.apply(dict(self.fill, side='SELL'))
        with self.assertRaisesRegex(ValueError, 'AWARE_EXECUTION_TIME_REQUIRED'):
            self.apply(dict(self.fill, executed_at='2026-10-16T10:05:00'))


if __name__ == '__main__':
    unittest.main()
