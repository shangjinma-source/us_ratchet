import tempfile
import unittest
from pathlib import Path
from api.strategy_account import StrategyAccountService
from scripts.backup_strategy_account import backup_account


class BackupTests(unittest.TestCase):
    def test_absent_amendment_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = StrategyAccountService(database_path=root/'account.db', account_id='test', resolver=None)
            service.initialize({'event_id': 'init'})
            before = service.store.path.read_bytes()
            result = backup_account(service.store.path, root/'backup')
            self.assertEqual(len(result['files']), 1)
            self.assertEqual(service.store.path.read_bytes(), before)
            manifest = (root/'backup'/'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError):
                backup_account(service.store.path, root/'backup')
            self.assertEqual((root/'backup'/'manifest.json').read_bytes(), manifest)


if __name__ == '__main__':
    unittest.main()
