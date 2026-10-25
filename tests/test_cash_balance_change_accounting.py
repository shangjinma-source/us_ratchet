import unittest
from backtest.cash_balance_change_accounting import replace_available_cash, unitized_performance


class CashBalanceChangeTests(unittest.TestCase):
    def test_user_deposit_and_withdrawal_are_not_returns(self):
        for cash, flow, equity in [('30000', '20000', '50000'), ('5000', '-5000', '25000')]:
            with self.subTest(cash=cash):
                change = replace_available_cash(previous_cash='10000', entered_cash=cash,
                                                tradable_stock_value='20000')
                self.assertEqual(change['cash'], cash)
                self.assertEqual(change['external_flow'], flow)
                self.assertEqual(change['equity_after'], equity)
                metric = unitized_performance(initial_equity='30000', observations=[dict(
                    date='2026-10-01', close_equity=equity, **change)])
                self.assertEqual(metric['time_weighted_return'], '0')
                self.assertEqual(metric['maximum_flow_adjusted_drawdown'], '0')

    def test_repeat_total_is_not_another_deposit_and_pending_rights_cannot_fund_selection(self):
        change = replace_available_cash(previous_cash='30000', entered_cash='30000',
                                        tradable_stock_value='20000', nontradable_value='4000')
        self.assertEqual(change['external_flow'], '0')
        self.assertEqual(change['selection_equity'], '50000')
        self.assertEqual(change['equity_after'], '54000')

    def test_deposit_does_not_hide_loss_and_withdrawal_does_not_create_loss(self):
        metric = unitized_performance(initial_equity='30000', observations=[
            dict(date='2026-10-01', equity_before='27000', external_flow='20000',
                 equity_after='47000', close_equity='47000'),
            dict(date='2026-10-02', equity_before='47000', external_flow='-5000',
                 equity_after='42000', close_equity='46200')])
        self.assertEqual(metric['time_weighted_return'], '-1/100')
        self.assertEqual(metric['maximum_flow_adjusted_drawdown'], '1/10')

    def test_unreconciled_flow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'RECONCILIATION'):
            unitized_performance(initial_equity='30000', observations=[dict(
                date='2026-10-01', equity_before='30000', external_flow='20000',
                equity_after='70000', close_equity='70000')])

    def test_clustered_exchange_then_stable_period_has_no_artificial_gain(self):
        cash = '10000'
        rows = []
        for day, new_cash in [('01', '15000'), ('02', '20000'), ('03', '30000'),
                              ('04', '30000'), ('05', '30000')]:
            change = replace_available_cash(previous_cash=cash, entered_cash=new_cash,
                                            tradable_stock_value='20000')
            rows.append(dict(date='2026-10-'+day, close_equity=change['equity_after'], **change))
            cash = new_cash
        result = unitized_performance(initial_equity='30000', observations=rows)
        self.assertEqual([r['external_flow'] for r in rows], ['5000', '5000', '10000', '0', '0'])
        self.assertEqual(result['time_weighted_return'], '0')
        self.assertEqual(result['maximum_flow_adjusted_drawdown'], '0')

    def test_booked_sale_is_reconciled_before_cash_confirmation(self):
        # Selling stock transfers value to cash. Confirming that current cash
        # must not classify the sale proceeds as an external contribution.
        change = replace_available_cash(previous_cash='15000', entered_cash='15000',
                                        tradable_stock_value='15000')
        self.assertEqual(change['external_flow'], '0')
        self.assertEqual(change['equity_after'], '30000')


if __name__ == '__main__':
    unittest.main()
