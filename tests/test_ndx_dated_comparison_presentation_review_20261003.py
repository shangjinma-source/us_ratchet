"""Display-only independent checks using synthetic summaries."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest import ndx_dated_comparison_presentation_research as module
from backtest import ndx_dated_comparison_results_summary_research as summary
from test_ndx_dated_comparison_presentation_research import source
from test_ndx_dated_comparison_results_summary_research import fixture


def tables(document):
    return {table['name']: table['rows'] for table in module.build_tables(document)['tables']}


class Review(unittest.TestCase):
    def test_all_missing_keeps_exact_denominator_and_original_order(self):
        document = summary.summarize_comparisons(**fixture())
        output = tables(document)
        self.assertEqual(len(output['全部任务']), 1632)
        self.assertEqual([row[1] for row in output['全部任务']],
                         [row['numerical_task_id'] for row in document['rows']])
        self.assertEqual(output['四轨指标'], [])
        self.assertEqual(output['双基准距离'], [])
        self.assertEqual(output['原始目标权重'], [])
        overview = dict(output['研究概览'])
        self.assertEqual(overview['完整组合域任务数（精确文本）'], str(module.FULL))
        self.assertEqual(overview['完整域未在本比较汇总中体现（精确文本）'], str(module.FULL))
        self.assertEqual(overview['未提供比较'], 1632)

    def test_signed_distances_original_nonunit_weights_and_no_alias(self):
        document = source()
        row = document['rows'][2]
        row['original_targets'][0]['target_weight'] = 0.25000000000000006
        for index, mode in enumerate(module.MODES):
            metric = row['nav_modes'][mode]['absolute_distance_comparisons']['integer']['annualized_return']
            metric['candidate_minus_incumbent_distance'] = {'exact': '-2/7' if index == 0 else '3/11'}
        before = deepcopy(document)
        output = tables(document)
        self.assertEqual(output['双基准距离'][8][-1], float(Fraction(-2, 7)))
        self.assertEqual(output['双基准距离'][12][-1], float(Fraction(3, 11)))
        self.assertEqual(output['原始目标权重'][4][-1], 0.25000000000000006)
        self.assertEqual(output['原始目标权重'][0][-1], 0.0)
        output['全部任务'][0][1] = 'changed display'
        output['原始目标权重'][4][-1] = 1.0
        self.assertEqual(document, before)

    def test_missing_distinct_from_actual_zero_and_reject_unsafe_display(self):
        document = source()
        output = tables(document)
        self.assertEqual(output['四轨指标'][0][-3:], [None, None, None])
        self.assertEqual(output['四轨指标'][4][-3:], [0.0, 0.0, 0.0])
        self.assertEqual(output['四轨指标'][4][3:5], ['无交易计划', '无执行记录'])
        self.assertIsNone(output['双基准距离'][0][-1])
        for mutate in (
            lambda d: d['rows'][1]['original_targets'][0].update(target_weight=True),
            lambda d: d['rows'][2]['tracks']['candidate_integer']['metrics']['cumulative_return'].update(exact='0.0'),
            lambda d: d['rows'][2]['nav_modes'].pop(next(iter(module.MODES))),
            lambda d: d.update(formal_comparison_passed=0),
        ):
            bad = source()
            mutate(bad)
            with self.assertRaises(ValueError):
                module.build_tables(bad)
        result = module.build_tables(document)
        for key in ('source_bytes_authenticated', 'economics_recomputed', 'formal_comparison_passed', 'future_independent_oos'):
            self.assertIs(result[key], False)


if __name__ == '__main__':
    unittest.main()
