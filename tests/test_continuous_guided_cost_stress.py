from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch
import test_continuous_guided_half_next_open as half_tests
from backtest.continuous_guided_cost_stress import prepare_arm, run_cost_stress_arm
from backtest import continuous_guided_account_decision as selector
from backtest.continuous_guided_cost_half_next_open import run_cost_half_next_open


class CostStressTests(unittest.TestCase):
    def data(self):
        assembled, bars, resolver = half_tests.GuidedHalfTests().data()
        assembled['monthly_inputs'][0]['search_arguments']['max_objective_evaluations'] = 8192
        return assembled, bars, resolver

    def test_fixed_scenario_alignment_and_no_mutation(self):
        assembled, _, _ = self.data()
        saved = deepcopy(assembled)
        result = prepare_arm(assembled, 'fee1_slippage10')
        self.assertEqual(result['monthly_inputs'][0]['search_arguments']['fee_bps'], '1')
        self.assertEqual(assembled, saved)
        with self.assertRaises(ValueError): prepare_arm(assembled, 'best_cost')
        assembled['monthly_inputs'][0]['search_arguments']['max_objective_evaluations'] = 32
        with self.assertRaises(ValueError): prepare_arm(assembled, 'slippage5')

    def test_cost_arithmetic_half_recovery_and_own_capital(self):
        assembled, bars, resolver = self.data()
        day = assembled['session_dates'][2]
        second = deepcopy(assembled['monthly_inputs'][0])
        second['decision_date'] = day
        second['search_arguments'].update(decision_date=day, quote_as_of=day,
                                         prices={'A': assembled['close_prices']['A'][day]})
        second['valuation_quotes'][0].update(as_of=day, price=assembled['close_prices']['A'][day])
        assembled['monthly_inputs'].append(second)
        with patch.object(selector, 'original_search', wraps=selector.original_search) as search:
            result = run_cost_stress_arm(arm='continuous32_half', scenario='fee1_slippage10',
                assembled=assembled, ohlc=bars, initial_cash='1000', history_resolver=resolver)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(search.call_count, 2)
        self.assertTrue(all(str(call.kwargs['fee_bps']) == '1' for call in search.call_args_list))
        fills = [row for row in result['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual({row['side'] for row in fills}, {'BUY', 'SELL'})
        total_fee = Fraction(0)
        for row in fills:
            opening = Fraction(bars[row['security_id']][row['date']]['open'])
            multiplier = Fraction(1001 if row['side'] == 'BUY' else 999, 1000)
            self.assertEqual(Fraction(row['price']), opening * multiplier)
            fee = row['quantity'] * Fraction(row['price']) / 10000
            self.assertEqual(Fraction(row['fee']), fee)
            self.assertGreaterEqual(Fraction(row['cash_after']), 0)
            total_fee += fee
        self.assertEqual(Fraction(result['fees']), total_fee)
        state = result['selection_account_states'][1]['account_state']
        ledger = next(row for row in result['daily_ledger'] if row['date'] == day)
        self.assertEqual((state['cash'], state['shares']), (ledger['cash'], ledger['shares']))
        wealth = Fraction(state['cash']) + sum(q * Fraction(assembled['close_prices'][sid][day]) for sid, q in state['shares'].items())
        self.assertEqual(Fraction(search.call_args_list[1].kwargs['entered_cash']), wealth)

    def test_all_on_matches_nohalf_both_costs(self):
        assembled, bars, resolver = self.data()
        def always_on(**kwargs):
            inputs = resolver(**kwargs)
            for history in inputs['histories'].values():
                for row in history['closes'][:-1]: row['close'] = '1'
            return inputs
        for scenario in ('slippage5', 'fee1_slippage10'):
            common = dict(scenario=scenario, assembled=assembled, ohlc=bars, initial_cash='1000')
            half = run_cost_stress_arm(arm='continuous32_half', history_resolver=always_on, **common)
            full = run_cost_stress_arm(arm='continuous32', **common)
            self.assertEqual(half['status'], 'COMPLETE')
            self.assertEqual(half['daily_ledger'], full['daily_ledger'])
            self.assertEqual(half['selection_account_states'], full['selection_account_states'])

    def test_direct_half_rejects_unaligned_fees(self):
        assembled, bars, resolver = self.data()
        with self.assertRaisesRegex(ValueError, 'MONTHLY_EXECUTION_FEE_MISMATCH'):
            run_cost_half_next_open(assembled=assembled, ohlc=bars, initial_cash='1000',
                fee_bps='1', slippage_bps='10', history_resolver=resolver)


if __name__ == '__main__': unittest.main()
