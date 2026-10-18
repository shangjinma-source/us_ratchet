from copy import deepcopy
import unittest

from backtest import ndx_dated_comparison_presentation_research as presentation
from backtest import ndx_dated_comparison_results_summary_research as summary_core
from test_ndx_dated_comparison_results_summary_research import fixture, saved


def source():
    arguments = fixture()
    for index in (1, 2):
        task = arguments['task_summary']['rows'][index]
        arguments['comparisons_by_task'][task['numerical_task_id']] = saved(
            task, missing=index == 1, decision='NO_PLAN' if index == 2 else 'FROZEN',
            execution=None if index == 2 else 'REJECTED')
    return summary_core.summarize_comparisons(**arguments)


class Tests(unittest.TestCase):
    def test_full_denominator_zero_and_missing_and_input_unchanged(self):
        original = source()
        before = deepcopy(original)
        result = presentation.build_tables(original)
        tables = {table['name']: table for table in result['tables']}
        self.assertEqual(original, before)
        self.assertEqual(len(tables['全部任务']['rows']), 1632)
        self.assertEqual(len(tables['四轨指标']['rows']), 8)
        self.assertEqual(tables['四轨指标']['rows'][0][-3:], [None, None, None])
        self.assertEqual(tables['四轨指标']['rows'][4][-3:], [0.0, 0.0, 0.0])
        self.assertEqual(tables['四轨指标']['rows'][4][3], '无交易计划')
        self.assertEqual(tables['原始目标权重']['rows'][0][-1], 0.0)
        self.assertEqual(tables['研究概览']['rows'][3][1], '6222659648236112670')
        self.assertIs(result['source_bytes_authenticated'], False)

    def test_fx_modes_and_negative_distance_preserved_without_ranking(self):
        original = source()
        modes = original['rows'][2]['nav_modes']
        modes[summary_core.MODES[0]]['absolute_distance_comparisons']['integer']['annualized_return']['candidate_minus_incumbent_distance'] = {'exact': '-1/4'}
        result = presentation.build_tables(original)
        distances = next(table for table in result['tables'] if table['name'] == '双基准距离')['rows']
        self.assertEqual(len(distances), 16)
        self.assertEqual(distances[8][-1], -0.25)
        self.assertEqual(distances[12][-1], 0.0)
        self.assertEqual(distances[0][5], None)

    def test_reject_authority_denominator_and_concealed_absence(self):
        for mutate in (
            lambda document: document.update(future_independent_oos=0),
            lambda document: document.update(materialized_task_count=True),
            lambda document: document.update(supplied_comparison_count=1632),
            lambda document: document['rows'][1]['tracks']['candidate_integer'].update(metrics={}),
            lambda document: document['mode_order'].reverse(),
        ):
            document = source()
            mutate(document)
            with self.assertRaises(ValueError):
                presentation.build_tables(document)


if __name__ == '__main__':
    unittest.main()
