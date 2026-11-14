import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from api.strategy_account import StrategyAccountService
from scripts.backup_strategy_account import backup_account


class BackupTests(unittest.TestCase):
    def test_side_journals_preserved_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service=StrategyAccountService(database_path=root/'account.db',account_id='test',resolver=None)
            service.initialize({'event_id':'init'})
            paths=[]
            for suffix in ('.internal-transfers.sqlite3','.broker-cash.sqlite3','.transfer-reconciliation.sqlite3'):
                path=root/('account.db'+suffix);paths.append(path)
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute('CREATE TABLE evidence (sequence INTEGER, payload TEXT)')
                    connection.execute('INSERT INTO evidence VALUES (?,?)',(1,suffix))
                    connection.commit()
            before={path:path.read_bytes() for path in paths}
            result=backup_account(service.store.path,root/'backup')
            self.assertEqual(len(result['files']),4)
            self.assertEqual(result['absent_broker_journals'],[])
            for path in paths:
                self.assertEqual(path.read_bytes(),before[path])
                with closing(sqlite3.connect(root/'backup'/path.name)) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM evidence').fetchone(),(1,))

    def test_explicit_classification_sidecar_is_copied_and_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service=StrategyAccountService(database_path=root/'account.db',account_id='test',resolver=None)
            service.initialize({'event_id':'init'})
            side=root/'cash-flow.sqlite'
            with closing(sqlite3.connect(side)) as connection:
                connection.execute('CREATE TABLE classifications (payload TEXT)')
                connection.execute('INSERT INTO classifications VALUES (?)',('confirmed fee',));connection.commit()
            result=backup_account(service.store.path,root/'backup',classification_path=side)
            self.assertTrue(result['flow_classification_included'])
            with closing(sqlite3.connect(root/'backup'/side.name)) as connection:
                self.assertEqual(connection.execute('SELECT payload FROM classifications').fetchone(),('confirmed fee',))
            with self.assertRaisesRegex(ValueError,'BACKUP_CLASSIFICATION_PATH_INVALID'):
                backup_account(service.store.path,root/'invalid',classification_path=root/'missing.sqlite')
            self.assertFalse((root/'invalid').exists())

    def test_lifecycle_preserved_and_invalid_hash_rejected(self):
        import json
        from data.roa_execution_lifecycle import digest
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service=StrategyAccountService(database_path=root/'account.db',account_id='test',resolver=None)
            service.initialize({'event_id':'init'})
            life=root/'roa'/'lifecycle.json';life.parent.mkdir()
            state=dict(account_id='test',version=3,pending=['held-risk-exit'])
            life.write_text(json.dumps(dict(state=state,sha256=digest(state))))
            original=life.read_bytes()
            result=backup_account(service.store.path,root/'backup',lifecycle_path=life)
            self.assertTrue(result['lifecycle_included'])
            self.assertEqual((root/'backup'/'lifecycle.json').read_bytes(),original)
            self.assertEqual(life.read_bytes(),original)
            life.write_text(json.dumps(dict(state=state,sha256='incorrect')))
            with self.assertRaisesRegex(ValueError,'BACKUP_LIFECYCLE_SCOPE_OR_HASH'):
                backup_account(service.store.path,root/'invalid',lifecycle_path=life)
            self.assertFalse((root/'invalid').exists())

    def test_lifecycle_change_prevents_success_manifest(self):
        import json
        from unittest.mock import patch
        from data.roa_execution_lifecycle import digest
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service=StrategyAccountService(database_path=root/'account.db',account_id='test',resolver=None)
            service.initialize({'event_id':'init'})
            life=root/'lifecycle.json'
            state=dict(account_id='test',version=1)
            life.write_text(json.dumps(dict(state=state,sha256=digest(state))))
            original_read=StrategyAccountService.read
            def read_and_change(instance):
                result=original_read(instance)
                if instance.store.path.parent.name=='backup':
                    changed=dict(account_id='test',version=2)
                    life.write_text(json.dumps(dict(state=changed,sha256=digest(changed))))
                return result
            with patch.object(StrategyAccountService,'read',read_and_change):
                with self.assertRaisesRegex(ValueError,'BACKUP_LIFECYCLE_CHANGED_DURING_CAPTURE'):
                    backup_account(service.store.path,root/'backup',lifecycle_path=life)
            self.assertFalse((root/'backup'/'manifest.json').exists())

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
