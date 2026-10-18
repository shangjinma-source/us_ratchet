import unittest
from unittest.mock import patch

from test_ndx_next_session_execution_research import fixture
from backtest import ndx_next_session_execution_research_v2 as candidate
from backtest.ndx_incumbent_execution_control_research import simulate_fixed_weight_incumbent_control as control


def inputs():
    original = fixture()
    schedule = original.pop('schedule')
    original.pop('selection_policy')
    return dict(**original, decision_dates=[d for d, _ in schedule],
                incumbent_weights=schedule[0][1], corporate_actions=[])


class IncumbentExecutionControlTests(unittest.TestCase):
    def test_risk_violation_does_not_erase_control_or_change_candidate(self):
        global_snapshot = dict(candidate.__dict__)
        original_allocator = candidate.search_integer_allocation_domain
        values = inputs()
        values['constraints']['max_single_weight'] = .1
        result = control(**values)
        self.assertEqual(result['trade_execution_count'], 1)
        self.assertFalse(result['all_days_constraints_passed'])
        self.assertFalse(result['candidate_eligibility'])
        self.assertEqual(result['incumbent_target_weights'], values['incumbent_weights'])
        candidate_values = fixture()
        candidate_values['constraints'] = values['constraints']
        other = candidate.simulate_next_session_execution_research_v2(**candidate_values, corporate_actions=[])
        self.assertEqual(other['trade_execution_count'], 0)
        self.assertEqual(other['status'], 'UNRESOLVED')
        self.assertIs(candidate.search_integer_allocation_domain, original_allocator)
        self.assertEqual(set(candidate.__dict__), set(global_snapshot))
        self.assertTrue(all(candidate.__dict__[key] is value for key, value in global_snapshot.items()))

    def test_loaded_execution_source_drift_rejected(self):
        with patch.object(candidate, '_hashes', return_value={}):
            with self.assertRaisesRegex(ValueError, 'changed since original import'):
                control(**inputs())

    def test_no_event_risk_qualified_path_matches_candidate(self):
        actual = control(**inputs())
        expected = candidate.simulate_next_session_execution_research_v2(**fixture(), corporate_actions=[])
        for field in ('daily', 'executions', 'terminal_cash_usd', 'terminal_shares', 'total_fees_usd'):
            self.assertEqual(actual[field], expected[field])

    def test_split_pending_cancellation_remains_identical(self):
        values = inputs()
        values['corporate_actions'] = [dict(ticker='A', session=str(values['execution_calendar'][1].date()),
            new_shares=20, old_shares=1, source_url='https://example.org/event', evidence_sha256='a'*64)]
        actual = control(**values)
        self.assertEqual(actual['cancelled_pending_plan_count'], 1)
        self.assertEqual(actual['executions'], [])
        self.assertEqual(actual['terminal_cash_usd'], 100.)


if __name__ == '__main__':
    unittest.main()
