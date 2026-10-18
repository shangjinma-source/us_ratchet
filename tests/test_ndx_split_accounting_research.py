import copy
import unittest

from backtest.ndx_split_accounting_research import apply_split_session


def fixture():
    return dict(session='2022-07-18', shares={'GOOG': 3, 'A': 7}, cash_usd=100.,
        pending_plan={'delta_shares': {'GOOG': 1, 'A': -1}},
        events=[dict(ticker='GOOG', session='2022-07-18', new_shares=20, old_shares=1,
            source_url='https://example.org/synthetic', evidence_sha256='a'*64)])


class SplitAccountingTests(unittest.TestCase):
    def test_twenty_for_one_conserves_equity_without_fee(self):
        inputs = fixture()
        original = copy.deepcopy(inputs)
        result = apply_split_session(**inputs)
        self.assertEqual(result['shares'], {'GOOG': 60, 'A': 7})
        self.assertEqual(3*2000+100, result['shares']['GOOG']*100+result['cash_usd'])
        self.assertEqual(result['split_fees_usd'], 0.)
        self.assertEqual(inputs, original)
        self.assertFalse(result['evidence_authenticated'])

    def test_pending_basket_cancelled_not_rescaled(self):
        inputs = fixture()
        result = apply_split_session(**inputs)
        self.assertIsNone(result['pending_plan'])
        self.assertEqual(result['cancelled_plan'], inputs['pending_plan'])
        result['cancelled_plan']['delta_shares']['GOOG'] = 900
        self.assertEqual(inputs['pending_plan']['delta_shares']['GOOG'], 1)

    def test_no_events_preserves_pending_without_alias(self):
        inputs = fixture()
        inputs['events'] = []
        result = apply_split_session(**inputs)
        self.assertEqual(result['pending_plan'], inputs['pending_plan'])
        self.assertIsNot(result['pending_plan'], inputs['pending_plan'])
        self.assertEqual(result['shares'], inputs['shares'])

    def test_reverse_fraction_not_rounded_or_paid_with_invented_price(self):
        inputs = fixture()
        inputs['events'][0].update(new_shares=1, old_shares=2)
        with self.assertRaisesRegex(ValueError, 'FRACTIONAL'):
            apply_split_session(**inputs)
        inputs['shares']['GOOG'] = 4
        self.assertEqual(apply_split_session(**inputs)['shares']['GOOG'], 2)

    def test_invalid_events_fail_closed(self):
        for change in ({'new_shares': True}, {'old_shares': 0}, {'new_shares': 20.},
                       {'ticker': 'UNKNOWN'}, {'session': '2022-07-15'},
                       {'evidence_sha256': ''}, {'source_url': 'inferred_price_ratio'},
                       {'source_url': 'https://'}, {'source_url': 'https://a b/x'},
                       {'source_url': 'https://user:password@example.org/x'}):
            inputs = fixture()
            inputs['events'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                apply_split_session(**inputs)
        inputs = fixture()
        inputs['events'] *= 2
        with self.assertRaises(ValueError):
            apply_split_session(**inputs)

    def test_nominal_goog_return_not_false_ninety_five_percent_loss(self):
        inputs = fixture()
        result = apply_split_session(**inputs)
        before = 3*2255.34
        after = result['shares']['GOOG']*109.91
        self.assertAlmostEqual(after/before-1, -0.0253354261441734)
        self.assertLess(109.91/2255.34-1, -.95)


if __name__ == '__main__':
    unittest.main()
