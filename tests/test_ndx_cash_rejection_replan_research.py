import unittest
from unittest.mock import patch

from test_ndx_next_session_execution_research import fixture
from test_ndx_next_session_execution_research_v2 import event
from backtest import ndx_cash_rejection_replan_research as engine
from backtest.ndx_next_session_execution_research_v2 import simulate_next_session_execution_research_v2 as old
from backtest.ndx_incumbent_cash_rejection_replan_research import simulate_fixed_weight_incumbent_replan as control
from backtest.ndx_incumbent_execution_control_research_v2 import simulate_fixed_weight_incumbent_control_v2 as old_control


def inputs():
    result = fixture()
    result['corporate_actions'] = []
    return result


def control_inputs(values):
    values = dict(values)
    schedule = values.pop('schedule')
    values.pop('selection_policy')
    return dict(values, decision_dates=[d for d, _ in schedule], incumbent_weights=schedule[0][1])


class CashReplanTests(unittest.TestCase):
    def test_no_trigger_complete_old_fields_equal(self):
        values = inputs()
        before, after = old(**values), engine.simulate_cash_rejection_replan(**values)
        for key in before.keys() - {'schema', 'source_hashes'}:
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after['supplemental_decision_count'], 0)

    def test_future_cannot_change_replan_but_can_reject_again(self):
        values = inputs()
        values['prices'].iloc[1:] = 12.
        accepted = engine.simulate_cash_rejection_replan(**values)
        values['prices'].iloc[2:] = 100.
        rejected = engine.simulate_cash_rejection_replan(**values)
        self.assertEqual(accepted['decisions'], rejected['decisions'])
        self.assertEqual(accepted['daily'][:2], rejected['daily'][:2])
        self.assertEqual(accepted['executions'][1]['status'], 'FILLED')
        self.assertEqual([x['status'] for x in rejected['executions']],
                         ['REJECTED_INSUFFICIENT_CASH_AT_FILL'] * 2)
        self.assertEqual(rejected['supplemental_decision_count'], 1)
        self.assertEqual(rejected['total_fees_usd'], 0.)
        self.assertEqual(rejected['terminal_cash_usd'], values['initial_cash'])
        self.assertEqual(rejected['terminal_shares'], values['initial_shares'])
        self.assertIsNone(rejected['pending_plan'])
        self.assertEqual(accepted['decisions'][0]['target_weights'], accepted['decisions'][1]['target_weights'])
        self.assertNotEqual(accepted['decisions'][0]['target_shares'], accepted['decisions'][1]['target_shares'])
        self.assertEqual(accepted['decision_lineage'][1]['parent_decision_id'],
                         accepted['decisions'][0]['decision_date'])
        self.assertEqual(accepted['executions'][1]['decision_date'], str(values['execution_calendar'][1].date()))
        self.assertEqual(accepted['executions'][1]['execution_date'], str(values['execution_calendar'][2].date()))

    def test_original_schedule_has_priority(self):
        values = inputs()
        values['prices'].iloc[1:] = 12.
        values['schedule'].append((values['execution_calendar'][1], dict(A=.4, B=.3, C=.3)))
        result = engine.simulate_cash_rejection_replan(**values)
        self.assertEqual(len(result['decisions']), 2)
        self.assertEqual(result['supplemental_decision_count'], 0)
        self.assertEqual(result['decisions'][1]['target_weights'], values['schedule'][1][1])

    def test_period_end_pending_not_filled(self):
        values = inputs()
        values['execution_calendar'] = values['execution_calendar'][:2]
        values['prices'] = values['prices'].iloc[:2].copy()
        values['prices'].iloc[1] = 12.
        result = engine.simulate_cash_rejection_replan(**values)
        self.assertEqual(len(result['executions']), 1)
        self.assertEqual(result['pending_plan']['status'], 'PENDING_OUTSIDE_EVALUATION')
        self.assertIsNone(result['pending_plan']['expected_execution_date'])
        self.assertEqual(result['pending_lineage']['decision_kind'], 'ONE_REPLAN_AFTER_CASH_REJECTION')
        self.assertEqual(result['terminal_shares'], values['initial_shares'])

    def test_split_cancellation_never_replans(self):
        values = inputs()
        values['corporate_actions'] = [event(values['execution_calendar'][1])]
        before, after = old(**values), engine.simulate_cash_rejection_replan(**values)
        for key in before.keys() - {'schema', 'source_hashes'}:
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after['supplemental_decision_count'], 0)

    def test_baseline_drift_never_replans(self):
        values = inputs()
        original_fill = engine._fill_frozen_plan
        def changed_baseline(plan, *args):
            plan = dict(plan, baseline_cash_usd=-1.)
            return original_fill(plan, *args)
        with patch.object(engine, '_fill_frozen_plan', changed_baseline):
            result = engine.simulate_cash_rejection_replan(**values)
        self.assertEqual(result['executions'][0]['status'], 'REJECTED_ACCOUNT_BASELINE_DRIFT')
        self.assertEqual(result['supplemental_decision_count'], 0)
        self.assertEqual(len(result['executions']), 1)

    def test_no_feasible_replan_stops(self):
        values = inputs()
        values['prices'].iloc[1:] = 100.
        result = engine.simulate_cash_rejection_replan(**values)
        self.assertEqual(result['supplemental_decision_count'], 1)
        self.assertEqual(len(result['executions']), 1)
        self.assertEqual(result['decisions'][1]['status'], 'UNRESOLVED_NO_FEASIBLE_OBSERVED_NO_PLAN')
        self.assertTrue(result['any_unresolved_decision'])

    def test_control_same_policy_not_risk_projection(self):
        values = inputs()
        values['prices'].iloc[1:] = 12.
        candidate = engine.simulate_cash_rejection_replan(**values)
        result = control(**control_inputs(values))
        self.assertEqual(result['executions'], candidate['executions'])
        self.assertEqual(result['daily'], candidate['daily'])
        self.assertEqual(result['decision_lineage'], candidate['decision_lineage'])
        self.assertFalse(result['candidate_eligibility'])
        self.assertFalse(result['allocation_risk_constraints_enforced'])
        self.assertFalse(result['target_weights_projected'])
        values = inputs()
        before, after = old_control(**control_inputs(values)), control(**control_inputs(values))
        for key in before.keys() - {'schema', 'source_hashes'}:
            self.assertEqual(before[key], after[key], key)

    def test_sources_fail_closed(self):
        with patch.object(engine, '_hashes', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Sources changed'):
                engine.simulate_cash_rejection_replan(**inputs())


if __name__ == '__main__':
    unittest.main()
