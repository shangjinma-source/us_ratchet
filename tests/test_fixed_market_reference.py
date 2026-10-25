"""Synthetic checks only; no registered historical books or market fetching."""
from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from scripts.run_fixed_market_reference import RULES, WINDOWS, execute_reference, review_reference, verify_pins, window_market


def fixture(first_open='100', first_close='100', last_close='80'):
    calendar = ['2025-01-02', '2025-01-03', '2025-01-06']
    def bar(opening, closing):
        values = [Fraction(opening), Fraction(closing)]
        return dict(open=opening, close=closing, low=str(min(values)), high=str(max(values)))
    return calendar, {calendar[0]: bar('100', '100'), calendar[1]: bar(first_open, first_close),
                      calendar[2]: bar(last_close, last_close)}


class FixedMarketReferenceTests(unittest.TestCase):
    def test_gap_up_cash_rationing_and_initial_equity_drawdown(self):
        calendar, prices = fixture('110', '108', '80')
        result = execute_reference('QQQ', calendar, prices)
        self.assertEqual(result['requested_quantity'], 199)
        review = result['independent_formula_review']
        self.assertEqual(review['filled_quantity'], 181)
        self.assertEqual(Fraction(review['fill_price']), Fraction('110.11'))
        expected_cash = Fraction(20000) - 181 * Fraction('110.11') * Fraction('1.0001')
        self.assertEqual(Fraction(review['residual_cash']), expected_cash)
        self.assertEqual(Fraction(result['metrics']['maximum_close_drawdown']),
                         1 - (expected_cash + 181 * 80) / 20000)

    def test_gap_down_keeps_prior_close_request_and_single_purchase(self):
        calendar, prices = fixture('80', '90', '120')
        result = execute_reference('SPY', calendar, prices)
        self.assertEqual(result['independent_formula_review']['filled_quantity'], 199)
        self.assertGreater(Fraction(result['independent_formula_review']['residual_cash']), 4000)
        fills = [row for row in result['outcome']['order_log'] if row.get('event') == 'ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]['date'], calendar[1])
        self.assertEqual(result['outcome']['shares']['reference:SPY'], 199)
        self.assertEqual(result['outcome']['state_date'], calendar[-1])

    def test_independent_review_rejects_modified_cash_fee_date_and_drawdown(self):
        calendar, prices = fixture()
        original = execute_reference('QQQ', calendar, prices)
        for change in ('cash', 'fee', 'date', 'drawdown'):
            with self.subTest(change=change):
                result = deepcopy(original)
                if change == 'cash':
                    result['outcome']['daily_ledger'][1]['cash'] = '1'
                elif change == 'fee':
                    result['outcome']['fees'] = '0'
                elif change == 'date':
                    result['outcome']['daily_ledger'][0]['date'] = calendar[0]
                else:
                    result['metrics']['maximum_close_drawdown'] = '0'
                with self.assertRaises(ValueError):
                    review_reference('QQQ', calendar, prices, result['outcome'], result['metrics'])

    def test_dividend_exclusion_missing_price_and_nondividend_action_guards(self):
        calendar, prices = fixture()
        dividend = dict(kind='dividends', date=calendar[1], amount='9')
        market = dict(rows=prices, events=[dividend])
        filtered, events = window_market(market, calendar)
        self.assertEqual(filtered, prices)
        self.assertEqual(events, [dividend])
        with self.assertRaisesRegex(ValueError, 'MISSING_REQUIRED_SESSION'):
            window_market(dict(rows={calendar[0]: prices[calendar[0]]}, events=[]), calendar)
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_RETURNED_ACTION'):
            window_market(dict(rows=prices, events=[dict(kind='splits', date=calendar[1])]), calendar)

    def test_registration_rejects_removed_or_changed_source_pins(self):
        registration = dict(schema='FIXED_MARKET_REFERENCE_REGISTRATION_V1', rules=deepcopy(RULES),
            windows=deepcopy(WINDOWS), markets={'QQQ': {}, 'SPY': {}}, source_pins={'synthetic.py': 'expected'})
        with patch('scripts.run_fixed_market_reference.registered_source_names', return_value={'synthetic.py'}):
            with patch('scripts.run_fixed_market_reference.digest', return_value='changed'):
                with self.assertRaisesRegex(ValueError, 'REGISTERED_SOURCE_CHANGED'):
                    verify_pins(registration)
            registration['source_pins'] = {}
            with self.assertRaisesRegex(ValueError, 'REGISTERED_SOURCE_SET_CHANGED'):
                verify_pins(registration)


if __name__ == '__main__':
    unittest.main()
