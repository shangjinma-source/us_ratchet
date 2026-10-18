"""Compare the new execution phase against the existing book, without selection."""
import unittest
from fractions import Fraction

from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.daily_sell_switch_execution import execute_day


class BaselineCompatibilityTests(unittest.TestCase):
    def test_open_cash_and_positions_match_existing_book(self):
        bars = {
            'A': dict(open='17', high='19', low='15', close='16'),
            'B': dict(open='13', high='14', low='11', close='12'),
            'C': dict(open='7', high='8', low='6', close='7'),
        }
        orders = [dict(id='sale', security_id='A', side='SELL', quantity=7, limit='18'),
                  dict(id='buy-b', security_id='B', side='BUY', quantity=10),
                  dict(id='buy-c', security_id='C', side='BUY', quantity=15)]
        for initial_cash, fee in [('0', '0'), ('20', '10'), ('300', '100')]:
            with self.subTest(cash=initial_cash, fee=fee):
                phased = execute_day(orders=orders, ohlc=bars, cash=initial_cash,
                                     shares={'A': 9}, fee_bps=fee, slippage_bps='0', mode='BASELINE_OPEN')
                existing = run_next_open_book(
                    session_dates=['2024-01-02', '2024-01-03'],
                    orders=[dict(order, decision_date='2024-01-02', active_date='2024-01-03',
                                 decision_mark=bars[order['security_id']]['close']) for order in orders],
                    ohlc={sid: {'2024-01-03': bar} for sid, bar in bars.items()},
                    initial_cash=initial_cash, initial_shares={'A': 9}, fee_bps=fee, slippage_bps='0')
                self.assertEqual(existing['status'], 'COMPLETE', existing.get('reason'))
                self.assertEqual(phased['shares'], existing['shares'])
                self.assertEqual(Fraction(phased['cash']), Fraction(existing['cash']))
                self.assertEqual(Fraction(phased['fees']), Fraction(existing['fees']))


if __name__ == '__main__':
    unittest.main()
