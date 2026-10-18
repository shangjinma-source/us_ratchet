"""Independent capture-reader adversarial checks; no actual source collection."""
import ast
from copy import deepcopy
from pathlib import Path
import unittest

from scripts import ndx_variable_prefix_capture_independent_readback_20261003 as reader
from test_ndx_variable_prefix_capture_research import fixture, resign, m as planner
from test_ndx_variable_prefix_capture_independent_readback_20261003 import arguments


class RootReview(unittest.TestCase):
    def test_equal_numeric_values_do_not_hide_original_text_revision(self):
        inputs = fixture()
        first_day = inputs['parent']['document']['known_typed_rows'][0]['session']
        before = (first_day + ',10,12,8,10,100').encode()
        after = (first_day + ',10.0,12,8,10,100').encode()
        self.assertIn(before, inputs['source_bytes']['QQQ'])
        inputs['source_bytes']['QQQ'] = inputs['source_bytes']['QQQ'].replace(before, after)
        resign(inputs, 'QQQ')
        plan = planner.plan_history_capture(**inputs)
        result = reader.inspect_plan(**arguments(inputs, plan))
        self.assertEqual(result['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
        self.assertEqual({d['reason'] for d in plan['diagnostics']},
                         {'FULL_ORIGINAL_PREFIX_CHANGED', 'PARENT_SOURCE_REVISION'})
        forged = deepcopy(plan)
        forged['diagnostics'] = []
        with self.assertRaises(ValueError):
            reader.inspect_plan(**arguments(inputs, forged))

    def test_first_actual_month_day_cannot_be_replaced_by_later_capture(self):
        inputs = fixture(second=True)
        plan = planner.plan_history_capture(**inputs)
        self.assertEqual(plan['proposed_first_actual_session_of_month'], '2026-10-02')
        self.assertEqual(plan['candidate_session'], '2026-10-06')
        reader.inspect_plan(**arguments(inputs, plan))
        for key, value in [('proposed_first_actual_session_of_month', '2026-10-06'),
                           ('timeliness_verified', True), ('observation_created', True)]:
            forged = deepcopy(plan)
            forged[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                reader.inspect_plan(**arguments(inputs, forged))

    def test_reader_has_no_production_import_or_dynamic_execution(self):
        tree = ast.parse(Path(reader.__file__).read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(not x.name.startswith(('backtest', 'scripts'))
                                    for x in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or '').startswith(('backtest', 'scripts')))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('exec', 'eval', '__import__', 'compile'))


if __name__ == '__main__':
    unittest.main()
