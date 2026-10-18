from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.ndx_single_replacement_path_requests_research import prepare_single_replacement_path_requests
from backtest.ndx_signed_cash_flow_return_accounting_research import account_path
from backtest.ndx_signed_cash_flow_account_inspection_research import inspect_saved_signed_account
from test_ndx_single_replacement_path_requests_research import fixture


class RootIntegration(unittest.TestCase):
    def test_complete_synthetic_forty_requests_account_and_independent_inspection(self):
        arguments = fixture()
        original = deepcopy(arguments)
        result = prepare_single_replacement_path_requests(**arguments)
        self.assertEqual(len(result['rows']), 40)
        for row in result['rows']:
            with self.subTest(scenario=row['scenario_id']):
                request = row['accounting_request']
                saved = account_path(**request)
                inspected = inspect_saved_signed_account(**request, saved_result=saved)
                expected = row['expected_first_trade']
                self.assertEqual(inspected['status'], 'PASS')
                self.assertEqual(Fraction(saved['rows'][0]['fees_usd']), Fraction(expected['total_fee_usd']))
                self.assertEqual(Fraction(saved['rows'][0]['cash_after_usd']), Fraction(expected['cash_after_usd']))
                self.assertEqual(saved['rows'][0]['holdings_after'], row['selection_row']['selected']['task']['proposed_holdings'])
                self.assertEqual(saved['total_cash_injection_usd'], request['sessions'][0]['cash_injection_usd'])
                self.assertTrue(all(item['trade_shares'] == {} for item in saved['rows'][1:]))
                self.assertFalse(inspected['point_in_time_verified'])
                self.assertIsNone(row['reused_candidate_path_reference'])
        self.assertEqual(arguments, original)


if __name__ == '__main__':
    unittest.main()
