"""Independent publication-boundary checks; no real cohort is merged."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_corrected_base_overlay_research as publication


class PublicationReviewTests(unittest.TestCase):
    def test_actual_atomic_output_write_then_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'original_source.json';source.write_text('original source bytes')
            output=Path(directory)/'output.json'
            value=dict(source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()},
                promotion_allowed=False)
            real_publish=publication.publish

            def write_then_drift(path,payload):
                saved=real_publish(path,payload)
                self.assertTrue(output.is_file())
                self.assertEqual(json.loads(output.read_bytes()),payload)
                source.write_text('source changed while output was being published')
                return saved

            with patch.object(publication,'publish',side_effect=write_then_drift) as publish:
                with self.assertRaisesRegex(ValueError,'Source changed during overlay publication'):
                    publication.publish_verified(output,value)
                publish.assert_called_once()
            # The immutable file may remain as forensic evidence, but no
            # successful publication result was returned to the caller.
            self.assertTrue(output.exists())

    def test_all_four_direct_loaded_dependencies_are_bound_to_actual_bytes(self):
        expected={str(Path(publication.__file__).resolve()),str(Path(publication.merger.__file__).resolve()),
            str(Path(publication.merger.digest.__code__.co_filename).resolve()),
            str(Path(publication.publish.__code__.co_filename).resolve())}
        self.assertEqual(len(expected),4)
        self.assertEqual(set(publication.LOADED),expected)
        for path in expected:
            self.assertEqual(publication.LOADED[path],hashlib.sha256(Path(path).read_bytes()).hexdigest())

    def test_unchanged_source_publishes_exact_bytes_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';source.write_bytes(b'unchanged')
            output=Path(directory)/'output.json'
            value=dict(source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()})
            saved=publication.publish_verified(output,value)
            self.assertEqual(saved['sha256'],hashlib.sha256(output.read_bytes()).hexdigest())
            before=output.read_bytes()
            with self.assertRaises(ValueError):publication.publish_verified(output,dict(value,extra=True))
            self.assertEqual(output.read_bytes(),before)
