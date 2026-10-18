"""Independent side-effect boundary checks for the new calendar publisher."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import ndx_persisted_candidate_calendar_20261003 as subject


class CalendarPublisherReview(unittest.TestCase):
    def test_new_parent_failure_or_output_mutation_retains_failed_attempt(self):
        from test_ndx_persisted_candidate_calendar_20261003 import file_fixture
        for mode in ('parent_failure', 'output_mutation'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                bindings = file_fixture(Path(directory))
                original_save = subject.save

                def inject(path, value, **kwargs):
                    result = original_save(path, value, **kwargs)
                    if mode == 'parent_failure' and path.name == 'started.json':
                        parent = Path(bindings['HISTORY_BOUND']['reference'][0]).parent
                        (parent / 'failure.json').write_bytes(b'{"status":"FAILED"}')
                    if mode == 'output_mutation' and path.name == 'publication.json':
                        saved = bindings['OUTPUT'] / 'result.json'
                        saved.write_bytes(saved.read_bytes() + b' ')
                    return result

                with patch.multiple(subject, **bindings), \
                     patch.object(subject, 'now', return_value='2026-11-02T21:02:00+00:00'), \
                     patch.object(subject, 'save', side_effect=inject):
                    expected = 'Failed source namespace' if mode == 'parent_failure' else 'Final output bytes'
                    with self.assertRaisesRegex(ValueError, expected):
                        subject.run(execute=True)
                    self.assertTrue((bindings['OUTPUT'] / 'started.json').exists())
                    self.assertTrue((bindings['OUTPUT'] / 'failure.json').exists())
                    with self.assertRaises(ValueError):
                        subject.run(execute=True)

    def test_pending_external_roles_precede_all_filesystem_access(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('early read')), \
             patch.object(Path, 'exists', side_effect=AssertionError('early probe')), \
             patch.object(Path, 'mkdir', side_effect=AssertionError('early mkdir')):
            with self.assertRaisesRegex(ValueError, 'Pending'):
                subject.run(execute=True)

    def test_reserve_includes_this_write_but_failure_receipt_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            payload = {'status': 'TEST_ONLY'}
            required = len(subject.enc(payload))
            with patch.object(subject, 'OUTPUT', target), \
                 patch.object(subject.shutil, 'disk_usage',
                              return_value=SimpleNamespace(free=subject.MIN_FREE + required - 1)):
                with self.assertRaisesRegex(ValueError, 'RESOURCE_STOP_BEFORE_WRITE'):
                    subject.save(target / 'result.json', payload)
                self.assertFalse((target / 'result.json').exists())
                receipt = subject.save(target / 'failure.json', payload, failure=True)
                self.assertEqual(subject.sha(Path(receipt['path']).read_bytes()), receipt['sha256'])
                with self.assertRaises(FileExistsError):
                    subject.save(target / 'failure.json', payload, failure=True)


if __name__ == '__main__':
    unittest.main()
