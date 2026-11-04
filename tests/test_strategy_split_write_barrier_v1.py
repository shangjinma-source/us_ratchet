from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from data.strategy_split_write_barrier_v1 import freeze_split_sources

class SplitBarrierTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.paths={name:Path(self.directory.name)/(name+'.sqlite3') for name in ('account','target','risk')}
        for path in self.paths.values():
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('CREATE TABLE marker(value INTEGER)')
                connection.execute('INSERT INTO marker VALUES(1)');connection.commit()
    def assert_write_available(self,path):
        with closing(sqlite3.connect(path,timeout=0)) as connection:
            connection.execute('BEGIN IMMEDIATE');connection.rollback()
    def test_all_writers_blocked_readers_available_and_no_data_changes(self):
        before={name:path.read_bytes() for name,path in self.paths.items()}
        with freeze_split_sources(paths=self.paths):
            for path in self.paths.values():
                with self.assertRaises(sqlite3.OperationalError):self.assert_write_available(path)
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(connection.execute('SELECT value FROM marker').fetchone(),(1,))
        self.assertEqual(before,{name:path.read_bytes() for name,path in self.paths.items()})
        for path in self.paths.values():self.assert_write_available(path)
    def test_exception_releases_every_lock(self):
        with self.assertRaisesRegex(ValueError,'injected'):
            with freeze_split_sources(paths=self.paths):raise ValueError('injected')
        for path in self.paths.values():self.assert_write_available(path)
    def test_partial_acquisition_failure_releases_earlier_locks(self):
        with closing(sqlite3.connect(self.paths['target'])) as occupied:
            occupied.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):
                with freeze_split_sources(paths=self.paths,timeout=0):self.fail('Must not enter')
            self.assert_write_available(self.paths['account'])
            self.assert_write_available(self.paths['risk'])
            occupied.rollback()
    def test_missing_file_not_created_and_alias_rejected(self):
        missing=Path(self.directory.name)/'missing.sqlite3'
        with self.assertRaisesRegex(ValueError,'EXISTING_FILES'):
            with freeze_split_sources(paths=dict(self.paths,risk=missing)):self.fail()
        self.assertFalse(missing.exists())
        with self.assertRaisesRegex(ValueError,'DATABASE_ALIAS'):
            with freeze_split_sources(paths=dict(self.paths,risk=self.paths['account'])):self.fail()

if __name__=='__main__':unittest.main()
