"""Independent accounting invariants for the declared-event return kernel."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.ndx_split_neutral_price_return_research import calculate_split_neutral_price_returns


def panel(prices, new_shares, old_shares, basis):
    dates = ['2022-07-15', '2022-07-18']
    return dict(schema='ndx_split_neutral_return_input_v1', basis=basis,
        dividend_adjustment_in_close=False,
        event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS', calendar=dates,
        securities={'security:A': {'issuer_id': 'issuer:A'}},
        rows=[dict(security_id='security:A', issuer_id='issuer:A', ticker=ticker, session=day, close=price)
              for day, ticker, price in zip(dates, ['OLD', 'NEW'], prices)],
        daily_share_ratios=[dict(security_id='security:A', session=dates[0], new_shares=1, old_shares=1),
                           dict(security_id='security:A', session=dates[1], new_shares=new_shares,
                                old_shares=old_shares)])


class IndependentSplitReturnTests(unittest.TestCase):
    def test_market_value_conservation_across_forward_reverse_and_rename(self):
        for new, old in [(1, 4), (1, 1), (3, 2), (10, 1), (20, 1)]:
            for move in [-.9, -.5, -.02, 0., .01, .5]:
                before = 120.
                after = before * (1 + move) * old / new
                payload = panel([before, after], new, old, 'NOMINAL_CLOSE')
                observed = calculate_split_neutral_price_returns(payload)['rows'][0]
                # A real investor starts with old shares and ends with new shares.
                economic_return = (new * after - old * before) / (old * before)
                self.assertAlmostEqual(observed['price_return'], economic_return, places=14)
                self.assertEqual(observed['previous_ticker'], 'OLD')
                self.assertEqual(observed['ticker'], 'NEW')
                adjusted = panel([before * old / new, after], new, old, 'SPLIT_ONLY_ADJUSTED_CLOSE')
                self.assertAlmostEqual(calculate_split_neutral_price_returns(adjusted)['rows'][0]['price_return'],
                                       observed['price_return'], places=14)

    def test_same_issuer_different_share_classes_keep_independent_returns(self):
        payload = panel([100, 10.1], 10, 1, 'NOMINAL_CLOSE')
        payload['securities']['security:B'] = {'issuer_id': 'issuer:A'}
        for original in list(payload['rows']):
            row = deepcopy(original)
            row.update(security_id='security:B', ticker='B', close=80 if row['session']=='2022-07-15' else 40)
            payload['rows'].append(row)
        for original in list(payload['daily_share_ratios']):
            row = deepcopy(original)
            row.update(security_id='security:B', new_shares=1, old_shares=1)
            payload['daily_share_ratios'].append(row)
        result = calculate_split_neutral_price_returns(payload)
        self.assertEqual({row['security_id']: row['price_return'] for row in result['rows']},
                         {'security:A': .01, 'security:B': -.5})

    def test_equivalent_noninteger_ratio_units_and_input_order(self):
        payload = panel([120, 81], 1.5, 1, 'NOMINAL_CLOSE')
        expected = calculate_split_neutral_price_returns(payload)
        payload['daily_share_ratios'][1].update(new_shares=3, old_shares=2)
        payload['rows'].reverse()
        payload['daily_share_ratios'].reverse()
        self.assertEqual(expected, calculate_split_neutral_price_returns(payload))
        self.assertEqual(Fraction(expected['rows'][0]['declared_share_ratio']), Fraction(3, 2))


if __name__ == '__main__':
    unittest.main()
