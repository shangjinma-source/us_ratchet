"""Adversarial source preservation checks; synthetic inputs, no live capture."""
from copy import deepcopy
import unittest

from backtest import ndx_variable_prefix_capture_research as planner
from test_ndx_variable_prefix_capture_research import fixture, resign


class RootReview(unittest.TestCase):
    def test_original_rows_before_scope_cannot_disappear_or_change(self):
        for action in ('drop', 'revise', 'insert'):
            arguments = fixture()
            original = arguments['source_bytes']['QQQ']
            if action == 'drop':
                changed = original.replace(b'2020-01-02,5,12,8,10,100\n', b'')
            elif action == 'revise':
                changed = original.replace(b'2020-01-02,5,12,8,10,100',
                                           b'2020-01-02,6,12,8,10,100')
            else:
                changed = original.replace(b'2020-01-02,5,12,8,10,100\n',
                    b'2020-01-02,5,12,8,10,100\n2020-01-03,10,12,8,10,100\n')
            self.assertNotEqual(changed, original)
            arguments['source_bytes']['QQQ'] = changed
            resign(arguments, 'QQQ')
            result = planner.plan_history_capture(**arguments)
            with self.subTest(action=action):
                self.assertEqual(result['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
                self.assertIsNone(result['candidate_session'])

    def test_result_references_do_not_alias_parent_or_captured_sources(self):
        arguments = fixture()
        original = deepcopy(arguments)
        result = planner.plan_history_capture(**arguments)
        result['source_evidence']['QQQ']['source_reference']['path'] = 'changed-output'
        result['source_evidence']['SPY']['baseline_reference']['path'] = 'changed-baseline'
        self.assertEqual(arguments, original)

    def test_one_source_suffix_is_not_a_shared_observation(self):
        arguments = fixture(second=True)
        arguments['source_bytes']['SPY'] = arguments['baseline_bytes']['SPY']
        resign(arguments, 'SPY')
        result = planner.plan_history_capture(**arguments)
        self.assertEqual(result['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
        self.assertIsNone(result['candidate_session'])
        self.assertEqual(result['source_evidence']['QQQ']['new_session_dates'], ['2026-10-06'])
        self.assertEqual(result['source_evidence']['SPY']['new_session_dates'], [])
        self.assertFalse(result['observation_created'])


if __name__ == '__main__':
    unittest.main()
