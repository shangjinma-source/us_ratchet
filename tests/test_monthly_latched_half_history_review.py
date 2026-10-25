"""Independent synthetic checks; no historical economic replay."""
from copy import deepcopy
import unittest

import test_continuous_guided_cost_stress as fixtures
from backtest.continuous_guided_cost_stress import prepare_arm, SCENARIOS, run_cost_stress_arm
from backtest.continuous_guided_monthly_latched_half_next_open import run_cost_monthly_latched_half_next_open


class HistoryReviewTests(unittest.TestCase):
    def run_candidate(self, assembled, bars, resolver, scenario):
        return run_cost_monthly_latched_half_next_open(
            assembled=prepare_arm(assembled, scenario), ohlc=bars,
            history_resolver=resolver, initial_cash='1000', **SCENARIOS[scenario])

    def test_future_completed_close_and_wrong_units_stop_before_fill(self):
        for fault in ('completion', 'future_date', 'unit', 'current_price'):
            with self.subTest(fault=fault):
                assembled, bars, resolver = fixtures.CostStressTests().data()

                def invalid_history(**kwargs):
                    value = deepcopy(resolver(**kwargs))
                    if fault == 'completion':
                        value['histories']['A']['closes'][-1]['completed_at'] = '2099-01-01T16:00:00-05:00'
                    elif fault == 'future_date':
                        value['histories']['A']['closes'][-1]['date'] = '2099-01-01'
                    elif fault == 'unit':
                        value['base_target']['price_units']['A'] = 'UNVERIFIED_UNIT'
                    else:
                        value['histories']['A']['closes'][-1]['close'] = '999'
                    return value

                result = self.run_candidate(assembled, bars, invalid_history, 'slippage5')
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertFalse(any(row['event'] == 'ASSUMED_NEXT_OPEN_FILLED'
                                     for row in result['order_log']))

    def test_always_strong_matches_real_full_book_under_both_costs(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                assembled, bars, resolver = fixtures.CostStressTests().data()

                def strong_history(**kwargs):
                    value = deepcopy(resolver(**kwargs))
                    for history in value['histories'].values():
                        for row in history['closes'][:-1]:
                            row['close'] = '1'
                    return value

                candidate = self.run_candidate(assembled, bars, strong_history, scenario)
                baseline = run_cost_stress_arm(arm='continuous32', scenario=scenario,
                    assembled=assembled, ohlc=bars, initial_cash='1000')
                self.assertEqual(candidate['status'], 'COMPLETE')
                self.assertEqual(candidate['daily_ledger'], baseline['daily_ledger'])
                self.assertEqual(candidate['selection_account_states'], baseline['selection_account_states'])
                self.assertEqual(candidate['fees'], baseline['fees'])


if __name__ == '__main__':
    unittest.main()
