"""Independent adversarial checks of one-shot cash-rejection recovery."""
import unittest
from types import FunctionType
import pandas as pd

from test_ndx_next_session_execution_research import fixture
from backtest import ndx_cash_rejection_replan_research as candidate
from backtest.ndx_next_session_execution_research_v2 import simulate_next_session_execution_research_v2


def inputs_for_rejection():
    inputs = fixture()
    inputs['corporate_actions'] = []
    inputs['prices'].iloc[1:] = 12.
    return inputs


class CashReplanAdversarialTests(unittest.TestCase):
    def test_new_original_decision_gets_own_single_recovery_budget(self):
        inputs = inputs_for_rejection()
        dates = pd.bdate_range('2023-01-02', periods=7)
        inputs['execution_calendar'] = dates
        inputs['prices'] = pd.DataFrame([[v]*3 for v in (10., 12., 20., 10., 12., 20., 20.)],
                                         index=dates, columns=list('ABC'))
        inputs['schedule'] = [(dates[index], dict(A=1/3, B=1/3, C=1/3)) for index in (0, 3)]
        result = candidate.simulate_cash_rejection_replan(**inputs)
        self.assertEqual(len(result['executions']), 4)
        self.assertTrue(all(row['status'] == 'REJECTED_INSUFFICIENT_CASH_AT_FILL'
                            for row in result['executions']))
        self.assertEqual(result['supplemental_decision_count'], 2)
        parents = [row['parent_decision_id'] for row in result['decision_lineage']]
        self.assertEqual(parents, ['2023-01-02', '2023-01-02', '2023-01-05', '2023-01-05'])
        self.assertEqual(result['execution_lineage'], [
            dict(execution_date=str(dates[index+1].date()), **lineage)
            for index, lineage in zip((0, 1, 3, 4), result['decision_lineage'])])
        self.assertEqual(result['total_fees_usd'], 0.)

    def test_future_prices_cannot_rewrite_recovery_quantity(self):
        inputs = inputs_for_rejection()
        stable = candidate.simulate_cash_rejection_replan(**inputs)
        changed_inputs = {**inputs, 'prices': inputs['prices'].copy()}
        changed_inputs['prices'].iloc[2:] = 20.
        changed = candidate.simulate_cash_rejection_replan(**changed_inputs)
        self.assertEqual(stable['decisions'], changed['decisions'])
        self.assertEqual(stable['daily'][:2], changed['daily'][:2])
        self.assertEqual(len(stable['decisions']), 2)
        self.assertEqual(stable['executions'][1]['status'], 'FILLED')
        self.assertEqual(changed['executions'][1]['status'], 'REJECTED_INSUFFICIENT_CASH_AT_FILL')
        self.assertEqual(len(changed['executions']), 2)
        self.assertEqual(changed['total_fees_usd'], 0.)
        self.assertEqual(changed['terminal_cash_usd'], 100.)
        self.assertEqual(changed['terminal_shares'], inputs['initial_shares'])
        self.assertIsNone(changed['pending_plan'])
        for result in (stable, changed):
            self.assertEqual(result['decisions'][0]['target_weights'], result['decisions'][1]['target_weights'])
            self.assertEqual(result['decisions'][1]['decision_date'], '2023-01-03')
            self.assertEqual(result['executions'][1]['execution_date'], '2023-01-04')

    def test_scheduled_decision_has_priority_even_when_infeasible(self):
        inputs = inputs_for_rejection()
        inputs['prices'].iloc[1:] = 100.
        new_weights = dict(A=.4, B=.3, C=.3)
        inputs['schedule'].append((inputs['execution_calendar'][1], new_weights))
        result = candidate.simulate_cash_rejection_replan(**inputs)
        self.assertEqual(len(result['decisions']), 2)
        self.assertEqual(result['decisions'][1]['target_weights'], new_weights)
        self.assertEqual(result['decisions'][1]['status'], 'UNRESOLVED_NO_FEASIBLE_OBSERVED_NO_PLAN')
        self.assertEqual(len(result['executions']), 1)
        self.assertIsNone(result['pending_plan'])

    def test_terminal_cash_rejection_records_pending_not_imaginary_fill(self):
        inputs = inputs_for_rejection()
        inputs['prices'] = inputs['prices'].iloc[:2].copy()
        inputs['execution_calendar'] = inputs['execution_calendar'][:2]
        result = candidate.simulate_cash_rejection_replan(**inputs)
        self.assertEqual(len(result['executions']), 1)
        self.assertEqual(len(result['decisions']), 2)
        self.assertEqual(result['pending_plan']['status'], 'PENDING_OUTSIDE_EVALUATION')
        self.assertIsNone(result['pending_plan']['expected_execution_date'])
        self.assertEqual(result['terminal_shares'], inputs['initial_shares'])
        self.assertEqual(result['terminal_cash_usd'], 100.)

    def test_split_cancellation_never_becomes_cash_recovery(self):
        inputs = inputs_for_rejection()
        inputs['corporate_actions'] = [dict(ticker='A', session='2023-01-03',
            new_shares=2, old_shares=1, source_url='https://example.org/split', evidence_sha256='a'*64)]
        result = candidate.simulate_cash_rejection_replan(**inputs)
        self.assertEqual(len(result['decisions']), 1)
        self.assertEqual(result['executions'], [])
        self.assertEqual(result['cancelled_pending_plan_count'], 1)
        self.assertIsNone(result['pending_plan'])

    def test_no_rejection_full_economic_path_matches_original(self):
        inputs = fixture()
        inputs['corporate_actions'] = []
        original = simulate_next_session_execution_research_v2(**inputs)
        recovered = candidate.simulate_cash_rejection_replan(**inputs)
        for field in ('daily', 'decisions', 'executions', 'pending_plan', 'terminal_shares',
                      'terminal_cash_usd', 'total_fees_usd', 'path_return_net', 'path_max_drawdown'):
            self.assertEqual(original[field], recovered[field], field)

    def test_baseline_drift_rejection_is_not_cash_recovery(self):
        inputs = inputs_for_rejection()
        function = candidate.simulate_cash_rejection_replan
        bindings = dict(function.__globals__)
        original_fill = bindings['_fill_frozen_plan']

        def drift_fill(plan, shares, cash, marks, minimum_cash_buffer_usd):
            # Alter the declared plan baseline, not the real account or status.
            plan = {**plan, 'baseline_cash_usd': plan['baseline_cash_usd'] + 1.}
            return original_fill(plan, shares, cash, marks, minimum_cash_buffer_usd)

        bindings['_fill_frozen_plan'] = drift_fill
        isolated = FunctionType(function.__code__, bindings)
        result = isolated(**inputs)
        self.assertEqual(result['executions'][0]['status'], 'REJECTED_ACCOUNT_BASELINE_DRIFT')
        self.assertLess(result['executions'][0]['hypothetical_posttrade_cash_usd'], 5.)
        self.assertEqual(len(result['decisions']), 1)
        self.assertEqual(len(result['executions']), 1)
        self.assertEqual(result['terminal_cash_usd'], 100.)
        self.assertIsNone(result['pending_plan'])


if __name__ == '__main__':
    unittest.main()
