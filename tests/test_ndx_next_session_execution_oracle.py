import copy
import unittest

import pandas as pd

from backtest import ndx_next_session_execution_research as execution


def arguments():
    dates = pd.bdate_range('2024-01-02', periods=4)
    names = list('ABCD')
    return dict(prices=pd.DataFrame(10., index=dates, columns=names), execution_calendar=dates,
        schedule=[(dates[0], {ticker: .25 for ticker in names}),
                  (dates[-1], {ticker: .25 for ticker in names})],
        initial_cash=1000., initial_shares={ticker: 0 for ticker in names},
        minimum_cash_buffer_usd=100., transaction_cost_bps=10.,
        risk_chain_by_ticker={ticker: ticker for ticker in names},
        constraints=dict(max_single_weight=.5, min_single_weight=.1, top_weight_cap=.9,
                         minimum_effective_n_ratio=.5, risk_chain_top1_cap=.5),
        domain_radius=1, max_evaluations_per_rebalance=10000, selection_policy='TRACKING_FIRST')


class NextSessionExecutionOracleTests(unittest.TestCase):
    def test_next_price_cannot_change_frozen_order_but_can_reject_whole_basket(self):
        original = arguments()
        accepted = execution.simulate_next_session_execution_research(**original)
        jumped = copy.deepcopy(original)
        jumped['prices'].iloc[1] = 20.
        rejected = execution.simulate_next_session_execution_research(**jumped)
        self.assertEqual(accepted['decisions'][0], rejected['decisions'][0])
        self.assertEqual(accepted['executions'][0]['status'], 'FILLED')
        fill = rejected['executions'][0]
        self.assertEqual(fill['status'], 'REJECTED_INSUFFICIENT_CASH_AT_FILL')
        self.assertEqual(fill['fees_usd'], 0.)
        self.assertEqual(fill['trade_notional_usd'], 0.)
        self.assertEqual(fill['posttrade_shares'], original['initial_shares'])
        self.assertEqual(fill['posttrade_cash_usd'], original['initial_cash'])
        self.assertEqual(len(rejected['executions']), 1, 'Rejected plans must not automatically retry')

    def test_future_after_fill_cannot_change_prior_decision_or_execution(self):
        original = arguments()
        reference = execution.simulate_next_session_execution_research(**original)
        altered = copy.deepcopy(original)
        altered['prices'].iloc[2:] = [23., 4., 12., 7.]
        changed = execution.simulate_next_session_execution_research(**altered)
        self.assertEqual(reference['decisions'][0], changed['decisions'][0])
        self.assertEqual(reference['executions'][0], changed['executions'][0])
        self.assertEqual(reference['daily'][:2], changed['daily'][:2])

    def test_last_decision_pending_and_initial_positions_in_equity_peak(self):
        inputs = arguments()
        inputs['initial_shares'] = {ticker: 1 for ticker in inputs['prices']}
        result = execution.simulate_next_session_execution_research(**inputs)
        self.assertEqual(result['initial_equity_usd'], 1040.)
        self.assertEqual(result['daily'][0]['shares'], inputs['initial_shares'])
        self.assertEqual(result['pending_plan']['status'], 'PENDING_OUTSIDE_EVALUATION')
        self.assertIsNone(result['pending_plan']['expected_execution_date'])
        self.assertEqual(len(result['executions']), 1)
        self.assertEqual(result['trade_execution_count'], 1)
        self.assertAlmostEqual(result['path_max_drawdown'], result['total_fees_usd'] / 1040.)

    def test_fill_oracle_uses_gross_actual_turnover_and_allows_declared_sale_proceeds(self):
        plan = dict(baseline_shares={'A': 2, 'B': 1}, baseline_cash_usd=100.,
                    delta_shares={'A': -1, 'B': 1}, transaction_cost_bps=100., decision_date='2024-01-02')
        fill = execution._fill_frozen_plan(plan, {'A': 2, 'B': 1}, 100., {'A': 15., 'B': 12.}, 100.)
        self.assertEqual(fill['status'], 'FILLED')
        self.assertAlmostEqual(fill['fees_usd'], .27)
        self.assertAlmostEqual(fill['posttrade_cash_usd'], 102.73)
        self.assertEqual(fill['posttrade_shares'], {'A': 1, 'B': 2})
        before_equity = 100. + 2 * 15. + 12.
        after_equity = fill['posttrade_cash_usd'] + 15. + 2 * 12.
        self.assertAlmostEqual(before_equity - after_equity, .27)

    def test_positive_cash_below_buffer_still_rejects_and_account_drift_rejects(self):
        plan = dict(baseline_shares={'A': 1, 'B': 1}, baseline_cash_usd=110.,
                    delta_shares={'A': 1, 'B': 0}, transaction_cost_bps=0., decision_date='2024-01-02')
        fill = execution._fill_frozen_plan(plan, {'A': 1, 'B': 1}, 110., {'A': 11., 'B': 10.}, 100.)
        self.assertEqual(fill['hypothetical_posttrade_cash_usd'], 99.)
        self.assertEqual(fill['status'], 'REJECTED_INSUFFICIENT_CASH_AT_FILL')
        for shares, cash in (({'A': 2, 'B': 1}, 110.), ({'A': 1, 'B': 1}, 111.)):
            drifted = execution._fill_frozen_plan(plan, shares, cash, {'A': 1., 'B': 1.}, 100.)
            self.assertEqual(drifted['status'], 'REJECTED_ACCOUNT_BASELINE_DRIFT')
            self.assertEqual(drifted['posttrade_shares'], shares)
            self.assertEqual(drifted['posttrade_cash_usd'], cash)
            self.assertEqual(drifted['fees_usd'], 0.)

    def test_declared_calendar_missing_interior_row_rejected(self):
        inputs = arguments()
        inputs['prices'] = inputs['prices'].drop(inputs['execution_calendar'][1])
        with self.assertRaisesRegex(ValueError, 'exactly match complete declared execution calendar'):
            execution.simulate_next_session_execution_research(**inputs)


if __name__ == '__main__':
    unittest.main()
