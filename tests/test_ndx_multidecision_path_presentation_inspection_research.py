from copy import deepcopy
import hashlib
from unittest.mock import patch
import unittest

from backtest import ndx_multidecision_path_presentation_research as producer
from backtest import ndx_multidecision_path_presentation_inspection_research as checker
import test_ndx_multidecision_path_presentation_research as fixtures


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = fixtures.fixture()
        cls.presentation = producer.build_tables(**cls.inputs)

    def test_all_original_cells_without_any_producer_function(self):
        original = deepcopy(self.presentation)
        with patch.object(producer, 'build_tables', side_effect=AssertionError('producer called')), patch.object(producer, 'encoded', side_effect=AssertionError('helper called')), patch.object(producer, 'additional_tables', side_effect=AssertionError('helper called')):
            report = checker.inspect_presentation(presentation=original, **self.inputs)
        self.assertEqual(original, self.presentation)
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['table_count'], 11)
        self.assertEqual(report['table_row_counts'][5]['count'], 3120)
        self.assertEqual(report['table_row_counts'][9]['count'], 192)
        self.assertEqual(report['checked_cell_count'], sum(len(row) for table in original['tables'] for row in table['rows']))
        reordered = dict(self.inputs, references=dict(sorted(self.inputs['references'].items())))
        self.assertEqual(checker.inspect_presentation(presentation=original, **reordered), report)

    def test_resigned_saved_display_attacks_are_rejected(self):
        attacks = ('ticker', 'weight', 'distance', 'date', 'missing', 'risk', 'curve_tail', 'curve_drop', 'pointer', 'flags', 'gaps', 'original', 'header', 'extra_table')
        for attack in attacks:
            with self.subTest(attack=attack):
                changed = deepcopy(self.presentation)
                tables = changed['tables']
                if attack == 'ticker': next(row for row in tables[8]['rows'] if row[4] == '已保存原目标')[6] = 'WRONG'
                elif attack == 'weight': next(row for row in tables[8]['rows'] if row[4] == '已保存原目标')[8] = '0.0'
                elif attack == 'distance': tables[2]['rows'][-1][4] = '0'
                elif attack == 'date': tables[4]['rows'][-1][1] = '2026-10-01'
                elif attack == 'missing': tables[8]['rows'][0][4] = '已保存原目标'
                elif attack == 'risk': tables[10]['rows'][-1][7] = '0'
                elif attack == 'curve_tail': tables[5]['rows'][-1][-1] = '1/1'
                elif attack == 'curve_drop': tables[5]['rows'].pop()
                elif attack == 'pointer': tables[9]['rows'][0][-1] = '{}'
                elif attack == 'flags': changed['promotion_allowed'] = 0
                elif attack == 'gaps': changed['remaining_delivery_gaps'].pop()
                elif attack == 'original': changed['original_coordinates_preserved'][0]['status'] = 'SUCCESS'
                elif attack == 'header': tables[0]['headers'][0] = 'changed'
                else: tables.append(deepcopy(tables[0]))
                # A fresh digest authenticates attacker bytes but cannot validate their values.
                digest = hashlib.sha256(checker.json_text(changed).encode()).hexdigest()
                self.assertEqual(len(digest), 64)
                with self.assertRaises(ValueError):
                    checker.inspect_presentation(presentation=changed, **self.inputs)

    def test_source_identity_or_authority_cannot_be_laundered(self):
        for attack in ('audit', 'count', 'binding'):
            with self.subTest(attack=attack):
                arguments = deepcopy(self.inputs)
                if attack == 'audit': arguments['audit']['status'] = 'FAILED'
                elif attack == 'count': arguments['audit']['inspection']['coordinate_count'] = True
                else: arguments['references']['candidate_inputs']['sha256'] = '0' * 64
                with self.assertRaises(ValueError):
                    checker.inspect_presentation(presentation=self.presentation, **arguments)


if __name__ == '__main__':
    unittest.main()
