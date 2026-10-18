"""Independent full-table EOF and literal-type rejection tests."""
from copy import deepcopy
import unittest
from backtest import ndx_multidecision_path_presentation_inspection_research as checker
from backtest import ndx_multidecision_path_presentation_research as projection
import test_ndx_multidecision_path_presentation_research as fixtures


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arguments = fixtures.fixture()
        cls.presentation = projection.build_tables(**cls.arguments)

    def test_every_table_extra_tail_and_empty_tail_rejected(self):
        for table_index in range(11):
            for mode in ('extra', 'missing'):
                with self.subTest(table=table_index, mode=mode):
                    value = deepcopy(self.presentation)
                    rows = value['tables'][table_index]['rows']
                    if mode == 'extra': rows.append(deepcopy(rows[-1]))
                    else: rows.pop()
                    with self.assertRaises(ValueError): checker.inspect_presentation(presentation=value, **self.arguments)

    def test_literal_numbers_not_coerced_and_reference_pointer_exact(self):
        for table, row, column, bad in ((1, 0, 0, False), (8, -1, 8, 0.1), (10, -1, -1, '{}'), (7, -1, -1, '[]')):
            with self.subTest(table=table):
                value = deepcopy(self.presentation)
                value['tables'][table]['rows'][row][column] = bad
                with self.assertRaises(ValueError): checker.inspect_presentation(presentation=value, **self.arguments)


if __name__ == '__main__':
    unittest.main()
