"""Independent bounded XML counterexamples; no actual workbook IO."""
import importlib.util
from pathlib import Path
import unittest
from copy import deepcopy

from backtest import ndx_dated_comparison_xlsx_inspection_research as core

spec = importlib.util.spec_from_file_location('xlsx_owner_fixture', Path(__file__).with_name('test_ndx_dated_comparison_xlsx_inspection_research.py'))
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


class IndependentReview(unittest.TestCase):
    def reject_sheet_mutation(self, old, new):
        presentation = fixture_module.fixture()
        def mutate(parts):
            key = 'xl/worksheets/sheet1.xml'
            self.assertIn(old, parts[key])
            parts[key] = parts[key].replace(old, new)
        with self.assertRaises(ValueError):
            core.inspect_export(fixture_module.package(presentation, change=mutate), presentation)

    def test_zero_is_exact_even_when_nonzero_decimal_underflows_binary64(self):
        for tiny in ('1e-400', '-1e-400'):
            with self.subTest(tiny=tiny):
                self.reject_sheet_mutation('<v>0.0</v>', '<v>' + tiny + '</v>')

    def test_duplicate_coordinates_external_targets_and_cached_formulas(self):
        self.reject_sheet_mutation('<c r="C5"/>', '<c r="C5"/><c r="C5"/>')
        self.reject_sheet_mutation('<c r="B5">', '<c r="B5"><f>SUM(A1)</f>')
        presentation = fixture_module.fixture()
        def external(parts):
            key = 'xl/_rels/workbook.xml.rels'
            parts[key] = parts[key].replace('Id="r1"', 'Id="r1" TargetMode="External"')
        with self.assertRaises(ValueError):
            core.inspect_export(fixture_module.package(presentation, change=external), presentation)

    def test_literal_identifier_spaces_negative_and_source_immutability(self):
        presentation = fixture_module.fixture()
        for table in presentation['display']['tables']:
            table['rows'][0][0] = '0' * 63 + '1'
            table['rows'][0][1] = -0.125
            table['rows'][1][0] = '=not-a-formula'
        before = deepcopy(presentation)
        for encoding in ('inlineStr', 's', 'str'):
            report = core.inspect_export(fixture_module.package(presentation, encoding), presentation)
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(report['layout'], 'ACTUAL_FIXED_ROW4')
            self.assertIs(report['source_bytes_authenticated'], False)
        self.assertEqual(presentation, before)
        self.reject_sheet_mutation('6222659648236112670', '6222659648236112000')


if __name__ == '__main__':
    unittest.main()
