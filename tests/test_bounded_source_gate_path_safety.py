"""Source gate must inspect each path component and recheck actual bytes."""
from hashlib import sha256
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import data.strategy_bounded_source_gate_v1 as gate


class PathSafetyTests(unittest.TestCase):
    def test_windows_directory_reparse_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'source.py'
            path.write_bytes(b'fixture')
            original = Path.lstat
            def metadata(item):
                if item == path.parent:
                    return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
                return original(item)
            with patch.object(Path, 'lstat', metadata):
                with self.assertRaisesRegex(ValueError, 'BOUNDED_SOURCE_LINK_REFUSED'):
                    gate._no_links(path)

    def test_missing_file_never_returns_digest(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'BOUNDED_SOURCE_MISSING'):
                gate._read_digest(Path(directory) / 'missing', 100)

    def test_same_size_same_timestamp_edit_is_rehashed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'source'
            path.write_bytes(b'original')
            before = path.stat()
            self.assertEqual(gate._read_digest(path, 100), sha256(b'original').hexdigest())
            path.write_bytes(b'modified')
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertEqual(gate._read_digest(path, 100), sha256(b'modified').hexdigest())

    def test_link_replacement_after_stream_read_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'source'
            path.write_bytes(b'original')
            original_lstat, original_fstat = Path.lstat, os.fstat
            completed = False
            count = 0
            def stream_stat(fd):
                nonlocal completed, count
                count += 1
                value = original_fstat(fd)
                if count == 2:
                    completed = True
                return value
            def metadata(item):
                if item == path and completed:
                    return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
                return original_lstat(item)
            with patch.object(gate.os, 'fstat', stream_stat), patch.object(Path, 'lstat', metadata):
                with self.assertRaisesRegex(ValueError, 'BOUNDED_SOURCE_LINK_REFUSED'):
                    gate._read_digest(path, 100)


if __name__ == '__main__':
    unittest.main()
