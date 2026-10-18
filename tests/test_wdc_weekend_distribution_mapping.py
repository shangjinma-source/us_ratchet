"""Synthetic WDC-shaped clock tests, not historical delivery certification."""
import unittest

from backtest.current_quantity_v2_next_open_book import run_next_open_book


class WeekendDistributionTests(unittest.TestCase):
    def run_book(self, quantity=3, orders=None):
        def bar(price):
            return dict(open=price, high=price, low=price, close=price)

        return run_next_open_book(
            session_dates=['2025-02-20', '2025-02-21', '2025-02-24'],
            orders=orders or [], initial_cash='0', initial_shares={'P': quantity},
            fee_bps='0', slippage_bps='0',
            ohlc={'P': {'2025-02-21': bar('100'), '2025-02-24': bar('90')},
                  'C': {'2025-02-24': bar('30')}},
            price_source_references={'P': ['synthetic'], 'C': ['synthetic']},
            distribution_events=[dict(
                event_id='synthetic-weekend', effective_date='2025-02-21',
                timing='AFTER_CLOSE', parent_sid='P', post_parent_sid='P',
                child_sid='C', child_ratio='1/3', parent_ratio='1',
                eligibility_rule='ACTUAL_HOLDINGS_IMMEDIATELY_BEFORE_EVENT',
                eligibility_confirmed=True, ordered_steps_confirmed=True,
                parent_delivered_units_confirmed=True,
                source_references=['synthetic-fixture-not-official-admission'])])

    def test_friday_close_before_rights_then_monday_valuation(self):
        result = self.run_book()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual([r['equity'] for r in result['daily_ledger']], ['300', '300'])
        self.assertEqual(result['daily_ledger'][0]['distribution_rights'], [])
        self.assertEqual(result['distribution_rights'][0]['units'], '1')
        self.assertFalse(result['distribution_rights'][0]['tradable'])
        self.assertEqual(result['shares'].get('C', 0), 0)
        self.assertEqual(result['cash'], '0')

    def test_fraction_is_not_guessed_from_monday_open(self):
        result = self.run_book(quantity=1)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['last_valued_date'], '2025-02-21')
        self.assertEqual(result['distribution_rights'][0]['units'], '1/3')
        self.assertEqual(result['cash'], '0')

    def test_friday_regular_way_sale_transfers_entitlement(self):
        result = self.run_book(orders=[dict(
            id='sell', security_id='P', side='SELL', quantity=3,
            decision_mark='100', decision_date='2025-02-20', active_date='2025-02-21')])
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['distribution_rights'], [])
        self.assertEqual(result['cash'], '300')


if __name__ == '__main__':
    unittest.main()
