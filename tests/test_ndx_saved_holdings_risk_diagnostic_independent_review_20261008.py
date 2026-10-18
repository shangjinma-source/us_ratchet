from fractions import Fraction
import unittest

from backtest import ndx_saved_holdings_risk_diagnostic_research as subject


def ratio(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


class Tests(unittest.TestCase):
    def test_decimal_basis_top_three_and_chain_weights_are_independent_of_order(self):
        amounts = {'a': 0.1, 'b': 0.2, 'c': 0.3, 'd': 0.4}
        labels = {key: dict(label='X' if key in ('a','d') else 'Y', observation_session='2026-04-01') for key in amounts}
        args = dict(session='2026-04-01', shares=amounts, close_prices=dict.fromkeys(amounts, 1), labels=labels)
        result = subject.derive_daily_diagnostic(**args)
        self.assertEqual(ratio(result['invested_value']), 1)
        self.assertEqual(ratio(result['metrics']['hhi']), Fraction(3,10))
        self.assertEqual(ratio(result['metrics']['effective_n']), Fraction(10,3))
        self.assertEqual(ratio(result['metrics']['top3_weight']), Fraction(9,10))
        self.assertEqual(ratio(result['chain_weights']['X']), Fraction(1,2))
        self.assertNotEqual(subject.saved_number(0.1), Fraction.from_float(0.1))
        self.assertEqual(subject.derive_daily_diagnostic(**dict(args, shares=dict(reversed(list(amounts.items()))))), result)

    def test_label_carry_is_per_sid_as_of_close_and_does_not_fill_new_holding(self):
        observations = {'2026-04-01': {'a':'old','b':'carry'}, '2026-04-03': {'a':'new'}, '2026-04-05': {'c':'future'}}
        at = subject.latest_labels(session='2026-04-03', security_ids=['b','a'], observations=observations)
        self.assertEqual(at, {'a':dict(label='new',observation_session='2026-04-03'), 'b':dict(label='carry',observation_session='2026-04-01')})
        with self.assertRaises(ValueError): subject.latest_labels(session='2026-04-04',security_ids=['a','c'],observations=observations)
        with self.assertRaises(ValueError): subject.latest_labels(session='2026-04-04',security_ids=['a','a'],observations=observations)
        self.assertEqual(subject.latest_labels(session='2026-04-04',security_ids=[],observations=observations),{})

    def test_extra_sid_price_and_label_or_noncanonical_date_are_rejected(self):
        base = dict(session='2026-04-01', shares={'a':1}, close_prices={'a':1}, labels={'a':dict(label='X',observation_session='2026-04-01')})
        for key, changed in (('close_prices',{'a':1,'b':1}), ('labels',{}), ('session','20260401')):
            with self.subTest(key=key), self.assertRaises(ValueError): subject.derive_daily_diagnostic(**dict(base,**{key:changed}))


if __name__ == '__main__': unittest.main()
