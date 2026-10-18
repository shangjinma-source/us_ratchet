from copy import deepcopy
import unittest

from backtest import ndx_dated_workbook_extension_tables_research as core
from test_ndx_dated_workbook_extension_tables_research import fixture


class RootReview(unittest.TestCase):
    def test_shared_control_role_swap_and_preserved_limits(self):
        values = fixture()
        row, chain, shared, aggregates = values
        integer_key = row['tracks']['incumbent_integer']['shared_path_id']
        continuous_key = row['tracks']['incumbent_continuous']['shared_path_id']
        bad = deepcopy(aggregates)
        bad[integer_key]['aggregation'] = deepcopy(bad[continuous_key]['aggregation'])
        with self.assertRaises(ValueError):
            core.project_task_display(row, chain, shared, bad)
        bad_chain = deepcopy(chain)
        bad_chain['limitations_preserved'].append('unrelated scope')
        with self.assertRaises(ValueError):
            core.project_task_display(row, bad_chain, shared, aggregates)

    def test_two_fx_roles_remain_distinct_at_equal_values_and_underflow(self):
        values = fixture()
        result = core.project_task_display(*values)
        left, right = (result['series'][mode] for mode in core.MODES)
        self.assertEqual(len(left['slots']), 127)
        self.assertEqual(len(right['slots']), 127)
        self.assertNotEqual(left['source_reference'], right['source_reference'])
        tiny = {'numerator': '1', 'denominator': '1' + '0' * 400}
        cell = core.display_number(tiny)
        self.assertEqual(cell['exact_value'], tiny)
        self.assertIsNone(cell['display_value'])
        self.assertEqual(cell['display_status'], 'OUTSIDE_DISPLAY_PRECISION')
        self.assertEqual(core.display_number('0')['display_value'], 0.0)

    def test_bytes_drive_package_boundary_and_incomplete_generator_fails(self):
        tasks = [dict(task_ordinal=i, numerical_task_id=f'{i:064x}',
                      data_row_count=3, estimated_bytes=7) for i in range(3)]
        limits = dict(max_rows_per_sheet=4, max_rows_per_package=20,
                      max_estimated_bytes_per_package=10)
        expected = [row['numerical_task_id'] for row in tasks]
        result = core.plan_display_packages(iter(tasks), limits, expected_task_ids=expected)
        self.assertEqual(len(result['packages']), 3)
        self.assertEqual(result['packages'][-1]['stop_task_ordinal'], 3)
        with self.assertRaises(ValueError):
            core.plan_display_packages(iter(tasks[:-1]), limits, expected_task_ids=expected)
        with self.assertRaises(ValueError):
            core.plan_display_packages(iter(tasks), {}, expected_task_ids=expected)


if __name__ == '__main__':
    unittest.main()
