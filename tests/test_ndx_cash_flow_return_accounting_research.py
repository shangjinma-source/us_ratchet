from copy import deepcopy
from decimal import Decimal, localcontext, Inexact, ROUND_UP
from fractions import Fraction
import unittest
from backtest import ndx_cash_flow_return_accounting_research as module


def fraction(record):
    return Fraction(int(record['numerator']), int(record['denominator']))


def fixture(open_price='20', close_price='20', flow='100', buy=5):
    return dict(initial=dict(session='2023-04-28', cash_usd='0', holdings={'A': 10}, close_prices={'A': '10'}),
                sessions=[dict(session='2023-05-01', open_prices={'A': open_price}, close_prices={'A': close_price}, cash_injection_usd=flow, buy_shares={'A': buy})],
                transaction_cost_bps='0')


class CashFlowAccountingTests(unittest.TestCase):
    def test_overnight_gain_and_loss_not_diluted_by_injection(self):
        for inputs, expected in [(fixture(), Fraction(1)), (fixture('5', '5', buy=20), Fraction(-1, 2))]:
            before = deepcopy(inputs)
            result = module.account_path(**inputs)
            self.assertEqual(inputs, before)
            self.assertEqual(fraction(result['chained_twr']), expected)
            self.assertEqual(fraction(result['rows'][0]['after_flow_return']), 0)

    def test_fees_reduce_return_postflow_denominator_not_postfee(self):
        inputs = fixture('10', '10', buy=9)
        inputs['transaction_cost_bps'] = '100'
        result = module.account_path(**inputs)
        self.assertEqual(result['total_fees_usd'], '0.9')
        self.assertEqual(result['net_dollar_pnl_excluding_injections_usd'], '-0.9')
        self.assertEqual(fraction(result['chained_twr']), Fraction(-9, 2000))

    def test_cash_only_injection_and_multiday_chain(self):
        inputs = dict(initial=dict(session='2023-04-28', cash_usd='100', holdings={}, close_prices={}),
                      sessions=[dict(session='2023-05-01', open_prices={}, close_prices={}, cash_injection_usd='900', buy_shares={})], transaction_cost_bps='10')
        result = module.account_path(**inputs)
        self.assertEqual(result['terminal_equity_usd'], '1000')
        self.assertEqual(fraction(result['chained_twr']), 0)
        inputs = fixture()
        inputs['sessions'].append(dict(session='2023-05-02', open_prices={'A': '10'}, close_prices={'A': '12'}, cash_injection_usd='0', buy_shares={}))
        result = module.account_path(**inputs)
        self.assertEqual(fraction(result['chained_twr']), Fraction(1, 5))
        self.assertEqual(result['net_dollar_pnl_excluding_injections_usd'], '-20')

    def test_zero_flow_telescopes_and_keeps_unbought_old_holdings(self):
        inputs = fixture('20', '30', flow='0', buy=0)
        inputs['initial']['holdings']['B'] = 1
        inputs['initial']['close_prices']['B'] = '100'
        inputs['sessions'][0]['open_prices']['B'] = '50'
        inputs['sessions'][0]['close_prices']['B'] = '100'
        result = module.account_path(**inputs)
        self.assertEqual(fraction(result['chained_twr']), Fraction(1))
        self.assertEqual(result['rows'][0]['holdings_after'], {'A': 10, 'B': 1})

    def test_missing_union_zero_inception_and_insufficient_cash_fail(self):
        inputs = fixture()
        del inputs['sessions'][0]['open_prices']['A']
        with self.assertRaises(ValueError):
            module.account_path(**inputs)
        inputs = fixture(buy=6)
        with self.assertRaises(ValueError):
            module.account_path(**inputs)
        inputs = fixture()
        inputs['initial'].update(holdings={}, close_prices={})
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_ZERO_CAPITAL_INCEPTION'):
            module.account_path(**inputs)

    def test_hostile_context_fractional_precision_and_invalid_types(self):
        inputs = fixture('10', '10', buy=1)
        inputs['initial']['cash_usd'] = '1478.4820750045776'
        inputs['transaction_cost_bps'] = '10'
        expected = module.account_path(**inputs)
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            self.assertEqual(module.account_path(**inputs), expected)
        for bad in (True, 1.5, 'NaN', '-1', '1e999999'):
            value = fixture()
            value['sessions'][0]['cash_injection_usd'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.account_path(**value)

    def test_explicit_dates_flow_and_no_sells(self):
        for key, value in [('session', '2023-04-28'), ('buy_shares', {'A': -1}), ('buy_shares', {'A': True})]:
            inputs = fixture()
            inputs['sessions'][0][key] = value
            with self.assertRaises(ValueError):
                module.account_path(**inputs)
        inputs = fixture()
        del inputs['sessions'][0]['cash_injection_usd']
        with self.assertRaises(ValueError):
            module.account_path(**inputs)


if __name__ == '__main__':
    unittest.main()
