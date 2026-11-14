import unittest
from scripts.research.aapl_execution_terminal_comparison import terminal_value

class TerminalComparisonTests(unittest.TestCase):
    def test_unfilled_buy_keeps_cash_and_avoids_fee(self):
        self.assertEqual(terminal_value('BUY', 10, 90, None, 18), 0)
        self.assertEqual(terminal_value('BUY', 10, 90, {'price': 100}, 18), -118)

    def test_unfilled_sell_retains_stock_value(self):
        self.assertEqual(terminal_value('SELL', 10, 90, None, 18), 900)
        self.assertEqual(terminal_value('SELL', 10, 90, {'price': 100}, 18), 982)

if __name__ == '__main__':
    unittest.main()
