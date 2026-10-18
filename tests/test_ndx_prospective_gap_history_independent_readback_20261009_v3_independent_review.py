"""Independent synthetic/temporary checks; never executes the actual readback."""
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_prospective_gap_history_independent_readback_20261009_v3 as reader
from test_ndx_prospective_gap_history_research_v3 import fixture


PARENT_FLAGS = (
    'source_authenticity_verified', 'filesystem_attempt_inventory_authenticated',
    'clock_authenticity_verified', 'candidate_seal_allowed', 'cohort_registration_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'future_independent_oos', 'production_generator_authorized', 'seal_event_created',
    'partial_recovery_performed', 'old_calendar_mutated',
)


class IndependentReviewTests(unittest.TestCase):
    def test_parent_mandatory_authority_fields_cannot_be_missing_or_numeric(self):
        checker = reader.private_checker(reader.CAPTURE_READER.read_bytes())
        for key in PARENT_FLAGS:
            for mode in ('missing', 'numeric'):
                arguments = fixture()
                if mode == 'missing':
                    arguments['parent']['document'].pop(key)
                else:
                    arguments['parent']['document'][key] = 0
                with self.subTest(key=key, mode=mode), self.assertRaises((ValueError, KeyError)):
                    reader.reconstruct_history(**arguments, checker=checker)

    def test_saved_source_guard_detects_drift_and_failed_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.json'
            path.write_bytes(b'original')
            item = reader.reference(str(path), reader.digest(b'original'))
            reader.consume(item, {})
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                reader.consume(item, {})
            path.write_bytes(b'original')
            (path.parent / 'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                reader.consume(item, {})

    def test_namespace_rejects_extra_files_directories_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / 'namespace'
            directory.mkdir()
            source = directory / 'source.json'
            source.write_bytes(b'{}')
            reader.namespace(directory, ('source.json',))
            for directory_extra in (False, True):
                extra = directory / 'extra'
                extra.mkdir() if directory_extra else extra.write_bytes(b'')
                with self.assertRaises(ValueError):
                    reader.namespace(directory, ('source.json',))
                extra.rmdir() if directory_extra else extra.unlink()
            source.unlink()
            target = Path(folder) / 'target.json'
            target.write_bytes(b'{}')
            try:
                source.symlink_to(target)
            except OSError as error:
                self.skipTest('Symlink unavailable: ' + str(error))
            with self.assertRaises(ValueError):
                reader.namespace(directory, ('source.json',))

    def test_createonly_output_stops_before_source_io(self):
        with tempfile.TemporaryDirectory() as folder:
            with (patch.multiple(reader, OUTPUT=Path(folder), PRODUCER_SHA='a'*64,
                                 HISTORY_SHA='b'*64, PUBLICATION_SHA='c'*64),
                  patch.object(Path, 'read_bytes', side_effect=AssertionError('Source IO'))):
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    reader.readback(execute=True)

    def test_save_is_exclusive_and_mutable_cache_cannot_enter_closure(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            path = output / 'evidence.json'
            with (patch.object(reader, 'OUTPUT', output),
                  patch.object(reader.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 10**12})())):
                reader.save(path, {'evidence': False})
                with self.assertRaises(FileExistsError):
                    reader.save(path, {'evidence': True})
            self.assertEqual(reader.decode(path.read_bytes()), {'evidence': False})
        with patch.object(reader, 'consume', side_effect=AssertionError('Mutable bytes read')):
            with self.assertRaisesRegex(ValueError, 'Mutable cache'):
                reader.guard({str(reader.ROOT/'data/cache/QQQ.csv'): 'a'*64})

    def test_reader_has_no_publisher_or_newpure_import_or_execution(self):
        tree = ast.parse(reader.SOURCE.read_bytes())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
        self.assertFalse(any('prospective_gap_history' in name for name in imports))
        exec_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name) and node.func.id == 'exec']
        self.assertEqual(len(exec_calls), 1)
        checker = reader.private_checker(reader.CAPTURE_READER.read_bytes())
        with (patch.object(checker, 'readback', side_effect=AssertionError('Old entrypoint called')),
              patch.object(reader, 'save', side_effect=AssertionError('Output written'))):
            result = reader.reconstruct_history(**fixture(), checker=checker)
        self.assertEqual((result['typed_row_count'], result['observation_count']), (69, 1))


if __name__ == '__main__':
    unittest.main()
