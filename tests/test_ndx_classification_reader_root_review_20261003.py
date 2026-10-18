from copy import deepcopy
import unittest
from scripts import ndx_saved_classification_coverage_independent_readback_20261003 as reader
from test_ndx_saved_classification_coverage_independent_readback_20261003 import case


class Tests(unittest.TestCase):
    def test_unknown_row_cannot_be_replaced_by_another_unknown(self):
        arguments = case()
        arguments[0]['rows'][-1] = deepcopy(arguments[0]['rows'][-2])
        with self.assertRaises(ValueError): reader.inspect(*arguments)

    def test_coverage_and_training_coordinates_are_not_interchangeable(self):
        for mutation in ('issuer', 'selection', 'pure_auth'):
            arguments = case()
            if mutation == 'issuer': arguments[0]['counts']['training_selected_issuer_count'] = 77
            elif mutation == 'selection': arguments[0]['rows'][77]['training_selected'] = True
            else: arguments[0]['source_bytes_authenticated'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                reader.inspect(*arguments)

    def test_closed_source_count_and_conflicting_producer_path(self):
        refs = {key: reader.ref(reader.ROOT / path, digest) for key, (path, digest) in reader.BOUND.items()}
        self.assertEqual(len(reader.expected_sources(refs)), 10)
        wrong = deepcopy(refs)
        wrong['core'] = reader.ref(reader.PRODUCER, '0' * 64)
        with self.assertRaises(ValueError): reader.expected_sources(wrong)
        del refs['wiring_reader']
        with self.assertRaises(ValueError): reader.expected_sources(refs)


if __name__ == '__main__':
    unittest.main()
