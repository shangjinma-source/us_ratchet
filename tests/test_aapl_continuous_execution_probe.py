import unittest
from unittest.mock import patch
from scripts.research.aapl_continuous_execution_probe import replay


class ContinuousExecutionTests(unittest.TestCase):
    def test_missed_buy_does_not_create_sell_or_fee(self):
        events = [({'date':'2022-01-03','side':'BUY','quantity':'10'}, b'{"c":[90]}'),
                  ({'date':'2022-01-24','side':'SELL','quantity':'10'}, b'{"c":[80]}')]
        with patch('scripts.research.aapl_continuous_execution_probe.inspect',
                   return_value={'arms':[{'name':'OPEN_REFERENCE','fill':None}]}):
            result = replay(events, 'OPEN_REFERENCE')
        self.assertEqual(result['ending_cash'], 10000)
        self.assertEqual(result['ending_shares'], 0)
        self.assertEqual(result['records'][1]['action'], 'NO_CHANGE')

    def test_insufficient_cash_does_not_create_position(self):
        events = [({'date':'2022-01-03','side':'BUY','quantity':'10'}, b'{"c":[90]}')]
        with patch('scripts.research.aapl_continuous_execution_probe.inspect',
                   return_value={'arms':[{'name':'OPEN_REFERENCE','fill':{'price':100}}]}):
            result = replay(events, 'OPEN_REFERENCE', initial_cash=1000)
        self.assertEqual(result['ending_cash'], 1000)
        self.assertEqual(result['ending_shares'], 0)
        self.assertEqual(result['records'][0]['reason'], 'INSUFFICIENT_CASH_WHOLE_ORDER')


if __name__ == '__main__':
    unittest.main()
