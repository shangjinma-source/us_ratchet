import unittest
from core.hsbc_trade25_commission import quote_commission


class CommissionTests(unittest.TestCase):
    def quote(self, **changes):
        arguments = dict(executed_at='2026-10-26T14:00:00Z', turnover_month='2026-10',
            prior_turnover_hkd='180000', gross_usd='10000', quantity=100,
            execution_hkd_per_usd='8', charging_unit_confirmed=True)
        arguments.update(changes)
        return quote_commission(**arguments)

    def test_official_crossing_example_and_next_trade(self):
        first = self.quote()
        self.assertEqual(first['after_turnover_hkd'], '260000')
        self.assertEqual(first['commission_usd'], '0')
        self.assertEqual(self.quote(prior_turnover_hkd=first['after_turnover_hkd'])['commission_usd'], '18')

    def test_share_tiers(self):
        for quantity, expected in [(1, '18'), (1000, '18'), (1001, '3603/200'), (2000, '33')]:
            self.assertEqual(self.quote(prior_turnover_hkd='260000', quantity=quantity)['commission_usd'], expected)

    def test_unknown_is_not_free(self):
        self.assertIsNone(self.quote(charging_unit_confirmed=False)['commission_usd'])
        self.assertIsNone(self.quote(prior_turnover_hkd='250000')['commission_usd'])

    def test_hong_kong_month_boundary(self):
        self.assertEqual(self.quote(executed_at='2026-10-31T15:59:59Z')['month'], '2026-10')
        with self.assertRaisesRegex(ValueError, 'EXECUTION_MONTH'):
            self.quote(executed_at='2026-10-31T16:00:00Z')
        self.assertEqual(self.quote(executed_at='2026-10-31T16:00:00Z', turnover_month='2026-11', prior_turnover_hkd='0')['commission_usd'], '0')

    def test_invalid_inputs(self):
        for changes in [dict(quantity=True), dict(quantity=0), dict(execution_hkd_per_usd='0'),
                        dict(prior_turnover_hkd='-1'), dict(gross_usd=10.1),
                        dict(executed_at='2026-10-26T14:00:00')]:
            with self.assertRaises(ValueError):
                self.quote(**changes)


if __name__ == '__main__':
    unittest.main()
