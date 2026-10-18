"""Opaque ancestor verification must stay bounded and retain exact hashes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_cash_neighbor_combined_independent_readback_v2_20261008 as subject


class BoundedOpaqueAncestors(unittest.TestCase):
    def test_opaque_verification_never_materializes_or_parses(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'ancestor.json'
            path.write_bytes(b'x' * (2 * 1024**2 + 19))
            reference = subject.ref(path, subject.file_sha(path))
            opened = Path.open
            requested = []

            class CheckedStream:
                def __init__(self, raw):
                    self.raw = raw

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.raw.close()

                def read(self, length=-1):
                    requested.append(length)
                    self_outer.assertEqual(length, 1024**2)
                    return self.raw.read(length)

            self_outer = self
            sources = {}
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('No materialization')), \
                    patch.object(subject, 'load_bytes', side_effect=AssertionError('Opaque source is not parsed')), \
                    patch.object(Path, 'open', lambda p, *a, **kw: CheckedStream(opened(p, *a, **kw))):
                subject.authenticate_reference(reference, sources)
            self.assertEqual(sources, {str(path): reference['sha256']})
            self.assertEqual(len(requested), 4)

    def test_opaque_drift_and_parsed_limits_still_reject(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'source'
            path.write_bytes(b'original')
            reference = subject.ref(path, subject.file_sha(path))
            with self.assertRaisesRegex(ValueError, 'registered resource bound'):
                subject.load_bytes(reference, maximum_bytes=2, available=10 * 1024**3)
            with self.assertRaisesRegex(ValueError, 'Source closure conflict'):
                subject.authenticate_reference(reference, {str(path): '0' * 64})
            path.write_bytes(b'changed!')
            with self.assertRaisesRegex(ValueError, 'Opaque ancestor source bytes'):
                subject.authenticate_reference(reference, {})


if __name__ == '__main__':
    unittest.main()
