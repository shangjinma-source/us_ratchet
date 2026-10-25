from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.strategy_upgrade_blob_store_v1 import save_sources, load_sources, validate_files


class BlobStoreTests(unittest.TestCase):
    def test_55_mib_unique_roundtrip_no_base64(self):
        with tempfile.TemporaryDirectory() as folder:
            files = {f'training/{n}': bytes([n])*1024*1024 for n in range(55)}
            hashes = {name: sha256(raw).hexdigest() for name, raw in files.items()}
            path = Path(folder)/'sources'
            reference = save_sources(path, files, hashes)
            self.assertEqual(load_sources(path, reference), files)
            self.assertLess((path/'manifest.json').stat().st_size, 16000)
            self.assertEqual(len(list((path/'blobs').iterdir())), 55)
            blob = next((path/'blobs').iterdir())
            blob.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'BLOB_CHANGED'):
                load_sources(path, reference)

    def test_all_budgets_before_directory_or_claim(self):
        cases = (
            ({str(i): b'' for i in range(2001)}, 'DOMAIN'),
            ({'large': b'x'*(32*1024*1024+1)}, 'FILE_BUDGET'),
            ({str(i): b'x'*(32*1024*1024) for i in range(5)}, 'TOTAL_BUDGET'))
        with tempfile.TemporaryDirectory() as folder:
            for index, (files, reason) in enumerate(cases):
                path = Path(folder)/str(index)
                hashes = {name: sha256(raw).hexdigest() for name, raw in files.items()}
                with self.assertRaisesRegex(ValueError, reason):
                    save_sources(path, files, hashes)
                self.assertFalse(path.exists())

    def test_failed_durability_and_manifest_change_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sources'
            files = {'source': b'original'}
            hashes = {'source': sha256(b'original').hexdigest()}
            with patch('data.strategy_upgrade_blob_store_v1.os.fsync', side_effect=OSError('fixture')):
                with self.assertRaises(OSError):
                    save_sources(path, files, hashes)
            self.assertTrue(path.exists())
            self.assertFalse((path/'manifest.json').exists())
            with self.assertRaises(FileExistsError):
                save_sources(path, files, hashes)
            other = Path(folder)/'other'
            reference = save_sources(other, files, hashes)
            (other/'manifest.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'MANIFEST_CHANGED'):
                load_sources(other, reference)
