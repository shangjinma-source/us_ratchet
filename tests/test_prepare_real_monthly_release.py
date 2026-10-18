from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from scripts.prepare_real_monthly_release import prepare
from data.strategy_account_runtime_archive import require_archived_configuration
import test_strategy_account_monthly_release as fixtures


class PrepareReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.MonthlyReleaseTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.old_entry=dict(self.fixture.entry,target_month='2026-11')
        registry=dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=[self.old_entry])
        old_configuration=dict(self.fixture.resolve(),target_month='2026-11')
        self.old_archive_entry=dict(configuration_path='old-runtime.json',
            configuration_sha256=self.fixture.put('old-runtime.json',old_configuration))
        archive=dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[self.old_archive_entry])
        self.arguments=dict(root=self.root,registry_path='old-registry.json',
            registry_sha256=self.fixture.put('old-registry.json',registry),archive_path='old-archive.json',
            archive_sha256=self.fixture.put('old-archive.json',archive),new_entry=deepcopy(self.fixture.entry),
            output_directory='candidate',clock=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00'))

    def test_preserves_old_entries_and_builds_resolvable_archive(self):
        old=(self.root/'old-registry.json').read_bytes()
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            receipt=prepare(**self.arguments)
        self.assertEqual(receipt['status'],'PREPARED_NOT_ACTIVATED')
        registry=json.loads((self.root/'candidate/registry.json').read_bytes())
        self.assertEqual(registry['entries'],[self.old_entry,self.fixture.entry])
        archive=json.loads((self.root/'candidate/archive.json').read_bytes())
        self.assertEqual(archive['entries'][0],self.old_archive_entry)
        self.assertEqual(len(archive['entries']),2)
        config=json.loads((self.root/'candidate/runtime.json').read_bytes())
        self.assertEqual(require_archived_configuration(root=self.root,archive_path='candidate/archive.json',
            archive_sha256=receipt['files']['archive.json'],configuration=config),config)
        self.assertEqual((self.root/'old-registry.json').read_bytes(),old)
        self.assertFalse((self.root/'data/strategy_account').exists())
        self.assertEqual(list(self.root.glob('prepare-monthly-*')),[])
        before={p.name:p.read_bytes() for p in (self.root/'candidate').iterdir()}
        with self.assertRaisesRegex(ValueError,'PREPARE_OUTPUT_CONFLICT'):prepare(**self.arguments)
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'candidate').iterdir()})

    def test_same_month_replacement_refused(self):
        registry=dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=[dict(self.fixture.entry,identity_sha256='0'*64)])
        self.arguments['registry_sha256']=self.fixture.put('old-registry.json',registry)
        with self.assertRaisesRegex(ValueError,'PREPARE_MONTH_CONFLICT'):prepare(**self.arguments)
        self.assertFalse((self.root/'candidate').exists())

    def test_bad_hash_and_unsafe_output(self):
        with self.assertRaisesRegex(ValueError,'PREPARE_SOURCE_CHANGED'):
            prepare(**dict(self.arguments,archive_sha256='0'*64))
        with self.assertRaises(ValueError):
            prepare(**dict(self.arguments,output_directory='../escape'))
        self.assertFalse((self.root/'candidate').exists())

    def test_future_publication_and_naive_clock_leave_no_output(self):
        with self.assertRaises(ValueError):
            prepare(**dict(self.arguments,clock=lambda:datetime.fromisoformat('2026-12-01T13:00:00+00:00')))
        with self.assertRaisesRegex(ValueError,'AWARE_SERVER_CLOCK_REQUIRED'):
            prepare(**dict(self.arguments,clock=lambda:datetime(2026,12,1)))
        self.assertFalse((self.root/'candidate').exists())
        self.assertEqual(list(self.root.glob('prepare-monthly-*')),[])

    def test_missing_account_identity_fails_without_output(self):
        from core.strategy_account_ledger import replay
        state=replay('isolated',[self.fixture.holding_event()])
        with self.assertRaisesRegex(ValueError,'IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE'):
            prepare(**dict(self.arguments,account_state=state))
        self.assertFalse((self.root/'candidate').exists())


if __name__=='__main__':unittest.main()
