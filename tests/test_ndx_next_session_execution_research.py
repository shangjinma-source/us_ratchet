import unittest

import pandas as pd

from backtest.ndx_next_session_execution_research import simulate_next_session_execution_research as simulate


def fixture():
    dates = pd.bdate_range('2023-01-02', periods=4)
    prices = pd.DataFrame(10., index=dates, columns=list('ABC'))
    kwargs = dict(prices=prices, execution_calendar=dates,
        schedule=[(dates[0], dict(A=1/3, B=1/3, C=1/3))],
        initial_cash=100., initial_shares=dict(A=0, B=0, C=0),
        minimum_cash_buffer_usd=5., transaction_cost_bps=10.,
        risk_chain_by_ticker=dict(A='A', B='B', C='C'),
        constraints=dict(max_single_weight=.8, min_single_weight=.1, top_weight_cap=1.,
                         minimum_effective_n_ratio=.5, risk_chain_top1_cap=.8),
        domain_radius=1, max_evaluations_per_rebalance=1000, selection_policy='TRACKING_FIRST')
    return kwargs


class NextSessionExecutionTests(unittest.TestCase):
    def test_next_close_cannot_change_frozen_decision_and_cash_rejects(self):
        inputs = fixture()
        baseline = simulate(**inputs)
        prices = inputs['prices'].copy()
        prices.iloc[1] = 100.
        changed = simulate(**{**inputs, 'prices': prices})
        self.assertEqual(baseline['decisions'][0], changed['decisions'][0])
        self.assertEqual(changed['executions'][0]['status'], 'REJECTED_INSUFFICIENT_CASH_AT_FILL')
        self.assertEqual(changed['total_fees_usd'], 0.)
        self.assertEqual(changed['terminal_shares'], inputs['initial_shares'])
        self.assertEqual(changed['terminal_cash_usd'], inputs['initial_cash'])
        self.assertEqual(len(changed['executions']), 1)
        self.assertFalse(changed['daily'][1]['all_constraints_passed'])

    def test_future_prices_cannot_change_prior_decision_or_fill(self):
        inputs = fixture()
        baseline = simulate(**inputs)
        prices = inputs['prices'].copy()
        prices.iloc[2:] = 70.
        changed = simulate(**{**inputs, 'prices': prices})
        self.assertEqual(baseline['decisions'], changed['decisions'])
        self.assertEqual(baseline['executions'], changed['executions'])
        self.assertEqual(baseline['daily'][:2], changed['daily'][:2])

    def test_conservation_initial_equity_and_postfill_next_decision(self):
        inputs = fixture()
        inputs['initial_shares'] = dict(A=1, B=2, C=1)
        inputs['schedule'].append((inputs['execution_calendar'][1], dict(A=.4, B=.3, C=.3)))
        result = simulate(**inputs)
        self.assertEqual(result['initial_equity_usd'], 140.)
        first = result['executions'][0]
        for fill in result['executions']:
            self.assertEqual(fill['status'], 'FILLED')
            notional = sum(abs(fill['frozen_delta_shares'][t])*fill['fill_prices'][t] for t in 'ABC')
            self.assertAlmostEqual(fill['fees_usd'], notional*.001)
            cash = fill['pretrade_cash_usd']-sum(fill['frozen_delta_shares'][t]*fill['fill_prices'][t] for t in 'ABC')-fill['fees_usd']
            self.assertAlmostEqual(fill['posttrade_cash_usd'], cash)
            for ticker in 'ABC':
                self.assertEqual(fill['posttrade_shares'][ticker], fill['pretrade_shares'][ticker]+fill['frozen_delta_shares'][ticker])
        self.assertEqual(result['decisions'][1]['baseline_shares'], first['posttrade_shares'])
        self.assertEqual(result['decisions'][1]['baseline_cash_usd'], first['posttrade_cash_usd'])
        self.assertAlmostEqual(result['path_max_drawdown'], result['total_fees_usd']/140.)

    def test_last_day_pending_is_not_execution(self):
        inputs = fixture()
        inputs['schedule'] = [(inputs['execution_calendar'][-1], dict(A=1/3, B=1/3, C=1/3))]
        result = simulate(**inputs)
        self.assertEqual(result['executions'], [])
        self.assertEqual(result['trade_execution_count'], 0)
        self.assertEqual(result['pending_plan']['status'], 'PENDING_OUTSIDE_EVALUATION')
        self.assertEqual(result['terminal_cash_usd'], 100.)

    def test_missing_duplicate_unsorted_calendar_rejected(self):
        inputs = fixture()
        for dates in (inputs['execution_calendar'].delete(1),
                      inputs['execution_calendar'][[0, 1, 1, 3]],
                      inputs['execution_calendar'][::-1]):
            with self.assertRaises(ValueError):
                simulate(**{**inputs, 'execution_calendar': dates})
        with self.assertRaises(ValueError):
            simulate(**{**inputs, 'prices': inputs['prices'].drop(inputs['execution_calendar'][1])})


if __name__ == '__main__':
    unittest.main()
