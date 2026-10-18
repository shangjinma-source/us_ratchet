"""Independent V2 writer failure-marker and frozen capture-role checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_prospective_observation_writer_v2_20261003 as writer
from test_ndx_prospective_observation_writer_v2_20261003 import fixture


class RootReview(unittest.TestCase):
    def test_new_parent_failure_after_payload_is_retained_and_blocks_receipt(self):
        parent, capture, arguments, references, sources, core = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent_folder = root / 'parent'
            parent_folder.mkdir()
            parent_file = parent_folder / 'source.json'
            parent_file.write_bytes(b'unchanged immutable source')
            probe = {str(parent_file): writer.sha(parent_file.read_bytes())}
            output = root / 'observation'
            original_save, original_guard = writer.save, writer.guard

            def save(path, value):
                reference = original_save(path, value)
                if path.name == 'observation_payload.json':
                    (parent_folder / 'failure.json').write_bytes(b'{"status":"FAILED"}')
                return reference

            day = arguments['session']
            times = [day + 'T21:01:00+00:00', day + 'T21:01:01+00:00', day + 'T21:02:00+00:00']
            with patch.object(writer, 'OUTPUT', output), patch.object(writer, 'resource_gate'), \
                 patch.object(writer, 'load_inputs', return_value=(arguments, references, sources, core)), \
                 patch.object(writer, 'guard', side_effect=lambda _: original_guard(probe)), \
                 patch.object(writer, 'save', side_effect=save), \
                 patch.object(writer, 'now', side_effect=times):
                with self.assertRaises(ValueError):
                    writer.run(execute=True)
                self.assertTrue((output / 'observation_payload.json').is_file())
                self.assertFalse((output / 'receipt.json').exists())
                failure = writer.load_json((output / 'failure.json').read_bytes())
                self.assertTrue(failure['observation_payload_must_not_be_discarded'])
                self.assertFalse(failure['retry_allowed'])
                with self.assertRaisesRegex(ValueError, 'no retry'):
                    writer.run(execute=True)

    def test_self_consistent_foreign_capture_code_is_not_the_frozen_role(self):
        for role in ('producer', 'core'):
            parent, capture, *_ = fixture()
            capture = deepcopy(capture)
            if role == 'producer':
                path = writer.CAPTURE_PRODUCER[0]
                for document in ('document', 'publication', 'readback'):
                    capture[document]['source_hashes'][path] = 'b' * 64
            else:
                capture['document']['input_references']['core']['sha256'] = 'b' * 64
            with self.subTest(role=role), self.assertRaises(ValueError):
                writer.validate_documents(parent, capture)


if __name__ == '__main__':
    unittest.main()
