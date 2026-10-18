from datetime import date, timedelta
from fractions import Fraction
import unittest

from scripts.return_priority_sma20_ablation_research import build_sma20_plans
from backtest.return_priority_paper_continuous_book_research import simulate_paper_book


class SMA20Tests(unittest.TestCase):
    def args(self):
        calendar = [(date(2026, 1, 1)+timedelta(days=i)).isoformat() for i in range(25)]
        return dict(calendar=calendar, close_by_security={'A': [10]*19+[11, 9, 12, 9, object(), object()]},
                    frozen_weights={'A': '1'}, decision_date=calendar[19], end_date=calendar[22])

    def test_future_poison_terminal_signal_and_full_off_reentry(self):
        args = self.args()
        result = build_sma20_plans(**args)
        self.assertEqual(len(result['plans']), 3)
        self.assertEqual(result['plans'][1]['target_shares'], {})
        self.assertEqual(result['plans'][2]['target_weights'], {'A': '1'})
        self.assertTrue(result['signals'][-1]['terminal_signal_only'])
        self.assertTrue(result['signals'][-1]['changed'])
        self.assertFalse(result['signals'][-1]['plan_submitted'])

    def test_boundary_equality_subset_and_no_daily_rebalance(self):
        args = self.args()
        args['frozen_weights'] = {'A': '1/4', 'B': '1/2'}
        args['close_by_security'] = {'A': [10]*19+[11]*4, 'B': [10]*23}
        result = build_sma20_plans(**args)
        self.assertEqual(len(result['plans']), 1)
        self.assertEqual(result['plans'][0]['target_weights'], {'A': '1/4'})
        self.assertEqual(result['signals'][0]['target_cash_fraction'], '3/4')
        self.assertFalse(result['signals'][0]['securities']['B']['on'])
        args['decision_date'] = args['calendar'][18]
        with self.assertRaises(ValueError):
            build_sma20_plans(**args)

    def test_next_open_gap_liquidation_and_reentry(self):
        args = self.args(); plan = build_sma20_plans(**args)
        dates = args['calendar'][19:23]
        opens = {day: {'A': price} for day, price in zip(dates, [11, 20, 15, 10])}
        closes = {day: {'A': price} for day, price in zip(dates, [11, 9, 12, 9])}
        book = simulate_paper_book(calendar=dates, open_prices=opens, close_prices=closes,
            metadata={'A': dict(ticker='A', issuer_id='A', risk_chain='A')}, initial_shares={},
            initial_cash=100, fee_bps=0, minimum_cash_buffer=0, decisions=plan['plans'], cash_events=[],
            risk_parameters=dict(min_single_weight=0, max_single_weight=1, top_three_cap=1, min_neff_ratio=0, chain_cap=1),
            enforce_initial_target_risk=False, declared_price_basis='CONDITIONAL_SYNTHETIC')
        self.assertEqual(book['status'], 'COMPLETE_CONDITIONAL_PAPER_BOOK')
        self.assertEqual(book['executions'][0]['target_shares'], {'A': 5})
        self.assertEqual(book['executions'][1]['target_shares'], {})
        self.assertEqual(book['executions'][2]['target_shares'], {'A': 7})
        self.assertEqual(Fraction(book['final_cash']), 5)
        self.assertEqual(book['executions'][0]['execution_date'], dates[1])

    def test_missing_observed_close_rejected(self):
        args = self.args(); args['close_by_security']['A'][18] = None
        with self.assertRaises(ValueError):
            build_sma20_plans(**args)


if __name__ == '__main__':
    unittest.main()
