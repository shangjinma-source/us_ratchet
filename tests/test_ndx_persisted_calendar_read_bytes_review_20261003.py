"""The consumed bytes must be the same bytes authenticated by the reader."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_persisted_candidate_calendar_independent_readback_20261003 as subject


class ConsumedBytesReview(unittest.TestCase):
    def test_load_returns_only_the_authenticated_read(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'source.json'
            expected = b'{"value":1}'
            target.write_bytes(expected)
            original = Path.read_bytes
            calls = []

            def changing_read(path):
                if path == target:
                    calls.append(path)
                    return expected if len(calls) == 1 else b'{"value":2}'
                return original(path)

            with patch.object(Path, 'read_bytes', changing_read):
                actual = subject.load(subject.reference(str(target), subject.sha(expected)), {})
            self.assertEqual(actual, expected)
            self.assertEqual(len(calls), 1)

    def test_bad_consumed_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'source.json'
            target.write_bytes(b'{"value":2}')
            with self.assertRaises(ValueError):
                subject.load(subject.reference(str(target), subject.sha(b'{"value":1}')), {})


if __name__ == '__main__':
    unittest.main()
