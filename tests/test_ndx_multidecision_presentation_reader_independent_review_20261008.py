from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_multidecision_path_presentation_independent_readback_20261008 as reader
import test_ndx_multidecision_presentation_reader_source_20261008 as fixtures


class Tests(unittest.TestCase):
    def test_saved_publisher_failure_overrides_other_valid_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            env = fixtures.ReaderSourceTests().environment(directory)
            (env['PRESENTATION_ROOT'] / 'failure.json').write_text('{}')
            with patch.multiple(reader, **env):
                with self.assertRaisesRegex(ValueError, 'Failed successful-role source'):
                    reader.readback(execute=True)
                self.assertFalse(reader.OUTPUT.exists())

    def test_late_reader_output_drift_leaves_failure_and_forbids_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            env = fixtures.ReaderSourceTests().environment(directory)
            original_save = reader.save
            def drift(path, value):
                reference = original_save(path, value)
                if path.name == 'independent_readback.json':
                    (path.parent / 'started.json').write_text('{}')
                return reference
            with patch.multiple(reader, **env), patch.object(reader, 'save', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'Final independent report drift'):
                    reader.readback(execute=True)
                self.assertTrue((reader.OUTPUT / 'failure.json').is_file())
                self.assertTrue((reader.OUTPUT / 'independent_readback.json').is_file())
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    reader.readback(execute=True)


if __name__ == '__main__':
    unittest.main()
