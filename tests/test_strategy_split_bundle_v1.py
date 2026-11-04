from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.strategy_split_bundle_v1 import prepare_split_bundle, verify_split_bundle
import test_strategy_split_risk_preparation_v1 as risk_fixture


class SplitBundleTests(unittest.TestCase):
    def setUp(self):
        fixture = risk_fixture.SplitRiskPreparationTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        root = Path(fixture.directory.name)
        self.clock = lambda: datetime.fromisoformat('2026-10-29T15:00:00+00:00')
        self.source = StrategyAccountStore(root/'source.sqlite3', clock=self.clock)
        state = self.source.initialize('synthetic-account', operation_id='init')
        state, _ = self.source.append(dict(event_id='buy', kind='DIRECT_FILL', security_id='A', side='BUY',
            quantity=14, price='100', fees='0', executed_at='2026-10-20T15:00:00Z'), expected_revision=state['revision'])
        self.directory = root/'bundle'
        self.arguments = {key:value for key,value in fixture.arguments.items() if key not in ('destination_path','account_after','action_id')}
        self.arguments.update(source_account_path=self.source.path, destination_directory=self.directory,
            expected_revision=state['revision'], action=fixture.arguments['account_after']['events'][-1]['payload'], clock=self.clock)

    def test_one_manifest_binds_both_databases_and_preserves_source(self):
        before = self.source.path.read_bytes()
        result = prepare_split_bundle(**self.arguments)
        self.assertEqual(verify_split_bundle(self.directory), result)
        self.assertEqual(SplitStrategyAccountStore(self.directory/'account.sqlite3').read()['shares']['A'], 112)
        self.assertEqual(self.source.path.read_bytes(), before)
        self.assertFalse(result['production_activated'])
        with (self.directory/'inputs.json').open('ab') as stream: stream.write(b' ')
        with self.assertRaisesRegex(ValueError, 'FILE_CHANGED'): verify_split_bundle(self.directory)

    def test_risk_failure_does_not_publish_half_bundle(self):
        before = self.source.read()
        with patch('data.strategy_split_bundle_v1.prepare_split_risk', side_effect=ValueError('injected')):
            with self.assertRaisesRegex(ValueError, 'injected'): prepare_split_bundle(**self.arguments)
        self.assertFalse((self.directory/'complete.json').exists())
        self.assertTrue((self.directory/'failed.json').exists())
        with self.assertRaisesRegex(ValueError, 'BUNDLE_FAILED'): verify_split_bundle(self.directory)
        self.assertEqual(self.source.read(), before)
