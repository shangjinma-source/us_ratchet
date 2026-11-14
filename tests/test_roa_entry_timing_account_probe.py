import unittest
from scripts.research.roa_entry_timing_account_probe import simulate


def session(bar):
    return {minute * 60: list(bar) for minute in range(390)}


class TimingReplayTests(unittest.TestCase):
    def test_opening_wick_cannot_fill_before_submission(self):
        buy = session((11, 12, 10.5, 11, 100))
        buy[0] = [10, 11, 8, 10, 100]
        result = simulate([{'A': buy}, {'A': session((12, 13, 11, 12, 100))}],
                          {'A': 1}, 20, 'OPEN_REFERENCE', 1)
        self.assertEqual(result['buy_count'], 0)
        self.assertEqual(result['fees'], 0)
        self.assertEqual(result['ending_cash'], 20)

    def test_limit_uses_completed_minute_not_future_close(self):
        buy = session((11, 21, 9, 20, 100))
        buy[59 * 60] = [10, 10, 10, 10, 100]
        result = simulate([{'A': buy}, {'A': session((12, 13, 11, 12, 100))}],
                          {'A': 1}, 30, 'BUY_1030', 1)
        self.assertEqual(result['fills'][0]['minute'], 60)
        self.assertEqual(result['fills'][0]['price'], 10)
        self.assertEqual(result['fees'], 2)
        self.assertEqual(result['ending_equity'], 30)

    def test_pending_orders_reserve_cash_and_cannot_borrow(self):
        buy = session((10, 11, 9, 10, 100))
        sell = session((12, 13, 11, 12, 100))
        result = simulate([{'A': buy, 'B': buy}, {'A': sell, 'B': sell}],
                          {'A': 1, 'B': 1}, 11, 'OPEN_REFERENCE', 1)
        self.assertEqual(result['buy_count'], 1)
        self.assertEqual(result['cash_rejected'], [{'ticker': 'B', 'reason': 'INSUFFICIENT_CASH'}])
        self.assertEqual(result['ending_cash'], 11)

    def test_touch_and_cross_are_distinct_and_unfilled_stays_cash(self):
        buy = session((11, 12, 10, 11, 100))
        buy[0] = [10, 11, 10, 10, 100]
        sell = session((12, 13, 11, 12, 100))
        args = ([{'A': buy}, {'A': sell}], {'A': 1}, 20, 'OPEN_REFERENCE', 0)
        self.assertEqual(simulate(*args, touch=False)['buy_count'], 0)
        self.assertEqual(simulate(*args, touch=True)['buy_count'], 1)

    def test_delayed_sell_uses_prior_close_and_cannot_sell_early(self):
        buy = session((10, 11, 9, 10, 100))
        sell = session((12, 13, 11, 12, 100))
        sell[59 * 60] = [14, 14, 14, 14, 100]
        sell[60 * 60] = [13, 15, 12, 13, 100]
        result = simulate([{'A': buy}, {'A': sell}], {'A': 1}, 20,
                          'OPEN_REFERENCE', 0, sell_start=60)
        sale = [fill for fill in result['fills'] if fill['side'] == 'SELL'][0]
        self.assertEqual(sale['minute'], 60)
        self.assertEqual(sale['price'], 14)
        self.assertEqual(result['ending_cash'], 24)


if __name__ == '__main__':
    unittest.main()
