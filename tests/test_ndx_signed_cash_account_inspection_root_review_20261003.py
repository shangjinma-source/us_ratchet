from copy import deepcopy
from decimal import Inexact, localcontext
from fractions import Fraction
import unittest
from unittest.mock import patch

from backtest import ndx_signed_cash_flow_return_accounting_research as producer
from backtest import ndx_signed_cash_flow_account_inspection_research as reader


class RootReview(unittest.TestCase):
    def test_sub_cent_sell_fee_is_reconstructed_without_producer_helpers(self):
        arguments = dict(
            initial=dict(session='2026-03-30', cash_usd='1', holdings={'A': 1}, close_prices={'A': '1e-40'}),
            sessions=[dict(session='2026-03-31', open_prices={'A': '1e-40'}, close_prices={'A': '1e-40'},
                           cash_injection_usd='0', trade_shares={'A': -1})],
            transaction_cost_bps='1e-40')
        saved = producer.account_path(**arguments)
        self.assertEqual(Fraction(saved['total_fees_usd']), Fraction(1, 10**84))
        self.assertEqual(Fraction(saved['terminal_equity_usd']), 1 + Fraction(1, 10**40) - Fraction(1, 10**84))
        with (patch.object(producer, 'account_path', side_effect=AssertionError('No producer')),
              patch.object(producer, 'money', side_effect=AssertionError('No helper'))):
            with localcontext() as context:
                context.prec = 1
                context.traps[Inexact] = True
                result = reader.inspect_saved_signed_account(**arguments, saved_result=saved)
            self.assertEqual(result['status'], 'PASS')
            corrupt = deepcopy(saved)
            corrupt['rows'][0]['fees_usd'] = '0'
            corrupt['total_fees_usd'] = '0'
            with self.assertRaises(ValueError):
                reader.inspect_saved_signed_account(**arguments, saved_result=corrupt)


if __name__ == '__main__':
    unittest.main()
