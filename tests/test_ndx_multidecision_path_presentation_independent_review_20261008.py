"""Independent projection checks; saved fixtures only, no account execution."""
from copy import deepcopy
import unittest
from backtest import ndx_multidecision_path_presentation_research as subject
from test_ndx_multidecision_path_presentation_research import fixture


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arguments = fixture()

    def test_every_metric_and_curve_literal_is_preserved(self):
        result = subject.build_tables(**deepcopy(self.arguments))
        tables = {t['name']: t for t in result['tables']}
        metrics = tables['已存路径指标']['rows']
        curves = tables['已存归一轨迹']['rows']
        expected_curves = []
        for index, row in enumerate(self.arguments['comparison_document']['comparison']['rows']):
            for offset, (role, label) in enumerate((('candidate', '候选'), ('control', '原八只控制'))):
                saved = row[role]['metrics']
                cells = metrics[2 * index + offset]
                if saved is None:
                    self.assertEqual(cells[-3:], [None] * 3)
                    continue
                self.assertEqual(cells[-2], saved['annualized_return_diagnostic_decimal'])
                for key, cell in [('cumulative_return', cells[-3]), ('maximum_drawdown', cells[-1])]:
                    self.assertEqual(cell, saved[key]['numerator'] + '/' + saved[key]['denominator'])
                expected_curves.extend((index, label, point['session'], point['normalized_wealth']['numerator'] + '/' + point['normalized_wealth']['denominator']) for point in saved['wealth'])
        self.assertEqual([(r[0], r[4], r[5], r[6]) for r in curves if r[0] is not None], expected_curves)
        self.assertTrue(all(t['all_cells_literal'] is True for t in result['tables']))
        result['original_comparison_preserved']['rows'].clear()
        self.assertEqual(len(self.arguments['comparison_document']['comparison']['rows']), 16)

    def test_cross_bound_sources_and_typed_flags_rejected(self):
        for attack in ('reader', 'candidate', 'pub', 'auditinputs', 'flagzero', 'duplicatecalendar', 'trackorder'):
            with self.subTest(attack=attack):
                args = deepcopy(self.arguments)
                if attack == 'reader': args['references']['reader']['sha256'] = 'f' * 64
                elif attack == 'candidate': args['references']['candidate_inputs']['path'] += '.old'
                elif attack == 'pub': args['publication']['comparison_reference']['sha256'] = 'f' * 64
                elif attack == 'auditinputs': args['audit']['input_references']['candidate_inputs']['path'] += '.old'
                elif attack == 'flagzero': args['comparison_document']['comparison']['promotion_allowed'] = 0
                elif attack == 'duplicatecalendar': args['comparison_document']['comparison']['calendar'][-1] = args['comparison_document']['comparison']['calendar'][-2]
                else: args['comparison_document']['comparison']['rows'][0]['track_index'] = False
                with self.assertRaises(ValueError): subject.build_tables(**args)

    def test_target_weights_and_distances_remain_original_text(self):
        result = subject.build_tables(**deepcopy(self.arguments))
        tables = {t['name']: t for t in result['tables']}
        expected = []
        inputs = self.arguments['candidate_inputs_document']['inputs']
        for lane in inputs['rows']:
            for entry in lane['original_targets_schedule']:
                for sid, target in entry['targets'].items():
                    expected.append((entry['decision_date'], subject.MODES[lane['fx_mode']], subject.LANES[lane['lane']], sid, target['ticker'], target['issuer_id'], subject.encoded(target['target_weight']), entry['execution_date']))
        actual = [(r[1], r[2], r[3], r[5], r[6], r[7], r[8], r[9]) for r in tables['候选原目标证券']['rows'] if r[4] == '已保存原目标']
        self.assertCountEqual(actual, expected)
        for original, shown in zip(self.arguments['comparison_document']['comparison']['rows'], tables['到NAV的逐项距离']['rows']):
            self.assertEqual(shown[-1], subject.encoded(original['distances']))
            distances = original['distances']
            expected_cells = []
            for role in ('candidate', 'control'):
                value = distances[role]
                expected_cells += [None, None] if value is None else [value['annualized_return_absolute_distance'], value['maximum_drawdown_absolute_distance']]
            value = distances['candidate_minus_control_absolute_distance']
            expected_cells += [None, None] if value is None else [value['annualized_return'], value['maximum_drawdown']]
            self.assertEqual(shown[4:-1], expected_cells)
        self.assertEqual(len(tables['已保存决策风险']['rows']), 192)
        self.assertFalse(result['full_h_delivery_complete'])
        self.assertTrue(result['remaining_delivery_gaps'])


if __name__ == '__main__':
    unittest.main()
