from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.ndx_signed_cash_flow_return_accounting_research import account_path


def fixture():
    return dict(
        initial=dict(session='2026-03-30', cash_usd='100', holdings={'A': 10}, close_prices={'A': '10'}),
        sessions=[
            dict(session='2026-03-31', open_prices={'A': '12', 'B': '20'},
                 close_prices={'A': '11', 'B': '22'}, cash_injection_usd='100', trade_shares={'A': -10, 'B': 5}),
            dict(session='2026-04-01', open_prices={'A': '11', 'B': '21'},
                 close_prices={'A': '12', 'B': '20'}, cash_injection_usd='0', trade_shares={}),
        ], transaction_cost_bps='100')


def fraction(row):
    return Fraction(int(row['numerator']), int(row['denominator']))


class SignedAccountingTests(unittest.TestCase):
    def test_two_session_hand_account_does_not_reset_sale_cash(self):
        arguments = fixture()
        original = deepcopy(arguments)
        result = account_path(**arguments)
        first, second = result['rows']
        self.assertEqual(first['gross_sell_usd'], '120')
        self.assertEqual(first['gross_buy_usd'], '100')
        self.assertEqual(first['fees_usd'], '2.2')
        self.assertEqual(first['cash_after_usd'], '217.8')
        self.assertEqual(first['post_flow_pre_fee_open_equity_usd'], '320')
        self.assertEqual(first['post_trade_open_equity_usd'], '317.8')
        self.assertEqual(first['close_equity_usd'], '327.8')
        self.assertEqual(second['holdings_before'], {'A': 0, 'B': 5})
        self.assertEqual(second['cash_after_usd'], '217.8')
        self.assertEqual(second['close_equity_usd'], '317.8')
        self.assertEqual(fraction(result['chained_twr']), Fraction(220, 200) * Fraction(3178, 3200) - 1)
        self.assertEqual(result['net_dollar_pnl_excluding_injections_usd'], '17.8')
        self.assertEqual(arguments, original)

    def test_sell_only_charges_fee_and_keeps_cash(self):
        arguments = fixture()
        arguments['sessions'] = [dict(session='2026-03-31', open_prices={'A': '10'},
                                     close_prices={'A': '50'}, cash_injection_usd='0', trade_shares={'A': -10})]
        result = account_path(**arguments)
        self.assertEqual(result['terminal_equity_usd'], '199')
        self.assertEqual(result['rows'][0]['holdings_after'], {'A': 0})
        self.assertEqual(fraction(result['chained_twr']), Fraction(-1, 200))

    def test_oversell_and_invalid_signed_inputs_rejected(self):
        for trades in ({'A': -11, 'B': 5}, {'A': True}, {'A': -1.0}, {'C': -1}):
            with self.subTest(trades=trades):
                arguments = fixture()
                arguments['sessions'][0]['trade_shares'] = trades
                for sid in trades:
                    arguments['sessions'][0]['open_prices'].setdefault(sid, '1')
                    arguments['sessions'][0]['close_prices'].setdefault(sid, '1')
                with self.assertRaises(ValueError):
                    account_path(**arguments)

    def test_sell_fees_cannot_be_omitted_at_cash_boundary(self):
        arguments = fixture()
        arguments['initial']['cash_usd'] = '0'
        arguments['sessions'] = [dict(session='2026-03-31', open_prices={'A': '10', 'B': '99'},
                                     close_prices={'A': '10', 'B': '99'}, cash_injection_usd='0',
                                     trade_shares={'A': -10, 'B': 1})]
        with self.assertRaisesRegex(ValueError, 'both-side fees'):
            account_path(**arguments)
        arguments['sessions'][0]['cash_injection_usd'] = '0.99'
        self.assertEqual(account_path(**arguments)['rows'][0]['cash_after_usd'], '0')


if __name__ == '__main__':
    unittest.main()
