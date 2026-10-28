"""Real temporary SQLite activation preparation; no production files."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from hashlib import sha256
import unittest
from contextlib import closing

from core.strategy_account_store import StrategyAccountStore
from scripts.prepare_reentry_activation_v1 import prepare, digest


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.account = StrategyAccountStore(self.root / 'account.sqlite3')
        self.state = self.account.initialize('test-account', operation_id='initial')
        self.risk_path = self.root / 'risk.sqlite3'
        self.risk = dict(account_id='test-account', session_date='2026-10-28', marker='preserved')
        with closing(sqlite3.connect(self.risk_path)) as connection:
            connection.execute('CREATE TABLE risk_state(account_id TEXT PRIMARY KEY,state TEXT NOT NULL)')
            connection.execute('INSERT INTO risk_state VALUES (?,?)', ('test-account', json.dumps(self.risk)))
            connection.commit()
        self.config = self.root / 'base.json'
        self.config.write_bytes(b'{"schema":"fixture"}')
        self.args = dict(output_directory=self.root / 'new-package', risk_path=self.risk_path,
                         account_store=self.account, configuration_path=self.config,
                         expected_account_revision=self.state['revision'],
                         expected_risk_sha256=digest(self.risk),
                         expected_configuration_sha256=sha256(self.config.read_bytes()).hexdigest(),
                         clock=lambda: datetime(2026, 10, 29, 1, tzinfo=timezone.utc))

    def test_real_backup_activates_only_isolated_database(self):
        before = {path:path.read_bytes() for path in (self.risk_path, self.account.path, self.config)}
        result = prepare(**self.args)
        self.assertEqual(result['status'], 'PREPARED_NOT_PRODUCTION_ACTIVATED')
        self.assertEqual(result['reference']['locks'], {})
        self.assertEqual(result['binding']['activation_at'], '2026-10-29T01:00:00+00:00')
        self.assertEqual(result['binding']['activation_session'], '2026-10-28')
        self.assertFalse(result['production_activated'])
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        with closing(sqlite3.connect(self.risk_path)) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='reentry_state'").fetchone())

    def test_existing_directory_rejected_without_touch(self):
        self.args['output_directory'].mkdir()
        marker=self.args['output_directory']/'keep';marker.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_EXISTS'):
            prepare(**self.args)
        self.assertEqual(marker.read_text(), 'keep')

    def test_initial_source_binding_changes_reject(self):
        for key in ('expected_account_revision','expected_risk_sha256','expected_configuration_sha256'):
            arguments=dict(self.args);arguments[key]='0'*64
            with self.subTest(key=key), self.assertRaises(ValueError):prepare(**arguments)
            self.assertFalse(self.args['output_directory'].exists())

    def test_late_source_change_is_not_successful_package(self):
        def clock():
            self.config.write_bytes(b'{"changed":true}')
            return datetime(2026,10,29,1,tzinfo=timezone.utc)
        self.args['clock']=clock
        with self.assertRaisesRegex(ValueError,'CONFIGURATION_CHANGED'):prepare(**self.args)
        self.assertFalse((self.args['output_directory']/'manifest.json').exists())
        self.assertTrue((self.args['output_directory']/'FAILED.json').exists())

    def test_naive_clock_rejected(self):
        self.args['clock']=lambda:datetime(2026,10,29)
        with self.assertRaisesRegex(ValueError,'AWARE_CLOCK'):prepare(**self.args)


if __name__ == '__main__':
    unittest.main()
