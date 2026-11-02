from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.strategy_sized_read_v1 import read_sized_source


class RecordingReader:
    def __init__(self, source, mutate=None):
        self.source = source
        self.mutate = mutate
        self.requested = []

    def fileno(self): return self.source.fileno()
    def tell(self): return self.source.tell()

    def read(self, amount):
        self.requested.append(amount)
        if self.mutate:
            self.mutate()
        return self.source.read(amount)


class SizedReadTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'source.bin'
        self.path.write_bytes(b'original')

    def test_small_source_does_not_request_maximum_buffer(self):
        with self.path.open('rb') as source:
            reader = RecordingReader(source)
            self.assertEqual(read_sized_source(reader, 32*1024*1024), b'original')
            self.assertEqual(reader.requested, [9])

    def test_oversized_source_is_rejected_before_read(self):
        with self.path.open('rb') as source:
            reader = RecordingReader(source)
            with self.assertRaisesRegex(ValueError, 'SOURCE_SIZE_LIMIT_EXCEEDED'):
                read_sized_source(reader, 7)
            self.assertEqual(reader.requested, [])

    def test_growth_during_read_is_rejected(self):
        def append():
            with self.path.open('ab') as writer:
                writer.write(b'added')
        with self.path.open('rb') as source:
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED_DURING_READ'):
                read_sized_source(RecordingReader(source, append), 100)

    def test_shrink_during_read_is_rejected(self):
        with self.path.open('rb') as source:
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED_DURING_READ'):
                read_sized_source(RecordingReader(source, lambda: self.path.write_bytes(b'x')), 100)

    def test_nonzero_offset_is_rejected(self):
        with self.path.open('rb') as source:
            source.read(1)
            with self.assertRaisesRegex(ValueError, 'SOURCE_REGULAR_FILE_AT_START_REQUIRED'):
                read_sized_source(source, 100)

    def test_empty_file_and_exact_limit(self):
        with self.path.open('rb') as source:
            self.assertEqual(read_sized_source(source, 8), b'original')
        self.path.write_bytes(b'')
        with self.path.open('rb') as source:
            self.assertEqual(read_sized_source(source, 0), b'')


if __name__ == '__main__': unittest.main()
