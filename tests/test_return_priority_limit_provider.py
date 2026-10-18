import unittest

from backtest.return_priority_limit_book import run_limit_book


class LimitProviderTests(unittest.TestCase):
    def test_provider_uses_prior_fill_and_cannot_mutate_book(self):
        observed = []
        def provider(*, decision_date, active_date, state):
            observed.append((decision_date, state['cash'], dict(state['shares'])))
            if decision_date == '2024-01-01':
                self.assertEqual(state['order_log'], [])
                order = dict(id='buy', security_id='x', side='BUY', quantity=2, limit='10')
            else:
                self.assertEqual(state['shares'], {'x': 2})
                self.assertEqual(state['cash'], '82')
                self.assertTrue(all(row['date'] <= decision_date for row in state['daily_ledger']))
                state['shares']['x'] = 999
                state['daily_ledger'][0]['cash'] = '-1'
                order = dict(id='sell', security_id='x', side='SELL', quantity=2, limit='11')
            order.update(decision_date=decision_date, active_date=active_date)
            return dict(status='READY', orders=[order])
        result = run_limit_book(session_dates=['2024-01-01', '2024-01-02', '2024-01-03'],
             initial_cash='100', order_provider=provider, ohlc={'x': {
                 '2024-01-02': dict(open=9, high=10, low=8, close=9),
                 '2024-01-03': dict(open=12, high=13, low=10, close=11)}})
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['cash'], '106')
        self.assertEqual(result['shares']['x'], 0)
        self.assertEqual(result['daily_ledger'][0]['cash'], '82')
        self.assertEqual(len(observed), 2)

    def test_provider_failure_or_misdated_orders_do_not_trade(self):
        args = dict(session_dates=['2024-01-01', '2024-01-02'], initial_cash='100', ohlc={})
        blocked = run_limit_book(**args, order_provider=lambda **_: {'status': 'CASH_ALLOCATION_REQUIRED', 'orders': []})
        self.assertEqual(blocked['status'], 'BLOCKED')
        self.assertEqual(blocked['daily_ledger'], [])
        misdated = run_limit_book(**args, order_provider=lambda **_: {'status': 'READY', 'orders': [{'active_date': '2024-01-03'}]})
        self.assertEqual(misdated['reason'], 'PROVIDER_ORDER_NOT_ACTIVE_SESSION')


if __name__ == '__main__':
    unittest.main()
