import unittest
from backtest.return_priority_cash_stock_entitlements import convert_cash_stock_entitlement, value_cash_stock_entitlements


def fixture(held=10):
    state = dict(cash='100', shares={'anss': held, 'snps': 7})
    event = dict(event_id='closing', old_sid='anss', new_sid='snps', effective_date='2025-07-17',
                 effective_time_confirmed=True, eligibility_confirmed=True, cash_per_share='199.91',
                 new_shares_per_old_share='0.3399', source_references=['synthetic closing terms'])
    return state, event


class MergerRightsTests(unittest.TestCase):
    def test_missing_invalid_or_future_settlement_date_preserves_state(self):
        state, event = fixture()
        converted = convert_cash_stock_entitlement(state=state, event=event, as_of='2025-07-17')
        marks = {'snps': dict(date='2025-07-17', price='100', source_references=['mark'])}
        for settlement in ({}, {'known_asof': 'invalid'},
                           {'known_asof': '9999-01-01', 'fraction_reference_close': object()}):
            result = value_cash_stock_entitlements(state=converted, marks=marks, as_of='2025-07-17',
                                                  fractional_settlements={'closing': settlement})
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertIsNone(result['total_equity'])
            self.assertEqual(result['state'], converted)

    def test_conversion_preserves_separate_cash_stock_and_fraction(self):
        state, event = fixture()
        result = convert_cash_stock_entitlement(state=state, event=event, as_of='2025-07-17')
        self.assertEqual(result['cash'], '100')
        self.assertEqual(result['shares'], {'anss': 0, 'snps': 7})
        right = result['merger_entitlements'][0]
        self.assertEqual(right['pending_whole_shares'], 3)
        self.assertEqual(right['fractional_share_entitlement'], '399/1000')
        self.assertEqual(right['cash_receivable'], '19991/10')
        self.assertEqual(state['shares']['anss'], 10)
        with self.assertRaises(ValueError):
            convert_cash_stock_entitlement(state=result, event=event, as_of='2025-07-17')

    def test_unknown_fraction_price_blocks_but_unknown_payment_retains_right(self):
        state, event = fixture()
        converted = convert_cash_stock_entitlement(state=state, event=event, as_of='2025-07-17')
        marks = {'snps': dict(date='2025-07-17', price='100', source_references=['fixture mark'])}
        result = value_cash_stock_entitlements(state=converted, marks=marks, as_of='2025-07-17')
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIsNone(result['total_equity'])
        self.assertEqual(result['existing_stock_value'], '700')
        self.assertEqual(result['pending_stock_entitlement_value'], '300')
        settlement = dict(known_asof='2025-07-17', fraction_reference_close=dict(date='2025-07-16', price='100.001', source_references=['fixture precise reference']),
                          reference_is_previous_closing_session=True, payment_date=None, source_references=['fixture contractual rounding'])
        result = value_cash_stock_entitlements(state=converted, marks=marks, as_of='2025-07-17', fractional_settlements={'closing': settlement})
        self.assertEqual(result['status'], 'BLOCKED')
        settlement['fraction_cash_rounding'] = 'CEIL_CENT'
        result = value_cash_stock_entitlements(state=converted, marks=marks, as_of='2025-07-17', fractional_settlements={'closing': settlement})
        self.assertEqual(result['status'], 'VALUED_NONTRADABLE_RECEIVABLE')
        self.assertEqual(result['fractional_cash_receivable'], '3991/100')
        self.assertEqual(result['total_equity'], '313901/100')
        self.assertEqual(result['available_cash'], '100')

    def test_no_fraction_needs_no_invented_payment_or_price(self):
        state, event = fixture(10000)
        converted = convert_cash_stock_entitlement(state=state, event=event, as_of='2025-07-17')
        marks = {'snps': dict(date='2025-07-17', price='100', source_references=['mark'])}
        result = value_cash_stock_entitlements(state=converted, marks=marks, as_of='2025-07-17')
        self.assertEqual(result['status'], 'VALUED_NONTRADABLE_RECEIVABLE')
        self.assertEqual(result['state']['shares']['snps'], 7)
        self.assertEqual(result['merger_cash_receivable'], '1999100')

    def test_unknown_effective_time_and_future_mark_fail_closed(self):
        state, event = fixture()
        event['effective_time_confirmed'] = False
        with self.assertRaises(ValueError):
            convert_cash_stock_entitlement(state=state, event=event, as_of='2025-07-17')
        event['effective_time_confirmed'] = True
        converted = convert_cash_stock_entitlement(state=state, event=event, as_of='2025-07-17')
        result = value_cash_stock_entitlements(state=converted, as_of='2025-07-17',
                    marks={'snps': {'date': '9999-01-01', 'price': object()}},
                    fractional_settlements={'closing': {'known_asof': '9999-01-01', 'price_per_fractional_share': object()}})
        self.assertEqual(result['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
