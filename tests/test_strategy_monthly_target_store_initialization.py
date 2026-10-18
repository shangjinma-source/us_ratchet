from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore


class TargetInitializationTests(unittest.TestCase):
    def test_interrupted_publication_leaves_no_authoritative_empty_database(self):
        with TemporaryDirectory() as directory:
            store=StrategyMonthlyTargetStore(Path(directory)/'target.sqlite3')
            with patch('core.strategy_monthly_target_store.os.link',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):store._initialize()
            self.assertFalse(store.path.exists())
            self.assertIsNone(store.current())
            self.assertEqual(list(Path(directory).iterdir()),[])
            store._initialize()
            self.assertIsNone(store.current())

    def test_concurrent_initialization_and_foreign_empty_database(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'target.sqlite3'
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _:StrategyMonthlyTargetStore(path)._initialize(),range(8)))
            self.assertIsNone(StrategyMonthlyTargetStore(path).current())
            self.assertEqual(len(list(Path(directory).iterdir())),1)
            other=Path(directory)/'foreign.sqlite3'
            sqlite3.connect(other).close()
            before=other.read_bytes()
            with self.assertRaisesRegex(ValueError,'TARGET_DATABASE_SCHEMA_INVALID'):
                StrategyMonthlyTargetStore(other).current()
            self.assertEqual(other.read_bytes(),before)


if __name__=='__main__':unittest.main()
