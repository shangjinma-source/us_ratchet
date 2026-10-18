"""Retain a returned object even when JSON and its diagnostic repr both fail."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from scripts import ndx_multidecision_account_execution_20261003 as worker
from test_ndx_multidecision_account_execution_20261003 import physical


class BrokenRepresentation:
    def __repr__(self):
        raise RuntimeError('synthetic repr failure')


class RawReturnTests(TestCase):
    def test_non_json_return_is_counted_once_and_preserved_before_validation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent, bindings = physical(root)
            output = root / 'output'
            original_engines = worker.private_engines

            def engines(sources):
                functions, pandas, runtime = original_engines(sources)
                functions['CONTINUOUS'] = lambda **arguments: BrokenRepresentation()
                return functions, pandas, runtime

            with patch.object(worker, 'ROOT', root), patch.object(worker, 'PARENT', parent), patch.object(worker, 'BOUND', bindings), patch.object(worker, 'OUTPUT', output), patch.object(worker, 'resource'), patch.object(worker, 'private_engines', side_effect=engines):
                with self.assertRaisesRegex(ValueError, 'technical failure'):
                    worker.run(execute=True)
                with self.assertRaisesRegex(ValueError, 'Exclusive'):
                    worker.run(execute=True)
            raw = worker.decode((output / 'tracks/08/raw_result.json').read_bytes())
            result = worker.decode((output / 'result.json').read_bytes())
            self.assertTrue(raw['returned'])
            self.assertEqual(raw['returned_call_count'], 1)
            self.assertFalse(raw['original_return_is_json'])
            self.assertEqual(raw['repr_error']['type'], 'RuntimeError')
            self.assertEqual(Path(raw['diagnostic_reference']['path']).read_bytes(), b'REPR_FAILED')
            self.assertEqual(result['account_call_count'], 1)
            self.assertEqual(result['counts']['UNDISPATCHED'], 7)
            self.assertTrue((output / 'failure.json').exists())
            self.assertFalse((output / 'publication.json').exists())


if __name__ == '__main__':
    main()
