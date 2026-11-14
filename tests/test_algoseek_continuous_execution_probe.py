import unittest

from scripts.research.algoseek_continuous_execution_probe import settle, replay


class ContinuousExecutionTests(unittest.TestCase):
    def test_future_sale_cannot_fund_earlier_buy(self):
        holdings = {'OLD': 1}
        orders = [dict(symbol='OLD', side='SELL', minute=2, price=100, quantity=1),
                  dict(symbol='NEW', side='BUY', minute=1, price=50, quantity=2)]
        cash, records = settle(0, holdings, orders, 0)
        self.assertEqual(records[0]['filled'], 0)
        self.assertEqual(cash, 100)
        self.assertEqual(holdings.get('NEW', 0), 0)

    def test_fees_and_integer_cash_limit(self):
        holdings = {}
        cash, records = settle(118, holdings, [dict(symbol='NEW', side='BUY', minute=1, price=50, quantity=3)], 18)
        self.assertEqual(records[0]['filled'], 2)
        self.assertEqual(cash, 0)

    def test_split_adjusts_only_actual_holdings(self):
        def prices(fill):
            return {'NVDA': dict(close=25, checked={side: dict(arms=[dict(name='OPEN_REFERENCE', fill=fill)]) for side in ('BUY', 'SELL')})}
        sessions = [('2021-07-01', {'NVDA': 2}, prices(None)),
                    ('2021-08-02', {'NVDA': 8}, prices(None))]
        result = replay(sessions, 'OPEN_REFERENCE', 'OPEN_REFERENCE', 0, 1000)
        self.assertEqual(result['records'][-1]['holdings'].get('NVDA', 0), 0)
        sessions[0] = ('2021-07-01', {'NVDA': 2}, prices(dict(minute=1, price=100)))
        result = replay(sessions, 'OPEN_REFERENCE', 'OPEN_REFERENCE', 0, 1000)
        self.assertEqual(result['records'][-1]['holdings']['NVDA'], 8)
        self.assertEqual(result['records'][-1]['fills'], [])


if __name__ == '__main__':
    unittest.main()
