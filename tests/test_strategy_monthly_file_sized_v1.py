from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration as Original
from data.strategy_monthly_file_sized_v1 import MonthlyFileConfiguration as Sized


class MonthlySizedReaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root/'source.json'
        self.body = b'{"value":"same original bytes"}'
        self.path.write_bytes(self.body)
        self.digest = sha256(self.body).hexdigest()

    def readers(self):
        return [reader(root=self.root,path='unused.json',sha256_value='0'*64,clock=None)
                for reader in (Original, Sized)]

    def test_original_bytes_and_exact_size_boundary(self):
        for reader in self.readers():
            self.assertEqual(reader._read('source.json',self.digest,len(self.body)),self.body)

    def test_wrong_hash_rejected(self):
        for reader in self.readers():
            with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):
                reader._read('source.json','0'*64)

    def test_changed_file_rejected_without_cached_success(self):
        for reader in self.readers():
            self.path.write_bytes(self.body)
            reader._read('source.json',self.digest)
            self.path.write_bytes(b'X'*len(self.body))
            with self.assertRaises(ValueError):reader._read('source.json',self.digest)

    def test_unsafe_path_and_oversize_rejected(self):
        for reader in self.readers():
            with self.assertRaises(ValueError):reader._read('../source.json',self.digest)
            with self.assertRaises(ValueError):reader._read('source.json',self.digest,len(self.body)-1)


if __name__=='__main__':unittest.main()
