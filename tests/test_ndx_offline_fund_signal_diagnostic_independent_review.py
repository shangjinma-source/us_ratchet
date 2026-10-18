"""Independent adversarial acceptance; no live API or account access."""
import copy
from decimal import Decimal, localcontext, ROUND_DOWN, ROUND_UP
import unittest

from backtest.ndx_offline_fund_signal_diagnostic_research import diagnose


class IndependentDiagnosticReview(unittest.TestCase):
    def arguments(self):
        return dict(execution_items=[dict(ticker='MSFT', side='BUY', source='tactical_limit',
                    action='BUY_NOW', amount='1000', limit='100', share_plan_eligible=True)],
                    gap_rows=[dict(ticker='MSFT', position_kind='real_position', gap_amount='1000')],
                    policy=dict(allow_fractional=False, lot_size=1, fee_bps=10, min_fee=1),
                    research_cash_usd='1000')

    def test_whole_share_policy_rejects_fractional_lot(self):
        arguments = self.arguments()
        for lot in ['0.5', '1.5']:
            arguments['policy']['lot_size'] = lot
            row = diagnose(**arguments)['rows'][0]
            self.assertIsNot(row['first_unit_affordable'], True)
            self.assertNotEqual(row['gates']['whole_unit_policy']['status'], 'PASS')

    def test_unknown_position_kind_never_passes(self):
        arguments = self.arguments()
        for kind in ['not_a_position', 'REAL_POSITION', ' ', None]:
            arguments['gap_rows'][0]['position_kind'] = kind
            row = diagnose(**arguments)['rows'][0]
            self.assertIsNot(row['first_unit_affordable'], True)
            self.assertNotEqual(row['gates']['position_kind']['status'], 'PASS')

    def test_blank_ticker_never_passes_even_matching_gap(self):
        arguments = self.arguments()
        for ticker in ['', ' ', '\t', None]:
            arguments['execution_items'][0]['ticker'] = ticker
            arguments['gap_rows'][0]['ticker'] = ticker
            row = diagnose(**arguments)['rows'][0]
            self.assertIsNot(row['first_unit_affordable'], True)
            self.assertNotEqual(row['gates']['ticker']['status'], 'PASS')

    def test_caller_decimal_context_cannot_change_gate(self):
        arguments = self.arguments()
        arguments['execution_items'][0].update(amount='100.00', limit='100.019')
        results = []
        for precision, rounding in [(28, ROUND_DOWN), (3, ROUND_DOWN), (3, ROUND_UP)]:
            with localcontext() as context:
                context.prec = precision
                context.rounding = rounding
                results.append(diagnose(**arguments))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        self.assertIs(results[0]['rows'][0]['first_unit_affordable'], False)

    def test_independent_rows_do_not_claim_joint_cash_or_capital(self):
        arguments = self.arguments()
        arguments['research_cash_usd'] = '101'
        second_item = copy.deepcopy(arguments['execution_items'][0])
        second_item['ticker'] = 'GOOG'
        second_gap = copy.deepcopy(arguments['gap_rows'][0])
        second_gap['ticker'] = 'GOOG'
        arguments['execution_items'].append(second_item)
        arguments['gap_rows'].append(second_gap)
        report = diagnose(**arguments)
        self.assertTrue(all(row['first_unit_affordable'] for row in report['rows']))
        self.assertTrue(report['independent_row_cash_checks_are_not_joint_allocation'])
        self.assertFalse(report['portfolio_allocation_performed'])
        self.assertFalse(report['core_deployment_planner_called'])
        self.assertFalse(report['dynamic_optimization_performed'])
        self.assertTrue(all(row['allocated_shares'] is None for row in report['rows']))
        self.assertTrue(all(not row['order_authorized'] for row in report['rows']))

    def test_three_long_decimal_operands_have_exact_fee(self):
        arguments = self.arguments()
        integer = '123456789012345678901234567890123456789012345678901234567890123456789012345678901'
        arguments['execution_items'][0]['limit'] = integer
        arguments['policy'].update(lot_size=integer, fee_bps=integer, min_fee=0)
        with localcontext() as context:
            context.prec = 300
            exact_fee = Decimal(integer) ** 3 / Decimal(10000)
        report = diagnose(**arguments)
        self.assertEqual(Decimal(report['rows'][0]['one_unit_fee_usd']), exact_fee)


if __name__ == '__main__':
    unittest.main()
