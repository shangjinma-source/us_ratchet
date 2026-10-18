import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_multidecision_path_presentation_20261008 as subject
import test_ndx_multidecision_path_presentation_source_20261008 as fixtures


class Tests(unittest.TestCase):
    def test_resigned_conflicting_source_union_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            env = fixtures.SourceTests().environment(directory)
            path = Path(env['BOUND']['audit'][0])
            audit = json.loads(path.read_bytes())
            audit['source_hashes'][env['BOUND']['candidate_inputs'][0]] = '0' * 64
            reference = fixtures.write(path, audit)
            env['BOUND']['audit'] = (reference['path'], reference['sha256'])
            with patch.multiple(subject, **env):
                with self.assertRaisesRegex(ValueError, 'Conflicting source SHA'):
                    subject.run(execute=True)
                self.assertFalse(subject.OUTPUT.exists())

    def test_output_drift_after_publication_cannot_leave_success_only(self):
        with tempfile.TemporaryDirectory() as directory:
            env = fixtures.SourceTests().environment(directory)
            original_save = subject.save
            def tamper(path, value):
                reference = original_save(path, value)
                if path.name == 'publication.json':
                    (path.parent / 'presentation.json').write_text('{}')
                return reference
            with patch.multiple(subject, **env), patch.object(subject, 'save', side_effect=tamper):
                with self.assertRaisesRegex(ValueError, 'Final output drift'):
                    subject.run(execute=True)
                self.assertTrue((subject.OUTPUT / 'failure.json').is_file())
                self.assertTrue((subject.OUTPUT / 'publication.json').is_file())
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    subject.run(execute=True)


if __name__ == '__main__':
    unittest.main()
