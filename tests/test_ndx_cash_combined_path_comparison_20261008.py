"""Exercise the versioned combined source comparison with saved synthetic paths."""
from pathlib import Path
from types import ModuleType
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_cash_neighbor_combined_path_comparison_20261008 as producer
from scripts import ndx_cash_neighbor_combined_path_comparison_independent_readback_20261008 as reader

ROOT = Path(__file__).resolve().parents[1]


class CombinedBindingsTests(unittest.TestCase):
    def test_same_complete_source_contract_and_current_bindings(self):
        self.assertEqual(producer.BOUND, reader.INPUT_BOUND)
        documents = {}
        for role in ('selected_result', 'selected_publication', 'selected_audit', 'selected_reader'):
            path, digest = producer.BOUND[role]
            self.assertIn('cash_neighbor_combined_selected_paths', path)
            if digest is not None:
                raw = Path(path).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
                if role != 'selected_reader':
                    documents[role] = json.loads(raw)
        pending = [producer.BOUND[k][1] is None for k in ('selected_result', 'selected_publication', 'selected_audit', 'selected_reader')]
        self.assertTrue(all(pending) or not any(pending), 'Four input bindings must be a complete stage')
        if documents:
            result_ref = dict(zip(('path', 'sha256'), producer.BOUND['selected_result']))
            publication_ref = dict(zip(('path', 'sha256'), producer.BOUND['selected_publication']))
            self.assertEqual(documents['selected_publication']['result_reference'], result_ref)
            self.assertEqual(documents['selected_audit']['result_reference'], result_ref)
            self.assertEqual(documents['selected_audit']['publication_reference'], publication_ref)
            self.assertEqual(documents['selected_audit']['reader_sha256'], producer.BOUND['selected_reader'][1])
            self.assertEqual(documents['selected_audit']['status'], 'PASS_SAVED_PATH_ARITHMETIC')
        self.assertEqual(reader.BOUND['producer'], (str(producer.SOURCE), producer.LOADED))
        self.assertEqual(reader.COMPARISON, producer.OUTPUT)

    def test_pending_inputs_in_explicit_isolated_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'never-created'
            with patch.object(producer, 'OUTPUT', output), patch.dict(producer.BOUND, {'selected_result': (producer.BOUND['selected_result'][0], None)}), patch.object(Path, 'read_bytes', side_effect=AssertionError('No pending source reads')):
                with self.assertRaisesRegex(ValueError, 'Pending'):
                    producer.load()
            self.assertFalse(output.exists())


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite([standard_tests])
    for index, name in enumerate((
        'test_ndx_cash_neighbor_path_comparison_20261003.py',
        'test_ndx_cash_neighbor_path_comparison_wrapper_review_20261003.py',
        'test_ndx_cash_neighbor_path_comparison_independent_readback_20261003.py',
        'test_ndx_cash_comparison_reader_implementation_review_20261003.py',
    )):
        path = ROOT / 'tests' / name
        source = path.read_text(encoding='utf-8')
        source = source.replace('from scripts import ndx_cash_neighbor_path_comparison_20261003', 'from scripts import ndx_cash_neighbor_combined_path_comparison_20261008')
        source = source.replace('from scripts import ndx_cash_neighbor_path_comparison_independent_readback_20261003', 'from scripts import ndx_cash_neighbor_combined_path_comparison_independent_readback_20261008')
        if name == 'test_ndx_cash_neighbor_path_comparison_wrapper_review_20261003.py':
            old = "with patch.object(Path,'read_bytes',side_effect=AssertionError('No actual reads'))"
            new = "with patch.dict(m.BOUND, {'selected_result': (m.BOUND['selected_result'][0], None)}), patch.object(Path,'read_bytes',side_effect=AssertionError('No actual reads'))"
            assert source.count(old) == 1
            source = source.replace(old, new, 1)
        elif name == 'test_ndx_cash_neighbor_path_comparison_independent_readback_20261003.py':
            old = "with patch.object(Path,'read_bytes',side_effect=AssertionError('No future IO'))"
            new = "with patch.dict(m.BOUND, {'index': (m.BOUND['index'][0], None)}), patch.object(Path,'read_bytes',side_effect=AssertionError('No future IO'))"
            assert source.count(old) == 1
            source = source.replace(old, new, 1)
        module = ModuleType(f'combined_comparison_inherited_{index}')
        module.__file__ = str(path)
        exec(compile(source, str(path), 'exec'), module.__dict__)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


if __name__ == '__main__':
    unittest.main()
