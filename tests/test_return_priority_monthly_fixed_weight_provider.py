import unittest
from fractions import Fraction

from backtest.return_priority_monthly_fixed_weight_provider import build_monthly_fixed_weight_provider


class FixedWeightProviderTests(unittest.TestCase):
    dates = ['2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07']

    def build(self, weights, prices=None):
        prices = prices or {'a': '10', 'b': '10'}
        plans = [dict(decision_date=d, valuation_quotes=[dict(security_id=s, price=p)
                 for s, p in prices.items()], search_arguments=dict(fee_bps=0, minimum_cash_buffer=0),
                 source_hashes={}) for d in (self.dates[0], self.dates[2])]
        return build_monthly_fixed_weight_provider(weights=weights, session_dates=self.dates,
            monthly_inputs=plans, close_prices={s: dict.fromkeys(self.dates, p) for s,p in prices.items()})

    def call(self, provider, index=0, cash='100', shares=None):
        return provider(decision_date=self.dates[index], active_date=self.dates[index+1],
            state=dict(asof=self.dates[index], cash=cash, shares=shares or {}))

    def test_sale_cash_not_spent_until_next_session(self):
        provider = self.build({'a': '1/2', 'b': '1/2'})
        result = self.call(provider, cash='0', shares={'a': 10})
        self.assertEqual(result['target_shares'], {'a': 5, 'b': 5})
        self.assertEqual([(o['side'], o['quantity']) for o in result['orders']], [('SELL', 5)])
        self.assertEqual(result['wait_cash'][0]['remaining_deficit'], 5)
        result = self.call(provider, 1, cash='50', shares={'a': 5})
        self.assertEqual([(o['side'], o['quantity']) for o in result['orders']], [('BUY', 5)])

    def test_monthly_reset_actual_equity_and_frozen_weights(self):
        weights = {'a': '1/2', 'b': '1/2'}
        provider = self.build(weights)
        weights['a'] = '1'
        self.call(provider)
        self.call(provider, 1, cash='200')
        result = self.call(provider, 2, cash='200')
        self.assertEqual(result['target_shares'], {'a': 10, 'b': 10})
        self.assertEqual(result['selection']['investable_equity'], '200')
        self.assertFalse(result['selection']['weights_normalized'])

    def test_above_one_preserved_but_infeasible_target_blocked(self):
        weight = '50000000000000001/50000000000000000'
        result = self.call(self.build({'a': weight}))
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(Fraction(result['selection']['original_weight_sum']), Fraction(weight))
        result = self.call(self.build({'a': weight}, {'a': '1/100000000000000000'}))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['orders'], [])
        self.assertIn('EXCEEDS_EQUITY', result['reason']['detail'])

    def test_missing_weight_quote_blocks(self):
        result = self.call(self.build({'c': '1'}))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['orders'], [])


if __name__ == '__main__':
    unittest.main()
